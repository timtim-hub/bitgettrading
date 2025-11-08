# 📋 BACKTESTING SYSTEM - MANDATORY INSTRUCTIONS

## 🎯 CORE REQUIREMENTS (NEVER FORGET!)

### 1. Strategy File Management
- ✅ **ALWAYS create a NEW file for each strategy** - NEVER overwrite existing strategies
- ✅ Strategy files: `strategies/strategy_XXX.json` (increment XXX)
- ✅ Find next ID: `max(existing) + 1`
- ✅ Keep ALL old strategies for comparison

### 2. Testing Protocol (MANDATORY 2-STEP PROCESS)

**STEP 1: Test on ALL tokens (338)**
- Test every new strategy on complete token universe
- Generate metrics for ALL tokens
- Save to: `backtest_results/{strategy_name}_all338_*.json`

**STEP 2: Test on 5%+ ROI tokens**
- Filter tokens with `total_roi_pct >= 5.0` from Step 1
- Re-test strategy on filtered subset ONLY
- Save to: `backtest_results/{strategy_name}_5pct_plus_*.json`

### 3. Initial Capital
- **ALWAYS $50 per token** (never change this)
- Total portfolio capital = $50 × number of tokens
- Example: 48 tokens = $2,400 total capital

### 4. Required Metrics in Reports

**Must Always Include:**
1. **Portfolio ROI** (most important!)
2. **ROI per Day** (daily compounded)
3. **ROI per Week** (weekly compounded)
4. **ROI per Month** (monthly compounded)
5. **Trades per Day** (TOTAL, not per token)
6. **Win Rate %**
7. **Sharpe Ratio**
8. **Max Drawdown %**
9. **Profit Factor**
10. **Profitable Tokens Count**
11. **Total Tokens Tested**
12. **Final Portfolio Value**
13. **Total Profit/Loss ($)**

### 5. Leverage and Fees
- **Leverage:** 25x (match live trading!)
- **Taker Fee:** 0.06% (Bitget standard)
- **Round-trip Fee:** 0.12% per complete trade

---

## 🧠 MACHINE LEARNING STRATEGIES (LightGBM)

### Feature Engineering Requirements

**Technical Indicators (Input Features):**
1. **Price Features:**
   - Returns (1, 3, 5, 10, 15 periods)
   - Log returns
   - Price volatility (rolling std)
   - High-Low spread
   - Close-Open spread

2. **Momentum Indicators:**
   - RSI (14, 21)
   - Stochastic RSI
   - ROC (Rate of Change)
   - Williams %R
   - CCI (Commodity Channel Index)

3. **Trend Indicators:**
   - MACD (histogram, signal, diff)
   - EMA (9, 21, 50)
   - SMA (20, 50, 200)
   - ADX (trend strength)
   - Aroon (up, down)

4. **Volatility Indicators:**
   - Bollinger Bands (width, %B)
   - ATR (Average True Range)
   - Keltner Channels
   - Standard deviation

5. **Volume Indicators:**
   - Volume ratio (vs MA)
   - OBV (On-Balance Volume)
   - MFI (Money Flow Index)
   - VWAP distance
   - Chaikin Money Flow

6. **Time Features:**
   - Hour of day (0-23)
   - Day of week (0-6)
   - Time since last trade
   - Candle age

**Target Variable:**
- Binary: Price up/down in next N candles (classification)
- Continuous: % price change in next N candles (regression)
- Multi-class: Strong up / weak up / flat / weak down / strong down

**Training Protocol:**
1. Use 70% data for training
2. Use 15% for validation
3. Use 15% for testing
4. Walk-forward validation (avoid look-ahead bias)
5. Cross-validation (5-fold minimum)

**LightGBM Hyperparameters:**
```python
params = {
    'objective': 'binary',  # or 'regression'
    'metric': 'auc',  # or 'rmse'
    'boosting_type': 'gbdt',
    'num_leaves': 31,
    'learning_rate': 0.05,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'max_depth': -1,
    'min_data_in_leaf': 20,
    'lambda_l1': 0.1,
    'lambda_l2': 0.1,
    'verbose': -1
}
```

### Model Training Requirements

1. **Data Preparation:**
   - Remove NaN values
   - Normalize/standardize features
   - Handle outliers (clip at 3-5 sigma)
   - Balance classes (for classification)

2. **Feature Importance:**
   - Analyze feature importance after training
   - Remove features with <1% importance
   - Re-train with selected features

3. **Prediction Confidence:**
   - For classification: Use probability scores (0-1)
   - Threshold: Only trade if probability > 0.65 (65% confidence)
   - For regression: Only trade if predicted return > 0.5%

4. **Model Retraining:**
   - Retrain every 7 days (weekly)
   - Use sliding window (last 30 days)
   - Keep model versioned

---

## 📊 STRATEGY VARIATIONS TO TEST

### LightGBM Strategy #1: Pure ML Classifier
- **Primary Signal:** LightGBM prediction (>65% confidence)
- **Confirmation:** None (trust the model)
- **Features:** All 50+ features
- **Target:** Binary (up/down in next 5 candles)

### LightGBM Strategy #2: ML + Volume Confirmation
- **Primary Signal:** LightGBM prediction (>60% confidence)
- **Confirmation:** Volume > 1.5x average
- **Features:** All features + volume emphasis
- **Target:** Binary (up/down in next 3 candles)

### LightGBM Strategy #3: ML + Trend Filter
- **Primary Signal:** LightGBM prediction (>70% confidence)
- **Confirmation:** EMA(9) > EMA(21) (uptrend only)
- **Features:** All features + trend indicators
- **Target:** Multi-class (strong up / weak up / flat / weak down / strong down)

### LightGBM Strategy #4: ML Ensemble + TA
- **Primary Signal:** Average of 3 LightGBM models (>65% confidence)
- **Confirmation:** RSI < 70 AND Volume > 1.3x average
- **Features:** Different feature sets for each model
- **Target:** Regression (% change in next 5 candles)

### LightGBM Strategy #5: ML with Dynamic Stop-Loss
- **Primary Signal:** LightGBM prediction (>65% confidence)
- **Stop-Loss:** Model predicts expected volatility, SL = 2 × predicted volatility
- **Take-Profit:** Model predicts expected gain, TP = predicted gain × 0.8
- **Features:** All features + volatility prediction
- **Target:** Two outputs (direction + magnitude)

---

## 🔧 BACKTESTER IMPROVEMENTS

### Current Implementation
✅ Parallel processing (10 workers)
✅ Cached data loading
✅ Comprehensive metrics
✅ JSON output
✅ Markdown reports

### Required Improvements

1. **Add ML Model Support:**
   ```python
   class MLBacktestEngine:
       def __init__(self, model_path, strategy):
           self.model = lgb.Booster(model_file=model_path)
           self.strategy = strategy
       
       def predict(self, features):
           return self.model.predict(features)
   ```

2. **Feature Calculation:**
   ```python
   def calculate_features(df):
       # Add all 50+ features
       df['rsi'] = ta.rsi(df['close'], 14)
       df['macd'] = ta.macd(df['close'])
       # ... 50+ more features
       return df
   ```

3. **Walk-Forward Validation:**
   ```python
   def walk_forward_backtest(df, strategy, train_window=30, test_window=7):
       for i in range(0, len(df), test_window):
           train_data = df[i:i+train_window]
           test_data = df[i+train_window:i+train_window+test_window]
           # Train model on train_data
           # Test on test_data
   ```

4. **Model Performance Tracking:**
   - Track prediction accuracy
   - Track confidence calibration
   - Track feature importance over time

5. **Advanced Metrics:**
   - Calmar Ratio (return / max drawdown)
   - Sortino Ratio (downside risk)
   - Information Ratio
   - Alpha / Beta
   - Win/Loss streak analysis

---

## 🎯 TESTING WORKFLOW

### Step-by-Step Process

1. **Create New Strategy:**
   ```bash
   # Find next ID
   ls strategies/ | sort | tail -1
   # Create strategy_046.json, strategy_047.json, etc.
   ```

2. **Run Complete Test Pipeline:**
   ```bash
   python filtered_backtest_pipeline.py
   ```
   - Automatically tests on ALL 338 tokens
   - Automatically filters to 5%+ ROI tokens
   - Automatically re-tests on filtered subset
   - Generates all required reports

3. **Analyze Results:**
   ```bash
   cat FILTERED_BACKTEST_RESULTS.md
   ```
   - Check Portfolio ROI (Step 4)
   - If > 20%, strategy is good!
   - If < 10%, refine and retry

4. **Compare Strategies:**
   ```bash
   python analyze_all_strategies.py
   cat COMPREHENSIVE_STRATEGY_REPORT.md
   ```

5. **Deploy Best Strategy:**
   - Update `live_trade.py` with best strategy ID
   - Update token whitelist to top 30-50 performers
   - Paper trade for 24-48 hours
   - Deploy live with small capital

---

## 📈 SUCCESS CRITERIA

### Minimum Acceptable Performance
- Portfolio ROI (on 5%+ filtered tokens): **> 15%**
- Win Rate: **> 55%**
- Sharpe Ratio: **> 1.0**
- Max Drawdown: **< 30%**
- Profitable Tokens: **> 70%**

### Excellent Performance
- Portfolio ROI (on 5%+ filtered tokens): **> 25%**
- Win Rate: **> 60%**
- Sharpe Ratio: **> 1.5**
- Max Drawdown: **< 20%**
- Profitable Tokens: **> 85%**

### World-Class Performance (GOAL!)
- Portfolio ROI (on 5%+ filtered tokens): **> 35%**
- Win Rate: **> 65%**
- Sharpe Ratio: **> 2.0**
- Max Drawdown: **< 15%**
- Profitable Tokens: **> 90%**

---

## ⚠️ CRITICAL REMINDERS

1. **NEVER overwrite existing strategy files**
2. **ALWAYS test on ALL 338 tokens first**
3. **ALWAYS re-test on 5%+ ROI tokens second**
4. **ALWAYS use $50 initial capital per token**
5. **ALWAYS include ROI per day/week/month in reports**
6. **ALWAYS include trades per day in reports**
7. **ALWAYS use 25x leverage (match live trading)**
8. **ALWAYS account for 0.06% taker fees**
9. **ALWAYS commit results to GitHub**
10. **ALWAYS document strategy rationale**

---

## 📁 File Structure

```
strategies/
├── strategy_001.json - strategy_040.json  # Original 40 strategies
├── strategy_041.json - strategy_044.json  # Test strategies (failed)
├── strategy_045.json                       # LightGBM (no ML yet)
├── strategy_046.json                       # NEW: LightGBM Pure ML
├── strategy_047.json                       # NEW: LightGBM + Volume
├── strategy_048.json                       # NEW: LightGBM + Trend
└── ...                                     # More strategies

backtest_results/
├── {strategy_name}_all338_detailed_{timestamp}.json
├── {strategy_name}_all338_summary_{timestamp}.json
├── {strategy_name}_5pct_plus_detailed_{timestamp}.json
└── {strategy_name}_5pct_plus_summary_{timestamp}.json

models/ (NEW!)
├── lightgbm_model_v1.txt
├── lightgbm_model_v2.txt
└── feature_importance.json
```

---

## 🚀 IMMEDIATE ACTION ITEMS

1. ✅ Create this instructions file (DONE)
2. ⬜ Implement proper LightGBM model training
3. ⬜ Create feature engineering module
4. ⬜ Create 3+ LightGBM strategies with REAL ML
5. ⬜ Test all strategies using 2-step process
6. ⬜ Generate comprehensive reports
7. ⬜ Commit everything to GitHub

---

**Last Updated:** November 8, 2025  
**Version:** 3.0  
**Status:** ACTIVE - MUST FOLLOW ALL RULES!  
**Goal:** Find the best trading strategy in the world! 🚀

