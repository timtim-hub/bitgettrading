# Bot Monitoring Status

## ✅ Current Status

**Bot**: Running (restarted with trailing stop fixes)  
**Extended Monitor**: Running  
**Monitoring**: Active for trailing stop activity

## 🔍 What's Being Monitored

### 1. Trailing Stop Activity
- TP1 hits (when position size decreases significantly)
- Trailing stop placement attempts
- Trailing stop success/failure
- Trailing stop verification

### 2. Position Activity
- New positions opened
- TP/SL orders placed
- Position monitoring (every 5 seconds)
- Position closes

### 3. Signal Generation
- Signals found
- Signals executed
- Signals rejected (liq guards, concurrency limits)

## 📊 Quick Monitoring Commands

### View Trailing Stop Activity
```bash
./monitor_trailing.sh
```

### Watch Live Trailing Stop Logs
```bash
tail -f /tmp/live_bot.log | grep -E "(TP1|Trailing|place_trailing|NORMAL TRAILING)" -i
```

### View All Bot Activity
```bash
tail -f /tmp/live_bot.log
```

### View Extended Monitor Reports
```bash
tail -f /tmp/monitor.log
```

### Quick Status Check
```bash
./view_monitor.sh
```

## 🎯 What to Watch For

### ✅ Good Signs
- `🎯 TP1 HIT` - TP1 was detected
- `🚀 Placing trailing stop` - Trailing stop is being placed
- `✅ Trailing stop placed (Bitget API)` - Trailing stop successfully placed
- `✅ Verified: Trailing stop is active on exchange` - Confirmed on exchange

### ⚠️ Warning Signs
- `❌ Error preparing trailing stop` - Error in trailing stop logic
- `❌ Failed to place trailing stop` - API call failed
- `⚠️ WARNING: Trailing stop order NOT found on exchange` - Verification failed
- `✅ Fallback: Fixed stop at 2.5% profit` - Using fallback instead of trailing

## 📈 Expected Behavior

1. **When TP1 is Hit:**
   - Position size decreases significantly (75% exit)
   - Old SL order is cancelled
   - Wait 2 seconds for exchange processing
   - Fresh position size is fetched
   - Trailing stop is placed with 3% callback
   - Trailing stop is verified on exchange

2. **Trailing Stop Parameters:**
   - **Callback Ratio**: 3% (tighter = more profit potential)
   - **Trigger Price**: TP1 price or current price (whichever ensures minimum 2.5% profit)
   - **Minimum Profit**: 2.5% locked in before trailing activates

3. **Fallback Behavior:**
   - If trailing stop fails, fixed stop at 2.5% profit is placed
   - This ensures profit protection even if trailing fails

## 🔄 Monitoring Frequency

- **Position Monitoring**: Every 5 seconds
- **Signal Scanning**: Every 15 seconds (configurable)
- **TP/SL Verification**: Every 5 minutes
- **Extended Monitor Reports**: Every 5 minutes

## 📝 Log Files

- **Bot Logs**: `/tmp/live_bot.log`
- **Monitor Logs**: `/tmp/monitor.log`

## 🚨 Troubleshooting

If trailing stops aren't working:

1. **Check for TP1 hits:**
   ```bash
   tail -1000 /tmp/live_bot.log | grep "TP1 HIT"
   ```

2. **Check for trailing stop placement:**
   ```bash
   tail -1000 /tmp/live_bot.log | grep -E "(Placing trailing|Trailing stop placed)"
   ```

3. **Check for errors:**
   ```bash
   tail -1000 /tmp/live_bot.log | grep -E "(ERROR|FAILED|❌)" -i
   ```

4. **Verify on Bitget App:**
   - Check "Trailing" tab (NOT "TP/SL" tab)
   - Look for active trailing orders

## 📊 Current Session

- **Bot Started**: Just restarted with trailing stop fixes
- **Positions Tracked**: 9 positions recovered on startup
- **Monitoring**: Active and watching for trailing stop activity

The bot is now ready to place trailing stops when TP1 is hit!

