#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/battery_control.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

get_battery_percent() {
    local percent
    # Try upower first
    if command -v upower &> /dev/null; then
        percent=$(upower -i /org/freedesktop/UPower/devices/battery_BAT0 2>/dev/null | grep -E "percentage" | awk '{print $2}' | tr -d '%')
        if [ -n "$percent" ]; then
            echo "$percent"
            return
        fi
    fi
    # Try sysfs
    if [ -f /sys/class/power_supply/BAT0/capacity ]; then
        cat /sys/class/power_supply/BAT0/capacity
        return
    fi
    # If we can't get it, return empty
    echo ""
}

battery_percent=$(get_battery_percent)

if [ -z "$battery_percent" ]; then
    log "Could not determine battery percentage. Exiting."
    exit 1
fi

log "Battery percentage: $battery_percent%"

# Service name
SERVICE_NAME="vj.service"

# Check if service is active (user service)
is_active() {
    systemctl --user is-active --quiet "$SERVICE_NAME"
}

# Thresholds
LOW_THRESHOLD=20
HIGH_THRESHOLD=60

if [ "$battery_percent" -lt "$LOW_THRESHOLD" ]; then
    if is_active; then
        log "Battery below $LOW_THRESHOLD%. Stopping $SERVICE_NAME."
        systemctl --user stop "$SERVICE_NAME"
    else
        log "Battery below $LOW_THRESHOLD%. Service already inactive."
    fi
elif [ "$battery_percent" -gt "$HIGH_THRESHOLD" ]; then
    if ! is_active; then
        log "Battery above $HIGH_THRESHOLD%. Starting $SERVICE_NAME."
        systemctl --user start "$SERVICE_NAME"
    else
        log "Battery above $HIGH_THRESHOLD%. Service already active."
    fi
else
    log "Battery between $LOW_THRESHOLD% and $HIGH_THRESHOLD%. No action taken."
fi