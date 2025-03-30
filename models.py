from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Default storage paths
    default_local_storage_path = db.Column(db.String(255))
    default_nextcloud_storage_path = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<User {self.username}>'

class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text)
    
    @classmethod
    def get(cls, key, default=None):
        """Get a setting value by key"""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @classmethod
    def set(cls, key, value):
        """Set a setting value"""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        
    def __repr__(self):
        return f'<AppSettings {self.key}>'

class RadioStation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    recordings = db.relationship('Recording', backref='station', lazy=True)
    recurring_recordings = db.relationship('RecurringRecording', backref='station', lazy=True)
    
    def __repr__(self):
        return f'<RadioStation {self.name}>'

class Recording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_station.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # Duration in minutes
    file_name = db.Column(db.String(255))
    local_path = db.Column(db.String(255))
    additional_local_path = db.Column(db.String(255))
    nextcloud_path = db.Column(db.String(255))
    status = db.Column(db.String(20), default='scheduled')  # scheduled, recording, completed, failed
    file_size = db.Column(db.Integer)  # Size in bytes
    format = db.Column(db.String(10), default='mp3')  # Audio format (mp3, ogg, aac, flac, etc.)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    process_id = db.Column(db.Integer)  # Process ID of the ffmpeg process
    send_notification = db.Column(db.Boolean, default=True)  # Whether to send Pushover notification
    
    def __repr__(self):
        return f'<Recording {self.name}>'

class RecurringRecording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_station.id'), nullable=False)
    schedule_type = db.Column(db.String(20), nullable=False)  # daily, weekly, weekends
    days_of_week = db.Column(db.String(20))  # Comma-separated list of days (0-6, where 0 is Monday)
    start_time = db.Column(db.Time, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # Duration in minutes
    keep_recordings = db.Column(db.Integer, default=10)  # Number of recordings to keep
    additional_local_path = db.Column(db.String(255))
    nextcloud_path = db.Column(db.String(255))
    create_podcast = db.Column(db.Boolean, default=False)
    format = db.Column(db.String(10), default='mp3')  # Audio format (mp3, ogg, aac, flac, etc.)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    send_notification = db.Column(db.Boolean, default=True)  # Whether to send Pushover notification
    
    recordings = db.relationship('Recording', secondary='recurring_recording_instance', backref='recurring')
    podcast = db.relationship('Podcast', backref='recurring_recording', lazy=True, uselist=False)
    
    def __repr__(self):
        return f'<RecurringRecording {self.name}>'

# Association table for recurring recordings and their instances
recurring_recording_instance = db.Table('recurring_recording_instance',
    db.Column('recurring_id', db.Integer, db.ForeignKey('recurring_recording.id'), primary_key=True),
    db.Column('recording_id', db.Integer, db.ForeignKey('recording.id'), primary_key=True)
)

class Podcast(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    language = db.Column(db.String(10), default='en')
    author = db.Column(db.String(100))
    image_path = db.Column(db.String(255))
    recurring_recording_id = db.Column(db.Integer, db.ForeignKey('recurring_recording.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    itunes_category = db.Column(db.String(100), default='Technology')
    itunes_explicit = db.Column(db.String(5), default='no')  # 'yes' or 'no'
    itunes_owner_email = db.Column(db.String(100))
    
    episodes = db.relationship('PodcastEpisode', backref='podcast', lazy=True)
    
    def __repr__(self):
        return f'<Podcast {self.title}>'

class PodcastEpisode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    podcast_id = db.Column(db.Integer, db.ForeignKey('podcast.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    duration = db.Column(db.Integer)  # Duration in seconds
    publication_date = db.Column(db.DateTime, default=datetime.utcnow)
    recording_id = db.Column(db.Integer, db.ForeignKey('recording.id'))
    
    recording = db.relationship('Recording')
    
    def __repr__(self):
        return f'<PodcastEpisode {self.title}>'
