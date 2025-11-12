# Trade Tracking System

## Overview

Every trade is automatically tracked with comprehensive details for later analysis. All data is saved to both **CSV** and **JSONL** formats in the `trades_data/` directory.

## Files Generated

- **`trades_YYYYMMDD_HHMMSS.csv`**: CSV file with all trades (easy to import into Excel/Python)
- **`trades_YYYYMMDD_HHMMSS.jsonl`**: JSON Lines format (one trade per line, easy to parse)

## Data Captured

### Entry Details
- Symbol, side (long/short), strategy (LSVR/VWAP-MR/Trend), regime (Range/Trend)
- Entry time, price, size (contracts), notional (USD), equity at entry
- Stop price, TP1/TP2/TP3 prices
- Leverage (25x), margin fraction (10%)

### Market Conditions at Entry
- ADX, RSI, BB-width%, VWAP slope
- Volume ratio, ATR
- Bucket (Majors/Mid-caps/Micros)
- Sweep level (for LSVR)

### Exit Details
- Exit time, price, reason (TP1/TP2/TP3/SL/Trailing/Time-Stop/Manual)
- Exit size, duration (seconds)
- Market conditions at exit (same indicators as entry)

### Performance Metrics
- P&L (USD and %)
- P&L as % of capital (leveraged)
- Fees (entry + exit)
- Net P&L (after fees)
- Peak P&L (highest reached)
- Drawdown from peak

### TP/SL Behavior
- TP1/TP2/TP3 hit times
- Trailing stop activation (trigger price)
- Breakeven move time
- Exit reason

## Analysis Examples

### Python
```python
import pandas as pd
import json

# Load CSV
df = pd.read_csv('trades_data/trades_20240101_120000.csv')

# Load JSONL
trades = []
with open('trades_data/trades_20240101_120000.jsonl', 'r') as f:
    for line in f:
        trades.append(json.loads(line))
df = pd.DataFrame(trades)

# Analysis
print(f"Total trades: {len(df)}")
print(f"Win rate: {(df['net_pnl'] > 0).mean() * 100:.1f}%")
print(f"Total P&L: ${df['net_pnl'].sum():.2f}")
print(f"Avg P&L: ${df['net_pnl'].mean():.2f}")

# By strategy
print(df.groupby('strategy')['net_pnl'].agg(['count', 'sum', 'mean']))

# By regime
print(df.groupby('regime')['net_pnl'].agg(['count', 'sum', 'mean']))

# Best/worst trades
print(df.nlargest(5, 'net_pnl')[['symbol', 'strategy', 'net_pnl', 'duration_seconds']])
print(df.nsmallest(5, 'net_pnl')[['symbol', 'strategy', 'net_pnl', 'duration_seconds']])
```

### Excel
1. Open the CSV file in Excel
2. Use pivot tables to analyze by:
   - Strategy
   - Regime
   - Symbol
   - Time of day
   - Exit reason

## Key Metrics to Track

1. **Win Rate**: % of profitable trades
2. **Average P&L**: Mean profit per trade
3. **Profit Factor**: Total wins / Total losses
4. **Max Drawdown**: Largest peak-to-trough decline
5. **Average Duration**: Mean time in trade
6. **Best Strategy**: Which strategy (LSVR/VWAP-MR/Trend) performs best
7. **Best Regime**: Range vs Trend performance
8. **Exit Analysis**: Which exit reasons are most profitable

## Notes

- All times are in ISO format (UTC)
- Fees are estimated at 0.06% per side (maker/taker)
- P&L calculations include leverage effects
- Peak P&L tracks the highest unrealized profit reached
- Drawdown shows how much profit was given back from peak

