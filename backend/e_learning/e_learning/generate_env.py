#!/usr/bin/env python3
import secrets
import os

# Generate secure random keys
SECRET_KEY = secrets.token_hex(50)
DB_PASSWORD = os.popen("openssl rand -hex 12").read().strip()

env_content = f"""# Django Settings
SECRET_KEY={SECRET_KEY}
DEBUG=True

# Database Settings
DB_ENGINE=django.db.backends.postgresql
DB_NAME=e_learning_db
DB_USER=e_learning_user
DB_PASSWORD={DB_PASSWORD}
DB_HOST=localhost
DB_PORT=5432

# Email Settings (Example)
EMAIL_HOST=your_smtp.com
EMAIL_PORT=587
EMAIL_USER=your_email@example.com
EMAIL_PASSWORD=your_email_password
"""

with open('.env', 'w') as f:
    f.write(env_content)

print("✅ .env file generated successfully!")