#!/usr/bin/env python3
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import logging
from datetime import datetime, timedelta
import pytz
from tzlocal import get_localzone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import subprocess
import shutil
import time
import json
import uuid
from feedgen.feed import FeedGenerator
import requests

# Initialize timezone from environment variable
time.tzset()

from models import db, User, RadioStation, Recording, RecurringRecording, Podcast, PodcastEpisode, AppSettings
from forms import LoginForm, UserProfileForm, RadioStationForm, RecordingForm, RecurringRecordingForm, PodcastForm, SettingsForm
from config import Config
from utils.recorder import start_recording, resume_recording, check_active_recordings
from utils.notifications import send_notification
from utils.storage import save_to_additional_locations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.route('/')
def index():
    server_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    server_timezone = time.tzname[0]
    return render_template('index.html', server_time=server_time, server_timezone=server_timezone)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = UserProfileForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        if form.password.data:
            current_user.password_hash = generate_password_hash(form.password.data)
        
        # Update default storage paths
        current_user.default_local_storage_path = form.default_local_storage_path.data
        current_user.default_nextcloud_storage_path = form.default_nextcloud_storage_path.data
        
        db.session.commit()
        flash('Your profile has been updated.')
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.default_local_storage_path.data = current_user.default_local_storage_path
        form.default_nextcloud_storage_path.data = current_user.default_nextcloud_storage_path
    return render_template('profile.html', form=form)

@app.route('/stations')
@login_required
def stations():
    stations = RadioStation.query.all()
    return render_template('stations.html', stations=stations)

@app.route('/stations/add', methods=['GET', 'POST'])
@login_required
def add_station():
    form = RadioStationForm()
    if form.validate_on_submit():
        station = RadioStation(
            name=form.name.data,
            url=form.url.data,
            description=form.description.data
        )
        db.session.add(station)
        db.session.commit()
        flash(f'Radio station {form.name.data} has been added.')
        return redirect(url_for('stations'))
    return render_template('station_form.html', form=form, title='Add Radio Station')

@app.route('/stations/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_station(id):
    station = RadioStation.query.get_or_404(id)
    form = RadioStationForm(obj=station)
    if form.validate_on_submit():
        station.name = form.name.data
        station.url = form.url.data
        station.description = form.description.data
        db.session.commit()
        flash(f'Radio station {station.name} has been updated.')
        return redirect(url_for('stations'))
    return render_template('station_form.html', form=form, title='Edit Radio Station')

@app.route('/stations/delete/<int:id>')
@login_required
def delete_station(id):
    station = RadioStation.query.get_or_404(id)
    db.session.delete(station)
    db.session.commit()
    flash(f'Radio station {station.name} has been deleted.')
    return redirect(url_for('stations'))

@app.route('/recordings')
@login_required
def recordings():
    recordings = Recording.query.all()
    return render_template('recordings.html', recordings=recordings)

@app.route('/recordings/add', methods=['GET', 'POST'])
@login_required
def add_recording():
    form = RecordingForm()
    form.station_id.choices = [(s.id, s.name) for s in RadioStation.query.all()]
    
    # Pre-fill storage paths from user defaults
    if request.method == 'GET' and current_user.default_local_storage_path:
        form.local_base_dir.data = current_user.default_local_storage_path
        form.save_to_local.data = True
    
    if request.method == 'GET' and current_user.default_nextcloud_storage_path:
        form.nextcloud_base_dir.data = current_user.default_nextcloud_storage_path
        form.save_to_nextcloud.data = True
    
    if form.validate_on_submit():
        # Log form data for debugging
        app.logger.info(f"Form validated successfully")
        app.logger.info(f"Start time: {form.start_time.data}, type: {type(form.start_time.data)}")
        
        # Get the selected audio format or use the default from settings
        audio_format = form.format.data
        if not audio_format:
            audio_format = AppSettings.get('default_audio_format', 'mp3')
        
        # Format the recording name with date and day
        now = datetime.now()
        formatted_date = now.strftime('%y%m%d-%a')
        file_name = f"{form.name.data}{formatted_date}.{audio_format}"
        
        recording = Recording(
            name=form.name.data,
            station_id=form.station_id.data,
            start_time=form.start_time.data,
            duration=form.duration.data,
            file_name=file_name,
            local_path=os.path.join(app.config['RECORDINGS_DIR'], file_name),
            format=audio_format,
            status='scheduled',
            send_notification=form.send_notification.data
        )
        
        # Handle additional storage locations
        if form.save_to_local.data:
            recording.additional_local_path = os.path.join(
                form.local_base_dir.data,
                form.name.data,
                now.strftime('%Y'),
                now.strftime('%m-%b')
            )
            
        if form.save_to_nextcloud.data:
            recording.nextcloud_path = os.path.join(
                form.nextcloud_base_dir.data,
                form.name.data,
                now.strftime('%Y'),
                now.strftime('%m-%b')
            )
        
        db.session.add(recording)
        db.session.commit()
        
        # Schedule the recording
        trigger = DateTrigger(run_date=form.start_time.data)
        scheduler.add_job(
            start_recording,
            trigger=trigger,
            args=[recording.id],
            id=f'recording_{recording.id}',
            replace_existing=True
        )
        
        flash(f'Recording {form.name.data} has been scheduled.')
        return redirect(url_for('recordings'))
    else:
        # Log validation errors
        for field, errors in form.errors.items():
            app.logger.error(f"Field {field} has errors: {errors}")
        
        # Log the raw form data
        app.logger.info(f"Raw start_time value: {request.form.get('start_time')}")
    
    return render_template('recording_form.html', form=form, title='Schedule Recording')

@app.route('/recordings/delete/<int:id>')
@login_required
def delete_recording(id):
    recording = Recording.query.get_or_404(id)
    
    # Remove from scheduler if still scheduled
    try:
        scheduler.remove_job(f'recording_{recording.id}')
    except:
        pass
    
    # Delete the file if it exists
    if recording.local_path:
        # Check for file with any supported extension
        base_path = os.path.splitext(recording.local_path)[0]
        supported_formats = ['mp3', 'ogg', 'aac', 'flac', 'wav']
        
        for fmt in supported_formats:
            file_path = f"{base_path}.{fmt}"
            if os.path.exists(file_path):
                os.remove(file_path)
                break
    
    db.session.delete(recording)
    db.session.commit()
    flash(f'Recording {recording.name} has been deleted.')
    return redirect(url_for('recordings'))

@app.route('/recurring')
@login_required
def recurring_recordings():
    recordings = RecurringRecording.query.all()
    return render_template('recurring_recordings.html', recordings=recordings)

@app.route('/recurring/add', methods=['GET', 'POST'])
@login_required
def add_recurring_recording():
    form = RecurringRecordingForm()
    form.station_id.choices = [(s.id, s.name) for s in RadioStation.query.all()]
    
    # Pre-fill storage paths from user defaults
    if request.method == 'GET' and current_user.default_local_storage_path:
        form.local_base_dir.data = current_user.default_local_storage_path
        form.save_to_local.data = True
    
    if request.method == 'GET' and current_user.default_nextcloud_storage_path:
        form.nextcloud_base_dir.data = current_user.default_nextcloud_storage_path
        form.save_to_nextcloud.data = True
    
    if form.validate_on_submit():
        recurring = RecurringRecording(
            name=form.name.data,
            station_id=form.station_id.data,
            schedule_type=form.schedule_type.data,
            days_of_week=','.join(form.days_of_week.data) if form.days_of_week.data else None,
            start_time=form.start_time.data,
            duration=form.duration.data,
            keep_recordings=form.keep_recordings.data,
            create_podcast=form.create_podcast.data,
            send_notification=form.send_notification.data
        )
        
        # Handle additional storage locations
        if form.save_to_local.data:
            recurring.additional_local_path = form.local_base_dir.data
            
        if form.save_to_nextcloud.data:
            recurring.nextcloud_path = form.nextcloud_base_dir.data
        
        db.session.add(recurring)
        db.session.commit()
        
        # Create podcast if requested
        if form.create_podcast.data:
            # Get iTunes specific fields from form
            itunes_category = request.form.get('itunes_category', 'Technology')
            itunes_explicit = request.form.get('itunes_explicit', 'no')
            itunes_owner_email = request.form.get('itunes_owner_email', 'admin@example.com')
            
            podcast = Podcast(
                title=form.podcast_title.data or form.name.data,
                description=form.podcast_description.data or f"Recordings of {form.name.data}",
                language=form.podcast_language.data,
                author=form.podcast_author.data,
                recurring_recording_id=recurring.id,
                # Add iTunes specific fields
                itunes_category=itunes_category,
                itunes_explicit=itunes_explicit,
                itunes_owner_email=itunes_owner_email
            )
            
            # Handle podcast image
            if form.podcast_image.data:
                filename = secure_filename(form.podcast_image.data.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                form.podcast_image.data.save(image_path)
                podcast.image_path = image_path
                
            db.session.add(podcast)
            db.session.commit()
        
        # Get the selected audio format or use the default from settings
        audio_format = form.format.data
        if not audio_format:
            audio_format = AppSettings.get('default_audio_format', 'mp3')
        
        # Set the format for the recurring recording
        recurring.format = audio_format
        db.session.commit()
        
        # Schedule the recurring recording
        if recurring.schedule_type == 'daily':
            trigger = CronTrigger(
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'weekly':
            days = recurring.days_of_week.split(',') if ',' in recurring.days_of_week else [recurring.days_of_week]
            trigger = CronTrigger(
                day_of_week=','.join(days),
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'weekends':
            trigger = CronTrigger(
                day_of_week='sat,sun',
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'weekdays':
            trigger = CronTrigger(
                day_of_week='mon,tue,wed,thu,fri',
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'monthly':
            # Handle monthly schedule with day of month
            day_of_month = request.form.get('days_of_month', '1')
            if day_of_month == 'last':
                # For last day of month, use day='last'
                trigger = CronTrigger(
                    day='last',
                    hour=recurring.start_time.hour,
                    minute=recurring.start_time.minute
                )
            else:
                trigger = CronTrigger(
                    day=day_of_month,
                    hour=recurring.start_time.hour,
                    minute=recurring.start_time.minute
                )
        else:
            # Default fallback to daily if something goes wrong
            trigger = CronTrigger(
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        
        scheduler.add_job(
            start_recording,
            trigger=trigger,
            args=[recurring.id, True],
            id=f'recurring_{recurring.id}',
            replace_existing=True
        )
        
        flash(f'Recurring recording {form.name.data} has been scheduled.')
        return redirect(url_for('recurring_recordings'))
    
    return render_template('recurring_form.html', form=form, title='Schedule Recurring Recording')

@app.route('/recurring/delete/<int:id>')
@login_required
def delete_recurring_recording(id):
    recurring = RecurringRecording.query.get_or_404(id)
    
    # Remove from scheduler
    try:
        scheduler.remove_job(f'recurring_{recurring.id}')
    except:
        pass
    
    # Delete associated podcast if exists
    podcast = Podcast.query.filter_by(recurring_recording_id=recurring.id).first()
    if podcast:
        # Delete podcast episodes
        episodes = PodcastEpisode.query.filter_by(podcast_id=podcast.id).all()
        for episode in episodes:
            db.session.delete(episode)
        db.session.delete(podcast)
    
    db.session.delete(recurring)
    db.session.commit()
    flash(f'Recurring recording {recurring.name} has been deleted.')
    return redirect(url_for('recurring_recordings'))

@app.route('/podcasts')
def podcasts():
    podcasts = Podcast.query.all()
    return render_template('podcasts.html', podcasts=podcasts)

@app.route('/podcasts/<int:id>')
def podcast_details(id):
    podcast = Podcast.query.get_or_404(id)
    episodes = PodcastEpisode.query.filter_by(podcast_id=podcast.id).order_by(PodcastEpisode.publication_date.desc()).all()
    return render_template('podcast_details.html', podcast=podcast, episodes=episodes)

@app.route('/podcasts/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_podcast(id):
    podcast = Podcast.query.get_or_404(id)
    form = PodcastForm(obj=podcast)
    
    if form.validate_on_submit():
        podcast.title = form.title.data
        podcast.description = form.description.data
        podcast.language = form.language.data
        podcast.author = form.author.data
        podcast.itunes_category = form.itunes_category.data
        podcast.itunes_explicit = form.itunes_explicit.data
        podcast.itunes_owner_email = form.itunes_owner_email.data
        
        # Handle image upload
        if form.image.data:
            filename = secure_filename(form.image.data.filename)
            # Generate unique filename to avoid overwriting
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            form.image.data.save(image_path)
            podcast.image_path = image_path
        
        db.session.commit()
        flash(f'Podcast {podcast.title} has been updated.')
        return redirect(url_for('podcast_details', id=podcast.id))
    
    return render_template('podcast_form.html', form=form, podcast=podcast, title='Edit Podcast')

@app.route('/podcasts/feed/<int:id>')
def podcast_feed(id):
    podcast = Podcast.query.get_or_404(id)
    
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.title(podcast.title)
    fg.link(href=request.url_root, rel='self')
    fg.description(podcast.description)
    fg.language(podcast.language)
    fg.author({'name': podcast.author})
    
    # Add iTunes specific tags using the podcast model fields
    fg.podcast.itunes_category(podcast.itunes_category or 'Technology')
    fg.podcast.itunes_explicit(podcast.itunes_explicit or 'no')
    fg.podcast.itunes_author(podcast.author)
    fg.podcast.itunes_owner(name=podcast.author, email=podcast.itunes_owner_email or 'admin@example.com')
    
    if podcast.image_path and os.path.exists(podcast.image_path):
        # Extract just the filename from the path and use it directly
        image_filename = os.path.basename(podcast.image_path)
        image_url = url_for('static', filename=f'images/{image_filename}', _external=True)
        fg.image(url=image_url)
        fg.podcast.itunes_image(image_url)
    
    # Import tzlocal at the top of the file if not already imported
    from tzlocal import get_localzone
    
    episodes = PodcastEpisode.query.filter_by(podcast_id=podcast.id).order_by(PodcastEpisode.publication_date.desc()).all()
    
    # Get local timezone
    local_timezone = get_localzone()
    
    for episode in episodes:
        fe = fg.add_entry()
        fe.id(str(episode.id))  # This is the GUID
        fe.title(episode.title)
        fe.description(episode.description)
        
        # Add timezone info to the publication date using replace() instead of localize()
        aware_datetime = episode.publication_date.replace(tzinfo=local_timezone)
        fe.pubdate(aware_datetime)
        
        file_url = url_for('download_episode', id=episode.id, _external=True)
        
        # Determine the MIME type based on the file extension
        mime_types = {
            'mp3': 'audio/mpeg',
            'ogg': 'audio/ogg',
            'aac': 'audio/aac',
            'flac': 'audio/flac',
            'wav': 'audio/wav'
        }
        
        # Get the file extension
        ext = os.path.splitext(episode.file_path)[1].lower().lstrip('.')
        mimetype = mime_types.get(ext, 'audio/mpeg')
        
        # Add enclosure with all required attributes
        fe.enclosure(file_url, str(episode.file_size), mimetype)
        
        # Add iTunes specific episode tags
        if episode.duration:
            fe.podcast.itunes_duration(str(episode.duration))
    
    # Set the correct XML declaration and namespaces
    response = app.response_class(
        response=fg.rss_str(),
        status=200,
        mimetype='application/rss+xml'
    )
    return response

@app.route('/download/<int:id>')
def download_recording(id):
    recording = Recording.query.get_or_404(id)
    
    # Get the base path and file name
    base_path = os.path.dirname(recording.local_path)
    file_name = os.path.basename(recording.local_path)
    
    # Define supported formats to check
    supported_formats = ['mp3', 'ogg', 'aac', 'flac', 'wav']
    
    # Check if the file exists
    if not os.path.exists(recording.local_path):
        # Try to find the file with any supported extension
        base_name = os.path.splitext(file_name)[0]
        for fmt in supported_formats:
            test_file = f"{base_name}.{fmt}"
            if os.path.exists(os.path.join(base_path, test_file)):
                file_name = test_file
                break
    
    # Get the MIME type based on the file extension
    mime_types = {
        'mp3': 'audio/mpeg',
        'ogg': 'audio/ogg',
        'aac': 'audio/aac',
        'flac': 'audio/flac',
        'wav': 'audio/wav'
    }
    
    # Get the file extension
    ext = os.path.splitext(file_name)[1].lower().lstrip('.')
    mimetype = mime_types.get(ext, 'audio/mpeg')
    
    return send_from_directory(base_path, file_name, as_attachment=True, mimetype=mimetype)

@app.route('/download/episode/<int:id>')
def download_episode(id):
    episode = PodcastEpisode.query.get_or_404(id)
    
    # Get the base path and file name
    base_path = os.path.dirname(episode.file_path)
    file_name = os.path.basename(episode.file_path)
    
    # Define supported formats to check
    supported_formats = ['mp3', 'ogg', 'aac', 'flac', 'wav']
    
    # Check if the file exists
    if not os.path.exists(episode.file_path):
        # Try to find the file with any supported extension
        base_name = os.path.splitext(file_name)[0]
        for fmt in supported_formats:
            test_file = f"{base_name}.{fmt}"
            if os.path.exists(os.path.join(base_path, test_file)):
                file_name = test_file
                break
    
    # Get the MIME type based on the file extension
    mime_types = {
        'mp3': 'audio/mpeg',
        'ogg': 'audio/ogg',
        'aac': 'audio/aac',
        'flac': 'audio/flac',
        'wav': 'audio/wav'
    }
    
    # Get the file extension
    ext = os.path.splitext(file_name)[1].lower().lstrip('.')
    mimetype = mime_types.get(ext, 'audio/mpeg')
    
    return send_from_directory(base_path, file_name, as_attachment=True, mimetype=mimetype)

# Initialize database and create admin user if not exists
with app.app_context():
    db.create_all()
    
    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin'),
            default_local_storage_path='',
            default_nextcloud_storage_path=''
        )
        db.session.add(admin)
        db.session.commit()
    
    # Create recordings directory if not exists
    os.makedirs(app.config['RECORDINGS_DIR'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Load settings from database into app config
    settings = AppSettings.query.all()
    for setting in settings:
        if setting.key in ['NEXTCLOUD_URL', 'NEXTCLOUD_USERNAME', 'NEXTCLOUD_PASSWORD', 
                          'PUSHOVER_USER_KEY', 'PUSHOVER_API_TOKEN', 'FFMPEG_PATH']:
            app.config[setting.key] = setting.value
    
    # Resume any interrupted recordings
    active_recordings = Recording.query.filter_by(status='recording').all()
    for recording in active_recordings:
        resume_recording(recording.id)
    
    # Schedule recurring recordings
    recurring_recordings = RecurringRecording.query.all()
    for recurring in recurring_recordings:
        # Default trigger in case schedule_type doesn't match any condition
        trigger = None
        
        if recurring.schedule_type == 'daily':
            trigger = CronTrigger(
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'weekly':
            days = recurring.days_of_week.split(',')
            trigger = CronTrigger(
                day_of_week=','.join(days),
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        elif recurring.schedule_type == 'weekends':
            trigger = CronTrigger(
                day_of_week='sat,sun',
                hour=recurring.start_time.hour,
                minute=recurring.start_time.minute
            )
        else:
            # Log unknown schedule type and skip this recording
            app.logger.error(f"Unknown schedule type '{recurring.schedule_type}' for recurring recording ID {recurring.id}")
            continue
        
        # Only add job if we have a valid trigger
        if trigger:
            scheduler.add_job(
                start_recording,
                trigger=trigger,
                args=[recurring.id, True],
                id=f'recurring_{recurring.id}',
                replace_existing=True
            )
    
    # Schedule job to check active recordings
    scheduler.add_job(
        check_active_recordings,
        'interval',
        minutes=1,
        id='check_active_recordings',
        replace_existing=True
    )

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = SettingsForm()
    
    if form.validate_on_submit():
        # Update NextCloud settings
        AppSettings.set('NEXTCLOUD_URL', form.nextcloud_url.data)
        AppSettings.set('NEXTCLOUD_USERNAME', form.nextcloud_username.data)
        if form.nextcloud_password.data:  # Only update password if provided
            AppSettings.set('NEXTCLOUD_PASSWORD', form.nextcloud_password.data)
        
        # Update Pushover settings
        AppSettings.set('PUSHOVER_USER_KEY', form.pushover_user_key.data)
        AppSettings.set('PUSHOVER_API_TOKEN', form.pushover_api_token.data)
        
        # Update FFmpeg path
        if form.ffmpeg_path.data:
            AppSettings.set('FFMPEG_PATH', form.ffmpeg_path.data)
            
        # Update default audio format
        AppSettings.set('default_audio_format', form.default_audio_format.data)
        
        # Update application config
        app.config['NEXTCLOUD_URL'] = form.nextcloud_url.data
        app.config['NEXTCLOUD_USERNAME'] = form.nextcloud_username.data
        if form.nextcloud_password.data:
            app.config['NEXTCLOUD_PASSWORD'] = form.nextcloud_password.data
        app.config['PUSHOVER_USER_KEY'] = form.pushover_user_key.data
        app.config['PUSHOVER_API_TOKEN'] = form.pushover_api_token.data
        if form.ffmpeg_path.data:
            app.config['FFMPEG_PATH'] = form.ffmpeg_path.data
        app.config['DEFAULT_AUDIO_FORMAT'] = form.default_audio_format.data
        
        flash('Settings have been updated.')
        return redirect(url_for('settings'))
    
    elif request.method == 'GET':
        # Load current settings
        form.nextcloud_url.data = AppSettings.get('NEXTCLOUD_URL', app.config.get('NEXTCLOUD_URL', ''))
        form.nextcloud_username.data = AppSettings.get('NEXTCLOUD_USERNAME', app.config.get('NEXTCLOUD_USERNAME', ''))
        form.pushover_user_key.data = AppSettings.get('PUSHOVER_USER_KEY', app.config.get('PUSHOVER_USER_KEY', ''))
        form.pushover_api_token.data = AppSettings.get('PUSHOVER_API_TOKEN', app.config.get('PUSHOVER_API_TOKEN', ''))
        form.ffmpeg_path.data = AppSettings.get('FFMPEG_PATH', app.config.get('FFMPEG_PATH', 'ffmpeg'))
        form.default_audio_format.data = AppSettings.get('default_audio_format', app.config.get('DEFAULT_AUDIO_FORMAT', 'mp3'))
    
    return render_template('settings.html', form=form)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
