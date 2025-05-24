# WebRadio4 - Radio Recording Application

## Overview
WebRadio4 is a Docker-based application for scheduling and recording radio streams. It provides a web interface for managing radio stations, scheduling recordings, and creating podcasts from recorded content.

## Features
- Record radio streams using FFmpeg
- Schedule one-time or recurring recordings
- Automatically create podcasts from recordings
- Store recordings locally or on NextCloud
- Send notifications when recordings complete

## Docker Setup
The application is available as a Docker image at `teleram/webradio:latest` or with specific version tags like `teleram/webradio:2.1.2`.

### Docker Compose Example
```yaml
services:
  webradio:
    image: teleram/webradio:latest
    container_name: webradio
    restart: unless-stopped
    ports:
      - "5850:5000"
    volumes:
      - /path/to/recordings:/app/recordings
      - /path/to/images:/app/static/images
      - /path/to/data:/data
      - /path/to/local/recordings:/localrec
    environment:
      - DATABASE_URL=sqlite:////data/webradio.db
      - DATABASE_PATH=/data/webradio.db
      - RECORDINGS_DIR=/app/recordings
      - UPLOAD_FOLDER=/app/static/images
      - TZ=Europe/Athens
      - SECRET_KEY=YourSecretKeyHere
      - LOG_LEVEL=WARNING
      - FFMPEG_PATH=/usr/bin/ffmpeg
```

## Environment Variables
- `DATABASE_URL`: SQLite database URL
- `DATABASE_PATH`: Path to the SQLite database file
- `RECORDINGS_DIR`: Directory to store recordings
- `UPLOAD_FOLDER`: Directory for uploaded images
- `TZ`: Timezone for the application
- `SECRET_KEY`: Secret key for Flask sessions
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `FFMPEG_PATH`: Path to the FFmpeg executable (required for recording)

## Volumes
- `/app/recordings`: Where recordings are stored
- `/app/static/images`: For station logos and other images
- `/data`: For the SQLite database
- `/localrec`: Optional additional storage location

## Schedule Types
WebRadio4 supports the following schedule types for recurring recordings:

- **Daily**: Records every day at the same time
- **Weekdays**: Records Monday through Friday at the same time
- **Weekends**: Records Saturday and Sunday at the same time
- **Weekly**: Records on a specific day of the week
- **Monthly**: Records on a specific day of the month

## Version History
- 2.1.9: Added FFmpeg error logging and improved stream connection parameters
- 2.1.8: Fixed SQLAlchemy query in retry_recording function to properly handle recording retries
- 2.1.7: Previous version changes
- 2.1.2: Fixed logging configuration to respect LOG_LEVEL environment variable and silence APScheduler messages
- 2.1.1: Added support for 'weekdays' and 'monthly' schedule types
- 2.1.0: Added FFMPEG_PATH environment variable to fix recording issues
- 2.0.0: Initial public release

## Troubleshooting
If you encounter recording errors like `'AppSettings' object has no attribute 'ffmpeg_path'`, make sure to set the `FFMPEG_PATH` environment variable in your Docker Compose file.

If you see an error like `Unknown schedule type 'weekdays'`, update to version 2.1.1 or later which adds support for this schedule type.

To reduce log verbosity, set the `LOG_LEVEL` environment variable to `WARNING` or `ERROR` in your Docker Compose file.
