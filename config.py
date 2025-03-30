import os
import secrets

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(16)
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///webradio.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File storage paths
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    RECORDINGS_DIR = os.environ.get('RECORDINGS_DIR') or os.path.join(BASE_DIR, 'recordings')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(BASE_DIR, 'static', 'images')
    
    # NextCloud configuration
    NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL')
    NEXTCLOUD_USERNAME = os.environ.get('NEXTCLOUD_USERNAME')
    NEXTCLOUD_PASSWORD = os.environ.get('NEXTCLOUD_PASSWORD')
    
    # Pushover notification configuration
    PUSHOVER_USER_KEY = os.environ.get('PUSHOVER_USER_KEY')
    PUSHOVER_API_TOKEN = os.environ.get('PUSHOVER_API_TOKEN')
    
    # FFmpeg configuration
    FFMPEG_PATH = os.environ.get('FFMPEG_PATH') or 'ffmpeg'
