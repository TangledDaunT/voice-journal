#!/bin/bash
# Quick setup script for Voice Journal
set -e

echo "========================================="
echo "Voice Journal Setup"
echo "========================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
echo "Creating directories..."
mkdir -p config logs data models obsidian_vault/VoiceJournal/{Daily,Conversations}

# Download Silero VAD model
if [ ! -f "models/silero_vad.onnx" ]; then
    echo "Downloading Silero VAD model..."
    wget -O models/silero_vad.onnx \
        https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Ensure Ollama is installed and running:"
echo "     curl -fsSL https://ollama.ai/install.sh | sh"
echo "     ollama pull llama3.2:3b"
echo ""
echo "  2. Run calibration:"
echo "     source venv/bin/activate"
echo "     python calibrate.py"
echo ""
echo "  3. Start the daemon:"
echo "     ./vj-control.sh start"
echo ""
