FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/recordings /app/static/images /app/static/uploads

# Set environment variables
ENV FLASK_APP=app.py
ENV RECORDINGS_DIR=/app/recordings
ENV UPLOAD_FOLDER=/app/static/images
ENV PYTHONUNBUFFERED=1
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV SQLALCHEMY_SILENCE_UBER_WARNING=1
ENV FLASK_DEBUG=False

# Expose port
EXPOSE 5000

# Run the application with Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
