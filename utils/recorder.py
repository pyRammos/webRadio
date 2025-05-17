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
            # Store necessary data before closing the session
            recording_data = {}
            
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
            
            # Store all necessary data before closing the session
            recording_data = {
                'id': recording.id,
                'stream_url': recording.station.url,
                'audio_format': recording.format or 'mp3',
                'output_file': recording.local_path,
                'duration': recording.duration
            }
            
            # Get FFmpeg path from environment variable or app settings
            ffmpeg_path = os.environ.get('FFMPEG_PATH')
            
            # If not in environment, try to get from app settings
            if not ffmpeg_path:
                from models import AppSettings
                app_settings = session.query(AppSettings).first()
                if app_settings:
                    # Try to get ffmpeg_path attribute, but handle the case where it doesn't exist
                    ffmpeg_path = getattr(app_settings, 'ffmpeg_path', None)
            
            # Default to 'ffmpeg' if not found anywhere
            if not ffmpeg_path:
                ffmpeg_path = 'ffmpeg'
                
            logger.info(f"Using FFmpeg path: {ffmpeg_path}")
            
            # Close the session before starting the FFmpeg process
            session.close()
            
            # Calculate duration in seconds
            duration_seconds = recording_data['duration'] * 60
            
            # Set encoding parameters based on format
            encoding_params = []
            audio_format = recording_data['audio_format']
            if audio_format == 'mp3':
                encoding_params = ['-c:a', 'libmp3lame', '-q:a', '2']
            elif audio_format == 'ogg':
                encoding_params = ['-c:a', 'libvorbis', '-q:a', '4']
            elif audio_format == 'aac':
                encoding_params = ['-c:a', 'aac', '-b:a', '192k']
            elif audio_format == 'flac':
                encoding_params = ['-c:a', 'flac']
            elif audio_format == 'wav':
                encoding_params = ['-c:a', 'pcm_s16le']
            else:
                # Default to mp3
                encoding_params = ['-c:a', 'libmp3lame', '-q:a', '2']
            
            # Start FFmpeg process
            cmd = [
                ffmpeg_path,
                '-y',  # Overwrite output file if exists
                '-i', recording_data['stream_url'],
                '-t', str(duration_seconds)
            ] + encoding_params + [recording_data['output_file']]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            
            # Start the process - use binary mode to avoid encoding issues
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Don't use text mode/universal_newlines to avoid UTF-8 decoding issues
            )
            
            # Update recording with process ID - need a new session
            session = get_db_session()
            try:
                recording = session.query(Recording).get(recording_id)
                recording.process_id = process.pid
                session.commit()
            except Exception as e:
                logger.error(f"Error updating process ID: {str(e)}")
            finally:
                session.close()
            
            # Start a thread to monitor the recording
            monitor_thread = threading.Thread(
                target=monitor_recording,
                args=(recording_id, process, recording_data['output_file'], is_recurring)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Add to active recordings dictionary
            end_time = datetime.now() + timedelta(minutes=recording_data['duration'])
            active_recordings[recording_id] = {
                'process': process,
                'start_time': datetime.now(),
                'end_time': end_time,
                'output_file': recording_data['output_file'],
                'is_recurring': is_recurring
            }
            
            return recording_id
            
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            try:
                # Try to update the recording status to failed
                if 'recording' in locals() and recording:
                    recording.status = 'failed'
                    session.commit()
            except Exception as inner_e:
                logger.error(f"Error updating recording status: {str(inner_e)}")
            finally:
                # Close the session
                session.close()
            return None

def format_recording_name(name, audio_format='mp3'):
    """Format the recording name with date and extension."""
    now = datetime.now()
    date_str = now.strftime("%y%m%d")
    day_str = now.strftime("%a")
    
    # Replace spaces and special characters
    safe_name = name.replace(' ', '')
    safe_name = ''.join(c for c in safe_name if c.isalnum())
    
    return f"{safe_name}{date_str}-{day_str}.{audio_format}"

def monitor_recording(recording_id, process, output_file, is_recurring):
    """Monitor a recording process and handle completion."""
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        
        try:
            # Wait for process to complete - use binary mode to avoid encoding issues
            try:
                stdout_data, stderr_data = process.communicate()
                # Don't try to decode the output as it may contain non-UTF-8 characters
            except Exception as e:
                logger.error(f"Error communicating with FFmpeg process: {str(e)}")
                stdout_data = b""
                stderr_data = b""
            
            recording = session.query(Recording).get(recording_id)
            
            if process.returncode == 0:
                # FFmpeg completed successfully - mark as completed regardless of timing
                logger.info(f"Recording {recording_id} ({recording.name}) completed successfully with FFmpeg exit code 0")
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
                # FFmpeg process failed or was interrupted
                logger.warning(f"FFmpeg process exited with code {process.returncode} for recording {recording_id} ({recording.name})")
                
                # Check if this was a user-initiated stop (code 255 often indicates SIGTERM)
                if process.returncode == 255:
                    recording.status = 'stopped'
                    recording.process_id = None
                    logger.info(f"Recording {recording_id} was stopped manually")
                else:
                    # This is a genuine error or interruption - handle as partial recording
                    now = datetime.now()
                    planned_end_time = recording.start_time + timedelta(minutes=recording.duration)
                    
                    # Create a partial file
                    base_name, ext = os.path.splitext(output_file)
                    partial_file = f"{base_name}-part1{ext}"
                    
                    if os.path.exists(output_file):
                        try:
                            os.rename(output_file, partial_file)
                            logger.info(f"Created partial file: {partial_file}")
                        except Exception as e:
                            logger.error(f"Error renaming partial file: {str(e)}")
                    
                    # Mark for retry if there's still meaningful time left
                    remaining_seconds = (planned_end_time - now).total_seconds()
                    if remaining_seconds > 60:  # Only retry if more than 1 minute remains
                        recording.status = 'interrupted'  # Use a specific status for interruptions
                        logger.info(f"Recording {recording_id} ({recording.name}) marked for retry")
                        
                        # Schedule a retry after a short delay
                        from app import scheduler
                        scheduler.add_job(
                            retry_recording,
                            'date',
                            run_date=datetime.now() + timedelta(seconds=60),
                            args=[recording_id, 1],
                            id=f'retry_{recording_id}_1',
                            replace_existing=True
                        )
                    else:
                        # Not enough time left, mark as partial
                        recording.status = 'partial'
                        recording.process_id = None
                        logger.warning(f"No time remaining for recording {recording_id} ({recording.name}), marking as partial")
            
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
            
            # Close the session before starting the recording
            session.close()
            
            # Start the recording with the remaining duration
            is_recurring = len(recording.recurring) > 0
            start_recording(recording_id, is_recurring)
            
        except Exception as e:
            logger.error(f"Error in resume_recording: {str(e)}")
        finally:
            # Always close the session
            if 'session' in locals() and session:
                session.close()

def check_active_recordings():
    """Check for active recordings that need to be resumed."""
    logger.debug("Checking for active recordings that need to be resumed")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        try:
            # Find recordings that are marked as 'recording' in the database
            active_db_recordings = session.query(Recording).filter_by(status='recording').all()
            
            for recording in active_db_recordings:
                # Check if the recording is in our active_recordings dictionary
                if recording.id not in active_recordings:
                    # Check if there's a process ID and if that process is still running
                    if recording.process_id and is_process_running(recording.process_id):
                        # Process is still running, update our tracking
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
                        resume_recording(recording.id)
            
            # Removed code that starts scheduled recordings - this is now handled exclusively by the scheduler
            # to prevent duplicate recordings and session errors
            
        except Exception as e:
            logger.error(f"Error in check_active_recordings: {str(e)}")
        finally:
            # Always close the session
            session.close()

def retry_recording(recording_id, retry_count):
    """Retry a recording that was interrupted."""
    logger.info(f"Retrying recording {recording_id}, attempt #{retry_count}")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        session = get_db_session()
        try:
            recording = session.query(Recording).get(recording_id)
            
            if not recording:
                logger.error(f"Recording {recording_id} not found for retry")
                return
            
            # Check if there's still time remaining for the recording
            now = datetime.now()
            planned_end_time = recording.start_time + timedelta(minutes=recording.duration)
            remaining_seconds = (planned_end_time - now).total_seconds()
            
            # Use tolerance thresholds
            time_threshold_seconds = 30
            percentage_threshold = 0.95
            
            total_duration_seconds = recording.duration * 60
            elapsed_seconds = (now - recording.start_time).total_seconds()
            completion_percentage = elapsed_seconds / total_duration_seconds
            
            if remaining_seconds <= -time_threshold_seconds or completion_percentage >= percentage_threshold:
                # No meaningful time remaining or recording is mostly complete
                logger.warning(f"Recording {recording_id} ({recording.name}) is already {completion_percentage:.1%} complete, marking as complete instead of partial")
                recording.status = 'completed'
                
                # Rename the partial file to the final name without the partial suffix
                base_name, ext = os.path.splitext(recording.local_path)
                partial_file = f"{base_name}-part1{ext}"
                if os.path.exists(partial_file):
                    try:
                        os.rename(partial_file, recording.local_path)
                        logger.info(f"Renamed single partial file to {os.path.basename(recording.local_path)}")
                    except Exception as e:
                        logger.error(f"Error renaming partial file: {str(e)}")
                
                session.commit()
                return
            
            # Calculate remaining duration
            remaining_minutes = max(1, int(remaining_seconds / 60))
            
            # Update recording with new duration
            recording.duration = remaining_minutes
            recording.status = 'scheduled'  # Reset status to scheduled for the retry
            session.commit()
            
            # Close the session before starting the recording
            session.close()
            
            # Start the recording with the remaining duration
            is_recurring_recording = len(recording.recurring) > 0
            start_recording(recording_id, is_recurring_recording)
            
        except Exception as e:
            logger.error(f"Error in retry_recording: {str(e)}")
        finally:
            # Always close the session
            if 'session' in locals() and session:
                session.close()
