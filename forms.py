from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, TextAreaField, SelectField, IntegerField, TimeField, DateTimeField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, URL, Optional, ValidationError
from datetime import datetime, time
import logging

# Configure logging
logger = logging.getLogger(__name__)

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class UserProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField('New Password', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('Confirm Password', validators=[EqualTo('password')])
    default_local_storage_path = StringField('Default Local Storage Path', validators=[Optional()])
    default_nextcloud_storage_path = StringField('Default NextCloud Storage Path', validators=[Optional()])
    submit = SubmitField('Update Profile')

class RadioStationForm(FlaskForm):
    name = StringField('Station Name', validators=[DataRequired(), Length(max=100)])
    url = StringField('Stream URL', validators=[DataRequired(), URL()])
    description = TextAreaField('Description')
    submit = SubmitField('Save Station')

class RecordingForm(FlaskForm):
    name = StringField('Recording Name', validators=[DataRequired(), Length(max=100)])
    station_id = SelectField('Radio Station', coerce=int, validators=[DataRequired()])
    start_time = DateTimeField('Start Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    duration = IntegerField('Duration (minutes)', validators=[DataRequired()])
    
    # Audio format
    format = SelectField('Audio Format', choices=[
        ('mp3', 'MP3'),
        ('ogg', 'OGG Vorbis'),
        ('aac', 'AAC'),
        ('flac', 'FLAC'),
        ('wav', 'WAV')
    ], default='mp3')
    
    # Additional storage options
    save_to_local = BooleanField('Save to Additional Local Folder')
    local_base_dir = StringField('Local Base Directory')
    
    save_to_nextcloud = BooleanField('Save to NextCloud')
    nextcloud_base_dir = StringField('NextCloud Base Directory')
    
    # Notification option
    send_notification = BooleanField('Send Pushover Notification', default=True)
    
    submit = SubmitField('Schedule Recording')
    
    def validate_start_time(self, field):
        logger.info(f"Validating start_time: {field.data}, type: {type(field.data)}")
        if field.data is None:
            logger.error("Start time is None")
            raise ValidationError('Start time is required')
    
    def validate_local_base_dir(self, field):
        if self.save_to_local.data and not field.data:
            raise ValidationError('Local base directory is required when saving to additional local folder')
    
    def validate_nextcloud_base_dir(self, field):
        if self.save_to_nextcloud.data and not field.data:
            raise ValidationError('NextCloud base directory is required when saving to NextCloud')

class RecurringRecordingForm(FlaskForm):
    name = StringField('Recording Name', validators=[DataRequired(), Length(max=100)])
    station_id = SelectField('Radio Station', coerce=int, validators=[DataRequired()])
    schedule_type = SelectField('Schedule Type', choices=[
        ('daily', 'Daily (Every day)'),
        ('weekdays', 'Weekdays (Monday to Friday)'),
        ('weekends', 'Weekends (Saturday and Sunday)'),
        ('weekly', 'Weekly (Same day every week)'),
        ('monthly', 'Monthly (Same day every month)')
    ])
    days_of_week = SelectField('Day of Week', choices=[
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ])
    start_time = TimeField('Start Time', format='%H:%M', validators=[DataRequired()])
    duration = IntegerField('Duration (minutes)', validators=[DataRequired()])
    keep_recordings = IntegerField('Number of Recordings to Keep', default=10)
    
    # Audio format
    format = SelectField('Audio Format', choices=[
        ('mp3', 'MP3'),
        ('ogg', 'OGG Vorbis'),
        ('aac', 'AAC'),
        ('flac', 'FLAC'),
        ('wav', 'WAV')
    ], default='mp3')
    
    # Additional storage options
    save_to_local = BooleanField('Save to Additional Local Folder')
    local_base_dir = StringField('Local Base Directory')
    
    save_to_nextcloud = BooleanField('Save to NextCloud')
    nextcloud_base_dir = StringField('NextCloud Base Directory')
    
    # Notification option
    send_notification = BooleanField('Send Pushover Notification', default=True)
    
    # Podcast options
    create_podcast = BooleanField('Create Podcast from Recordings')
    podcast_title = StringField('Podcast Title')
    podcast_description = TextAreaField('Podcast Description')
    podcast_language = SelectField('Language', choices=[
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('it', 'Italian'),
        ('pt', 'Portuguese'),
        ('ru', 'Russian'),
        ('ja', 'Japanese'),
        ('zh', 'Chinese')
    ], default='en')
    podcast_author = StringField('Author')
    podcast_image = FileField('Podcast Cover Image', validators=[
        FileAllowed(['jpg', 'png'], 'Images only!')
    ])
    
    submit = SubmitField('Schedule Recurring Recording')
    
    def validate_local_base_dir(self, field):
        if self.save_to_local.data and not field.data:
            raise ValidationError('Local base directory is required when saving to additional local folder')
    
    def validate_nextcloud_base_dir(self, field):
        if self.save_to_nextcloud.data and not field.data:
            raise ValidationError('NextCloud base directory is required when saving to NextCloud')
    
    def validate_podcast_title(self, field):
        if self.create_podcast.data and not field.data:
            raise ValidationError('Podcast title is required when creating a podcast')
    
    def validate_days_of_week(self, field):
        if self.schedule_type.data == 'weekly' and not field.data:
            raise ValidationError('Day selection is required for weekly schedule')
            
    def validate_days_of_month(self, field):
        if self.schedule_type.data == 'monthly' and not field.data:
            raise ValidationError('Day selection is required for monthly schedule')

class PodcastForm(FlaskForm):
    title = StringField('Podcast Title', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description')
    language = SelectField('Language', choices=[
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('it', 'Italian'),
        ('pt', 'Portuguese'),
        ('ru', 'Russian'),
        ('ja', 'Japanese'),
        ('zh', 'Chinese')
    ], default='en')
    author = StringField('Author')
    image = FileField('Cover Image', validators=[
        FileAllowed(['jpg', 'png'], 'Images only!')
    ])
    itunes_category = SelectField('iTunes Category', choices=[
        ('Arts', 'Arts'),
        ('Business', 'Business'),
        ('Comedy', 'Comedy'),
        ('Education', 'Education'),
        ('Fiction', 'Fiction'),
        ('Government', 'Government'),
        ('Health & Fitness', 'Health & Fitness'),
        ('History', 'History'),
        ('Kids & Family', 'Kids & Family'),
        ('Leisure', 'Leisure'),
        ('Music', 'Music'),
        ('News', 'News'),
        ('Religion & Spirituality', 'Religion & Spirituality'),
        ('Science', 'Science'),
        ('Society & Culture', 'Society & Culture'),
        ('Sports', 'Sports'),
        ('Technology', 'Technology'),
        ('True Crime', 'True Crime'),
        ('TV & Film', 'TV & Film')
    ], default='Technology')
    itunes_explicit = SelectField('Explicit Content', choices=[('no', 'No'), ('yes', 'Yes')], default='no')
    itunes_owner_email = StringField('Owner Email')
    submit = SubmitField('Save Podcast')

class SettingsForm(FlaskForm):
    # NextCloud settings
    nextcloud_url = StringField('NextCloud URL', validators=[Optional(), URL()])
    nextcloud_username = StringField('NextCloud Username', validators=[Optional()])
    nextcloud_password = PasswordField('NextCloud Password', validators=[Optional()])
    
    # Pushover settings
    pushover_user_key = StringField('Pushover User Key', validators=[Optional()])
    pushover_api_token = StringField('Pushover API Token', validators=[Optional()])
    
    # FFmpeg settings
    ffmpeg_path = StringField('FFmpeg Path', validators=[Optional()])
    
    # Default audio format
    default_audio_format = SelectField('Default Audio Format', choices=[
        ('mp3', 'MP3'),
        ('ogg', 'OGG Vorbis'),
        ('aac', 'AAC'),
        ('flac', 'FLAC'),
        ('wav', 'WAV')
    ], default='mp3')
    
    submit = SubmitField('Save Settings')
