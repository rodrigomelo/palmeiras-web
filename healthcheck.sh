#!/bin/bash
# Palmeiras Dashboard Health Check & Auto-Restart
# Run via cron: */5 * * * * /Users/rodrigomelo/.openclaw/workspace/projects/palmeiras-web/healthcheck.sh

PROJECT_DIR="/Users/rodrigomelo/.openclaw/workspace/projects/palmeiras-web"
PORT=5001
LOG_FILE="$PROJECT_DIR/dashboard.log"
ERROR_LOG="$PROJECT_DIR/dashboard.err"

# Check if port is listening
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "$(date): ✓ Dashboard is running on port $PORT"
    exit 0
else
    echo "$(date): ✗ Dashboard is DOWN on port $PORT, restarting..."
    
    # Kill any stale processes
    pkill -f "server.py" 2>/dev/null
    
    # Small delay to ensure clean start
    sleep 1
    
    # Start the dashboard in background
    cd "$PROJECT_DIR"
    "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/server.py" >> "$LOG_FILE" 2>> "$ERROR_LOG" &
    
    # Wait for startup
    sleep 3
    
    # Verify it started
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo "$(date): ✓ Dashboard restarted successfully"
    else
        echo "$(date): ✗ FAILED to restart dashboard" >> "$ERROR_LOG"
        exit 1
    fi
fi
