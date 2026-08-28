#!/bin/bash
# Voice Journal Control Script
# Simple wrapper for starting/stopping the daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
DAEMON_SCRIPT="$SCRIPT_DIR/voice_journal/daemon.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 {start|stop|restart|status|mute|unmute|toggle|logs}"
    exit 1
}

check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${RED}Error: Virtual environment not found at $VENV_DIR${NC}"
        echo "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

check_service() {
    if command -v systemctl &> /dev/null; then
        if systemctl --user is-active --quiet voice-journal.service 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start_daemon() {
    echo -e "${GREEN}Starting Voice Journal...${NC}"

    # Check if using systemd
    if command -v systemctl &> /dev/null && [ -f ~/.config/systemd/user/voice-journal.service ]; then
        systemctl --user start voice-journal.service
        echo -e "${GREEN}Started via systemd${NC}"
    else
        # Direct start
        check_venv
        cd "$SCRIPT_DIR"
        source "$VENV_DIR/bin/activate"
        nohup python -m voice_journal.daemon > logs/daemon.log 2>&1 &
        echo $! > data/daemon.pid
        echo -e "${GREEN}Started daemon (PID: $(cat data/daemon.pid))${NC}"
    fi
}

stop_daemon() {
    echo -e "${YELLOW}Stopping Voice Journal...${NC}"

    if command -v systemctl &> /dev/null && [ -f ~/.config/systemd/user/voice-journal.service ]; then
        systemctl --user stop voice-journal.service
        echo -e "${GREEN}Stopped via systemd${NC}"
    else
        if [ -f data/daemon.pid ]; then
            PID=$(cat data/daemon.pid)
            kill $PID 2>/dev/null || true
            rm -f data/daemon.pid
            echo -e "${GREEN}Stopped daemon${NC}"
        else
            echo -e "${YELLOW}No PID file found${NC}"
        fi
    fi
}

status_daemon() {
    if command -v systemctl &> /dev/null && [ -f ~/.config/systemd/user/voice-journal.service ]; then
        systemctl --user status voice-journal.service
    else
        if [ -f data/daemon.pid ]; then
            PID=$(cat data/daemon.pid)
            if ps -p $PID > /dev/null 2>&1; then
                echo -e "${GREEN}Voice Journal is running (PID: $PID)${NC}"
            else
                echo -e "${RED}Voice Journal is not running (stale PID file)${NC}"
            fi
        else
            echo -e "${YELLOW}Voice Journal is not running${NC}"
        fi
    fi

    # Show mute status
    if [ -f data/mute_flag ]; then
        echo -e "${YELLOW}Status: MUTED${NC}"
    else
        echo -e "${GREEN}Status: RECORDING${NC}"
    fi
}

mute_control() {
    check_venv
    cd "$SCRIPT_DIR"
    source "$VENV_DIR/bin/activate"
    python -m voice_journal.utils.mute "$1"
}

show_logs() {
    if [ -f logs/voice_journal.log ]; then
        tail -f logs/voice_journal.log
    else
        echo -e "${YELLOW}No log file found${NC}"
    fi
}

case "${1:-}" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        stop_daemon
        sleep 2
        start_daemon
        ;;
    status)
        status_daemon
        ;;
    mute)
        mute_control mute
        ;;
    unmute)
        mute_control unmute
        ;;
    toggle)
        mute_control toggle
        ;;
    logs)
        show_logs
        ;;
    *)
        usage
        ;;
esac
