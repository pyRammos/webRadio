# WebRadio Recorder

A web application for capturing internet audio streams and saving them for playback later. Perfect for recording radio shows to listen to at your convenience.

## Features

- Record audio from any internet radio station
- Schedule one-time and recurring recordings
- Resume interrupted recordings automatically
- Generate podcasts from recurring recordings
- Multiple storage options (local, NextCloud)
- Notification system for recording events
- Web-based playback interface
- Multi-format audio support (MP3, OGG, AAC, FLAC, WAV)
- Centralized settings management

## Requirements

- Python 3.8+
- FFmpeg
- Web server (for production deployment)
- Docker (optional, for containerized deployment)

## Installation

### Standard Installation

1. Clone this repository
   ```bash
   git clone https://github.com/yourusername/webradio.git
   cd webradio
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Configure the application settings in `.env` (copy from `.env.example`)
   ```bash
   cp .env.example .env
   # Edit .env with your preferred settings
   ```

4. Run the application
   ```bash
   python app.py
   ```

### Docker Installation

#### Option 1: Using Pre-built Docker Image

1. Clone this repository
   ```bash
   git clone https://github.com/yourusername/webradio.git
   cd webradio
   ```

2. Run the setup script to create necessary directories and files
   ```bash
   ./setup_docker.sh
   ```

3. Start the application
   ```bash
   docker compose up -d
   ```

#### Option 2: Building Your Own Docker Image

1. Clone this repository
   ```bash
   git clone https://github.com/yourusername/webradio.git
   cd webradio
   ```

2. Run the setup script to create necessary directories and files
   ```bash
   ./setup_docker.sh
   ```

3. Build the Docker image
   ```bash
   docker build -t webradio:latest .
   ```

4. Edit docker-compose.yml to use your local image
   ```bash
   # Change "image: teleram/webradio:latest" to "image: webradio:latest"
   ```

5. Start the application
   ```bash
   docker compose up -d
   ```

## Usage

Access the web interface at http://localhost:5000 after starting the application.

### Default Login

- Username: admin
- Password: admin

**Important**: Change the default password immediately after first login.

### Settings Configuration

1. Log in as admin
2. Click on your username in the top-right corner
3. Select "Settings" from the dropdown menu
4. Configure NextCloud, Pushover, FFmpeg settings, and default audio format
5. Click "Save Settings"

### Setting Default Storage Paths

1. Log in as admin
2. Click on your username in the top-right corner
3. Select "Profile" from the dropdown menu
4. Set your default local and NextCloud storage paths
5. Click "Update Profile"

## Recent Improvements

See [AmazonQ.md](AmazonQ.md) for details on recent improvements to the application.

## Docker Hub

The WebRadio Recorder Docker image is available on Docker Hub:

```bash
docker pull teleram/webradio:latest
```

## License

[MIT License](LICENSE)
