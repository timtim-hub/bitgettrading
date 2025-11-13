#!/bin/bash
# Live Dashboard for 24/7 Bot Monitoring
# Shows real-time stats and recent activity

clear
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          🏦 INSTITUTIONAL BOT - LIVE DASHBOARD 📊             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Bot Status
if pgrep -f "launch_institutional_live" > /dev/null; then
    pid=$(pgrep -f "launch_institutional_live")
    uptime=$(ps -p $pid -o etime= 2>/dev/null || echo "unknown")
    echo "✅ Bot Status: RUNNING"
    echo "   PID: $pid"
    echo "   Uptime: $uptime"
else
    echo "❌ Bot Status: NOT RUNNING"
fi

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "📊 RECENT SCANS (Last 5)"
echo "─────────────────────────────────────────────────────────────────"
tail -200 /tmp/live_bot.log | grep "Scan complete" | tail -5 | while read line; do
    echo "  $line"
done

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "💰 TRADES (Last 5)"
echo "─────────────────────────────────────────────────────────────────"
trades=$(grep "✅ Position opened" /tmp/live_bot.log | tail -5)
if [ -z "$trades" ]; then
    echo "  No trades yet..."
else
    echo "$trades"
fi

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "🎯 TRAILING STOPS (Last 5)"
echo "─────────────────────────────────────────────────────────────────"
trailing=$(grep -E "🎯.*Trailing|placed trailing" /tmp/live_bot.log | tail -5)
if [ -z "$trailing" ]; then
    echo "  No trailing stops yet..."
else
    echo "$trailing"
fi

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "⚠️  RECENT ERRORS (Last 5 non-SSL)"
echo "─────────────────────────────────────────────────────────────────"
tail -500 /tmp/live_bot.log | grep -E "ERROR|CRITICAL" | grep -v "SSL" | tail -5 | while read line; do
    echo "  $line"
done

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "📈 STATISTICS"
echo "─────────────────────────────────────────────────────────────────"

total_scans=$(grep -c "Scan complete" /tmp/live_bot.log 2>/dev/null || echo 0)
successful_scans=$(grep -c "data_failed=0" /tmp/live_bot.log 2>/dev/null || echo 0)
total_trades=$(grep -c "Position opened" /tmp/live_bot.log 2>/dev/null || echo 0)
trailing_stops=$(grep -cE "placed trailing|Verified: Trailing stop" /tmp/live_bot.log 2>/dev/null || echo 0)

echo "  Total Scans: $total_scans"
echo "  Successful: $successful_scans"
echo "  Trades Opened: $total_trades"
echo "  Trailing Stops: $trailing_stops"

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "💾 LOG FILES"
echo "─────────────────────────────────────────────────────────────────"
if [ -f "/tmp/live_bot.log" ]; then
    log_size=$(du -h /tmp/live_bot.log | cut -f1)
    echo "  Main log: /tmp/live_bot.log ($log_size)"
fi
if [ -d "logs" ]; then
    echo "  24/7 logs: ./logs/"
fi
if [ -f "trades.jsonl" ]; then
    trade_count=$(wc -l < trades.jsonl 2>/dev/null || echo 0)
    echo "  Trade tracking: ./trades.jsonl ($trade_count trades)"
fi

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Commands:"
echo "  ./run_bot_24x7.sh status  - Check bot status"
echo "  ./run_bot_24x7.sh logs    - Tail live logs"
echo "  ./run_bot_24x7.sh restart - Restart bot"
echo "  ./check_trades.sh         - Detailed trade check"
echo "─────────────────────────────────────────────────────────────────"

