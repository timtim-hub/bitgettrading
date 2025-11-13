#!/bin/bash
# Continuous monitoring script for leverage-aware bot

echo "🔍 LEVERAGE-AWARE BOT MONITOR"
echo "=============================="
echo ""

while true; do
    clear
    echo "🤖 Bot Status: $(./run_bot_24x7.sh status 2>&1 | grep -o 'RUNNING\|STOPPED')"
    echo "⏰ Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    echo "📊 LEVERAGE CALCULATIONS (Last 10):"
    echo "-----------------------------------"
    tail -1000 /tmp/live_bot.log | grep "Leverage-adjusted" | tail -10
    echo ""
    
    echo "🎯 SIGNAL CANDIDATES (Last 5):"
    echo "------------------------------"
    tail -1000 /tmp/live_bot.log | grep "SIGNAL CANDIDATE" | tail -5
    echo ""
    
    echo "✅ POSITIONS OPENED (Last 5):"
    echo "----------------------------"
    tail -1000 /tmp/live_bot.log | grep "POSITION OPENED" | tail -5
    echo ""
    
    echo "🎯 TP/SL PLACEMENTS (Last 5):"
    echo "-----------------------------"
    tail -1000 /tmp/live_bot.log | grep -E "(EXCHANGE TP|EXCHANGE SL)" | tail -5
    echo ""
    
    echo "📈 TP HITS (Last 5):"
    echo "-------------------"
    tail -1000 /tmp/live_bot.log | grep "TP1 HIT" | tail -5
    echo ""
    
    echo "❌ ERRORS (Last 3):"
    echo "------------------"
    tail -500 /tmp/live_bot.log | grep -i "error" | grep -v "No error" | tail -3
    echo ""
    
    echo "Press Ctrl+C to stop monitoring"
    echo "Refreshing in 30s..."
    sleep 30
done

