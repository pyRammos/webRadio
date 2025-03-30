#!/bin/bash

# WebRadio Recorder Docker Setup Script
# This script creates the necessary directory structure and files for running WebRadio Recorder in Docker

# Print colored messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== WebRadio Recorder Docker Setup ===${NC}"
echo -e "${YELLOW}This script will create the necessary directories and files for running WebRadio Recorder in Docker.${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
echo -e "${YELLOW}Setting up in directory: ${SCRIPT_DIR}${NC}"

# Create data directories
echo -e "${BLUE}Creating data directories...${NC}"
mkdir -p "${SCRIPT_DIR}/data/recordings"
mkdir -p "${SCRIPT_DIR}/data/images"
echo -e "${GREEN}✓ Created data directories${NC}"

# Create empty database file with proper permissions
echo -e "${BLUE}Creating empty database file...${NC}"
touch "${SCRIPT_DIR}/data/webradio.db"
chmod 666 "${SCRIPT_DIR}/data/webradio.db"
echo -e "${GREEN}✓ Created database file with proper permissions${NC}"

# Create .env file if it doesn't exist
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    echo -e "${BLUE}Creating .env file from example...${NC}"
    if [ -f "${SCRIPT_DIR}/.env.example" ]; then
        cp "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
        echo -e "${GREEN}✓ Created .env file from example${NC}"
        echo -e "${YELLOW}Please edit .env file with your specific configuration${NC}"
    else
        echo -e "${YELLOW}Warning: .env.example not found. Creating minimal .env file...${NC}"
        cat > "${SCRIPT_DIR}/.env" << EOF
# Flask configuration
SECRET_KEY=$(openssl rand -hex 16)
FLASK_APP=app.py
FLASK_ENV=production

# Database
DATABASE_URL=sqlite:////data/webradio.db

# Recording settings
RECORDINGS_DIR=/app/recordings
UPLOAD_FOLDER=/app/static/images
FFMPEG_PATH=/usr/bin/ffmpeg

# Allow registration (set to false after creating admin account)
ALLOW_REGISTRATION=true
EOF
        echo -e "${GREEN}✓ Created minimal .env file${NC}"
        echo -e "${YELLOW}Please edit .env file with your specific configuration${NC}"
    fi
else
    echo -e "${YELLOW}Note: .env file already exists, skipping creation${NC}"
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Warning: Docker is not installed or not in PATH${NC}"
    echo -e "${YELLOW}Please install Docker before continuing${NC}"
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    echo -e "${YELLOW}Warning: Docker Compose is not installed or not in PATH${NC}"
    echo -e "${YELLOW}Please install Docker Compose before continuing${NC}"
fi

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo -e "${BLUE}To start the application:${NC}"
echo -e "  docker compose up -d"
echo ""
echo -e "${BLUE}To view logs:${NC}"
echo -e "  docker compose logs -f"
echo ""
echo -e "${BLUE}Access the application at:${NC}"
echo -e "  http://localhost:5000"
echo ""
echo -e "${YELLOW}Default login is admin/admin - change this immediately after first login!${NC}"
echo ""
