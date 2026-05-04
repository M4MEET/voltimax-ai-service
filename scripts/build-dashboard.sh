#!/usr/bin/env bash
# Build the React analytics dashboard
set -e

cd "$(dirname "$0")/.."

if [ ! -d "dashboard-react" ]; then
    echo "ERROR: dashboard-react directory not found"
    exit 1
fi

cd dashboard-react

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dashboard dependencies..."
    npm install
fi

echo "Building dashboard..."
npm run build

echo "Dashboard built successfully → ../dashboard-build/"
