#!/bin/bash
# EMERGENCY FIX - Restart daemon and check logs
# Run this if the daemon isn't logging conversations

echo "========================================"
echo "EMERGENCY FIX - Restarting Daemon"
echo "========================================"

# 1. Check current status
echo "1. Checking current processes..."
ps aux | grep daemon | grep -v grep

# 2. Kill all daemon processes
echo ""
echo "2. Stopping all daemon processes..."
pkill -9 -f "python.*daemon" 2>/dev/null || true
pkill -9 -f "python.*voice" 2>/dev/null || true
sleep 2

# 3. Pull latest code
echo ""
echo "3. Pulling latest code..."
cd ~/voice_journal_src
git fetch origin main
git reset --hard origin/main
echo "Code updated: $(git log -1 --oneline)"

# 4. Reinstall
echo ""
echo "4. Reinstalling package..."
source venv/bin/activate
pip install -e . --force-reinstall

# 5. Remove mute flag if exists
echo ""
echo "5. Removing mute flag..."
rm -f data/mute_flag 2>/dev/null || true

# 6. Create necessary directories
echo ""
echo "6. Creating directories..."
mkdir -p logs data obsidian_vault/VoiceJournal/{Daily,Conversations} config models

# 7. Run integration tests
echo ""
echo "7. Running integration tests..."
python test_integration.py
if [ $? -ne 0 ]; then
    echo "❌ Tests failed! Check errors above."
    exit 1
fi

# 8. Start daemon fresh
echo ""
echo "8. Starting daemon..."
nohup python daemon.py > logs/daemon.log 2>&1 &
DAEMON_PID=$!
echo "Daemon PID: $DAEMON_PID"

# 9. Wait and check
echo ""
echo "9. Waiting for daemon to initialize..."
sleep 5

# Check if process is running
if ps -p $DAEMON_PID > /dev/null 2>&1; then
    echo "✅ Daemon is running (PID: $DAEMON_PID)"
else
    echo "❌ Daemon crashed! Check logs:"
    tail -50 logs/daemon.log
    exit 1
fi

# 10. Show logs
echo ""
echo "10. Last 30 lines of voice_journal.log:"
echo "========================================"
tail -30 logs/voice_journal.log 2>/dev/null || echo "No logs yet, waiting..."
sleep 2
tail -30 logs/voice_journal.log

echo ""
echo "11. Checking daemon.log for errors..."
echo "========================================"
tail -30 logs/daemon.log 2>/dev/null || echo "No daemon.log"

echo ""
echo "========================================"
echo "✅ RESTART COMPLETE"
echo "========================================"
echo ""
echo "Monitoring logs for 10 seconds..."
echo "(Speak into your microphone now!)"
echo ""
timeout 10 tail -f logs/voice_journal.log 2>/dev/null || tail -20 logs/voice_journal.log

echo ""
echo "To keep watching logs:"
echo "  tail -f ~/voice_journal_src/logs/voice_journal.log"
