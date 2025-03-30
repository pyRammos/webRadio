import logging
import requests
from flask import current_app, url_for

logger = logging.getLogger(__name__)

def send_notification(message, recording_id=None):
    """
    Send a notification about a recording event.
    
    Args:
        message (str): The notification message
        recording_id (int, optional): The ID of the recording
    """
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        try:
            # Check if notifications should be sent for this recording
            if recording_id:
                from models import Recording, RecurringRecording
                from sqlalchemy.orm import sessionmaker
                from sqlalchemy import create_engine
                from config import Config
                
                # Create a new session
                engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
                Session = sessionmaker(bind=engine)
                session = Session()
                
                # Try to find the recording
                recording = session.query(Recording).get(recording_id)
                
                if recording and not recording.send_notification:
                    logger.info(f"Notifications disabled for recording {recording_id}, skipping")
                    session.close()
                    return
                
                session.close()
            
            # Send Pushover notification if configured
            send_pushover_notification(message)
            
            logger.info(f"Notification sent: {message}")
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")

def send_pushover_notification(message):
    """
    Send a notification via Pushover.
    
    Args:
        message (str): The notification message
    """
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        user_key = current_app.config.get('PUSHOVER_USER_KEY')
        api_token = current_app.config.get('PUSHOVER_API_TOKEN')
        
        # Try to get from AppSettings if not in config
        if not user_key or not api_token:
            from models import AppSettings
            user_key = user_key or AppSettings.get('PUSHOVER_USER_KEY')
            api_token = api_token or AppSettings.get('PUSHOVER_API_TOKEN')
        
        if not user_key or not api_token:
            logger.debug("Pushover not configured, skipping notification")
            return
        
        try:
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": api_token,
                    "user": user_key,
                    "message": message,
                    "title": "WebRadio Recorder"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Pushover API error: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Pushover notification: {str(e)}")
