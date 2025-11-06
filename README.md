# Bitget Trading Bot - SOLUSDT Perpetual Futures (50x Leverage)

Professional trading bot for SOLUSDT perpetual futures on Bitget exchange using a CNN-LSTM-GRU hybrid neural network model.

## Features

- **Deep Learning Model**: CNN-LSTM-GRU architecture for time series prediction
- **High Leverage**: Supports up to 125x leverage (default 50x)
- **Comprehensive Backtesting**: Full backtesting engine with performance metrics
- **Risk Management**: Built-in daily loss limits and position sizing
- **Real-time Trading**: Async WebSocket integration with CCXT Pro
- **Professional Logging**: Structured logging with structlog
- **Type Safety**: Full type hints with mypy strict mode
- **95%+ Test Coverage**: Comprehensive test suite with pytest

## Architecture

```
CNN (Feature Extraction) → LSTM (Temporal) → GRU (Refinement) → FC (Classification)
```

**Model Output**: 3 classes (Long, Short, Flat)

## Installation

### Prerequisites

- Python 3.12+
- Poetry (dependency management)
- CUDA (optional, for GPU acceleration)

### Setup

```bash
# Clone repository
git clone https://github.com/timtim-hub/bitgettrading.git
cd bitgettrading

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env

# Edit .env with your API credentials
nano .env
```

### Environment Variables

```bash
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_secret
BITGET_PASSPHRASE=your_passphrase
SYMBOL=SOL/USDT:USDT
LEVERAGE=50
RISK_PER_TRADE=0.008
SANDBOX=true  # Set to false for live trading
```

## Usage

### Backtesting

Run a backtest on 30 days of historical data:

```bash
poetry run python run_backtest.py
```

Results will be saved to `backtest_results/` directory.

### Live Trading

**⚠️ WARNING: Set `SANDBOX=true` in .env for testing first!**

```bash
poetry run python run_live.py
```

### Fetch Historical Data

```python
from src.bitget_trading.data_fetcher import fetch_historical_data
import asyncio

data = asyncio.run(fetch_historical_data(
    "SOL/USDT:USDT",
    "1m",
    days=30,
    save_path="data/sol_30d.csv"
))
```

## Configuration

All parameters are managed through `TradingConfig` (pydantic-settings):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbol` | SOL/USDT:USDT | Trading pair |
| `timeframe` | 1m | Candle timeframe |
| `leverage` | 50 | Leverage (1-125x) |
| `risk_per_trade` | 0.008 | Risk per trade (0.8%) |
| `daily_loss_limit` | 0.10 | Max daily loss (10%) |
| `seq_len` | 60 | Model sequence length |
| `fee` | 0.0006 | Taker fee (0.06%) |

## Model

### Architecture

```python
CNN_LSTM_GRU(
    n_features=68,      # Technical indicators
    lstm_hidden=178,
    gru_hidden=92,
    dropout=0.31
)
```

### Training Your Own Model

The model expects 68 technical indicators:
- RSI (multiple periods)
- MACD
- Bollinger Bands
- EMAs (8, 21, 50, 200)
- Supertrend
- OBV, VWAP
- Stochastic, ADX, CCI, Williams %R
- ATR, MFI
- Custom features (returns, momentum, volatility)

Place trained weights in `models/sol_model_2025.pth`.

## Backtesting Results

Example backtest on 30 days (50x leverage):

```
Total Trades: 245
Win Rate: 58.37%
Total PnL: $3,245.67 (32.46%)
ROI: 32.46%
Max Drawdown: $542.31 (5.42%)
Sharpe Ratio: 2.34
Sortino Ratio: 3.12
Profit Factor: 2.18
```

## Risk Disclaimer

**⚠️ IMPORTANT**: Trading cryptocurrencies with leverage is extremely risky.

- Never trade with money you can't afford to lose
- Always test in sandbox mode first
- Use proper position sizing and stop losses
- Past performance does not guarantee future results
- This bot is for educational purposes

## Development

### Running Tests

```bash
poetry run pytest
```

### Linting

```bash
poetry run ruff check --fix
poetry run black .
```

### Type Checking

```bash
poetry run mypy src/
```

### Pre-commit Hooks

```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```

## Project Structure

```
bitgettrading/
├── src/
│   └── bitget_trading/
│       ├── __init__.py
│       ├── config.py          # Configuration management
│       ├── logger.py          # Structured logging
│       ├── model.py           # CNN-LSTM-GRU model
│       ├── features.py        # Technical indicators
│       ├── backtest.py        # Backtesting engine
│       ├── live_trader.py     # Live trading engine
│       └── data_fetcher.py    # Data fetching
├── tests/                     # Test suite
├── run_backtest.py           # Backtest runner
├── run_live.py               # Live trader runner
├── pyproject.toml            # Dependencies
├── .env.example              # Environment template
└── README.md
```

## Performance Optimization

- Uses PyTorch with CUDA support
- Async I/O with CCXT Pro WebSockets
- Efficient batch prediction
- Minimal data copying
- Structured logging (JSON in production)

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/timtim-hub/bitgettrading/issues
- Documentation: See `/docs` folder

## License

MIT License - See LICENSE file for details

## Acknowledgments

- CCXT Pro for exchange integration
- PyTorch for deep learning
- pandas-ta for technical indicators

---

**Built with Python 3.12+ | Type-safe | Production-ready**

