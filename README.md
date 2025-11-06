# Bitget Multi-Symbol Cross-Sectional Futures Trading System

**NEW**: Trade ALL Bitget USDT-M futures simultaneously using cross-sectional ranking and online learning (no heavy training required).

## 🚀 Key Features

### Multi-Symbol Cross-Sectional Trading
- **Universe Management**: Auto-discovers ALL Bitget USDT-M futures contracts
- **Online Learning**: No heavy training - uses bandit algorithms (UCB) for adaptive selection
- **Cross-Sectional Ranking**: Ranks all symbols every decision period, picks top K
- **Rule-Based + Bandit**: Combines momentum/imbalance/volatility rules with online performance tracking

### Market Microstructure
- **Real-time Data**: WebSocket streams for all symbols (ticker + order book)
- **30+ Features**: Order book imbalance, depth, spread, returns, volatility per symbol
- **Online Statistics**: Rolling win-rate, Sharpe estimates, no batch retraining needed

### Fast Optional ML
- **Single Global Model**: One LightGBM trained on ALL symbols pooled (<5 min)
- **Symbol-Agnostic**: Same features work across all futures
- **Realistic Costs**: Taker fees (0.06%), slippage, spread costs modeled

### Production Features
- **M1 Optimized**: Native ARM, no LLVM/heavy dependencies
- **Risk Management**: Global daily loss limits, per-symbol caps, kill-switches
- **Full Type Safety**: mypy strict mode, comprehensive logging

## 📊 Architecture

```
WebSocket (Bitget) → Feature Engine → LightGBM Model → Signal → Execution
     ↓                     ↓                                        ↓
 Order Book          Imbalance                              REST API Orders
 + Ticker           + Depth Stats
```

## ⚡ Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. Generate test data (or collect live data)
poetry run python generate_test_data.py

# 3. Train model
poetry run python train_model.py

# 4. Run backtest
poetry run python run_backtest.py
```

## 📈 Features Computed

### Order Book Microstructure
- **Imbalance**: Top 1/3/5 levels bid-ask ratio
- **Depth**: Total size, size within 5/10bps of mid
- **Spread**: BPS, rolling mean/std

### Price Dynamics
- **Returns**: 1s, 5s, 10s, 20s, 30s windows
- **Volatility**: Rolling std over multiple windows
- **Momentum**: Cross-window momentum signals

### Market Meta
- **Funding rate**: Current funding
- **Mark-Index spread**: Basis risk indicator
- **Volume**: 24h volume statistics

## 🎯 Model Performance

From test backtest (10,000 samples, 5x leverage):
- **Total Trades**: 1,293
- **Avg Duration**: 5.4 seconds
- **Win Rate**: 33.18%
- **Profit Factor**: 1.08
- **Total Fees**: $383.07
- **Total Slippage**: $127.69

*Note: Ultra-short-term strategies battle against transaction costs*

## 🔧 Configuration

Edit `.env` or environment variables:

```bash
# API Credentials (for live trading)
BITGET_API_KEY=your_key
BITGET_API_SECRET=your_secret
BITGET_PASSPHRASE=your_passphrase

# Trading Parameters
SYMBOL=BTCUSDT
LEVERAGE=5
SANDBOX=true

# Risk Management
DAILY_LOSS_LIMIT=0.10  # 10% daily stop
MAX_DRAWDOWN_PCT=0.15  # 15% max drawdown
```

## 📚 Project Structure

```
bitgettrading/
├── src/bitget_trading/
│   ├── bitget_ws.py          # WebSocket client
│   ├── bitget_rest.py        # REST API with HMAC signing
│   ├── features.py           # Microstructure feature engine
│   ├── model.py              # LightGBM training/prediction
│   ├── backtest.py           # Realistic backtest engine
│   ├── config.py             # Pydantic configuration
│   └── logger.py             # Structured logging
├── generate_test_data.py     # Synthetic data generator
├── collect_data.py           # Live data collector
├── train_model.py            # Model training script
├── run_backtest.py           # Backtest runner
└── pyproject.toml            # Dependencies
```

## 🎓 How It Works

### 1. Data Collection
Real-time WebSocket streams from Bitget:
- **Ticker**: Last, bid, ask, mark, index, funding
- **Order Book**: Top 5 levels with sizes

### 2. Feature Engineering
Every 1 second, compute:
- Order book imbalance ratios
- Depth within X bps
- Rolling returns and volatility
- Spread statistics

### 3. Prediction
LightGBM predicts 10s ahead:
- **0 = Flat**: No clear edge
- **1 = Long**: Bullish signal
- **2 = Short**: Bearish signal

With confidence thresholds to avoid low-conviction trades.

### 4. Execution
Based on signal:
- Calculate position size (risk-based)
- Place market order via REST API
- Apply leverage (default 5x)
- Track PnL including fees/slippage

## ⚠️ Important Notes

### Transaction Costs
Ultra-short-term trading fights against:
- **Taker fees**: 0.06% per side = 0.12% round-trip
- **Spread**: ~3-5bps on BTC
- **Slippage**: ~2bps additional

For a 10-second trade to be profitable, you need >15-20bps price move.

### Risk Management
Built-in protections:
- Max daily loss limit
- Max drawdown stop
- Kill-switch on wide spreads
- Kill-switch on thin depth

### Live Trading
**Before going live:**
1. Test in sandbox mode
2. Start with minimal leverage (2-3x)
3. Use small position sizes
4. Monitor for 24-48 hours
5. Never risk more than you can afford to lose

## 🛠️ Development

### Training Your Own Model

```python
# Collect live data (1 hour)
poetry run python collect_data.py

# Train on your data
poetry run python train_model.py

# Backtest
poetry run python run_backtest.py
```

### Feature Importance

Top features (from test model):
1. `return_30s` - 30-second returns
2. `funding_rate` - Funding rate pressure
3. `best_bid/ask` - Top of book
4. `volatility_30s` - Recent volatility
5. `spread_mean_10s` - Spread dynamics

## 📊 Backtesting

Realistic simulator includes:
- Market/limit order execution
- Taker fees (0.06%)
- Maker fees (0.02%) if applicable
- Slippage (configurable)
- Spread costs (half spread on entry/exit)
- Funding payments (simplified for ultra-short)

Results saved to `backtest_results/`:
- `trades.csv` - All trades with PnL
- `metrics.csv` - Performance summary

## 🔐 Security

- API keys stored in `.env` (gitignored)
- HMAC SHA256 signing for all requests
- Sandbox mode enabled by default
- No hardcoded credentials

## 📝 License

MIT License

## ⚡ Performance Tips

- M1 Macs: LightGBM uses native ARM
- Use `num_threads=4` for optimal CPU usage
- Keep feature window < 60s for low latency
- WebSocket pings every 20s
- Batch predictions when possible

## 🤝 Contributing

This is a research/educational project. Feel free to:
- Fork and experiment
- Report bugs
- Suggest features
- Share improvements

## ⚠️ Disclaimer

**This software is for educational and research purposes only.**

- Cryptocurrency trading is extremely risky
- High leverage amplifies losses
- Past performance ≠ future results
- You can lose more than your initial investment
- Always use sandbox mode first
- Never trade with money you can't afford to lose

**No warranty or guarantee of profitability.**

---

Built with Python 3.12+ | LightGBM | asyncio | Pydantic | structlog

**Repository**: https://github.com/timtim-hub/bitgettrading
