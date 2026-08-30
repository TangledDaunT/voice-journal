#!/bin/bash
# Reset staging queue (clear backlog)
# WARNING: This deletes all pending segments

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "Error: venv not found."
    exit 1
fi

echo "WARNING: This will delete all staged segments!"
echo "Press Enter to continue, or Ctrl+C to cancel..."
read

source venv/bin/activate

STAGING_DIR="./audio_clips/staging"

if [ -d "$STAGING_DIR" ]; then
    echo "Clearing staging directory..."
    rm -rf "$STAGING_DIR"/*
    echo "Done."
else
    echo "Staging directory not found."
fi

echo ""
echo "Backlog status:"
python status.py
