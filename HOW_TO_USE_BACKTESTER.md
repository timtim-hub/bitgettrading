# 🎯 HOW TO USE THE BACKTESTING SYSTEM

## 📚 Quick Reference

### Files Overview

```
BACKTESTER_GUIDE.md              # Complete documentation (read this!)
HOW_TO_USE_BACKTESTER.md        # This quick reference
FILTERED_BACKTEST_RESULTS.md    # Latest filtered test results
COMPREHENSIVE_STRATEGY_REPORT.md # All 40 strategies analysis
```

---

## 🚀 QUICK START (5 Minutes)

### 1. Run Complete Filtered Pipeline

```bash
python filtered_backtest_pipeline.py
```

**What it does:**
- Tests WINNER strategy on 130 profitable tokens
- Tests new LightGBM strategy on all 338 tokens
- Tests LightGBM strategy on 5%+ ROI tokens only
- Generates detailed JSON results + summary

**Time:** ~10 seconds  
**Output:** `backtest_results/*filtered*.json`

### 2. View Results

```bash
cat FILTERED_BACKTEST_RESULTS.md
```

**Look for:**
- Portfolio ROI for each test
- Top profitable tokens
- Worst performing tokens
- Recommendations

---

## 📊 TYPICAL WORKFLOWS

### Workflow 1: Find Best Tokens for Existing Strategy

```bash
# 1. Identify strategy ID (check strategies/ folder)
# Example: strategy_027.json = WINNER strategy

# 2. Edit filtered_backtest_pipeline.py
# Change: winner_strategy_id = 27  (line ~236)

# 3. Run pipeline
python filtered_backtest_pipeline.py

# 4. Check results
cat backtest_results/WINNER_profitable_only_summary_*.json
```

### Workflow 2: Test New Strategy on All Tokens

```bash
# 1. Create new strategy (don't overwrite existing!)
# Example: strategies/strategy_046.json

# 2. Edit filtered_backtest_pipeline.py
# Update lightgbm_strategy section with your strategy

# 3. Run pipeline
python filtered_backtest_pipeline.py

# 4. Find profitable tokens
# Check: backtest_results/YourStrategy_all338_detailed_*.json
# Filter for: total_roi_pct >= 5.0
```

### Workflow 3: Weekly Token Re-Evaluation

```bash
# 1. Delete old cached data (get fresh data)
rm -rf backtest_data/*.pkl

# 2. Fetch fresh historical data (1-2 min)
python -c "from data_fetcher import HistoricalDataFetcher, TEST_SYMBOLS; import asyncio; asyncio.run(HistoricalDataFetcher().fetch_all_symbols(TEST_SYMBOLS))"

# 3. Run pipeline with your best strategy
python filtered_backtest_pipeline.py

# 4. Update token whitelist in live_trade.py
# Add new winners, remove losers
```

---

## 🎯 CUSTOM BACKTESTING

### Create Your Own Strategy

1. **Copy existing strategy:**
   ```bash
   cp strategies/strategy_045.json strategies/strategy_046.json
   ```

2. **Edit parameters:**
   ```json
   {
     "id": 46,  // INCREMENT THIS!
     "name": "My_Custom_Strategy",
     "entry_threshold": 1.2,
     "stop_loss_pct": 0.40,
     "take_profit_pct": 0.18,
     // ... modify other params
   }
   ```

3. **Update pipeline to test it:**
   ```python
   # In filtered_backtest_pipeline.py, Step 3:
   step3_result = await run_filtered_backtest(
       "strategies/strategy_046.json",  # Your strategy!
       all_symbols,
       "MyStrategy_all338"
   )
   ```

4. **Run and analyze:**
   ```bash
   python filtered_backtest_pipeline.py
   cat backtest_results/MyStrategy_all338_summary_*.json
   ```

---

## 📖 KEY CONCEPTS

### Portfolio ROI vs Average ROI

- **Average ROI:** Simple average across all tokens (misleading!)
- **Portfolio ROI:** Actual P&L if you traded $50 on EVERY token (realistic!)

**Always use Portfolio ROI for decision-making!**

### Token Filtering Impact

| Scenario | Portfolio ROI | Why? |
|----------|---------------|------|
| All 338 tokens | -3.39% | Losers dilute winners |
| 48 filtered tokens | +28.42% | Only winners, no losers |

**Filtering improves ROI by +31.81%!**

### Trades per Day (Clarification)

- **23.2 trades/day** = TOTAL across all 338 tokens
- **0.07 trades/day/token** = Per token average (most tokens have 0)
- **Active tokens trade MORE:** ~1-5 trades/day each

---

## 🎓 UNDERSTANDING RESULTS

### Reading JSON Output

```json
{
  "symbol": "BTCUSDT",
  "total_roi_pct": 15.32,  // 15.32% ROI
  "win_rate_pct": 62.5,    // 62.5% win rate
  "total_trades": 47,      // 47 trades in backtest
  "sharpe_ratio": 1.85,    // Risk-adjusted return
  "max_drawdown_pct": 12.3, // Max 12.3% drawdown
  "final_capital": 57.66   // Started at $50, ended at $57.66
}
```

### Good vs Bad Tokens

**✅ Good Token (Trade This!):**
- total_roi_pct > 5%
- win_rate_pct > 55%
- sharpe_ratio > 0.5
- max_drawdown_pct < 30%
- total_trades > 10

**❌ Bad Token (Avoid!):**
- total_roi_pct < 0%
- win_rate_pct < 50%
- sharpe_ratio < 0
- max_drawdown_pct > 50%
- total_trades < 5 (luck/sample size)

---

## ⚙️ ADVANCED CONFIGURATION

### Adjust Backtest Parameters

Edit `backtest_engine.py`:

```python
INITIAL_CAPITAL = 50.0    # Starting capital per token
LEVERAGE = 25             # Match your live trading leverage!
TAKER_FEE_PCT = 0.0006    # Bitget taker fee (0.06%)
```

### Change Token Universe

Edit `data_fetcher.py`:

```python
# Option 1: Custom list
TEST_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", 
    # ... add your tokens
]

# Option 2: Load from file (default)
with open("all_bitget_symbols.txt", "r") as f:
    TEST_SYMBOLS = [line.strip() for line in f if line.strip()]
```

### Parallel Processing Speed

Edit `filtered_backtest_pipeline.py`:

```python
# More workers = faster, but uses more CPU
num_workers = min(10, os.cpu_count())

# For Apple Silicon (M1/M2/M3):
num_workers = 10  # Max out performance!

# For older CPUs:
num_workers = 4  # Conservative
```

---

## 🐛 TROUBLESHOOTING

### Issue: "No cached data found"

**Solution:**
```bash
# Fetch data first
python -c "from data_fetcher import HistoricalDataFetcher, TEST_SYMBOLS; import asyncio; asyncio.run(HistoricalDataFetcher().fetch_all_symbols(TEST_SYMBOLS))"
```

### Issue: "Strategy file not found"

**Solution:**
```bash
# Check strategy exists
ls strategies/strategy_0*.json

# If missing, generate strategies
python ultimate_strategy_generator.py
```

### Issue: "Results don't match live trading"

**Common causes:**
1. Different leverage (backtest vs live)
2. Slippage (not modeled in backtest)
3. API latency (not modeled)
4. Different entry timing

**Solution:** Use backtest for RELATIVE comparison, not absolute prediction!

### Issue: "Out of memory"

**Solution:**
```bash
# Reduce parallel workers
# In filtered_backtest_pipeline.py:
num_workers = min(4, os.cpu_count())  # Lower this
```

---

## 📊 INTERPRETING METRICS

### ROI Projections

```python
# Backtest: 8.3 days, 28.42% ROI
# Daily ROI: (1.2842)^(1/8.3) - 1 = 3.11% per day
# Weekly ROI: (1.0311)^7 - 1 = 23.62% per week
# Monthly ROI: (1.0311)^30 - 1 = 151.63% per month
```

**⚠️ WARNING:** These are COMPOUNDED projections!  
Real results may vary due to:
- Market conditions changing
- Capital availability
- Slippage
- Drawdowns

### Sharpe Ratio

- **< 0:** Strategy loses money (bad)
- **0 - 1:** Positive returns, high volatility (okay)
- **1 - 2:** Good risk-adjusted returns (good)
- **> 2:** Excellent risk-adjusted returns (great)

### Max Drawdown

- **< 20%:** Low risk (conservative)
- **20% - 40%:** Medium risk (balanced)
- **> 40%:** High risk (aggressive)

**Your tolerance:** Decide your max acceptable drawdown BEFORE trading!

---

## 🚀 DEPLOYMENT CHECKLIST

Before deploying a strategy live:

- [ ] Backtest on full 338-token universe
- [ ] Identify 30-50 profitable tokens (5%+ ROI)
- [ ] Re-test on filtered tokens (confirm >15% ROI)
- [ ] Check win rate (>55%), Sharpe (>1), drawdown (<30%)
- [ ] Paper trade for 24-48 hours
- [ ] Compare paper results to backtest
- [ ] Start live with small capital (test 1 week)
- [ ] Scale up if results match backtest

---

## 📞 NEED HELP?

1. **Read full documentation:**
   ```bash
   cat BACKTESTER_GUIDE.md
   ```

2. **Check comprehensive results:**
   ```bash
   cat COMPREHENSIVE_STRATEGY_REPORT.md
   cat FILTERED_BACKTEST_RESULTS.md
   ```

3. **Inspect strategy details:**
   ```bash
   cat strategies/ULTIMATE_STRATEGY_RATIONALES.md
   ```

4. **Review code comments:**
   ```bash
   # All Python files have detailed comments
   cat filtered_backtest_pipeline.py
   cat backtest_engine.py
   ```

---

**Last Updated:** November 8, 2025  
**Version:** 2.0  
**Status:** Production Ready ✅  
**Performance:** 28.42% ROI on filtered tokens 🚀

