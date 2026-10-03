#!/bin/bash
# Deployment script for Voice Journal
# Run this script to deploy to the laptop server

set -e

LAPTOP_IP="${LAPTOP_IP:-100.99.161.57}"
LAPTOP_USER="${LAPTOP_USER:-shreyansh}"
REMOTE_DIR="${REMOTE_DIR:-$HOME/voice_journal}"

echo "================================================"
echo "🎤 Voice Journal Deployment Script"
echo "================================================"
echo "Target: $LAPTOP_USER@$LAPTOP_IP:$REMOTE_DIR"
echo ""

# Check if we can SSH
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$LAPTOP_USER@$LAPTOP_IP" 'echo "Connected!"' 2>/dev/null; then
    echo "❌ Cannot SSH without password. Please set up SSH keys or run manually:"
    echo ""
    echo "  ssh $LAPTOP_USER@$LAPTOP_IP"
    echo "  cd $REMOTE_DIR"
    echo "  git pull"
    echo "  pip install -e ."
    echo "  python test_integration.py"
    echo "  python daemon.py"
    echo ""
    exit 1
fi

echo "✅ SSH connection successful"

# Deploy
echo ""
echo "Pulling latest code..."
ssh "$LAPTOP_USER@$LAPTOP_IP" << 'ENDSSH'
cd ~/voice_journal
git pull origin main
echo ""
echo "Installing dependencies..."
pip install -e .
echo ""
echo "Running tests..."
python test_integration.py
ENDSSH

echo ""
echo "================================================"
echo "✅ Deployment complete!"
echo "================================================"
echo ""
echo "To start the daemon, run:"
echo "  ssh $LAPTOP_USER@$LAPTOP_IP"
echo "  cd ~/voice_journal"
echo "  python daemon.py"
