#!/bin/bash
# Update existing deployment on laptop server
# The project is at ~/voice_journal_src (NOT ~/voice_journal)

set -e

PROJECT_DIR="$HOME/voice_journal_src"

echo "========================================"
echo "Updating Voice Journal Deployment"
echo "Project dir: $PROJECT_DIR"
echo "========================================"

cd $PROJECT_DIR

# Pull latest code
echo ""
echo "Pulling latest code..."
git stash
git pull origin main || git fetch origin main && git reset --hard origin/main

# Activate venv
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Reinstall
echo ""
echo "Reinstalling package..."
pip install -e .

# Run tests
echo ""
echo "Running tests..."
python test_integration.py

# Restart daemon
echo ""
echo "Restarting daemon..."
pkill -f "python.*daemon.py" 2>/dev/null || true
sleep 2
nohup python daemon.py > logs/daemon.log 2>&1 &
DAEMON_PID=$!

sleep 3
if ps -p $DAEMON_PID > /dev/null; then
    echo "✓ Daemon restarted (PID: $DAEMON_PID)"
else
    echo "✗ Daemon failed to start"
    cat logs/daemon.log
    exit 1
fi

echo ""
echo "Last 20 log lines:"
tail -n 20 logs/voice_journal.log

echo ""
echo "========================================"
echo "✅ UPDATE COMPLETE"
echo "========================================"
