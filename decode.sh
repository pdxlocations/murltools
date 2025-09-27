#!/bin/bash

# Murltools Command Line Decoder
# This script sets up the proper environment and runs the decode.py script

# Activate virtual environment
source .venv/bin/activate

# Set library path for zbar (needed by pyzbar)
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH

# Run the decode script with all provided arguments
python decode.py "$@"