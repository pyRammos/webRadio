#!/bin/bash
# Manual database upgrade script for WebRadio Recorder
# This script directly modifies the SQLite database to add the required columns

# Default paths
DEFAULT_DB_PATH="/home/george/projects/docker_webradio/data/webradio.db"
CONTAINER_NAME=${1:-webradio}

# Check if the container is running and stop it if it is
if docker ps | grep -q $CONTAINER_NAME; then
    echo "Stopping container: $CONTAINER_NAME"
    docker stop $CONTAINER_NAME
    # Wait a moment for the container to stop
    sleep 2
fi

# Check if the database file exists
if [ -f "$DEFAULT_DB_PATH" ]; then
    DB_PATH="$DEFAULT_DB_PATH"
else
    echo "Database not found at default path, trying to locate it..."
    # Try to find the database path from Docker volume
    DATA_DIR=$(docker inspect $CONTAINER_NAME | grep -A 10 "Mounts" | grep "Source" | grep "data" | awk -F'"' '{print $4}')
    
    if [ -z "$DATA_DIR" ]; then
        echo "Error: Could not find data directory for container $CONTAINER_NAME"
        exit 1
    fi
    
    DB_PATH="$DATA_DIR/webradio.db"
fi

echo "Using database path: $DB_PATH"

if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database file not found at $DB_PATH"
    exit 1
fi

# Check file permissions and ownership
echo "Current file permissions:"
ls -la "$DB_PATH"

# Make a backup of the database
BACKUP_PATH="${DB_PATH}.bak"
echo "Creating backup at $BACKUP_PATH"
sudo cp "$DB_PATH" "$BACKUP_PATH"

# Make the database writable
echo "Making database writable"
sudo chmod 666 "$DB_PATH"

echo "Adding columns to recording table..."
sqlite3 "$DB_PATH" <<EOF
ALTER TABLE recording ADD COLUMN finish_time TIMESTAMP;
ALTER TABLE recording ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE recording ADD COLUMN partial_files TEXT;
UPDATE recording SET finish_time = datetime(start_time, '+' || duration || ' minutes') WHERE finish_time IS NULL;
EOF

if [ $? -eq 0 ]; then
    echo "Database schema updated successfully"
    
    # Create migrations tracking table if it doesn't exist
    echo "Creating migrations tracking table if needed..."
    sqlite3 "$DB_PATH" <<EOF
CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL
);
INSERT INTO migrations (name, applied_at) VALUES ('001_add_retry_fields', datetime('now'));
EOF
    
    # Start the container if it was running before
    if docker ps -a | grep -q $CONTAINER_NAME; then
        echo "Starting container: $CONTAINER_NAME"
        docker start $CONTAINER_NAME
        echo "Container started. The application should now be working correctly."
    fi
else
    echo "Error: Failed to update database schema"
    
    # Restore from backup if update failed
    echo "Restoring from backup"
    sudo cp "$BACKUP_PATH" "$DB_PATH"
    
    # Start the container anyway if it was running before
    if docker ps -a | grep -q $CONTAINER_NAME; then
        echo "Starting container anyway: $CONTAINER_NAME"
        docker start $CONTAINER_NAME
    fi
    exit 1
fi
