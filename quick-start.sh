#!/bin/bash

# Structured Intelligence - Quick Start Script
# Automated deployment for development and production

set -e

echo "🧠 Structured Intelligence - Quick Start"
echo "========================================"
echo ""

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi
echo "✅ Docker found"

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed or outdated."
    echo "   Please upgrade to Docker Compose v2"
    exit 1
fi
echo "✅ Docker Compose found"

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found locally"
    read -p "Do you want to install Ollama? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📥 Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        echo "✅ Ollama installed"
    else
        echo "⚠️  Skipping Ollama installation. You'll need it for local LLM inference."
    fi
else
    echo "✅ Ollama found"
fi

echo ""
echo "🎯 Setup Mode"
echo "============="
echo "1) Development (local, with hot reload)"
echo "2) Production (optimized, with Nginx)"
echo ""
read -p "Select mode (1 or 2): " MODE

if [ "$MODE" = "2" ]; then
    COMPOSE_PROFILE="production"
    echo "🚀 Production mode selected"
else
    COMPOSE_PROFILE=""
    echo "🔧 Development mode selected"
fi

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "📝 Creating .env file..."
    cp .env.template .env
    
    echo "⚠️  IMPORTANT: Please edit .env and set:"
    echo "   - Secure passwords (PGPASSWORD, REDIS_PASSWORD, JWT_SECRET)"
    echo "   - Admin credentials (ADMIN_EMAIL, ADMIN_PASSWORD)"
    echo "   - Ollama model (DEFAULT_MODEL)"
    echo ""
    read -p "Press Enter after editing .env file..."
else
    echo "✅ .env file exists"
fi

# Pull Ollama model if needed
if command -v ollama &> /dev/null; then
    echo ""
    echo "🤖 Ollama Model Setup"
    echo "===================="
    
    # Check available RAM
    TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
    
    echo "💾 Detected ${TOTAL_RAM}GB RAM"
    
    if [ "$TOTAL_RAM" -lt 16 ]; then
        RECOMMENDED_MODEL="llama3.2:3b-instruct-q4_K_M"
        echo "📱 Laptop-friendly model recommended: $RECOMMENDED_MODEL"
    elif [ "$TOTAL_RAM" -lt 32 ]; then
        RECOMMENDED_MODEL="gemma2:9b"
        echo "💻 Balanced model recommended: $RECOMMENDED_MODEL"
    else
        RECOMMENDED_MODEL="qwen2.5:14b"
        echo "🖥️  High-quality model recommended: $RECOMMENDED_MODEL"
    fi
    
    echo ""
    read -p "Pull $RECOMMENDED_MODEL? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📥 Pulling model (this may take a few minutes)..."
        ollama pull $RECOMMENDED_MODEL
        echo "✅ Model ready"
        
        # Update .env with model
        sed -i.bak "s/DEFAULT_MODEL=.*/DEFAULT_MODEL=$RECOMMENDED_MODEL/" .env
    fi
fi

# Build and start containers
echo ""
echo "🏗️  Building containers..."
if [ -n "$COMPOSE_PROFILE" ]; then
    docker compose --profile $COMPOSE_PROFILE build
else
    docker compose build
fi

echo ""
echo "🚀 Starting Structured Intelligence..."
if [ -n "$COMPOSE_PROFILE" ]; then
    docker compose --profile $COMPOSE_PROFILE up -d
else
    docker compose up -d
fi

# Wait for services to be healthy
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check health
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend is healthy"
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "   Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Backend health check timeout"
    echo "   Check logs with: docker compose logs backend"
    exit 1
fi

# Create initial admin user
echo ""
echo "👤 Creating admin user..."
docker exec -it si-backend python -c "
from app.core.init_db import create_admin_user
import asyncio
asyncio.run(create_admin_user())
" 2>/dev/null || echo "   (Admin user may already exist)"

echo ""
echo "═══════════════════════════════════════════════════"
echo "🎉 Structured Intelligence is ready!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "📱 Access the application:"
echo "   Frontend:  http://localhost:3000"
echo "   Backend:   http://localhost:8000"
echo "   API Docs:  http://localhost:8000/api/docs"
echo "   Qdrant UI: http://localhost:6333/dashboard"
echo ""
echo "🔐 Default login (from .env):"
source .env
echo "   Email:    $ADMIN_EMAIL"
echo "   Password: $ADMIN_PASSWORD"
echo ""
echo "⚠️  IMPORTANT: Change your password immediately!"
echo ""
echo "📊 View logs:"
echo "   All:      docker compose logs -f"
echo "   Backend:  docker compose logs -f backend"
echo "   Frontend: docker compose logs -f frontend"
echo ""
echo "🛑 Stop services:"
echo "   docker compose down"
echo ""
echo "🔄 Restart services:"
echo "   docker compose restart"
echo ""
echo "═══════════════════════════════════════════════════"
