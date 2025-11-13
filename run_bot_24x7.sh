#!/bin/bash
# 24/7 Bot Runner with Auto-Restart and Logging
# Location: /Users/macbookpro13/bitgettrading/run_bot_24x7.sh

BOT_DIR="/Users/macbookpro13/bitgettrading"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
LOG_DIR="$BOT_DIR/logs"
MAIN_LOG="$LOG_DIR/bot_24x7.log"
ERROR_LOG="$LOG_DIR/bot_errors.log"
PID_FILE="$BOT_DIR/bot.pid"

# Create logs directory
mkdir -p "$LOG_DIR"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MAIN_LOG"
}

# Function to rotate logs if they get too large (>100MB)
rotate_logs() {
    for logfile in "$MAIN_LOG" "$ERROR_LOG" "/tmp/live_bot.log"; do
        if [ -f "$logfile" ]; then
            size=$(stat -f%z "$logfile" 2>/dev/null || echo 0)
            if [ "$size" -gt 104857600 ]; then  # 100MB
                log "📦 Rotating log: $logfile (size: $size bytes)"
                mv "$logfile" "${logfile}.old"
                gzip "${logfile}.old" 2>/dev/null &
            fi
        fi
    done
}

# Function to clean Python cache
clean_cache() {
    log "🧹 Cleaning Python cache..."
    find "$BOT_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
    find "$BOT_DIR" -name "*.pyc" -delete 2>/dev/null
}

# Function to check if bot is running
is_bot_running() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Function to stop bot
stop_bot() {
    log "🛑 Stopping bot..."
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null
        sleep 2
        kill -9 "$pid" 2>/dev/null
        rm -f "$PID_FILE"
    fi
    pkill -9 -f "launch_institutional_live" 2>/dev/null
    log "✅ Bot stopped"
}

# Function to start bot
start_bot() {
    log "🚀 Starting bot..."
    
    # Clean cache before start
    clean_cache
    
    # Set environment variables
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1
    
    # Start bot in background
    cd "$BOT_DIR"
    nohup $PYTHON -B launch_institutional_live.py > /tmp/live_bot.log 2>&1 &
    bot_pid=$!
    
    echo "$bot_pid" > "$PID_FILE"
    log "✅ Bot started with PID: $bot_pid"
    
    # Wait a few seconds and verify it started
    sleep 5
    if is_bot_running; then
        log "✅ Bot verified running"
    else
        log "❌ Bot failed to start!"
        return 1
    fi
}

# Function to monitor and restart if needed
monitor_loop() {
    log "👁️  Starting 24/7 monitoring loop..."
    log "   Logs: $MAIN_LOG"
    log "   Errors: $ERROR_LOG"
    log "   Bot output: /tmp/live_bot.log"
    
    restart_count=0
    last_restart=$(date +%s)
    
    while true; do
        # Rotate logs if needed
        rotate_logs
        
        # Check if bot is running
        if ! is_bot_running; then
            current_time=$(date +%s)
            time_since_last=$(( current_time - last_restart ))
            
            log "❌ Bot not running! (restart count: $restart_count)"
            
            # If restarting too frequently (< 60 seconds), wait longer
            if [ "$time_since_last" -lt 60 ]; then
                log "⚠️  Too many restarts! Waiting 5 minutes..."
                sleep 300
            fi
            
            # Stop any zombie processes
            stop_bot
            sleep 2
            
            # Start bot
            if start_bot; then
                restart_count=$((restart_count + 1))
                last_restart=$(date +%s)
                log "✅ Bot restarted successfully (restart #$restart_count)"
            else
                log "❌ Failed to restart bot! Waiting 2 minutes..."
                sleep 120
            fi
        fi
        
        # Check for errors in bot log
        if [ -f "/tmp/live_bot.log" ]; then
            # Extract recent errors
            tail -100 /tmp/live_bot.log | grep -E "ERROR|CRITICAL|Exception|Traceback" >> "$ERROR_LOG" 2>/dev/null
        fi
        
        # Log status every 10 minutes
        current_minute=$(date +%M)
        if [ "$((10#$current_minute % 10))" -eq 0 ]; then
            if is_bot_running; then
                pid=$(cat "$PID_FILE")
                uptime_seconds=$(ps -p "$pid" -o etime= | tr '-' ':' | awk -F: '{if (NF==4) print ($1*86400)+($2*3600)+($3*60)+$4; else if (NF==3) print ($1*3600)+($2*60)+$3; else print ($1*60)+$2}')
                log "💚 Bot running | PID: $pid | Uptime: ${uptime_seconds}s | Restarts: $restart_count"
                
                # Show recent scan results
                recent_scans=$(tail -20 /tmp/live_bot.log | grep "Scan complete" | tail -1)
                if [ -n "$recent_scans" ]; then
                    log "   $recent_scans"
                fi
            fi
        fi
        
        # Sleep for 30 seconds before next check
        sleep 30
    done
}

# Handle signals
trap 'log "🛑 Received SIGTERM, stopping..."; stop_bot; exit 0' SIGTERM SIGINT

# Main execution
case "${1:-start}" in
    start)
        log "============================================"
        log "🏦 INSTITUTIONAL BOT - 24/7 MODE"
        log "============================================"
        
        # Stop any existing instances
        stop_bot
        sleep 2
        
        # Start fresh
        start_bot
        
        # Enter monitoring loop
        monitor_loop
        ;;
    
    stop)
        stop_bot
        ;;
    
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    
    status)
        if is_bot_running; then
            pid=$(cat "$PID_FILE")
            echo "✅ Bot is RUNNING (PID: $pid)"
            echo ""
            echo "Recent activity:"
            tail -10 /tmp/live_bot.log | grep "Scan complete"
        else
            echo "❌ Bot is NOT running"
        fi
        ;;
    
    logs)
        tail -f /tmp/live_bot.log
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac

