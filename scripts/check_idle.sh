#!/bin/bash
# Quick check script for voice-journal status

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "Error: venv not found. Run setup.sh first."
    exit 1
fi

source venv/bin/activate

python status.py "$@"
