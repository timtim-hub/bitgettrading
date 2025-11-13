#!/bin/bash
echo "🔍 Checking for trades and trailing TP..."
echo ""
echo "=== TRADES OPENED ==="
grep "✅ Position opened" /tmp/live_bot.log | tail -5
echo ""
echo "=== TRAILING STOPS PLACED ==="
grep -E "🎯.*Trailing|placed trailing|track_plan" /tmp/live_bot.log | tail -5
echo ""
echo "=== TP1 HITS ==="
grep "TP1 hit" /tmp/live_bot.log | tail -5
echo ""
echo "=== RECENT SCANS ==="
tail -20 /tmp/live_bot.log | grep "Scan complete"
