#!/bin/bash
# Live TP/SL Monitor - Shows real-time TP triggers

echo "🎯 LIVE TP/SL TRIGGER MONITOR"
echo "======================================"
echo ""
echo "Monitoring: /tmp/live_bot.log"
echo "Press Ctrl+C to stop"
echo ""
echo "======================================"
echo ""

# Show existing trades first
echo "📊 EXISTING POSITIONS:"
grep "Position opened\|POSITION OPENED" /tmp/live_bot.log | tail -5 | while read line; do
    echo "  $line"
done
echo ""

echo "📋 EXISTING TP/SL ORDERS:"
grep "GESAMTER.*MODE\|TP/SL orders placed" /tmp/live_bot.log | tail -10 | while read line; do
    echo "  $line"
done
echo ""

echo "======================================"
echo "🔴 WATCHING FOR TP TRIGGERS..."
echo "======================================"
echo ""

# Watch for TP triggers in real-time
tail -f /tmp/live_bot.log | grep --line-buffered -E \
    "TP1 HIT|Trailing stop|Position.*closed|GESAMTER.*MODE|Position opened|P&L:" | \
    while read line; do
        timestamp=$(date '+%H:%M:%S')
        
        if [[ $line == *"TP1 HIT"* ]]; then
            echo "🎯 [$timestamp] TP1 TRIGGERED! $line"
        elif [[ $line == *"Trailing stop"* ]]; then
            echo "📈 [$timestamp] TRAILING: $line"
        elif [[ $line == *"Position.*closed"* ]] || [[ $line == *"closed"* ]]; then
            echo "✅ [$timestamp] CLOSED: $line"
        elif [[ $line == *"GESAMTER"* ]]; then
            echo "📋 [$timestamp] ORDER: $line"
        elif [[ $line == *"Position opened"* ]] || [[ $line == *"POSITION OPENED"* ]]; then
            echo "🚀 [$timestamp] NEW: $line"
        elif [[ $line == *"P&L"* ]]; then
            echo "💰 [$timestamp] PROFIT: $line"
        else
            echo "   [$timestamp] $line"
        fi
    done

