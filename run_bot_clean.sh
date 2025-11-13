#!/bin/bash
# Clean bot launcher - forces fresh imports

echo "🧹 Cleaning all Python cache..."
find /Users/macbookpro13/bitgettrading -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find /Users/macbookpro13/bitgettrading -name "*.pyc" -delete 2>/dev/null
find /Users/macbookpro13/bitgettrading -name "*.pyo" -delete 2>/dev/null

echo "🔪 Killing all Python processes..."
pkill -9 python3 2>/dev/null
sleep 3

echo "🚀 Starting bot with Python 3.13 (SSL fixed)..."
cd /Users/macbookpro13/bitgettrading
export PYTHONDONTWRITEBYTECODE=1

# Use Python 3.13 with SSL fix
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B launch_institutional_live.py > /tmp/live_bot.log 2>&1 &

echo "✅ Bot started! PID: $!"
echo "📊 Monitoring logs..."
sleep 10

tail -30 /tmp/live_bot.log | grep -E "(✅|fetched_historical_candles|SSL|signals_found)" | head -15

