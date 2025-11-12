#!/bin/bash
# Quick script to view monitor output

echo "📊 Bot Monitor Status"
echo "===================="
echo ""
echo "🤖 Bot Process:"
ps aux | grep "[p]ython launch_institutional_live.py" && echo "✅ Running" || echo "❌ Not Running"
echo ""
echo "📈 Monitor Process:"
ps aux | grep "[p]ython monitor_bot_extended.py" && echo "✅ Running" || echo "❌ Not Running"
echo ""
echo "📋 Latest Monitor Output:"
echo "========================"
tail -50 /tmp/monitor.log
echo ""
echo "📊 Latest Bot Logs:"
echo "==================="
tail -30 /tmp/live_bot.log | grep -E "(POSITION|TP1|Trailing|SIGNAL|ERROR)" -i | tail -10

