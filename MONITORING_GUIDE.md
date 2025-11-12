# Bot Monitoring Guide

## Overview

The bot is now running with **extended monitoring** that tracks all activity over long periods.

## Monitoring System

### Extended Monitor (`monitor_bot_extended.py`)

**Status**: Running in background with `nohup`

**Features**:
- ✅ Continuous monitoring (checks every 30 seconds)
- ✅ Quick status updates every 60 seconds
- ✅ Full reports every 5 minutes
- ✅ Tracks positions, TP/SL, TP hits, trailing stops
- ✅ Error and warning tracking
- ✅ Performance metrics (signals/hour, TP hit rate)
- ✅ Position history and details

**Output**: `/tmp/monitor.log`

## Quick Commands

### View Current Status
```bash
./view_monitor.sh
```

### View Monitor Output
```bash
tail -f /tmp/monitor.log
```

### View Bot Logs
```bash
tail -f /tmp/live_bot.log
```

### Check if Both Are Running
```bash
ps aux | grep -E "(monitor_bot|launch_institutional)" | grep -v grep
```

### View Recent Activity
```bash
tail -100 /tmp/live_bot.log | grep -E "(POSITION|TP1|Trailing|SIGNAL)" -i
```

## What's Being Monitored

### 1. Bot Status
- ✅ Bot process running
- ✅ Monitor process running
- ⏱️ Runtime tracking

### 2. Positions
- Active positions (symbols, sides, strategies)
- Entry times
- Position details

### 3. TP/SL Orders
- TP orders placed successfully
- SL orders placed successfully
- Failed orders (excluding expected "Insufficient position" errors)

### 4. Trading Activity
- Signals found
- Signals executed
- TP hits (with timestamps)
- Trailing stops activated
- Positions closed

### 5. Performance Metrics
- Signals per hour
- TP hit rate
- Average check interval

### 6. Errors & Warnings
- Recent errors (filtered to exclude expected ones)
- Recent warnings
- Error tracking over time

## Monitor Output Format

### Quick Status (Every 60s)
```
[HH:MM:SS] Runtime: X:XX:XX | Positions: N | TP Hits: N | Signals: N | Errors: N
```

### Full Report (Every 5 minutes)
- Bot status
- Runtime and check count
- Active positions with details
- TP/SL statistics
- Trading activity summary
- Recent TP hits, trailing activations, closes
- Recent activity log
- Errors and warnings
- Performance metrics

## Expected Behavior

### Normal Operations
- ✅ Bot running continuously
- ✅ Positions being tracked
- ✅ SL orders placed successfully
- ⚠️ Some TP orders may fail with "Insufficient position" (expected for very small positions)
- ✅ Periodic checks will retry failed TP orders

### What to Watch For

**Good Signs**:
- ✅ Regular signals being found
- ✅ Positions opening with SL protection
- ✅ TP hits occurring
- ✅ Trailing stops activating after TP1
- ✅ Positions closing at profit

**Warning Signs**:
- ❌ Bot process stops
- ❌ High error rate (excluding "Insufficient position")
- ❌ No signals for extended period
- ❌ TP orders consistently failing (not just "Insufficient position")
- ❌ Positions not closing when they should

## Long-Term Monitoring

The monitor will run indefinitely until stopped. It tracks:

1. **Position Lifecycle**: Entry → TP/SL placement → TP hits → Trailing → Close
2. **Performance Trends**: Signals/hour, TP hit rate over time
3. **Error Patterns**: Types of errors, frequency, timing
4. **Trading Activity**: When signals occur, which strategies, which symbols

## Stopping the Monitor

```bash
pkill -f "python monitor_bot_extended.py"
```

## Restarting the Monitor

```bash
cd /Users/macbookpro13/bitgettrading
nohup python monitor_bot_extended.py > /tmp/monitor.log 2>&1 &
```

## Monitoring Best Practices

1. **Check regularly**: Use `./view_monitor.sh` to get quick status
2. **Review full reports**: Check `/tmp/monitor.log` every few hours
3. **Watch for patterns**: Look for trends in TP hits, errors, signals
4. **Verify positions**: Check Bitget app to confirm positions match monitor
5. **Track performance**: Monitor TP hit rate and signals/hour over time

## Current Status

- ✅ Bot: Running
- ✅ Monitor: Running
- 📊 Monitoring: Active positions, TP/SL placement, trading activity
- ⏱️ Runtime: Tracking since monitor start
- 📈 Metrics: Being collected continuously

The monitor will continue running and collecting data for analysis.

