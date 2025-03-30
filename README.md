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

## Future Enhancements

### 1. Advanced Recording Features
1.1. **Smart recording detection**: Automatically detect silence or non-music segments to split recordings  
1.2. **Audio normalization**: Level out volume differences between recordings  
1.3. **Audio fingerprinting**: Detect and tag songs within recordings  
1.4. **Scheduled post-processing**: Allow users to schedule audio processing tasks (trimming, splitting) after recording  

### 2. User Experience Improvements
2.1. **Dark mode**: Add a toggle for light/dark theme  
2.2. **Mobile-responsive design**: Optimize the interface for mobile devices  
2.3. **Drag-and-drop scheduling**: Visual calendar interface for scheduling recordings  
2.4. **Audio waveform visualization**: Show waveforms for recorded audio  
2.5. **Keyboard shortcuts**: Add keyboard shortcuts for common actions  

### 3. Content Management
3.1. **Tagging system**: Allow users to tag recordings and filter by tags  
3.2. **Search functionality**: Full-text search across recording names and descriptions  
3.3. **Batch operations**: Select multiple recordings for batch actions (delete, move, tag)  
3.4. **Auto-categorization**: Suggest categories based on recording content or schedule  

### 4. Integration Enhancements
4.1. **Additional storage options**: Add support for S3, Google Drive, Dropbox  
4.2. **DLNA/UPnP support**: Make recordings available to smart TVs and media players  
4.3. **RSS feed generation**: Create RSS feeds for non-podcast recordings  
4.4. **Calendar integration**: Export recording schedules to calendar apps (iCal, Google Calendar)  
4.5. **Voice assistant integration**: Control via Alexa, Google Assistant, or Home Assistant  

### 5. Technical Improvements
5.1. **API endpoints**: Create a REST API for programmatic access  
5.2. **WebSocket support**: Real-time updates for recording status  
5.3. **User roles and permissions**: Add admin, editor, and viewer roles  
5.4. **Multi-user support**: Allow multiple users with separate settings and recordings  
5.5. **Recording presets**: Save common recording configurations as presets  
5.6. **Backup and restore**: Automated backup of application data and settings  

### 6. Analytics and Monitoring
6.1. **Recording statistics**: Track recording frequency, duration, and storage usage  
6.2. **Health monitoring**: Dashboard showing system status and resource usage  
6.3. **Error reporting**: Improved error handling with notifications  
6.4. **Usage analytics**: Track most-used features and popular stations  

### 7. Audio Processing
7.1. **Audio effects**: Add options for compression, EQ, noise reduction  
7.2. **Automatic chapter markers**: Detect program segments and add chapter markers  
7.3. **Transcription**: Integrate with speech-to-text services for searchable transcripts  
7.4. **Audio cleanup**: Remove ads or silence automatically  

### 8. Social Features
8.1. **Sharing options**: Generate shareable links for recordings  
8.2. **Public podcast directory**: Option to list podcasts in a public directory  
8.3. **Comments/notes**: Allow adding notes to recordings for future reference  
8.4. **Collaborative playlists**: Allow multiple users to contribute to recording collections  

## Docker Hub

The WebRadio Recorder Docker image is available on Docker Hub:

```bash
docker pull teleram/webradio:latest
```

## License

[MIT License](LICENSE)
