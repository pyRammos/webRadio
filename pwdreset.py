#!/usr/bin/env python3
"""
Password reset script for WebRadio Recorder
This script resets the admin password or creates an admin user if it doesn't exist
"""

import os
import sys
from werkzeug.security import generate_password_hash
from flask import Flask
from models import db, User

# Import configuration
from config import Config

# Create a minimal Flask app for database access
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def reset_password(username='admin', new_password='admin'):
    """Reset password for a user or create the user if it doesn't exist"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        
        if user:
            # Update existing user
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            print(f"Password for user '{username}' has been reset.")
        else:
            # Create new user
            new_user = User(
                username=username,
                password_hash=generate_password_hash(new_password),
                default_local_storage_path='',
                default_nextcloud_storage_path=''
            )
            db.session.add(new_user)
            db.session.commit()
            print(f"User '{username}' has been created with the specified password.")
        
        return True

if __name__ == "__main__":
    if len(sys.argv) == 3:
        # If username and password are provided as arguments
        username = sys.argv[1]
        password = sys.argv[2]
        reset_password(username, password)
    elif len(sys.argv) == 2:
        # If only password is provided, assume admin user
        password = sys.argv[1]
        reset_password('admin', password)
    else:
        # No arguments, use default values
        print("Usage: python pwdreset.py [username] password")
        print("Resetting 'admin' password to 'admin'...")
        reset_password()
