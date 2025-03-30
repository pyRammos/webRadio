# Docker Setup for WebRadio Recorder

This guide explains how to run the WebRadio Recorder application using Docker and Docker Compose.

## Prerequisites

- Docker installed on your system
- Docker Compose installed on your system

## Directory Structure

Before starting, create the necessary directories for persistent data:

```bash
mkdir -p data/recordings data/images
```

These directories will be mounted as volumes in the Docker container to ensure your data persists between container restarts.

## Environment Variables

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit the `.env` file with your specific configuration:

```
# Flask configuration
SECRET_KEY=generate-a-secure-random-key
FLASK_APP=app.py
FLASK_ENV=production

# Database
DATABASE_URL=sqlite:///webradio.db

# Recording settings
RECORDINGS_DIR=/app/recordings
FFMPEG_PATH=/usr/bin/ffmpeg

# NextCloud integration (if needed)
NEXTCLOUD_URL=https://your-nextcloud-instance.com
NEXTCLOUD_USERNAME=your-username
NEXTCLOUD_PASSWORD=your-password

# Pushover notifications (if needed)
PUSHOVER_USER_KEY=your-user-key
PUSHOVER_API_TOKEN=your-api-token
```

## Running with Docker Compose

1. Build and start the container:

```bash
docker-compose up -d
```

2. Access the application at http://localhost:5000

3. To view logs:

```bash
docker-compose logs -f
```

4. To stop the application:

```bash
docker-compose down
```

## Volume Mounts Explained

The Docker Compose configuration includes several volume mounts:

1. **Recordings Directory**: `/app/recordings`
   - Stores all recorded audio files
   - Mounted to `./data/recordings` on your host

2. **Images Directory**: `/app/static/images`
   - Stores podcast cover images and other uploads
   - Mounted to `./data/images` on your host

3. **Database File**: `/app/webradio.db`
   - The SQLite database file
   - Mounted to `./data/webradio.db` on your host

## Customization

### Using a Different Port

To use a different port (e.g., 8080 instead of 5000), modify the `ports` section in `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"
```

## Troubleshooting

### Permission Issues

If you encounter permission issues with the mounted volumes, ensure the directories have the correct permissions:

```bash
chmod -R 777 data/
```

Note: In a production environment, use more restrictive permissions based on the user ID that the container runs as.

### Container Not Starting

Check the logs for errors:

```bash
docker-compose logs
```

### FFmpeg Not Found

If you encounter issues with FFmpeg, verify that it's correctly installed in the container:

```bash
docker exec -it webradio which ffmpeg
```

This should return `/usr/bin/ffmpeg`. If it doesn't, there might be an issue with the Docker image build.
