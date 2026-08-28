#!/bin/bash
# Complete deployment script for Voice Journal
# Run on the laptop server

set -e

echo "========================================"
echo "Voice Journal - Full Deployment"
echo "========================================"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Project directory
PROJECT_DIR="$HOME/voice_journal"
VENV_DIR="$PROJECT_DIR/venv"

echo ""
echo "Step 1: Checking project directory..."
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${GREEN}✓${NC} Project directory exists: $PROJECT_DIR"
else
    echo -e "${RED}✗${NC} Project not found. Cloning..."
    cd $HOME
    git clone https://github.com/TangledDaunT/voice-journal.git voice_journal
    cd voice_journal
fi

cd $PROJECT_DIR

echo ""
echo "Step 2: Pulling latest code..."
git fetch origin main
git reset --hard origin/main
echo -e "${GREEN}✓${NC} Code updated"

echo ""
echo "Step 3: Creating virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}✓${NC} Virtual environment exists"
else
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
fi

echo ""
echo "Step 4: Activating virtual environment..."
source $VENV_DIR/bin/activate

echo ""
echo "Step 5: Installing dependencies..."
pip install --upgrade pip
pip install -e .

echo -e "${GREEN}✓${NC} Dependencies installed"

echo ""
echo "Step 6: Running integration tests..."
python test_integration.py
TEST_RESULT=$?

if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All tests passed"
else
    echo -e "${RED}✗${NC} Tests failed!"
    exit 1
fi

echo ""
echo "Step 7: Checking Ollama..."
if command -v ollama &> /dev/null; then
    if ollama list | grep -q "llama3.2:3b"; then
        echo -e "${GREEN}✓${NC} Ollama and model ready"
    else
        echo "Pulling llama3.2:3b model..."
        ollama pull llama3.2:3b
        echo -e "${GREEN}✓${NC} Model downloaded"
    fi
else
    echo -e "${RED}✗${NC} Ollama not found!"
    echo "Please install Ollama: curl -fsSL https://ollama.ai/install.sh | sh"
    exit 1
fi

echo ""
echo "Step 8: Creating directories..."
mkdir -p logs
mkdir -p data
mkdir -p obsidian_vault/VoiceJournal/{Daily,Conversations}
mkdir -p config
mkdir -p models

echo -e "${GREEN}✓${NC} Directories created"

echo ""
echo "Step 9: Stopping old daemon..."
pkill -f "python.*daemon.py" 2>/dev/null || true
sleep 2
echo -e "${GREEN}✓${NC} Old daemon stopped"

echo ""
echo "Step 10: Starting daemon..."
nohup python daemon.py > logs/daemon.log 2>&1 &
DAEMON_PID=$!
sleep 3

if ps -p $DAEMON_PID > /dev/null; then
    echo -e "${GREEN}✓${NC} Daemon started (PID: $DAEMON_PID)"
else
    echo -e "${RED}✗${NC} Daemon failed to start"
    cat logs/daemon.log
    exit 1
fi

echo ""
echo "Step 11: Checking logs..."
sleep 2
tail -n 20 logs/voice_journal.log 2>/dev/null || echo "Waiting for logs..."

echo ""
echo "========================================"
echo -e "${GREEN}DEPLOYMENT COMPLETE!${NC}"
echo "========================================"
echo ""
echo "Status:"
echo "  • Daemon running: PID $DAEMON_PID"
echo "  • View logs: tail -f $PROJECT_DIR/logs/voice_journal.log"
echo "  • Stop daemon: pkill -f 'python.*daemon.py'"
echo "  • Mute: python -m utils.mute toggle"
echo ""

# List audio devices
echo "Available audio devices:"
python -c "import sounddevice as sd; print(sd.query_devices())" 2>/dev/null || echo "  (Audio device check requires sounddevice)"

echo ""
echo "Done! 🎉"
