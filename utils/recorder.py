import os
import subprocess
import logging
import time
import shutil
import psutil
from datetime import datetime, timedelta
import threading
import signal
from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Recording, RecurringRecording, Podcast, PodcastEpisode, db
from utils.notifications import send_notification
from utils.storage import save_to_additional_locations

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

def start_recording(recording_id, is_recurring=False):
    """Start a new recording."""
    logger.info(f"Starting recording {recording_id} (recurring: {is_recurring})")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        
        try:
            if is_recurring:
                recurring = session.query(RecurringRecording).get(recording_id)
                if not recurring:
                    logger.error(f"Recurring recording {recording_id} not found")
                    session.close()
                    return
                
                # Get the audio format from the recurring recording or default to mp3
                audio_format = recurring.format or 'mp3'
                
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
                    status='scheduled'
                )
                
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
        finally:
            # Always close the session when done
            session.close()

def monitor_recording(recording_id, process, output_file, is_recurring):
    """Monitor a recording process and handle completion."""
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        # Get a new session for this thread
        session = get_db_session()
        
        try:
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            recording = session.query(Recording).get(recording_id)
            
            if process.returncode == 0:
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
                        recurring = recording.recurring[0]  # Get the associated recurring recording
                        if recurring.create_podcast and recurring.podcast:
                            podcast = recurring.podcast
                            
                            # Get the filename without extension as the episode title
                            episode_filename = os.path.basename(output_file)
                            episode_name = os.path.splitext(episode_filename)[0]
                            
                            # Create a new podcast episode
                            episode = PodcastEpisode(
                                podcast_id=podcast.id,
                                title=episode_name,  # Use filename without extension as title
                                description=f"Episode recorded on {datetime.now().strftime('%Y-%m-%d')}",
                                file_path=output_file,
                                file_size=recording.file_size,
                                duration=recording.duration * 60,  # Convert minutes to seconds
                                recording_id=recording.id,
                                publication_date=recording.start_time  # Use recording start time instead of default
                            )
                            
                            session.add(episode)
                            
                        # Check if we need to delete old recordings
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
                logger.info(f"Recording {recording_id} process {recording.process_id} is still running, no need to resume")
                # Update our tracking dictionary
                end_time = recording.start_time + timedelta(minutes=recording.duration)
                
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
                    'end_time': end_time,
                    'output_file': recording.local_path,
                    'is_recurring': len(recording.recurring) > 0
                }
                session.close()
                return
            
            # Calculate remaining duration
            elapsed_time = datetime.now() - recording.start_time
            remaining_minutes = recording.duration - (elapsed_time.total_seconds() / 60)
            
            if remaining_minutes <= 0:
                logger.info(f"Recording {recording_id} has already completed its duration")
                recording.status = 'completed'
                recording.process_id = None
                session.commit()
                return
            
            # Update recording with new duration
            recording.duration = int(remaining_minutes)
            session.commit()
            
            # Check if this is a recurring recording
            is_recurring = False
            recurring_ids = [r.id for r in recording.recurring]
            if recurring_ids:
                is_recurring = True
                
            # Close the session before starting the recording
            session.close()
            
            # Start the recording with the remaining duration
            start_recording(recording_id, is_recurring)
        except Exception as e:
            logger.error(f"Error in resume_recording: {str(e)}")
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
            
            # Find recordings that are marked as 'recording' in the database
            active_db_recordings = session.query(Recording).filter_by(status='recording').all()
            
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
                        
                        # Calculate end time based on start time and duration
                        end_time = recording.start_time + timedelta(minutes=recording.duration)
                        
                        # Add to active_recordings dictionary
                        active_recordings[recording.id] = {
                            'process': DummyProcess(recording.process_id),
                            'start_time': recording.start_time,
                            'end_time': end_time,
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
