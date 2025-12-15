-- Create database if it doesn't exist
SELECT 'CREATE DATABASE courseapp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'courseapp')\gexec

-- Grant privileges to postgres user
GRANT ALL PRIVILEGES ON DATABASE courseapp TO postgres;