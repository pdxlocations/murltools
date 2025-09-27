#!/bin/bash

# Murltools Flask Application Runner
# This script sets up the proper environment and runs the Flask app

# Activate virtual environment
source .venv/bin/activate

# Set library path for zbar (needed by pyzbar)
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH

# Run the Flask application
echo "🚀 Starting Murltools Flask Application..."
echo "📡 Server will be available at: http://localhost:5002"
echo "🔧 Copy JSON button fix has been applied"
echo ""

python app.py