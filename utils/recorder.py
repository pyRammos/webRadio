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
