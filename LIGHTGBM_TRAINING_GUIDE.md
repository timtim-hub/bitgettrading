# 🚀 LightGBM Training Guide for Live Trading

This guide explains how to train LightGBM models for live trading on Bitget futures.

## 📋 Overview

The training system creates optimized LightGBM models for **short-term trading (1-10 minutes)** with **high win rate** predictions. Each model is trained specifically for one token using 6 months of 5-minute candle data.

## 🎯 Training Configuration

### Data Requirements
- **Timeframe**: 5-minute candles
- **Data Period**: 6 months (180 days)
- **Minimum Samples**: 1,000 candles per token
- **Prediction Horizon**: 2 candles ahead (10 minutes)
- **Price Threshold**: 0.2% minimum price change to be significant

### Model Optimization
- **Hyperparameter Tuning**: Optuna with 50 trials
- **Objective**: Maximize win rate (accuracy) while maintaining precision and recall
- **Early Stopping**: 100 rounds
- **Max Boosting Rounds**: 2,000
- **Train/Test Split**: 80/20

### Target Variable
The model predicts whether price will move **UP** or **DOWN** by at least 0.2% in the next 10 minutes:
- **1 (LONG)**: Price will go UP by ≥0.2%
- **0 (SHORT)**: Price will go DOWN by ≥0.2%
- **-1 (NEUTRAL)**: No significant movement (excluded from training)

## 📁 File Structure

After training, models are saved in:

```
models/live_trading/
├── {SYMBOL}_lightgbm_{TIMESTAMP}.txt    # Trained model
├── {SYMBOL}_latest.txt                   # Symlink to latest model
├── {SYMBOL}_features.txt                 # Feature list used
├── metadata/
│   └── {SYMBOL}_metadata_{TIMESTAMP}.json  # Training metadata
└── training_summary.json                  # Overall summary
```

## 🚀 How to Train Models

### Step 1: Install Dependencies

```bash
pip install lightgbm optuna pandas numpy scikit-learn aiohttp
```

**Required packages**:
- `lightgbm`: Gradient boosting framework
- `optuna`: Hyperparameter optimization
- `pandas`, `numpy`: Data processing
- `scikit-learn`: Machine learning utilities
- `aiohttp`: Async HTTP for API calls

### Step 2: Run Training Script

```bash
python train_live_lightgbm.py
```

**⚡ Parallel Processing**: The training script uses **full parallel processing**:
- **Phase 1**: Fetches historical data for all tokens in parallel (async I/O, up to 20 concurrent requests)
- **Phase 2**: Trains models for all tokens in parallel (CPU-bound, uses all CPU cores)

**Expected Speedup**: 
- **Sequential**: ~6-12 hours for 300+ tokens
- **Parallel**: ~1-3 hours for 300+ tokens (depending on CPU cores)
- **Speedup**: ~4-6x faster with 8 CPU cores

The script will:
1. Fetch all active Bitget futures symbols from the API
2. For each symbol:
   - Fetch 6 months of 5-minute candle data
   - Calculate 58+ technical features
   - Create short-term prediction targets
   - Optimize hyperparameters with Optuna
   - Train the final model
   - Save model, features, and metadata
3. Generate a training summary

### Step 3: Monitor Progress

The script prints progress for each symbol:
- ✅ Successfully trained models
- ⚠️ Warnings (insufficient data, missing features)
- ❌ Errors (API failures, training errors)

### Step 4: Check Results

After training completes, check:
- `models/live_trading/training_summary.json` - Overall statistics
- `models/live_trading/metadata/{SYMBOL}_metadata_*.json` - Individual model metrics

## 📊 Model Performance Metrics

Each model reports:
- **Accuracy (Win Rate)**: Percentage of correct predictions
- **Precision**: Percentage of positive predictions that are correct
- **Recall**: Percentage of actual positives that were predicted
- **F1 Score**: Harmonic mean of precision and recall
- **AUC**: Area under ROC curve

**Target Performance**:
- Win Rate: >60% (aim for 65%+)
- Precision: >60%
- Recall: >60%
- F1 Score: >60%

## 🔄 Retraining Models

### When to Retrain

Retrain models when:
- **New data available**: After 1-2 months of new data
- **Performance degrades**: Win rate drops below 55%
- **Market regime changes**: Major market shifts (bull/bear transitions)
- **New features added**: If you add new technical indicators

### How to Retrain

1. **Update data cache** (optional):
   ```bash
   # Clear old cache to force fresh data fetch
   rm backtest_data/*_5m_180d.pkl
   ```

2. **Run training script**:
   ```bash
   python train_live_lightgbm.py
   ```

3. **Verify new models**:
   - Check `training_summary.json` for average metrics
   - Compare with previous training run
   - Test on recent data if possible

### Retraining Specific Tokens

To retrain only specific tokens, modify the script to filter symbols:

```python
# In main() function, filter symbols:
all_symbols = [s for s in all_symbols if s in ["BTCUSDT", "ETHUSDT", ...]]
```

## ⚙️ Customizing Training

### Adjust Prediction Horizon

For different timeframes:
- **1-5 min trades**: `prediction_horizon: 1` (5 minutes)
- **5-10 min trades**: `prediction_horizon: 2` (10 minutes) ← Default
- **10-15 min trades**: `prediction_horizon: 3` (15 minutes)

### Adjust Price Threshold

For different sensitivity:
- **More trades, lower accuracy**: `min_price_change: 0.001` (0.1%)
- **Fewer trades, higher accuracy**: `min_price_change: 0.003` (0.3%) ← Default is 0.002

### Adjust Optimization

For faster training (lower quality):
- `n_trials: 20` (instead of 50)
- `num_boost_round: 1000` (instead of 2000)

For better quality (slower training):
- `n_trials: 100`
- `num_boost_round: 3000`

## 🐛 Troubleshooting

### "Insufficient data" Error

**Cause**: Token doesn't have enough historical data

**Solution**:
- Check if token is new (recently listed)
- Reduce `min_samples` in config (not recommended)
- Skip token and train others

### "Too many missing features" Error

**Cause**: Feature calculation failed for some indicators

**Solution**:
- Check if data has enough history (need 200+ candles for some indicators)
- Verify `ml_feature_engineering.py` is working correctly
- Reduce required feature percentage (not recommended)

### API Rate Limiting

**Cause**: Too many API requests too quickly

**Solution**:
- Script already includes delays between requests
- If still hitting limits, add longer delays in `data_fetcher.py`
- Use cached data when possible (`use_cache=True`)

### Low Win Rate (<55%)

**Cause**: Model not learning patterns, or market too random

**Solution**:
- Increase training data period (try 12 months)
- Adjust prediction horizon (try 1 or 3 candles)
- Adjust price threshold (try 0.001 or 0.003)
- Check if token has clear trends (some tokens are too random)

## 📈 Best Practices

1. **Train on recent data**: Use last 6 months, not old data
2. **Monitor performance**: Check win rate regularly
3. **Retrain periodically**: Every 1-2 months or when performance drops
4. **Test before live**: Paper trade with new models first
5. **Keep old models**: Don't delete previous models until new ones are verified
6. **Track metrics**: Compare training metrics across retraining sessions

## 🔗 Integration with Live Trading

Models are automatically loaded by `live_trade.py`:
- Looks for `{SYMBOL}_latest.txt` in `models/live_trading/`
- Loads corresponding feature list from `{SYMBOL}_features.txt`
- Uses model predictions for entry/exit signals

See `live_trade.py` for integration details.

## 📝 Notes

- **Training time**: ~2-5 minutes per token (depends on data size and Optuna trials)
- **Total time**: ~6-12 hours for all 300+ tokens (can be parallelized)
- **Storage**: ~1-5 MB per model (300+ tokens = ~1-2 GB total)
- **CPU usage**: Uses all available cores (set `N_JOBS` to limit)

## 🎯 Goal

**Maximum Win Rate** for short-term trades (1-10 minutes) with high leverage.

The models are optimized specifically for:
- Quick entry/exit decisions
- High confidence predictions
- Minimal false signals
- Maximum profitability on short timeframes

---

**Last Updated**: 2025-11-08
**Training Script**: `train_live_lightgbm.py`
**Models Directory**: `models/live_trading/`

