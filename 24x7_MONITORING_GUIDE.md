# 24/7 Bot Monitoring Guide

## 🚀 Quick Start

### Start 24/7 Bot
```bash
cd /Users/macbookpro13/bitgettrading
./run_bot_24x7.sh start
```

This will:
- ✅ Auto-restart on crashes
- ✅ Rotate logs automatically (when > 100MB)
- ✅ Monitor every 30 seconds
- ✅ Log all activities
- ✅ Run indefinitely

---

## 📊 Monitoring Commands

### Check Status
```bash
./run_bot_24x7.sh status
```
Shows if bot is running and recent scan results.

### View Live Dashboard
```bash
./monitor_dashboard.sh
```
Shows:
- Bot uptime and PID
- Recent scans
- Trades opened
- Trailing stops placed
- Statistics
- Recent errors

### Watch Live Logs
```bash
./run_bot_24x7.sh logs
```
or
```bash
tail -f /tmp/live_bot.log
```

### Check Trades Detail
```bash
./check_trades.sh
```
Shows:
- All trades opened
- Trailing stops placed
- TP1 hits
- Recent scans

---

## 🔧 Management Commands

### Restart Bot
```bash
./run_bot_24x7.sh restart
```

### Stop Bot
```bash
./run_bot_24x7.sh stop
```

### View All Logs
```bash
# Main bot output
tail -100 /tmp/live_bot.log

# 24/7 runner logs
tail -100 logs/bot_24x7.log

# Errors only
tail -100 logs/bot_errors.log

# Trade tracking
cat trades.jsonl | python3 -m json.tool
```

---

## 📁 Log Files

| File | Purpose | Rotation |
|------|---------|----------|
| `/tmp/live_bot.log` | Main bot output | Auto (>100MB) |
| `logs/bot_24x7.log` | 24/7 runner activity | Auto (>100MB) |
| `logs/bot_errors.log` | Errors only | Auto (>100MB) |
| `trades.jsonl` | Trade tracking | No (append-only) |

**Old logs are automatically compressed to `.gz` when rotated.**

---

## 🔍 Monitoring Checklist

### Daily Check (5 minutes)
```bash
./monitor_dashboard.sh
```
Look for:
- ✅ Bot status: RUNNING
- ✅ Recent scans with `data_failed=0`
- ✅ No critical errors (SSL errors are OK)

### When Trades Happen
```bash
./check_trades.sh
```
Verify:
- ✅ Position opened
- ✅ TP/SL placed
- ✅ Trailing stop after TP1

### Weekly Check (10 minutes)
```bash
# Check log sizes
du -h /tmp/live_bot.log logs/

# Check restart count
grep "Bot restarted" logs/bot_24x7.log | wc -l

# Check trade statistics
echo "Total trades: $(grep -c 'Position opened' /tmp/live_bot.log)"
echo "Trailing stops: $(grep -c 'Trailing stop' /tmp/live_bot.log)"
```

---

## ⚠️ Troubleshooting

### Bot Keeps Restarting
```bash
# Check error log
tail -50 logs/bot_errors.log

# Check 24/7 runner log
tail -50 logs/bot_24x7.log

# Look for patterns
grep "Failed to restart" logs/bot_24x7.log
```

### Logs Too Large
Logs auto-rotate at 100MB, but if needed:
```bash
# Manual cleanup
rm /tmp/live_bot.log.old.gz
rm logs/*.old.gz

# Start fresh
./run_bot_24x7.sh stop
rm /tmp/live_bot.log
./run_bot_24x7.sh start
```

### Bot Not Trading
Check:
1. **Funding blackout?**
   ```bash
   grep "funding blackout" /tmp/live_bot.log | tail -5
   ```
   Wait 15 minutes after 00:00/08:00/16:00 UTC

2. **Market conditions?**
   ```bash
   tail -20 /tmp/live_bot.log | grep "Scan complete"
   ```
   Look for `no_signal=0` (normal) vs `no_signal=53` (no signals)

3. **Data fetching?**
   ```bash
   grep "data_failed" /tmp/live_bot.log | tail -5
   ```
   Should show `data_failed=0`

---

## 🎯 What Success Looks Like

### Healthy Bot Logs
```
📊 Scan complete: checked=53, gates_failed=0, data_failed=0, no_signal=0, signals_found=0
💚 Bot running | PID: 12345 | Uptime: 3600s | Restarts: 0
```

### When Trade Happens
```
🚀 TREND SIGNAL | LONG @ $101500
✅ Position opened | BTCUSDT | $101500
✅ Placed SL @ $100800 | TP1 @ $104000
[Later when price hits TP1]
🎯 TP1 HIT! Closing 75%
🚀 Placing trailing stop | Size: 0.25 | Trigger: $104000 | Callback: 3.0%
✅ Verified: Trailing stop is active on exchange | BTCUSDT | Order ID: 123456
```

---

## 🔐 Security Notes

- **API Keys**: Stored in `.env` file (git-ignored)
- **Logs**: Contain no sensitive data
- **PID File**: `bot.pid` tracks running instance
- **Auto-restart**: Prevents loss of uptime

---

## 📞 Quick Reference Card

| Action | Command |
|--------|---------|
| Start 24/7 | `./run_bot_24x7.sh start` |
| Stop | `./run_bot_24x7.sh stop` |
| Status | `./run_bot_24x7.sh status` |
| Dashboard | `./monitor_dashboard.sh` |
| Live Logs | `./run_bot_24x7.sh logs` |
| Check Trades | `./check_trades.sh` |
| Restart | `./run_bot_24x7.sh restart` |

---

## 🚨 Emergency Commands

### Kill Everything
```bash
pkill -9 -f "launch_institutional_live"
pkill -9 -f "run_bot_24x7"
rm bot.pid
```

### Fresh Start
```bash
./run_bot_24x7.sh stop
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm /tmp/live_bot.log
./run_bot_24x7.sh start
```

### Check System Resources
```bash
# CPU usage
ps aux | grep python | head -5

# Memory
ps -m $(cat bot.pid) 2>/dev/null || echo "Not running"

# Disk space
df -h /tmp
df -h .
```

---

## ✅ All Set!

Your bot is now running 24/7 with:
- ✅ **Auto-restart** on crashes
- ✅ **Log rotation** (no disk fill)
- ✅ **Comprehensive logging**
- ✅ **Easy monitoring**
- ✅ **SSL fix active**
- ✅ **Trailing TP ready**

**The bot will run indefinitely until you stop it manually.**

Run `./monitor_dashboard.sh` anytime to see current status! 📊

