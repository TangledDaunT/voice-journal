#!/bin/bash
# Manual batch processing script for voice-journal

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "Error: venv not found. Run setup.sh first."
    exit 1
fi

source venv/bin/activate

echo "Running batch processor..."
echo "Backlog status before:"
python status.py

echo ""
echo "Processing..."
python -m processing.batch_processor "$@"

echo ""
echo "Backlog status after:"
python status.py
