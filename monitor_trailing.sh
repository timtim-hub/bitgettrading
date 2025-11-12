#!/bin/bash
# Quick monitoring script for trailing stop activity

echo "🔍 TRAILING STOP MONITOR"
echo "========================"
echo ""

# Check bot status
if pgrep -f "python launch_institutional_live.py" > /dev/null; then
    echo "✅ Bot: RUNNING"
else
    echo "❌ Bot: NOT RUNNING"
fi

echo ""
echo "📊 Recent TP1 Hits & Trailing Stop Activity:"
echo "---------------------------------------------"
tail -200 /tmp/live_bot.log | grep -E "(TP1 HIT|Trailing stop|place_trailing|NORMAL TRAILING|track_plan)" -i | tail -15

echo ""
echo "📈 Current Positions:"
echo "---------------------"
tail -100 /tmp/live_bot.log | grep -E "📊.*SHORT|📊.*LONG" | tail -10

echo ""
echo "⚠️ Recent Errors:"
echo "-----------------"
tail -200 /tmp/live_bot.log | grep -E "(ERROR|FAILED|❌)" -i | tail -10

echo ""
echo "🔄 Monitor Status:"
if pgrep -f "python monitor_bot_extended.py" > /dev/null; then
    echo "✅ Extended Monitor: RUNNING"
else
    echo "❌ Extended Monitor: NOT RUNNING"
fi

echo ""
echo "📋 Quick Commands:"
echo "  tail -f /tmp/live_bot.log | grep -E '(TP1|Trailing)' -i"
echo "  ./view_monitor.sh"
echo "  tail -f /tmp/monitor.log"

