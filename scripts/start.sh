#!/usr/bin/env bash
# VoltimaxChat AI Service — Production Start Script
set -e

cd "$(dirname "$0")/.."

# Check required files
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in your values:"
    echo "  cp .env.example .env"
    exit 1
fi

if [ ! -f config.yaml ]; then
    echo "ERROR: config.yaml not found. Copy config.example.yaml and fill in your values:"
    echo "  cp config.example.yaml config.yaml"
    exit 1
fi

# Load environment
set -a; source .env; set +a

# Check Python
PYTHON="${PYTHON:-venv/bin/python}"
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python not found at $PYTHON"
    echo "Create a virtual environment: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Build dashboard if not built
if [ ! -d "dashboard-build" ] || [ ! -f "dashboard-build/index.html" ]; then
    echo "Building dashboard..."
    bash scripts/build-dashboard.sh
fi

# Start with production settings
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"

echo "Starting VoltimaxChat AI Service on $HOST:$PORT (workers=$WORKERS)..."
exec "$PYTHON" -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
