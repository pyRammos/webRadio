#!/usr/bin/env python3
"""
Database upgrade script for WebRadio Recorder

This script performs database schema upgrades for the WebRadio Recorder application.
It can be run manually or as part of an automated deployment process.

Usage:
    python db_upgrade.py

"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('db_upgrade')

# Database path from environment variable or default
DB_PATH = os.environ.get('DATABASE_PATH', '/data/webradio.db')

def get_db_connection():
    """Connect to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
        sys.exit(1)

def get_applied_migrations(conn):
    """Get list of already applied migrations."""
    try:
        # Check if migrations table exists
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='migrations'
        """)
        if not cursor.fetchone():
            # Create migrations table if it doesn't exist
            cursor.execute("""
                CREATE TABLE migrations (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP NOT NULL
                )
            """)
            conn.commit()
            logger.info("Created migrations tracking table")
            return []
        
        # Get applied migrations
        cursor.execute("SELECT name FROM migrations")
        return [row['name'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error getting applied migrations: {e}")
        conn.close()
        sys.exit(1)

def record_migration(conn, migration_name):
    """Record that a migration has been applied."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO migrations (name, applied_at) VALUES (?, ?)",
            (migration_name, datetime.now().isoformat())
        )
        conn.commit()
        logger.info(f"Recorded migration: {migration_name}")
    except sqlite3.Error as e:
        logger.error(f"Error recording migration: {e}")
        conn.close()
        sys.exit(1)

def check_column_exists(conn, table, column):
    """Check if a column exists in a table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row['name'] for row in cursor.fetchall()]
    return column in columns

def migration_001_add_retry_fields(conn):
    """Add retry-related fields to the recording table."""
    migration_name = "001_add_retry_fields"
    
    try:
        cursor = conn.cursor()
        
        # Check if columns already exist
        columns_to_add = []
        if not check_column_exists(conn, 'recording', 'finish_time'):
            columns_to_add.append("ADD COLUMN finish_time TIMESTAMP")
        
        if not check_column_exists(conn, 'recording', 'retry_count'):
            columns_to_add.append("ADD COLUMN retry_count INTEGER DEFAULT 0")
        
        if not check_column_exists(conn, 'recording', 'partial_files'):
            columns_to_add.append("ADD COLUMN partial_files TEXT")
        
        # Add columns if needed
        if columns_to_add:
            for column_sql in columns_to_add:
                cursor.execute(f"ALTER TABLE recording {column_sql}")
                logger.info(f"Added column: {column_sql}")
            
            # Update finish_time for existing recordings
            cursor.execute("""
                UPDATE recording 
                SET finish_time = datetime(start_time, '+' || duration || ' minutes')
                WHERE finish_time IS NULL
            """)
            logger.info("Updated finish_time for existing recordings")
            
            conn.commit()
            logger.info(f"Migration {migration_name} completed successfully")
        else:
            logger.info(f"Migration {migration_name} - all columns already exist")
        
        # Record the migration
        record_migration(conn, migration_name)
        
    except sqlite3.Error as e:
        logger.error(f"Error in migration {migration_name}: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)

def run_migrations():
    """Run all pending migrations."""
    conn = get_db_connection()
    applied_migrations = get_applied_migrations(conn)
    
    # List of all migrations
    migrations = [
        ("001_add_retry_fields", migration_001_add_retry_fields),
        # Add new migrations here
    ]
    
    # Run migrations that haven't been applied yet
    for name, func in migrations:
        if name not in applied_migrations:
            logger.info(f"Applying migration: {name}")
            func(conn)
        else:
            logger.info(f"Skipping already applied migration: {name}")
    
    conn.close()
    logger.info("Database upgrade completed successfully")

if __name__ == "__main__":
    logger.info(f"Starting database upgrade for {DB_PATH}")
    run_migrations()
