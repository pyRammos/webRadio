# WebRadio Recorder .gitignore Explanation

This document explains the rationale behind each entry in the `.gitignore` file for the WebRadio Recorder application.

## Files and Directories to Include in Git

1. **Python Source Code**
   - `app.py` - Main application file containing routes and application logic
   - `models.py` - Database models and schema definitions
   - `forms.py` - Form definitions for user input
   - `config.py` - Configuration settings (without sensitive information)
   - `utils/` - Utility modules for recording, notifications, and storage

2. **Templates and Static Assets**
   - `templates/` - HTML templates for the web interface
   - `static/css/` - CSS stylesheets
   - `static/js/` - JavaScript files
   - `static/img/` - Static images for the interface (not user uploads)

3. **Documentation**
   - `README.md` - Project overview and setup instructions
   - `AmazonQ.md` - Documentation of improvements
   - `LICENSE` - License information
   - `requirements.txt` - Python package dependencies

4. **Configuration Examples**
   - `.env.example` - Example environment variables (without actual secrets)

## Files and Directories Excluded from Git

1. **Python Bytecode Files** (`__pycache__/`, `*.py[cod]`, `*$py.class`, `*.so`, `.Python`)
   - Reason: These are compiled Python files that are generated at runtime and specific to the environment. They should be regenerated on each system.

2. **Virtual Environment** (`venv/`, `ENV/`, `env/`)
   - Reason: Virtual environments contain installed packages specific to the local setup and can be large. Users should create their own virtual environments based on requirements.txt.

3. **Flask Instance Directory** (`instance/`, `.webassets-cache`)
   - Reason: Contains instance-specific configuration that might include secrets or local paths.

4. **Database Files** (`*.db`, `*.sqlite`)
   - Reason: Database files contain user data and application state that should not be shared in version control. Each installation should start with a fresh database.

5. **Log Files** (`*.log`, `logs/`)
   - Reason: Log files contain runtime information specific to each installation and can grow large.

6. **Media Files** (`recordings/`, `static/uploads/`, `static/images/`)
   - Reason: These directories contain user-generated content like recorded audio files and uploaded podcast images that should not be in version control.

7. **Environment Variables** (`.env`)
   - Reason: Contains sensitive information like API keys, passwords, and local configuration that should be kept private.

8. **IDE Files** (`.idea/`, `.vscode/`, `*.swp`, `*.swo`)
   - Reason: IDE-specific files that are not relevant to the application and vary between developers.

9. **OS Specific Files** (`.DS_Store`, `Thumbs.db`)
   - Reason: Operating system generated files that are not part of the application.

10. **Example Files** (`example.rss`)
    - Reason: Example files used for testing or demonstration that are not needed for the application to function.

## Best Practices

- Keep sensitive information like API keys, passwords, and secret keys in the `.env` file, which is excluded from version control
- Provide an `.env.example` file with placeholder values to guide setup
- Initialize the database schema through code rather than committing database files
- Document any required directory structures that need to be created during setup
