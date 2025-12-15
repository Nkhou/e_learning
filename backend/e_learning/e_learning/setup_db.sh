#!/bin/bash

# Database configuration
DB_NAME="e_learning_db"
DB_USER="e_learning_user"
DB_PASSWORD=$(openssl rand -hex 12)  # Generates random password
DB_OWNER="postgres"  # Admin user for setup

echo "🚀 Setting up PostgreSQL database..."

# Execute as postgres user
sudo -u postgres psql <<EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE $DB_NAME WITH OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
\c $DB_NAME
GRANT ALL ON SCHEMA public TO $DB_USER;
EOF

echo "✅ Database '$DB_NAME' created with user '$DB_USER'"