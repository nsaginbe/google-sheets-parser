#!/bin/bash

# Quick deployment script for Digital Ocean Droplet
# Usage: ./deploy.sh

set -e

echo "🚀 Starting deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from env.example..."
    if [ -f env.example ]; then
        cp env.example .env
        echo "✅ Created .env file from env.example"
        echo "⚠️  Please edit .env file with your configuration before continuing."
        exit 1
    else
        echo "❌ env.example file not found. Please create .env file manually."
        exit 1
    fi
fi

# Check if key.json exists (if GOOGLE_CREDENTIALS_PATH points to it)
if grep -q "GOOGLE_CREDENTIALS_PATH=./key.json" .env && [ ! -f key.json ]; then
    echo "⚠️  key.json file not found. Please ensure your Google credentials file is present."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker compose down || true

# Build and start containers
echo "🔨 Building and starting containers..."
docker compose up -d --build

# Wait for service to be healthy
echo "⏳ Waiting for service to start..."
sleep 5

# Check health
echo "🏥 Checking service health..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Service is healthy and running!"
    echo ""
    echo "🌐 API is available at: http://localhost:8000"
    echo "📚 API docs: http://localhost:8000/docs"
    echo ""
    echo "To view logs: docker compose logs -f"
    echo "To stop: docker compose down"
else
    echo "⚠️  Service might not be ready yet. Check logs with: docker compose logs -f"
    exit 1
fi

