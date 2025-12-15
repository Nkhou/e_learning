# frontend/Dockerfile.dev
FROM node:18-bullseye

WORKDIR /app

# Copy package files from the my-app subdirectory
COPY my-app/package*.json ./

# Install all dependencies (including dev dependencies for development)
RUN npm install

# Copy source code from my-app subdirectory
COPY my-app/ .

# Expose port
EXPOSE 3000

# Start development server with host 0.0.0.0 for Docker
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]