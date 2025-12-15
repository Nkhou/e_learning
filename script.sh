#!/bin/bash

# Complete fix for "Dependency on app with no migrations: users" error
# Run this on your HOST machine

echo "=========================================="
echo "Fixing Migration Dependency Error"
echo "=========================================="

# Step 1: Stop containers and clean everything
echo -e "\n[1/7] Stopping containers and cleaning up..."
docker compose down -v  # -v removes volumes too

# Step 2: Clean up any orphaned volumes
echo -e "\n[2/7] Removing orphaned volumes..."
docker volume prune -f

# Step 3: Verify local migration structure
echo -e "\n[3/7] Checking local migration directories..."

# Ensure migrations directories exist locally
mkdir -p users/migrations
mkdir -p cours/migrations

# Create __init__.py files if they don't exist
touch users/migrations/__init__.py
touch cours/migrations/__init__.py

# Remove any old migration files locally first
echo "Cleaning local migration files..."
find users/migrations/ -name "*.py" ! -name "__init__.py" -delete
find cours/migrations/ -name "*.py" ! -name "__init__.py" -delete
find users/migrations/ -name "*.pyc" -delete
find cours/migrations/ -name "*.pyc" -delete

echo "✓ Local migrations cleaned"

# Step 4: Rebuild containers to ensure fresh copy
echo -e "\n[4/7] Rebuilding containers..."
docker compose build --no-cache backend

# Step 5: Start containers
echo -e "\n[5/7] Starting containers..."
docker compose up -d

# Wait for services to be ready
echo "Waiting for services to initialize..."
sleep 10

# Step 6: Create migrations inside container
echo -e "\n[6/7] Creating migrations inside container..."

docker compose exec backend bash -c '
set -e

echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"

# Navigate to project directory
cd /app/e_learning

# Check structure
echo -e "\n→ Checking directory structure..."
ls -la
echo -e "\n→ Checking users app..."
ls -la users/
echo -e "\n→ Checking migrations folder..."
ls -la users/migrations/ || echo "migrations folder missing!"

# Ensure migrations directories exist
mkdir -p users/migrations
mkdir -p cours/migrations
touch users/migrations/__init__.py
touch cours/migrations/__init__.py

# Remove database
echo -e "\n→ Removing old database..."
rm -f db.sqlite3

# Clean any existing migrations
echo -e "\n→ Cleaning existing migrations..."
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete 2>/dev/null || true
find . -path "*/migrations/*.pyc" -delete 2>/dev/null || true

# Create migrations - CRITICAL ORDER
echo -e "\n→ Creating migrations for users app (FIRST)..."
python manage.py makemigrations users --verbosity 2

if [ $? -ne 0 ]; then
    echo "✗ Failed to create users migrations!"
    echo "Showing users/models.py..."
    cat users/models.py
    exit 1
fi

echo -e "\n→ Creating migrations for cours app..."
python manage.py makemigrations cours --verbosity 2 || echo "No cours migrations needed"

echo -e "\n→ Creating any other migrations..."
python manage.py makemigrations --verbosity 2 || echo "No other migrations needed"

# Show what was created
echo -e "\n→ Migrations created:"
find . -path "*/migrations/*.py" -not -name "__init__.py" -ls

# Apply migrations
echo -e "\n→ Applying migrations..."
python manage.py migrate --verbosity 2

if [ $? -ne 0 ]; then
    echo "✗ Migration failed!"
    exit 1
fi

# Create superuser
echo -e "\n→ Creating superuser..."
python << EOFPYTHON
from django.contrib.auth import get_user_model
import os

User = get_user_model()

username = "admin"
email = "admin@example.com"
password = "admin123"

try:
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            privilege="A",
            accept_conditions=True
        )
        print(f"✓ Superuser created: {username}")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
    else:
        print(f"✓ Superuser already exists: {username}")
except Exception as e:
    print(f"✗ Error creating superuser: {e}")
    import traceback
    traceback.print_exc()
EOFPYTHON

echo -e "\n✓ All setup steps completed successfully!"
'

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "\n✗ Setup failed. Showing logs..."
    docker compose logs --tail=100 backend
    exit 1
fi

# Step 7: Restart to ensure clean state
echo -e "\n[7/7] Restarting backend..."
docker compose restart backend

sleep 3

echo -e "\n=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Credentials:"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "Check status:"
docker compose ps
echo ""
echo "View logs:"
echo "  docker compose logs -f backend"
echo ""