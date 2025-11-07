# Plan: Increase Win Rate and Profitability with Automated Backtesting

## Overview

Implement automated per-token backtesting system that continuously evaluates historical performance and dynamically adjusts trading parameters based on backtesting results. This system will filter out consistently losing tokens and optimize parameters for best-performing tokens.

## Current State Analysis

**Current Entry Criteria:**
- Only A-grade trades (5+ out of 10 factors)
- Multi-timeframe confluence (6 layers)
- Volume confirmation (3.0x+)
- Strong momentum (0.20%+ in 15s)
- R:R >= 6:1
- With market structure
- Near S/R levels
- Technical indicators aligned (RSI, MACD, Bollinger, EMA, VWAP)

**Current Order Frequency:**
- Entry check: Every 5 seconds when slots available
- Position check: Every 5ms (0.005s) for exits
- Max positions: 10

**Current Backtesting:**
- Manual backtesting scripts exist
- No automated per-token backtesting
- No performance-based filtering
- No dynamic parameter adjustment

## Core Requirements

1. **Automated Per-Token Backtesting**
   - Backtest each token automatically using historical data
   - Run backtests frequently but optimize for speed
   - Use current strategy (always, automatically even if changed)
   - Store results for analysis

2. **Performance-Based Filtering**
   - Boolean flag to filter out tokens that consistently lose in backtesting
   - Track win rate, profitability, Sharpe ratio per token
   - Filter tokens below threshold (e.g., <50% win rate, negative ROI)

3. **Dynamic Parameter Adjustment**
   - Best-performing tokens get more trailing TP (4% → 6% callback)
   - Other dynamic adjustments based on backtesting data:
     - Position size multiplier (larger for better tokens)
     - Entry threshold (lower for better tokens = more trades)
     - Stop-loss tightness (tighter for worse tokens)
     - Take-profit activation (lower for better tokens)

4. **Stats File for Viewing**
   - Human-readable stats file showing:
     - Per-token backtesting results
     - Win rate, ROI, Sharpe ratio
     - Filtered tokens list
     - Dynamic parameter adjustments
     - Last backtest timestamp

## Implementation Plan

### Phase 1: Automated Per-Token Backtesting System

#### 1.1 Create Fast Backtesting Engine
**File:** `src/bitget_trading/symbol_backtester.py`

**Features:**
- Fast backtesting using historical candles (1m, 5m, 15m)
- Simulates current strategy (entry/exit logic from `enhanced_ranker.py`)
- Optimized for speed: process 200 candles in <1 second per token
- Parallel processing: backtest multiple tokens simultaneously
- Returns: win_rate, roi, sharpe_ratio, total_trades, avg_win, avg_loss

**Implementation:**
- Use existing `get_historical_candles()` to fetch data
- Simulate entry/exit using current `compute_enhanced_score()` logic
- Track trades, PnL, fees, slippage
- Calculate performance metrics

#### 1.2 Performance Tracker
**File:** `src/bitget_trading/symbol_performance_tracker.py`

**Features:**
- Store per-token backtesting results
- Track historical performance over time
- Calculate rolling averages (last 7 days, 30 days)
- Persist to JSON file for durability

**Data Structure:**
```python
{
  "symbol": {
    "backtest_results": [
      {
        "timestamp": "2025-11-07T18:00:00Z",
        "win_rate": 0.65,
        "roi": 0.12,
        "sharpe_ratio": 1.5,
        "total_trades": 50,
        "avg_win": 0.08,
        "avg_loss": -0.05,
        "profit_factor": 1.6
      }
    ],
    "live_results": {
      "win_rate": 0.68,
      "total_trades": 25,
      "total_pnl": 2.5
    },
    "combined_score": 0.66,  # Weighted average of backtest + live
    "last_backtest": "2025-11-07T18:00:00Z"
  }
}
```

#### 1.3 Automated Backtesting Scheduler
**File:** `src/bitget_trading/backtest_scheduler.py`

**Features:**
- Run backtests automatically on schedule (e.g., every 6 hours)
- Backtest all tokens in parallel (batch processing)
- Optimize for speed: process 10-20 tokens concurrently
- Skip tokens that haven't changed (if strategy unchanged)
- Background task that doesn't block live trading

**Configuration:**
- `BACKTEST_INTERVAL_HOURS`: How often to run backtests (default: 6)
- `BACKTEST_LOOKBACK_DAYS`: How many days of history to use (default: 7)
- `BACKTEST_MIN_TRADES`: Minimum trades required for valid backtest (default: 10)

### Phase 2: Performance-Based Filtering

#### 2.1 Token Filtering System
**File:** `src/bitget_trading/symbol_filter.py`

**Features:**
- Boolean flag: `FILTER_LOSING_TOKENS` (default: True)
- Filter criteria:
  - Win rate < 50% (configurable)
  - ROI < 0% (negative returns)
  - Sharpe ratio < 0.5 (poor risk-adjusted returns)
  - Profit factor < 1.0 (losses > wins)
- Combine backtest + live results for filtering
- Weight recent results more heavily

**Implementation:**
- Add `should_trade_symbol()` method
- Check against filter criteria before ranking
- Log filtered tokens for transparency
- Allow manual override via config

#### 2.2 Integration with Live Trading
**File:** `live_trade.py`

**Changes:**
- Before ranking symbols, filter out losing tokens
- Skip filtered tokens in `rank_symbols_enhanced()`
- Log which tokens are filtered and why
- Make filtering optional via config flag

### Phase 3: Dynamic Parameter Adjustment

#### 3.1 Performance-Based Parameter Calculator
**File:** `src/bitget_trading/dynamic_params.py`

**Features:**
- Calculate dynamic parameters based on token performance
- Trailing TP callback adjustment:
  - Best tokens (top 20%): 6% callback (was 4%)
  - Good tokens (top 50%): 5% callback
  - Average tokens: 4% callback (default)
  - Poor tokens (bottom 20%): 3% callback (tighter)
- Position size multiplier:
  - Best tokens: 1.3x (30% larger)
  - Good tokens: 1.15x
  - Average tokens: 1.0x (default)
  - Poor tokens: 0.8x (20% smaller)
- Entry threshold adjustment:
  - Best tokens: Lower threshold (more trades)
  - Poor tokens: Higher threshold (fewer trades)

**Performance Tiers:**
- Tier 1 (Top 20%): Win rate >65%, ROI >10%, Sharpe >1.5
- Tier 2 (Top 50%): Win rate >55%, ROI >5%, Sharpe >1.0
- Tier 3 (Average): Win rate 45-55%, ROI 0-5%, Sharpe 0.5-1.0
- Tier 4 (Bottom 20%): Win rate <45%, ROI <0%, Sharpe <0.5

#### 3.2 Integration with Trading Logic
**File:** `live_trade.py`, `src/bitget_trading/enhanced_ranker.py`

**Changes:**
- Before placing trade, get token's performance tier
- Adjust trailing TP callback based on tier
- Adjust position size based on tier
- Adjust entry threshold based on tier
- Log parameter adjustments for transparency

### Phase 4: Stats File Generation

#### 4.1 Stats File Generator
**File:** `src/bitget_trading/stats_generator.py`

**Features:**
- Generate human-readable stats file: `data/symbol_performance_stats.txt`
- Update automatically after each backtest run
- Include:
  - Per-token backtesting results (sorted by performance)
  - Filtered tokens list
  - Dynamic parameter adjustments
  - Live trading results
  - Combined performance scores
  - Last backtest timestamp

**File Format:**
```
========================================
SYMBOL PERFORMANCE STATS
Last Updated: 2025-11-07 18:00:00 UTC
Last Backtest: 2025-11-07 18:00:00 UTC
========================================

TOP PERFORMERS (Tier 1):
  BTCUSDT: Win Rate 68% | ROI 15% | Sharpe 1.8 | Trades 120
    → Trailing TP: 6% callback | Position Size: 1.3x
  ETHUSDT: Win Rate 65% | ROI 12% | Sharpe 1.6 | Trades 95
    → Trailing TP: 6% callback | Position Size: 1.3x

GOOD PERFORMERS (Tier 2):
  SOLUSDT: Win Rate 58% | ROI 8% | Sharpe 1.2 | Trades 80
    → Trailing TP: 5% callback | Position Size: 1.15x

FILTERED TOKENS (Not Trading):
  BADUSDT: Win Rate 42% | ROI -5% | Sharpe 0.3 | Trades 25
    Reason: Win rate <50%, ROI <0%, Sharpe <0.5

...
```

#### 4.2 HTML Stats Dashboard (Optional)
**File:** `src/bitget_trading/stats_dashboard.py`

**Features:**
- Generate HTML dashboard: `data/symbol_performance_dashboard.html`
- Interactive charts (using Chart.js or similar)
- Sortable tables
- Filter by tier, win rate, ROI
- Auto-refresh every 5 minutes

### Phase 5: Integration with Live Trading

#### 5.1 Backtesting Service
**File:** `src/bitget_trading/backtest_service.py`

**Features:**
- Background service that runs backtests periodically
- Integrates with `LiveTrader` class
- Runs backtests without blocking live trading
- Updates performance tracker after each run
- Triggers stats file regeneration

**Implementation:**
- Run backtests in background thread/async task
- Schedule runs every 6 hours (configurable)
- Process tokens in batches (10-20 at a time)
- Cache results to avoid redundant backtests

#### 5.2 Live Trading Integration
**File:** `live_trade.py`

**Changes:**
- Initialize backtesting service on startup
- Filter symbols before ranking (if enabled)
- Use dynamic parameters when placing trades
- Update live results in performance tracker
- Combine live + backtest results for filtering

## File Structure

```
src/bitget_trading/
  ├── symbol_backtester.py          # Fast per-token backtesting engine
  ├── symbol_performance_tracker.py  # Performance tracking and storage
  ├── backtest_scheduler.py          # Automated backtesting scheduler
  ├── symbol_filter.py               # Token filtering logic
  ├── dynamic_params.py              # Dynamic parameter calculation
  ├── stats_generator.py             # Stats file generation
  └── backtest_service.py             # Backtesting service integration

data/
  ├── symbol_performance.json        # Performance data (JSON)
  ├── symbol_performance_stats.txt   # Human-readable stats
  └── symbol_performance_dashboard.html  # HTML dashboard (optional)

live_trade.py                        # Integration with live trading
```

## Configuration Options

Add to `.env` or config:
```python
# Backtesting
BACKTEST_ENABLED = True
BACKTEST_INTERVAL_HOURS = 6
BACKTEST_LOOKBACK_DAYS = 7
BACKTEST_MIN_TRADES = 10
BACKTEST_PARALLEL_TOKENS = 20

# Filtering
FILTER_LOSING_TOKENS = True
FILTER_MIN_WIN_RATE = 0.50
FILTER_MIN_ROI = 0.0
FILTER_MIN_SHARPE = 0.5

# Dynamic Parameters
DYNAMIC_PARAMS_ENABLED = True
TRAILING_TP_BEST_TOKENS = 0.06  # 6% for top 20%
TRAILING_TP_GOOD_TOKENS = 0.05  # 5% for top 50%
TRAILING_TP_AVERAGE_TOKENS = 0.04  # 4% default
TRAILING_TP_POOR_TOKENS = 0.03  # 3% for bottom 20%
POSITION_SIZE_BEST_MULTIPLIER = 1.3
POSITION_SIZE_GOOD_MULTIPLIER = 1.15
POSITION_SIZE_POOR_MULTIPLIER = 0.8
```

## Expected Impact

**Win Rate Improvement:** 10-20%
- Filtering out losing tokens: +5-10%
- Dynamic parameters for best tokens: +3-7%
- Better entry thresholds: +2-3%

**Profitability Improvement:** 15-30%
- Larger positions on best tokens: +5-10%
- Better trailing TP for winners: +3-8%
- Filtering losing tokens: +5-10%
- Optimized entry thresholds: +2-5%

**Order Frequency:** Maintained or slightly increased
- Filtering reduces candidate pool but doesn't slow entry checks
- Dynamic thresholds may allow more trades on best tokens
- Overall: Similar or slightly higher frequency

## Implementation Steps

1. **Create Fast Backtesting Engine** (`symbol_backtester.py`)
   - Implement fast backtesting using historical candles
   - Optimize for speed (<1 second per token)
   - Return performance metrics

2. **Create Performance Tracker** (`symbol_performance_tracker.py`)
   - Store backtesting results
   - Track historical performance
   - Persist to JSON

3. **Create Backtesting Scheduler** (`backtest_scheduler.py`)
   - Automated backtesting on schedule
   - Parallel processing
   - Background execution

4. **Create Symbol Filter** (`symbol_filter.py`)
   - Filter losing tokens
   - Configurable criteria
   - Integration with ranking

5. **Create Dynamic Params** (`dynamic_params.py`)
   - Calculate performance tiers
   - Adjust parameters per tier
   - Integration with trading

6. **Create Stats Generator** (`stats_generator.py`)
   - Generate human-readable stats file
   - Update automatically
   - Include all relevant metrics

7. **Create Backtesting Service** (`backtest_service.py`)
   - Background service
   - Integration with live trading
   - Automated execution

8. **Integrate with Live Trading** (`live_trade.py`)
   - Initialize backtesting service
   - Filter symbols before ranking
   - Use dynamic parameters
   - Update live results

9. **Testing and Validation**
   - Test backtesting speed (should be <1 min for 100 tokens)
   - Validate filtering logic
   - Verify dynamic parameter adjustments
   - Check stats file generation

10. **Documentation**
    - Update README with new features
    - Document configuration options
    - Add examples of stats file

## Risk Mitigation

- **Backtesting Speed:** Optimize to <1 second per token, use parallel processing
- **Data Quality:** Validate historical data before backtesting
- **Filtering Accuracy:** Use combined backtest + live results, weight recent data
- **Parameter Stability:** Use rolling averages, avoid sudden changes
- **Integration Safety:** Run backtests in background, don't block live trading
- **Fallback:** If backtesting fails, use default parameters

## Success Metrics

- Backtesting completes in <5 minutes for 300 tokens
- Stats file updates automatically after each backtest
- Filtered tokens show <45% win rate in live trading
- Best tokens (Tier 1) show >60% win rate in live trading
- Dynamic parameters improve profitability by 15-30%
- Order frequency maintained or increased



