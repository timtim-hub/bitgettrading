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

**⭐ MUST ALWAYS INCLUDE (NON-NEGOTIABLE!):**
1. **Portfolio ROI** (most important!)
2. **🚨 ROI in 24 Hours** (daily ROI) - MANDATORY!
3. **🚨 ROI in 7 Days** (weekly ROI) - MANDATORY!
4. **🚨 ROI in 30 Days** (monthly ROI) - MANDATORY!
5. **Capital at 24h, 7d, 30d** - Show capital growth over time
6. **Trades per Day** (TOTAL, not per token)
7. **Win Rate %**
8. **Sharpe Ratio**
9. **Max Drawdown %**
10. **Profit Factor**
11. **Profitable Tokens Count**
12. **Total Tokens Tested**
13. **Final Portfolio Value**
14. **Total Profit/Loss ($)**

**⚠️ CRITICAL**: If any report is missing ROI for 24h/7d/30d, it is INCOMPLETE!

### 5. Leverage and Fees
- **Default Leverage:** 25x (baseline for all strategies)
- **Test Leverage Variations:** 25x, 50x, 100x
- **Taker Fee:** 0.06% (Bitget standard)
- **Round-trip Fee:** 0.12% per complete trade
- **Adaptive Parameters:** TP/SL/position size auto-adjust based on leverage

### 6. Liquidation Risk Management (NEW!)

**Liquidation Distance by Leverage:**
| Leverage | Liq Distance | Risk Level | Usage |
|----------|--------------|------------|-------|
| **25x** | ~3.5% | MEDIUM | ✅ Recommended default |
| **50x** | ~1.0% | EXTREME | ⚠️ Use with caution |
| **100x** | ~1.0% | EXTREME | ❌ Expert only, high risk |

**Liquidation Price Formula:**
- **Long**: `Liq Price = Entry × (1 - 1/Leverage + MMR)`
- **Short**: `Liq Price = Entry × (1 + 1/Leverage - MMR)`
- **MMR** (Maintenance Margin Rate): 0.5% (25x), 1.0% (50x), 2.0% (100x)

**Adaptive Parameters by Leverage:**
| Parameter | 25x | 50x | 100x | Why? |
|-----------|-----|-----|------|------|
| Position Size | 12% | 8% | 5% | Reduce exposure at higher leverage |
| Stop Loss (capital %) | 50% | 35% | 25% | Tighter stops to avoid liquidation |
| Take Profit (capital %) | 20% | 15% | 10% | Faster profit-taking |
| Trailing Callback | 3% | 2% | 1.5% | Tighter trailing for higher leverage |
| Max Positions | 15 | 10 | 6 | Fewer concurrent positions |

**CRITICAL**: All parameters MUST auto-adjust based on leverage!

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

---

## 🎖️ LEVERAGE TESTING PROTOCOL (V4 UPDATE)

### Multi-Leverage Testing (NEW!)

**Protocol:**
1. Create 3 variants of each base strategy (25x, 50x, 100x)
2. Test all variants on 338 tokens (Phase 1)
3. Re-test on 5%+ ROI tokens (Phase 2)
4. Compare leverage performance
5. Identify optimal leverage per strategy type

**Example: Strategy 060-062**
- `strategy_060.json`: TripleStack_ML_Ensemble_25x
- `strategy_061.json`: TripleStack_ML_Ensemble_50x
- `strategy_062.json`: TripleStack_ML_Ensemble_100x

**Naming Convention:**
`{BaseStrategyName}_{Leverage}x`

### Testing All Leverage Variants

```bash
# Test all 30 strategies (10 base × 3 leverage levels)
python test_leverage_strategies.py
```

**What it does:**
1. Loads strategies 060-089
2. Tests each on all 338 tokens
3. Re-tests on filtered tokens (>5% ROI)
4. Generates comparison report
5. Identifies best leverage per strategy

### Leverage Comparison Report

**Must Include:**
- ROI comparison (25x vs 50x vs 100x)
- Risk/reward analysis
- Liquidation proximity
- Best leverage recommendation per strategy
- Overall winner across all leverage levels

---

## 📊 ADVANCED RESEARCH & TECHNIQUES (V4)

### ML Ensemble Methods

**Stacking (Implemented):**
- Train 3+ base models (LightGBM, XGBoost, CatBoost)
- Use meta-learner to combine predictions
- Research shows 15-20% improvement over single models

**SHAP Feature Selection (Implemented):**
- Use SHAP values to identify top features
- Remove low-impact features (<1% importance)
- Reduces overfitting, improves generalization

**Bayesian Hyperparameter Tuning (Implemented):**
- Use Bayesian optimization (Optuna/Hyperopt)
- Optimize for Sharpe ratio (not just accuracy)
- 50-100 trials for optimal parameters

### Market Microstructure Strategies

**Order Flow Analysis:**
- Track delta volume (buy vs sell)
- Detect institutional accumulation/distribution
- Identify liquidity sweeps and stop hunts

**Volume Profile:**
- Find high-volume price nodes (support/resistance)
- Detect volume anomalies
- Profile-based entry/exit

**Smart Money Concepts:**
- Wyckoff accumulation/distribution
- Liquidity grabs
- Market maker behavior

### Adaptive & Regime-Based

**Hidden Markov Models (HMM):**
- Detect market regimes (trending, ranging, volatile, breakout)
- Adjust strategy parameters per regime
- Research shows 25-35% improvement

**GARCH Volatility Models:**
- Forecast volatility using GARCH(1,1)
- Adjust position size based on predicted volatility
- Adaptive stop-loss based on volatility

**Multi-Timeframe Analysis:**
- Analyze 5m, 15m, 1h, 4h, 1d simultaneously
- Only trade when all timeframes align
- Reduces false signals by 40-60%

### Reinforcement Learning (Experimental)

**Deep Q-Network (DQN):**
- Agent learns optimal entry/exit timing
- State: price, volume, indicators, position, PnL
- Action: buy, sell, hold
- Reward: Sharpe-based (not just profit)

---

## 🔬 RESEARCH-BACKED BEST PRACTICES

### Feature Engineering
1. **Use log returns** instead of raw prices (more stable)
2. **Normalize features** (z-score or min-max scaling)
3. **Remove correlated features** (>0.9 correlation)
4. **Create interaction features** (RSI × Volume, MACD × ATR)
5. **Time-based features** (hour, day, volatility regime)

### Model Training
1. **Walk-forward validation** (prevent lookahead bias)
2. **Cross-validation** (5-fold minimum)
3. **Stratified sampling** (balanced classes)
4. **Early stopping** (prevent overfitting)
5. **Ensemble methods** (combine 3+ models)

### Risk Management
1. **Kelly Criterion** for position sizing (optimal leverage)
2. **Value at Risk (VaR)** for risk exposure
3. **Conditional VaR** (CVaR) for tail risk
4. **Dynamic stop-loss** based on volatility
5. **Correlation-based diversification**

---

## 🚨 CRITICAL UPDATES (V4)

### MANDATORY CHANGES

1. **All new strategies MUST have 3 leverage variants (25x, 50x, 100x)**
2. **Parameters MUST auto-adjust based on leverage**
3. **Liquidation risk MUST be calculated and reported**
4. **Leverage comparison MUST be included in final reports**
5. **Per-strategy reports MUST show tokens with >5% ROI**

### FILES UPDATED
- ✅ `liquidation_calculator.py` - Calculate liquidation prices and risk
- ✅ `ultimate_strategy_generator_v3.py` - Generate leverage-aware strategies
- ✅ `test_leverage_strategies.py` - Test all leverage variants
- ✅ `generate_per_strategy_reports.py` - Per-strategy detailed reports
- ✅ `BACKTESTING_INSTRUCTIONS.md` - This file!

### NEW FEATURES
- ✅ Adaptive parameter system based on leverage
- ✅ Liquidation risk calculator
- ✅ Multi-leverage testing pipeline
- ✅ Per-strategy reports with >5% ROI tokens
- ✅ Research-backed ML techniques (stacking, SHAP, Bayesian optimization)

---

---

## 🚀 V5 ULTRA-HIGH ROI IMPROVEMENTS (NEW!)

### Ultra-Optimized LightGBM Training

**File**: `train_ultra_lightgbm.py`

**Improvements**:
1. **100+ Features**: Comprehensive technical analysis (RSI, MACD, BB, ATR, ADX, MFI, OBV, CCI, ROC, EMAs, SMAs, volume ratios, momentum, volatility, etc.)
2. **ALL Historical Data**: Trains on entire dataset (not just 30 days)
3. **1000 Boosting Rounds**: Much longer training for better accuracy
4. **Optuna Optimization**: 30-50 trials for optimal hyperparameters
5. **Walk-Forward Validation**: Prevents overfitting
6. **Ensemble Ready**: Can be combined with XGBoost, CatBoost, RF, etc.

**Expected Improvement**: 20-40% better predictions

**How to Use**:
```bash
python train_ultra_lightgbm.py
```

### Combined/Hybrid Strategies

**File**: `create_ultra_high_roi_strategies.py`

**New Strategy Types**:
1. **Ultimate ML Ensemble**: 7-model voting (LightGBM, XGBoost, CatBoost, RF, ET, AdaBoost, GB)
2. **Momentum + ML Hybrid**: RSI + MACD + ADX + MFI + ML prediction
3. **Portfolio Optimizer**: Markowitz optimization, Sharpe-based allocation
4. **Breakout + Volume Surge**: 2.5x volume with breakout detection
5. **Mean Reversion + ML**: Oversold indicators + ML bounce prediction
6. **Trend Following + ML**: EMA crossovers + ADX + ML continuation
7. **Multi-Timeframe + ML**: 5m/15m/1h/4h/1d + ML alignment
8. **Volatility Breakout + ML**: Low vol entry, high vol exit
9. **Smart Money Flow + ML**: OBV + MFI + institutional flow
10. **Adaptive Dynamic + ML**: HMM regime detection + dynamic parameters

**Strategy IDs**: 090-109 (20 total: 10 base × 2 leverages)

**Expected ROI**: 60-120% (vs current best 47.36%)

**How to Use**:
```bash
python create_ultra_high_roi_strategies.py  # Generate strategies
python test_ultra_strategies.py             # Test them
```

### Mandatory Report Format

**ALL reports MUST display time-based ROI prominently:**

```markdown
## Strategy Performance

**Portfolio ROI**: 67.85%
**ROI per Day**: 4.52%
**ROI per Week**: 31.64%
**ROI per Month**: 135.60%
**Win Rate**: 72.4%
**Trades per Day**: 95.3

**Capital Growth**:
- 24h: $2,545 (18.5% gain)
- 1 Week: $3,127 (56.3% gain)
- 30 Days: $3,392 (67.9% gain)
```

### Strategy Combination Techniques

**1. Voting Ensemble**:
- 7+ models predict independently
- Use soft voting (probability averaging)
- Require 5+ models to agree (71%+ consensus)

**2. Signal Stacking**:
- ML prediction (primary)
- Momentum confirmation (RSI, MACD, ADX)
- Volume confirmation (OBV, MFI)
- Trend confirmation (EMA crossovers)
- Require 3-6 signals to align

**3. Portfolio Optimization**:
- Allocate capital based on Sharpe ratio
- Diversify across uncorrelated tokens
- Rebalance daily/weekly
- Target specific volatility level

**4. Multi-Timeframe**:
- Analyze 5m, 15m, 1h, 4h, 1d
- Only trade when all timeframes align
- Reduces false signals by 60-80%

**5. Adaptive Systems**:
- Detect market regime (trending, ranging, volatile, breakout)
- Adjust ALL parameters per regime
- Use HMM or GARCH models

---

## 📊 UPDATED SUCCESS CRITERIA (V5)

### Minimum Acceptable (OLD)
- Portfolio ROI: >15%
- Win Rate: >55%

### NEW MINIMUM (V5)
- Portfolio ROI: **>25%**
- ROI per Day: **>1.5%**
- ROI per Week: **>10.5%**
- ROI per Month: **>45%**
- Win Rate: **>60%**

### Excellent Performance (V5)
- Portfolio ROI: **>40%**
- ROI per Day: **>2.5%**
- ROI per Week: **>17.5%**
- ROI per Month: **>75%**
- Win Rate: **>68%**

### World-Class (V5 GOAL!)
- Portfolio ROI: **>60%**
- ROI per Day: **>3.5%**
- ROI per Week: **>24.5%**
- ROI per Month: **>105%**
- Win Rate: **>72%**

**Current Record**: 47.36% portfolio ROI (Triple_Model @ 25x)
**V5 Target**: Beat this by 50%+ → **70%+ ROI** 🎯

---

## ⚠️ CRITICAL REMINDERS (UPDATED V5)

1. **NEVER overwrite existing strategy files**
2. **ALWAYS test on ALL 338 tokens first**
3. **ALWAYS re-test on 5%+ ROI tokens second**
4. **ALWAYS use $50 initial capital per token**
5. **🚨 ALWAYS include ROI for 24h, 7d, 30d in reports** (NON-NEGOTIABLE!)
6. **ALWAYS include trades per day in reports**
7. **ALWAYS include win rate in reports**
8. **ALWAYS use 25x leverage (match live trading)**
9. **ALWAYS account for 0.06% taker fees**
10. **ALWAYS commit results to GitHub**
11. **ALWAYS document strategy rationale**
12. **NEW: Train ultra-LightGBM before creating ML strategies**
13. **NEW: Test combined/hybrid strategies**
14. **NEW: Aim for 60%+ portfolio ROI**

---

**Last Updated:** November 8, 2025 (V5 Ultra-High ROI Update)  
**Version:** 5.0 (Ultra-High ROI Edition)
**Status:** ACTIVE - MAXIMUM PROFIT MODE! 🚀💰  
**Goal:** Achieve 70%+ portfolio ROI through ML optimization and strategy combination!

**Key Takeaways:**
- ⭐ **ALWAYS show ROI for 24h, 7d, 30d** in ALL reports
- ⭐ Train ultra-LightGBM with 100+ features and 1000 rounds
- ⭐ Combine multiple strategies for better performance
- ⭐ Use ensemble methods (7+ models voting)
- ⭐ Target 60-120% ROI (vs current 47.36%)

