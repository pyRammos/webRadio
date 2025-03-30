import os
import shutil
import logging
from datetime import datetime
from flask import current_app
import requests
import base64

logger = logging.getLogger(__name__)

def save_to_additional_locations(recording):
    """
    Save a recording to additional configured locations.
    
    Args:
        recording: The Recording object
    """
    try:
        # Check if the recording file exists
        if not os.path.exists(recording.local_path):
            logger.error(f"Recording file not found: {recording.local_path}")
            return
        
        # Save to additional local path if configured
        if recording.additional_local_path:
            save_to_local_folder(recording)
        
        # Save to NextCloud if configured
        if recording.nextcloud_path:
            save_to_nextcloud(recording)
            
    except Exception as e:
        logger.error(f"Error saving to additional locations: {str(e)}")

def save_to_local_folder(recording):
    """
    Save a recording to an additional local folder.
    
    Args:
        recording: The Recording object
    """
    try:
        # Create the directory structure
        now = datetime.now()
        target_dir = os.path.join(
            recording.additional_local_path,
            recording.name,
            now.strftime('%Y'),
            now.strftime('%m-%b')
        )
        
        os.makedirs(target_dir, exist_ok=True)
        
        # Copy the file
        target_file = os.path.join(target_dir, os.path.basename(recording.local_path))
        shutil.copy2(recording.local_path, target_file)
        
        logger.info(f"Saved recording to additional local folder: {target_file}")
    except Exception as e:
        logger.error(f"Error saving to local folder: {str(e)}")

def save_to_nextcloud(recording):
    """
    Save a recording to NextCloud using direct WebDAV API.
    
    Args:
        recording: The Recording object
    """
    # Import app at function level to avoid circular imports
    from app import app
    
    with app.app_context():
        try:
            # Check if NextCloud is configured
            nextcloud_url = current_app.config.get('NEXTCLOUD_URL')
            nextcloud_username = current_app.config.get('NEXTCLOUD_USERNAME')
            nextcloud_password = current_app.config.get('NEXTCLOUD_PASSWORD')
            
            # Try to get from AppSettings if not in config
            if not all([nextcloud_url, nextcloud_username, nextcloud_password]):
                from models import AppSettings
                nextcloud_url = nextcloud_url or AppSettings.get('NEXTCLOUD_URL')
                nextcloud_username = nextcloud_username or AppSettings.get('NEXTCLOUD_USERNAME')
                nextcloud_password = nextcloud_password or AppSettings.get('NEXTCLOUD_PASSWORD')
            
            if not all([nextcloud_url, nextcloud_username, nextcloud_password]):
                logger.warning("NextCloud not fully configured, skipping upload")
                return
            
            # Create the directory structure
            now = datetime.now()
            remote_dir = os.path.join(
                recording.nextcloud_path,
                recording.name,
                now.strftime('%Y'),
                now.strftime('%m-%b')
            )
            
            # Ensure remote directory exists
            ensure_nextcloud_directory(nextcloud_url, nextcloud_username, nextcloud_password, remote_dir)
            
            # Upload the file
            remote_path = os.path.join(remote_dir, os.path.basename(recording.local_path))
            
            # Format WebDAV URL
            webdav_url = f"{nextcloud_url}/remote.php/dav/files/{nextcloud_username}/{remote_path}"
            
            # Basic auth credentials
            auth = (nextcloud_username, nextcloud_password)
            
            # Upload file
            with open(recording.local_path, 'rb') as f:
                response = requests.put(
                    webdav_url,
                    data=f,
                    auth=auth,
                    headers={'Content-Type': 'audio/mpeg'}
                )
                
                if response.status_code in (201, 204):
                    logger.info(f"Uploaded recording to NextCloud: {remote_path}")
                else:
                    logger.error(f"Failed to upload to NextCloud: {response.status_code} {response.text}")
                    
        except Exception as e:
            logger.error(f"Error uploading to NextCloud: {str(e)}")

def ensure_nextcloud_directory(nextcloud_url, username, password, path):
    """
    Ensure a directory exists on NextCloud, creating it if necessary.
    
    Args:
        nextcloud_url: Base URL of NextCloud instance
        username: NextCloud username
        password: NextCloud password
        path: Directory path to ensure exists
    """
    # Split the path into components
    components = path.strip('/').split('/')
    current_path = ''
    
    # Create each directory level if it doesn't exist
    for component in components:
        if not component:
            continue
            
        current_path = f"{current_path}/{component}" if current_path else component
        
        # Format WebDAV URL for MKCOL (create directory)
        webdav_url = f"{nextcloud_url}/remote.php/dav/files/{username}/{current_path}"
        
        # Basic auth credentials
        auth = (username, password)
        
        # Check if directory exists
        response = requests.request("PROPFIND", webdav_url, auth=auth)
        
        if response.status_code == 404:
            # Directory doesn't exist, create it
            mkcol_response = requests.request("MKCOL", webdav_url, auth=auth)
            
            if mkcol_response.status_code not in (201, 405):  # 405 means it already exists
                logger.error(f"Failed to create directory {current_path}: {mkcol_response.status_code}")
        elif response.status_code != 207:  # 207 means it exists
            logger.error(f"Error checking directory {current_path}: {response.status_code}")
