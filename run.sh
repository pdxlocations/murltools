#!/bin/bash

# Murltools Flask Application Runner
# This script sets up the proper environment and runs the Flask app

# Activate virtual environment
source .venv/bin/activate

# macOS only: help pyzbar find Homebrew's zbar. Ignored elsewhere.
if [ -d /opt/homebrew/lib ]; then
    export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
fi

# Run the Flask application
echo "🚀 Starting Murltools Flask Application..."
echo "📡 Server will be available at: http://localhost:5001"
echo ""

python app.py