#!/bin/bash
# WebRadio Recorder Database Upgrade Script
# This script runs database migrations for the WebRadio Recorder application

# Check if container name is provided
CONTAINER_NAME=${1:-webradio}

echo "Running database upgrade for container: $CONTAINER_NAME"

# Execute the Python upgrade script inside the container
docker exec -it $CONTAINER_NAME python /app/scripts/db_upgrade.py

# Check if the command was successful
if [ $? -eq 0 ]; then
    echo "Database upgrade completed successfully"
    echo "Restarting container to apply changes..."
    docker restart $CONTAINER_NAME
    echo "Container restarted. The application should now be working correctly."
else
    echo "Error: Database upgrade failed"
    exit 1
fi
