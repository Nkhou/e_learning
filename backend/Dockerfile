FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV DJANGO_SETTINGS_MODULE=e_learning.settings

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Ensure migration directories exist
RUN mkdir -p /app/e_learning/users/migrations && \
    mkdir -p /app/e_learning/cours/migrations && \
    touch /app/e_learning/users/migrations/__init__.py && \
    touch /app/e_learning/cours/migrations/__init__.py

# Set working directory to Django project
WORKDIR /app/e_learning

# Create logs directory
RUN mkdir -p /app/e_learning/logs

# Create non-root user and set permissions
RUN useradd -m appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Use entrypoint script if available, otherwise inline commands
CMD if [ -f "/app/docker-entrypoint.sh" ]; then \
        /app/docker-entrypoint.sh python manage.py runserver 0.0.0.0:8000; \
    else \
        python manage.py makemigrations users --noinput && \
        python manage.py makemigrations cours --noinput && \
        python manage.py makemigrations --noinput && \
        python manage.py migrate --noinput && \
        (python create_superuser.py || true) && \
        python manage.py runserver 0.0.0.0:8000; \
    fi