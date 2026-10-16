#!/bin/bash
# Voice Journal Control Script
# Docker-compatible wrapper for starting/stopping the daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|mute|unmute|toggle|transcribe-date}"
    exit 1
}

load_env() {
    if [ -f "$ENV_FILE" ]; then
        export $(grep -v '^#' "$ENV_FILE" | xargs)
    fi
}

check_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}Warning: $ENV_FILE not found. Creating from example...${NC}"
        cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
        echo -e "${YELLOW}Please edit $ENV_FILE to configure your settings${NC}"
    fi
}

start_services() {
    load_env
    check_env_file
    
    echo -e "${GREEN}Starting Voice Journal services...${NC}"
    
    if [ -z "$DATA_ROOT" ]; then
        echo -e "${RED}ERROR: Set DATA_ROOT=/mnt/music-drive in $ENV_FILE${NC}"
        exit 1
    fi

    # Check if DATA_ROOT is mounted
    if ! mountpoint -q "$DATA_ROOT"; then
        echo -e "${RED}ERROR: DATA_ROOT ($DATA_ROOT) is not mounted. Please connect your external drive.${NC}"
        echo -e "${YELLOW}Will retry in 30 seconds...${NC}"
        sleep 30
        if ! mountpoint -q "$DATA_ROOT"; then
            echo -e "${RED}ERROR: DATA_ROOT still not mounted after retry.${NC}"
            exit 1
        fi
    fi
    
    # Check if DATA_ROOT is writable
    if [ ! -w "$DATA_ROOT" ]; then
        echo -e "${RED}ERROR: DATA_ROOT ($DATA_ROOT) is not writable.${NC}"
        exit 1
    fi
    
    # Start services
    docker-compose -f "$COMPOSE_FILE" up -d
    echo -e "${GREEN}Voice Journal services started${NC}"
}

stop_services() {
    echo -e "${YELLOW}Stopping Voice Journal services...${NC}"
    docker-compose -f "$COMPOSE_FILE" down
    echo -e "${GREEN}Voice Journal services stopped${NC}"
}

restart_services() {
    stop_services
    start_services
}

status_services() {
    echo -e "${GREEN}Voice Journal service status:${NC}"
    docker-compose -f "$COMPOSE_FILE" ps
    
    # Show mute status
    if [ -f "$SCRIPT_DIR/data/mute_flag" ]; then
        echo -e "${YELLOW}Status: MUTED${NC}"
    else
        echo -e "${GREEN}Status: RECORDING${NC}"
    fi
}

show_logs() {
    echo -e "${GREEN}Showing logs (press Ctrl+C to stop):${NC}"
    docker-compose -f "$COMPOSE_FILE" logs -f
}

mute_control() {
    load_env
    check_env_file
    echo -e "${GREEN}Toggling mute state...${NC}"
    docker-compose -f "$COMPOSE_FILE" exec daemon python -m voice_journal.utils.mute "$1"
}

transcribe_date() {
    load_env
    check_env_file
    if [ -z "$1" ]; then
        echo -e "${RED}Usage: $0 transcribe-date YYYY-MM-DD${NC}"
        exit 1
    fi
    echo -e "${GREEN}Starting transcription for date $1...${NC}"
    docker-compose -f "$COMPOSE_FILE" run --rm transcribe --date "$1"
}

# Main script logic
case "${1:-}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        status_services
        ;;
    logs)
        show_logs
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
    transcribe-date)
        transcribe_date "$2"
        ;;
    *)
        usage
        ;;
esac
