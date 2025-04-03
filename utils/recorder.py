import os
import subprocess
import logging
import time
import shutil
import psutil
import json
from datetime import datetime, timedelta
import threading
import signal
from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Recording, RecurringRecording, Podcast, PodcastEpisode, db, AppSettings, recurring_recording_instance
from utils.notifications import send_notification
from utils.storage import save_to_additional_locations
from utils.audio import get_audio_duration, concatenate_audio_files

logger = logging.getLogger(__name__)

# Dictionary to keep track of active recording processes
active_recordings = {}

def is_process_running(pid):
    """Check if a process with the given PID is running."""
    try:
        # Check if process exists
        if pid is None:
            return False
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False

def get_db_session():
    """Create a new database session."""
    # Create a new session for background tasks to avoid thread issues
    from config import Config
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    Session = sessionmaker(bind=engine)
    return Session()

def create_podcast_episode(recording, output_file, session, is_recurring=False):
    """Create a podcast episode for a recording if it's part of a recurring recording with podcast enabled."""
    if not is_recurring or not recording.recurring:
        return
        
    recurring = recording.recurring[0]  # Get the associated recurring recording
    if recurring.create_podcast and recurring.podcast:
        podcast = recurring.podcast
        
        # Get the filename without extension as the episode title
        episode_filename = os.path.basename(output_file)
        episode_name = os.path.splitext(episode_filename)[0]
        
        # Add a note for partial recordings
        status_note = " (Partial recording)" if recording.status == 'partial' else ""
        
        # Create a new podcast episode
        episode = PodcastEpisode(
            podcast_id=podcast.id,
            title=episode_name,  # Use filename without extension as title
            description=f"Episode recorded on {datetime.now().strftime('%Y-%m-%d')}{status_note}",
            file_path=output_file,
            file_size=recording.file_size,
            duration=recording.duration * 60,  # Convert minutes to seconds
            recording_id=recording.id,
            publication_date=recording.start_time  # Use recording start time instead of default
        )
        
        # Use a new session for committing the podcast episode to avoid interfering with the recording session
        podcast_session = get_db_session()
        try:
            podcast_episode_copy = PodcastEpisode(
                podcast_id=episode.podcast_id,
                title=episode.title,
                description=episode.description,
                file_path=episode.file_path,
                file_size=episode.file_size,
                duration=episode.duration,
                recording_id=episode.recording_id,
                publication_date=episode.publication_date
            )
            podcast_session.add(podcast_episode_copy)
            podcast_session.commit()
            logger.info(f"Created podcast episode for {recording.status} recording {recording.id} ({recording.name})")
        finally:
            podcast_session.close()

def start_recording(recording_id, is_recurring=False):
    """Start a new recording."""
    logger.info(f"Starting recording {recording_id} (recurring: {is_recurring})")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        
        try:
            # Add a simple lock mechanism using the database
            if is_recurring:
                # Check if this recording is already being processed
                lock_key = f"recording_lock_{recording_id}"
                from models import AppSettings
                
                # Try to acquire lock
                lock = AppSettings.get(lock_key)
                if lock and float(lock) > time.time() - 60:  # Lock expires after 60 seconds
                    logger.info(f"Recording {recording_id} is already being processed by another worker. Skipping.")
                    session.close()
                    return
                
                # Set lock
                AppSettings.set(lock_key, str(time.time()))
                
                recurring = session.query(RecurringRecording).get(recording_id)
                if not recurring:
                    logger.error(f"Recurring recording {recording_id} not found")
                    # Release lock before returning
                    AppSettings.set(lock_key, "0")
                    session.close()
                    return
                
                # Get the audio format from the recurring recording or default to mp3
                audio_format = recurring.format or 'mp3'
                
                # Check if a recording for this recurring schedule already exists for today
                # within a reasonable time window (e.g., within the last hour)
                now = datetime.now()
                one_hour_ago = now - timedelta(hours=1)
                
                existing_recording = session.query(Recording).join(
                    recurring_recording_instance,
                    Recording.id == recurring_recording_instance.c.recording_id
                ).filter(
                    recurring_recording_instance.c.recurring_id == recurring.id,
                    Recording.start_time >= one_hour_ago,
                    Recording.start_time <= now
                ).first()
                
                if existing_recording:
                    logger.info(f"Found existing recording {existing_recording.id} for recurring recording {recurring.id} within the last hour. Skipping creation of duplicate.")
                    
                    # If the existing recording is not in 'recording' status, update it
                    if existing_recording.status != 'recording':
                        existing_recording.status = 'recording'
                        existing_recording.process_id = None  # Clear any old process ID
                        session.commit()
                        recording_id = existing_recording.id
                        # Assign the recording variable to existing_recording to avoid "referenced before assignment" error
                        recording = existing_recording
                    else:
                        # Recording is already in progress, nothing to do
                        # Release lock before returning
                        AppSettings.set(lock_key, "0")
                        session.close()
                        return
                else:
                    # Create a new recording instance for this recurring recording
                    station = recurring.station
                    formatted_name = format_recording_name(recurring.name, audio_format)
                    
                    recording = Recording(
                        name=recurring.name,
                        station_id=recurring.station_id,
                        start_time=datetime.now(),
                        duration=recurring.duration,
                        file_name=formatted_name,
                        local_path=os.path.join(current_app.config['RECORDINGS_DIR'], formatted_name),
                        additional_local_path=recurring.additional_local_path,
                        nextcloud_path=recurring.nextcloud_path,
                        format=audio_format,
                        status='scheduled',
                        send_notification=recurring.send_notification,
                        retry_count=0,
                        partial_files=json.dumps([])
                    )
                    
                    # Calculate finish time
                    recording.finish_time = recording.start_time + timedelta(minutes=recording.duration)
                    
                    session.add(recording)
                    session.commit()
                    
                    # Associate this recording with the recurring recording
                    recurring.recordings.append(recording)
                    session.commit()
                    
                    recording_id = recording.id
            else:
                recording = session.query(Recording).get(recording_id)
                if not recording:
                    logger.error(f"Recording {recording_id} not found")
                    session.close()
                    return
        
            # Update recording status
            recording.status = 'recording'
            session.commit()
            
            # Get the stream URL
            station = recording.station
            stream_url = station.url
            
            # Prepare output file path
            output_file = recording.local_path
            audio_format = recording.format or 'mp3'
            
            # Ensure the file has the correct extension
            if not output_file.lower().endswith(f'.{audio_format.lower()}'):
                output_file = f"{output_file.rstrip('.')}.{audio_format}"
                # Update the recording's local_path to include the correct extension
                recording.local_path = output_file
                session.commit()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Calculate duration in seconds
            duration_seconds = recording.duration * 60
            
            # Get FFmpeg path from config or AppSettings
            ffmpeg_path = current_app.config.get('FFMPEG_PATH')
            if not ffmpeg_path:
                from models import AppSettings
                ffmpeg_path = AppSettings.get('FFMPEG_PATH', 'ffmpeg')
            
            # Start FFmpeg process
            cmd = [
                ffmpeg_path,
                '-y',  # Overwrite output file if exists
                '-i', stream_url,
                '-t', str(duration_seconds)
            ]
            
            # Add format-specific encoding parameters
            if audio_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame', '-q:a', '2'])
            elif audio_format == 'ogg':
                cmd.extend(['-c:a', 'libvorbis', '-q:a', '4'])
            elif audio_format == 'aac':
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            elif audio_format == 'flac':
                cmd.extend(['-c:a', 'flac'])
            elif audio_format == 'wav':
                cmd.extend(['-c:a', 'pcm_s16le'])
            else:
                # Default to copy codec if format is unknown
                cmd.extend(['-c:a', 'copy'])
                
            # Add output file
            cmd.append(output_file)
            
            # Log the command with retry information if applicable
            if recording.retry_count > 0:
                logger.info(f"Retry #{recording.retry_count} for recording {recording_id} ({recording.name}) - Executing command: {' '.join(cmd)}")
            else:
                logger.info(f"Executing command: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Store the process ID in the database
            recording.process_id = process.pid
            session.commit()
            
            # Store process information
            active_recordings[recording_id] = {
                'process': process,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(minutes=recording.duration),
                'output_file': output_file,
                'is_recurring': is_recurring
            }
            
            # Start a monitoring thread
            monitor_thread = threading.Thread(
                target=monitor_recording,
                args=(recording_id, process, output_file, is_recurring)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            if 'recording' in locals() and recording:
                recording.status = 'failed'
                session.commit()
            
            # Make sure to release the lock if there was an error
            if is_recurring:
                try:
                    from models import AppSettings
                    lock_key = f"recording_lock_{recording_id}"
                    AppSettings.set(lock_key, "0")
                except Exception as lock_e:
                    logger.error(f"Error releasing lock: {str(lock_e)}")
        finally:
            # Always close the session when done
            session.close()
            
            # Release lock if this is a recurring recording
            if is_recurring:
                try:
                    from models import AppSettings
                    lock_key = f"recording_lock_{recording_id}"
                    AppSettings.set(lock_key, "0")
                except Exception as lock_e:
                    logger.error(f"Error releasing lock in finally block: {str(lock_e)}")

def monitor_recording(recording_id, process, output_file, is_recurring):
    """Monitor a recording process and handle completion."""
    # Import app at function level to avoid circular imports
    from app import app
    
    # Generate a unique ID for this monitoring thread
    monitor_id = f"{recording_id}_{time.time()}"
    logger.debug(f"Starting monitor thread {monitor_id} for recording {recording_id}")
    
    with app.app_context():
        # Get a new session for this thread
        session = get_db_session()
        
        try:
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            recording = session.query(Recording).get(recording_id)
            
            # Check if this monitor thread is still responsible for this recording
            # If the recording has a different process_id than what we started with, another thread is handling it
            if recording.process_id and recording.process_id != process.pid:
                logger.info(f"Monitor thread {monitor_id} is no longer responsible for recording {recording_id} (current PID: {recording.process_id}, our PID: {process.pid})")
                return
            
            if process.returncode == 0:
                # Check if the recording completed before the intended finish time
                now = datetime.now()
                
                # If finish_time is not set, calculate it
                if not recording.finish_time:
                    recording.finish_time = recording.start_time + timedelta(minutes=recording.duration)
                    session.commit()
                
                # Check if we're still before the intended finish time
                if now < recording.finish_time and recording.retry_count < 5:
                    # Recording completed prematurely but successfully
                    logger.warning(f"Recording {recording_id} ({recording.name}) disrupted - completed prematurely at {now}, should have finished at {recording.finish_time}")
                    
                    # Rename the current file to include part number
                    base_path = os.path.dirname(output_file)
                    filename = os.path.basename(output_file)
                    name, ext = os.path.splitext(filename)
                    part_num = recording.retry_count + 1
                    partial_file = os.path.join(base_path, f"{name}-part{part_num}{ext}")
                    
                    try:
                        # Rename the file
                        if os.path.exists(output_file):
                            os.rename(output_file, partial_file)
                            logger.info(f"Created partial file: {partial_file}")
                            
                            # Update partial_files list
                            partial_files = json.loads(recording.partial_files or '[]')
                            partial_files.append(partial_file)
                            recording.partial_files = json.dumps(partial_files)
                            
                            # Increment retry count
                            recording.retry_count += 1
                            
                            # Set status to retrying
                            recording.status = 'retrying'
                            session.commit()
                            logger.info(f"Recording {recording_id} ({recording.name}) marked for retry #{recording.retry_count}")
                            
                            # Wait 1 minute before retrying
                            logger.info(f"Waiting 60 seconds before retry attempt #{recording.retry_count}")
                            time.sleep(60)
                            
                            # Start a new recording for the remaining time
                            remaining_minutes = int((recording.finish_time - datetime.now()).total_seconds() / 60)
                            if remaining_minutes > 0:
                                # Update duration to remaining time
                                recording.duration = remaining_minutes
                                session.commit()
                                logger.info(f"Attempting retry #{recording.retry_count} for recording {recording_id} ({recording.name}) - {remaining_minutes} minutes remaining")
                                
                                # Get the recurring recording ID if this is a recurring recording
                                recurring_id = None
                                if is_recurring and recording.recurring:
                                    recurring_id = recording.recurring[0].id
                                    logger.info(f"Found recurring recording ID {recurring_id} for recording {recording_id}")
                                
                                # Clear the process_id before starting a new recording to avoid race conditions
                                recording.process_id = None
                                session.commit()
                                
                                # Close session before starting new recording
                                session.close()
                                
                                # Start a new recording with the correct recurring ID
                                if is_recurring and recurring_id:
                                    logger.info(f"Starting retry with recurring ID {recurring_id}")
                                    start_recording(recurring_id, is_recurring)
                                else:
                                    start_recording(recording_id, is_recurring)
                                return
                            else:
                                # No time left, mark as partial
                                recording.status = 'partial'
                                session.commit()
                                logger.warning(f"No time remaining for recording {recording_id} ({recording.name}), marking as partial")
                                
                                # Stitch partial files together if we have any
                                if recording.partial_files:
                                    try:
                                        partial_files = json.loads(recording.partial_files)
                                        
                                        # Concatenate all partial files
                                        if partial_files and len(partial_files) > 1:
                                            # Create a temporary output file with the correct extension
                                            temp_output = f"{os.path.splitext(output_file)[0]}.concat{os.path.splitext(output_file)[1]}"
                                            
                                            logger.info(f"Merging {len(partial_files)} partial files for recording {recording_id} ({recording.name})")
                                            for idx, part_file in enumerate(partial_files):
                                                logger.info(f"  Part {idx+1}: {os.path.basename(part_file)}")
                                            
                                            # Concatenate the files
                                            if concatenate_audio_files(partial_files, temp_output):
                                                # Replace the original file with the concatenated one
                                                if os.path.exists(temp_output):
                                                    if os.path.exists(output_file):
                                                        os.remove(output_file)
                                                    os.rename(temp_output, output_file)
                                                    logger.info(f"Successfully merged partial files into {os.path.basename(output_file)}")
                                                    
                                                    # Update file size for the recording
                                                    recording.file_size = os.path.getsize(output_file)
                                                    session.commit()
                                                    
                                                    # Save to additional locations if configured
                                                    save_to_additional_locations(recording)
                                                    
                                                    # Create podcast episode for partial recording
                                                    if is_recurring:
                                                        create_podcast_episode(recording, output_file, session, is_recurring)
                                                    
                                                    # Send notification for partial recording
                                                    if recording.send_notification:
                                                        # Calculate duration and file size
                                                        hours = recording.duration // 60
                                                        minutes = recording.duration % 60
                                                        file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                                                        
                                                        notification_message = (
                                                            f"Recorded {hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''} "
                                                            f"of {recording.name} (with interruptions). The file size is {file_size_mb:.2f} MB."
                                                        )
                                                        send_notification(notification_message, recording.id)
                                                    
                                                    # Clean up partial files
                                                    for partial_file in partial_files:
                                                        if partial_file != output_file and os.path.exists(partial_file):
                                                            try:
                                                                os.remove(partial_file)
                                                                logger.info(f"Removed partial file: {os.path.basename(partial_file)}")
                                                            except Exception as e:
                                                                logger.warning(f"Error removing partial file {partial_file}: {str(e)}")
                                            else:
                                                logger.error(f"Failed to merge partial files for recording {recording_id} ({recording.name})")
                                        elif partial_files and len(partial_files) == 1:
                                            # Only one partial file - rename it to the final output file
                                            partial_file = partial_files[0]
                                            if partial_file != output_file and os.path.exists(partial_file):
                                                if os.path.exists(output_file):
                                                    os.remove(output_file)
                                                os.rename(partial_file, output_file)
                                                logger.info(f"Renamed single partial file to {os.path.basename(output_file)}")
                                                
                                                # Update file size for the recording
                                                recording.file_size = os.path.getsize(output_file)
                                                session.commit()
                                                
                                                # Save to additional locations if configured
                                                save_to_additional_locations(recording)
                                                
                                                # Create podcast episode for partial recording
                                                if is_recurring:
                                                    create_podcast_episode(recording, output_file, session, is_recurring)
                                    except Exception as e:
                                        logger.error(f"Error handling partial recordings for {recording_id} ({recording.name}): {str(e)}")
                        else:
                            # File doesn't exist, mark as failed
                            recording.status = 'failed'
                            recording.process_id = None
                            session.commit()
                            logger.error(f"Output file not found for recording {recording_id} ({recording.name}), marking as failed")
                    except Exception as e:
                        logger.error(f"Error handling premature completion for recording {recording_id} ({recording.name}): {str(e)}")
                        recording.status = 'failed'
                        recording.process_id = None
                        session.commit()
                    
                    return
                
                # Recording completed normally or we've reached max retries
                if recording.retry_count > 0 and recording.partial_files:
                    # We have partial recordings to concatenate
                    try:
                        partial_files = json.loads(recording.partial_files)
                        
                        # Add the current file to the list if it exists
                        if os.path.exists(output_file):
                            partial_files.append(output_file)
                        
                        # Concatenate all partial files
                        if partial_files and len(partial_files) > 1:
                            # Create a temporary output file
                            temp_output = f"{output_file}.concat"
                            
                            logger.info(f"Merging {len(partial_files)} partial files for recording {recording_id} ({recording.name})")
                            for idx, part_file in enumerate(partial_files):
                                logger.info(f"  Part {idx+1}: {os.path.basename(part_file)}")
                            
                            # Concatenate the files
                            if concatenate_audio_files(partial_files, temp_output):
                                # Replace the original file with the concatenated one
                                if os.path.exists(temp_output):
                                    if os.path.exists(output_file):
                                        os.remove(output_file)
                                    os.rename(temp_output, output_file)
                                    logger.info(f"Successfully merged partial files into {os.path.basename(output_file)}")
                                    
                                    # Mark as partial since it was interrupted
                                    recording.status = 'partial'
                                    
                                    # Update file size
                                    recording.file_size = os.path.getsize(output_file)
                                    session.commit()
                                    
                                    # Save to additional locations if configured
                                    save_to_additional_locations(recording)
                                    
                                    # Create podcast episode for partial recording
                                    if is_recurring:
                                        create_podcast_episode(recording, output_file, session, is_recurring)
                                    
                                    # Send notification for partial recording
                                    if recording.send_notification:
                                        # Calculate duration and file size
                                        hours = recording.duration // 60
                                        minutes = recording.duration % 60
                                        file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                                        
                                        notification_message = (
                                            f"Recorded {hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''} "
                                            f"of {recording.name} (with interruptions). The file size is {file_size_mb:.2f} MB."
                                        )
                                        send_notification(notification_message, recording.id)
                                    
                                    # Clean up partial files
                                    for partial_file in partial_files:
                                        if partial_file != output_file and os.path.exists(partial_file):
                                            try:
                                                os.remove(partial_file)
                                                logger.info(f"Removed partial file: {os.path.basename(partial_file)}")
                                            except Exception as e:
                                                logger.warning(f"Error removing partial file {partial_file}: {str(e)}")
                            else:
                                logger.error(f"Failed to merge partial files for recording {recording_id} ({recording.name})")
                    except Exception as e:
                        logger.error(f"Error concatenating partial recordings for {recording_id} ({recording.name}): {str(e)}")
                    
                    # Return early since we've already handled everything for partial recordings
                    return
                
                # Recording completed successfully
                recording.status = 'completed'
                recording.process_id = None  # Clear the process ID

                # Get file size
                if os.path.exists(output_file):
                    recording.file_size = os.path.getsize(output_file)
                    
                    # Save to additional locations if configured
                    save_to_additional_locations(recording)
                    
                    # Create podcast episode if this is a recurring recording with podcast enabled
                    if is_recurring:
                        create_podcast_episode(recording, output_file, session, is_recurring)
                        
                        # Check if we need to delete old recordings
                        recurring = recording.recurring[0]
                        if recurring.keep_recordings > 0:
                            # Get all recordings for this recurring recording, ordered by date
                            all_recordings = sorted(
                                recurring.recordings, 
                                key=lambda r: r.start_time,
                                reverse=True
                            )
                            
                            # If we have more recordings than we should keep
                            if len(all_recordings) > recurring.keep_recordings:
                                # Delete the oldest recordings
                                for old_recording in all_recordings[recurring.keep_recordings:]:
                                    # Delete the file if it exists
                                    if old_recording.local_path and os.path.exists(old_recording.local_path):
                                        try:
                                            os.remove(old_recording.local_path)
                                        except Exception as e:
                                            logger.error(f"Error deleting old recording file: {str(e)}")
                                    
                                    # Remove from recurring recordings but don't delete the recording itself
                                    recurring.recordings.remove(old_recording)
                    
                    # Send notification
                    hours = recording.duration // 60
                    minutes = recording.duration % 60
                    file_size_mb = recording.file_size / (1024 * 1024)
                    
                    notification_message = (
                        f"Recorded {hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''} "
                        f"of {recording.name}. The file size is {file_size_mb:.2f} MB."
                    )
                    send_notification(notification_message, recording_id)
                else:
                    recording.status = 'failed'
                    recording.process_id = None  # Clear the process ID
                    logger.error(f"Output file not found: {output_file}")
            else:
                # Recording failed
                recording.status = 'failed'
                recording.process_id = None  # Clear the process ID
                logger.error(f"FFmpeg process failed with code {process.returncode}: {stderr.decode()}")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error in monitor_recording: {str(e)}")
            try:
                # Try to update the recording status to failed
                recording = session.query(Recording).get(recording_id)
                if recording:
                    recording.status = 'failed'
                    recording.process_id = None
                    session.commit()
            except Exception as inner_e:
                logger.error(f"Error updating recording status: {str(inner_e)}")
            
        finally:
            # Remove from active recordings
            if recording_id in active_recordings:
                del active_recordings[recording_id]
            
            # Always close the session
            session.close()

def resume_recording(recording_id):
    """Resume an interrupted recording."""
    logger.info(f"Resuming recording {recording_id}")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        try:
            recording = session.query(Recording).get(recording_id)
            
            if not recording:
                logger.error(f"Recording {recording_id} not found")
                return
            
            # Check if the process is still running by PID
            if recording.process_id and is_process_running(recording.process_id):
                logger.info(f"Recording {recording_id} ({recording.name}) process {recording.process_id} is still running, no need to resume")
                # Update our tracking dictionary
                
                # If finish_time is not set, calculate it
                if not recording.finish_time:
                    recording.finish_time = recording.start_time + timedelta(minutes=recording.duration)
                    session.commit()
                
                # Create a dummy process object
                class DummyProcess:
                    def __init__(self, pid):
                        self.pid = pid
                    
                    def poll(self):
                        return None if is_process_running(self.pid) else 1
                    
                    def terminate(self):
                        try:
                            os.kill(self.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    
                    def kill(self):
                        try:
                            os.kill(self.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                
                # Add to active_recordings dictionary
                active_recordings[recording_id] = {
                    'process': DummyProcess(recording.process_id),
                    'start_time': recording.start_time,
                    'end_time': recording.finish_time,
                    'output_file': recording.local_path,
                    'is_recurring': len(recording.recurring) > 0
                }
                session.close()
                return
            
            # Check if we've reached max retries
            if recording.retry_count >= 5:
                logger.warning(f"Recording {recording_id} ({recording.name}) has reached max retry count (5), marking as partial")
                recording.status = 'partial'
                recording.process_id = None
                session.commit()
                
                # Stitch partial files together if we have any
                if recording.partial_files:
                    try:
                        partial_files = json.loads(recording.partial_files)
                        
                        # Concatenate all partial files
                        if partial_files and len(partial_files) > 1:
                            # Create a temporary output file
                            temp_output = f"{os.path.splitext(recording.local_path)[0]}_temp{file_ext}"
                            
                            logger.info(f"Merging {len(partial_files)} partial files for recording {recording_id} ({recording.name})")
                            for idx, part_file in enumerate(partial_files):
                                logger.info(f"  Part {idx+1}: {os.path.basename(part_file)}")
                            
                            # Concatenate the files
                            if concatenate_audio_files(partial_files, temp_output):
                                # Replace the original file with the concatenated one
                                if os.path.exists(temp_output):
                                    if os.path.exists(recording.local_path):
                                        os.remove(recording.local_path)
                                    os.rename(temp_output, recording.local_path)
                                    logger.info(f"Successfully merged partial files into {os.path.basename(recording.local_path)}")
                                    
                                    # Clean up partial files
                                    for partial_file in partial_files:
                                        if partial_file != recording.local_path and os.path.exists(partial_file):
                                            try:
                                                os.remove(partial_file)
                                                logger.info(f"Removed partial file: {os.path.basename(partial_file)}")
                                            except Exception as e:
                                                logger.warning(f"Error removing partial file {partial_file}: {str(e)}")
                            else:
                                logger.error(f"Failed to merge partial files for recording {recording_id} ({recording.name})")
                    except Exception as e:
                        logger.error(f"Error concatenating partial recordings for {recording_id} ({recording.name}): {str(e)}")
                
                return
            
            # Check if we're past the finish time
            now = datetime.now()
            
            # If finish_time is not set, calculate it
            if not recording.finish_time:
                recording.finish_time = recording.start_time + timedelta(minutes=recording.duration)
                session.commit()
            
            if now >= recording.finish_time:
                logger.warning(f"Recording {recording_id} ({recording.name}) has passed its finish time {recording.finish_time}, marking as partial")
                recording.status = 'partial'
                recording.process_id = None
                session.commit()
                
                # Stitch partial files together if we have any
                if recording.partial_files:
                    try:
                        partial_files = json.loads(recording.partial_files)
                        
                        # Concatenate all partial files
                        if partial_files and len(partial_files) > 1:
                            # Create a temporary output file
                            temp_output = f"{os.path.splitext(recording.local_path)[0]}_temp{file_ext}"
                            
                            logger.info(f"Merging {len(partial_files)} partial files for recording {recording_id} ({recording.name})")
                            for idx, part_file in enumerate(partial_files):
                                logger.info(f"  Part {idx+1}: {os.path.basename(part_file)}")
                            
                            # Concatenate the files
                            if concatenate_audio_files(partial_files, temp_output):
                                # Replace the original file with the concatenated one
                                if os.path.exists(temp_output):
                                    if os.path.exists(recording.local_path):
                                        os.remove(recording.local_path)
                                    os.rename(temp_output, recording.local_path)
                                    logger.info(f"Successfully merged partial files into {os.path.basename(recording.local_path)}")
                                    
                                    # Clean up partial files
                                    for partial_file in partial_files:
                                        if partial_file != recording.local_path and os.path.exists(partial_file):
                                            try:
                                                os.remove(partial_file)
                                                logger.info(f"Removed partial file: {os.path.basename(partial_file)}")
                                            except Exception as e:
                                                logger.warning(f"Error removing partial file {partial_file}: {str(e)}")
                            else:
                                logger.error(f"Failed to merge partial files for recording {recording_id} ({recording.name})")
                    except Exception as e:
                        logger.error(f"Error concatenating partial recordings for {recording_id} ({recording.name}): {str(e)}")
                
                return
            
            # Calculate remaining duration based on finish_time
            remaining_minutes = int((recording.finish_time - now).total_seconds() / 60)
            
            if remaining_minutes <= 0:
                logger.warning(f"Recording {recording_id} ({recording.name}) has no remaining time, marking as partial")
                recording.status = 'partial'
                recording.process_id = None
                session.commit()
                
                # Stitch partial files together if we have any
                if recording.partial_files:
                    try:
                        partial_files = json.loads(recording.partial_files)
                        
                        # Concatenate all partial files
                        if partial_files and len(partial_files) > 1:
                            # Create a temporary output file
                            temp_output = f"{os.path.splitext(recording.local_path)[0]}_temp{file_ext}"
                            
                            logger.info(f"Merging {len(partial_files)} partial files for recording {recording_id} ({recording.name})")
                            for idx, part_file in enumerate(partial_files):
                                logger.info(f"  Part {idx+1}: {os.path.basename(part_file)}")
                            
                            # Concatenate the files
                            if concatenate_audio_files(partial_files, temp_output):
                                # Replace the original file with the concatenated one
                                if os.path.exists(temp_output):
                                    if os.path.exists(recording.local_path):
                                        os.remove(recording.local_path)
                                    os.rename(temp_output, recording.local_path)
                                    logger.info(f"Successfully merged partial files into {os.path.basename(recording.local_path)}")
                                    
                                    # Clean up partial files
                                    for partial_file in partial_files:
                                        if partial_file != recording.local_path and os.path.exists(partial_file):
                                            try:
                                                os.remove(partial_file)
                                                logger.info(f"Removed partial file: {os.path.basename(partial_file)}")
                                            except Exception as e:
                                                logger.warning(f"Error removing partial file {partial_file}: {str(e)}")
                            else:
                                logger.error(f"Failed to merge partial files for recording {recording_id} ({recording.name})")
                    except Exception as e:
                        logger.error(f"Error concatenating partial recordings for {recording_id} ({recording.name}): {str(e)}")
                
                return
                
            # Update recording with new duration
            recording.duration = remaining_minutes
            
            # Increment retry count
            recording.retry_count += 1
            
            # Update status to retrying
            recording.status = 'retrying'
            
            # If this is the first retry, initialize partial_files
            if not recording.partial_files:
                recording.partial_files = json.dumps([])
            
            # Clear the process_id before starting a new recording to avoid race conditions
            recording.process_id = None
            session.commit()
            logger.info(f"Preparing retry #{recording.retry_count} for recording {recording_id} ({recording.name}) - {remaining_minutes} minutes remaining")
            
            # Check if this is a recurring recording
            is_recurring = False
            recurring_id = None
            recurring_ids = [r.id for r in recording.recurring]
            if recurring_ids:
                is_recurring = True
                recurring_id = recurring_ids[0]  # Get the first recurring ID
                logger.info(f"Found recurring ID {recurring_id} for recording {recording_id}")
                
            # Close the session before starting the recording
            session.close()
            
            # Wait 1 minute before retrying
            logger.info(f"Waiting 60 seconds before retry attempt #{recording.retry_count} for recording {recording_id}")
            time.sleep(60)
            
            # Start the recording with the remaining duration
            logger.info(f"Starting retry #{recording.retry_count} for recording {recording_id}")
            if is_recurring and recurring_id:
                logger.info(f"Using recurring ID {recurring_id} for retry")
                start_recording(recurring_id, is_recurring)
            else:
                start_recording(recording_id, is_recurring)
        except Exception as e:
            logger.error(f"Error in resume_recording for {recording_id}: {str(e)}")
        finally:
            # Always close the session
            if 'session' in locals() and session:
                session.close()

def check_active_recordings():
    """Check for recordings that should be active but aren't in the active_recordings dict."""
    logger.debug("Checking for active recordings that need to be resumed")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        try:
            # Create a new session for this check
            session = get_db_session()
            
            # Find recordings that are marked as 'recording' or 'retrying' in the database
            active_db_recordings = session.query(Recording).filter(
                Recording.status.in_(['recording', 'retrying'])
            ).all()
            
            for recording in active_db_recordings:
                # Check if the recording is in our active_recordings dictionary
                if recording.id not in active_recordings:
                    # Check if there's a process ID and if that process is still running
                    if recording.process_id and is_process_running(recording.process_id):
                        # Process is still running, update our active_recordings dictionary
                        logger.info(f"Found active recording {recording.id} with running process {recording.process_id}, adding to tracking")
                        
                        # We need to create a dummy process object since we don't have the original
                        class DummyProcess:
                            def __init__(self, pid):
                                self.pid = pid
                            
                            def poll(self):
                                return None if is_process_running(self.pid) else 1
                            
                            def terminate(self):
                                try:
                                    os.kill(self.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                            
                            def kill(self):
                                try:
                                    os.kill(self.pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                        
                        # If finish_time is not set, calculate it
                        if not recording.finish_time:
                            recording.finish_time = recording.start_time + timedelta(minutes=recording.duration)
                            session.commit()
                        
                        # Add to active_recordings dictionary
                        active_recordings[recording.id] = {
                            'process': DummyProcess(recording.process_id),
                            'start_time': recording.start_time,
                            'end_time': recording.finish_time,
                            'output_file': recording.local_path,
                            'is_recurring': len(recording.recurring) > 0
                        }
                    else:
                        # Process is not running, resume the recording
                        logger.info(f"Found interrupted recording {recording.id}, resuming")
                        # Close this session before calling resume_recording which will create its own session
                        session.close()
                        resume_recording(recording.id)
                        # Get a fresh session after the resume operation
                        session = get_db_session()
            
            # Also check for scheduled recordings that should have started but haven't
            now = datetime.now()
            scheduled_recordings = session.query(Recording).filter_by(status='scheduled').all()
            
            for recording in scheduled_recordings:
                if recording.start_time <= now and recording.id not in active_recordings:
                    logger.info(f"Found missed scheduled recording {recording.id}, starting")
                    # Close this session before calling start_recording which will create its own session
                    session.close()
                    start_recording(recording.id)
                    # Get a fresh session after the start operation
                    session = get_db_session()
            
            # Check for completed or failed recordings that should be retried
            retry_candidates = session.query(Recording).filter(
                Recording.status.in_(['completed', 'failed']),
                Recording.retry_count < 5,
                Recording.finish_time > datetime.now()
            ).all()
            
            for recording in retry_candidates:
                logger.info(f"Found recording {recording.id} that completed/failed but should be retried (retry count: {recording.retry_count})")
                # Close this session before calling resume_recording which will create its own session
                session.close()
                resume_recording(recording.id)
                # Get a fresh session after the resume operation
                session = get_db_session()
        
        except Exception as e:
            logger.error(f"Error in check_active_recordings: {str(e)}")
        
        finally:
            # Always close the session when done
            if 'session' in locals():
                session.close()

def stop_recording(recording_id):
    """Stop an active recording."""
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        if recording_id in active_recordings:
            logger.info(f"Stopping recording {recording_id}")
            
            # Get process info
            process_info = active_recordings[recording_id]
            process = process_info['process']
            
            # Send SIGTERM to the process
            try:
                process.terminate()
                # Give it a moment to terminate gracefully
                time.sleep(1)
                
                # If still running, force kill
                if process.poll() is None:
                    process.kill()
            except Exception as e:
                logger.error(f"Error stopping recording process: {str(e)}")
            
            # Update recording status
            session = get_db_session()
            try:
                recording = session.query(Recording).get(recording_id)
                
                if recording:
                    recording.status = 'stopped'
                    recording.process_id = None  # Clear the process ID
                    session.commit()
                
                # Remove from active recordings
                del active_recordings[recording_id]
            except Exception as e:
                logger.error(f"Error updating recording status: {str(e)}")
            finally:
                session.close()
        else:
            # Check if there's a recording with this ID in the database that's marked as recording
            session = get_db_session()
            try:
                recording = session.query(Recording).filter_by(id=recording_id, status='recording').first()
                if recording and recording.process_id:
                    logger.info(f"Stopping recording {recording_id} by PID {recording.process_id}")
                    try:
                        # Try to kill the process
                        os.kill(recording.process_id, signal.SIGTERM)
                        time.sleep(1)
                        try:
                            os.kill(recording.process_id, signal.SIGKILL)
                        except ProcessLookupError:
                            pass  # Process already terminated
                        
                        # Update recording status
                        recording.status = 'stopped'
                        recording.process_id = None
                        session.commit()
                    except ProcessLookupError:
                        logger.warning(f"Process {recording.process_id} for recording {recording_id} not found")
                        recording.status = 'stopped'
                        recording.process_id = None
                        session.commit()
                    except Exception as e:
                        logger.error(f"Error stopping recording process by PID: {str(e)}")
                else:
                    logger.warning(f"Attempted to stop recording {recording_id} but it's not active")
            except Exception as e:
                logger.error(f"Error checking recording status: {str(e)}")
            finally:
                session.close()

def cleanup_recordings():
    """Clean up any active recordings when the application is shutting down."""
    logger.info(f"Cleaning up {len(active_recordings)} active recordings")
    
    for recording_id in list(active_recordings.keys()):
        stop_recording(recording_id)
        
    # Also check for any recordings in the database that are still marked as recording
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        try:
            active_db_recordings = session.query(Recording).filter_by(status='recording').all()
            for recording in active_db_recordings:
                if recording.process_id:
                    try:
                        logger.info(f"Cleaning up orphaned recording process {recording.process_id} for recording {recording.id}")
                        os.kill(recording.process_id, signal.SIGTERM)
                        time.sleep(0.5)
                        try:
                            os.kill(recording.process_id, signal.SIGKILL)
                        except ProcessLookupError:
                            pass  # Process already terminated
                    except ProcessLookupError:
                        pass  # Process doesn't exist
                    except Exception as e:
                        logger.error(f"Error killing process {recording.process_id}: {str(e)}")
                
                # Mark as stopped
                recording.status = 'stopped'
                recording.process_id = None
            
            session.commit()
        except Exception as e:
            logger.error(f"Error cleaning up recordings: {str(e)}")
        finally:
            session.close()
def format_recording_name(name, format='mp3'):
    """Format recording name with date and day of week."""
    now = datetime.now()
    formatted_date = now.strftime('%y%m%d-%a')
    file_name = f"{name}{formatted_date}"
    # Add the file extension based on the format
    if not file_name.endswith(f'.{format}'):
        file_name = f"{file_name}.{format}"
    return file_name
