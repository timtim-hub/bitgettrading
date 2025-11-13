# 🚀 Bitget Trading Strategy - Ultra-Short-Term Scalping

## Overview

Our trading strategy is a **ultra-short-term scalping system** that leverages **25x leverage** on Bitget futures to capture small, consistent profits from market microstructure movements. The system is designed for **maximum safety and reliability** with **exchange-side protection** that works even if the bot crashes.

**Key Characteristics:**
- ⚡ **Ultra-fast trades:** 1-10 minute holding periods
- 🎯 **Precise entries:** RSI-based momentum signals
- 🛡️ **Multi-layer protection:** Exchange-side TP/SL with verification
- 📈 **Consistent ROI:** 5-12% per trade target
- 🔄 **High frequency:** Multiple trades per hour

---

## 🏗️ System Architecture

### 1. **Exchange-Side Protection (PRIMARY SAFETY)**
All risk management is handled by **Bitget exchange servers**, ensuring protection 24/7:

#### **Fixed Stop-Loss** (`pos_loss`)
- **Trigger:** -2.0% Return on Equity (ROE)
- **Execution:** Immediate market order by exchange
- **Purpose:** Hard stop-loss protection
- **Example:** With 25x leverage, 0.08% price drop = -2% ROE

#### **Min-Profit Floor** (`profit_plan`)
- **Trigger:** +2.5% ROE guaranteed minimum
- **Execution:** Market order when reached
- **Purpose:** Ensures minimum profit on every trade
- **Benefit:** No small losses that bypass TP/SL logic

#### **Exchange Trailing Take-Profit** (`moving_plan`)
- **Activation:** At min-profit floor (+2.5% ROE)
- **Callback:** 0.3% (configurable)
- **Execution:** Automatic trailing by exchange
- **Purpose:** Lock in profits dynamically

#### **Time-Stop Safety Net** (24 hours)
- **Purpose:** Ultimate fallback if TP/SL fail
- **Logging:** Critical error if triggered with losses
- **Rare:** Should only trigger for extreme events

### 2. **Bot-Side Monitoring (SECONDARY)**
- **SL Verification:** Every 60 seconds checks SL orders exist and match parameters
- **Position Monitoring:** Every 2 seconds tracks open positions
- **Tripwire Checks:** Advanced exit conditions (LSVR re-sweeps, adverse spikes)
- **Logging:** Comprehensive error detection and reporting

---

## 📊 Entry Strategy

### **Signal Generation**
```python
# RSI-based momentum signals with confluence filters
rsi = calculate_rsi(price_data, period=14)
adx = calculate_adx(price_data, period=14)
bb_width = calculate_bollinger_width(price_data)

# Entry conditions
if rsi > 70 and adx > 25 and bb_width > 0.02:  # Bullish momentum
    if confluence_filters_pass():  # Additional filters
        enter_short_position()
```

### **Confluence Filters**
- **ADX > 25:** Strong trend confirmation
- **Bollinger Band Width > 2%:** Sufficient volatility
- **Volume Ratio:** Above average volume
- **Market Structure:** Proper trend context

### **Position Sizing**
- **Base Capital:** $40 per trade (10% of $400 total capital)
- **Leverage:** 25x fixed (institutional-grade)
- **Risk per Trade:** 2% of capital (-2% ROE max loss)
- **Max Concurrent Positions:** 5-8 (sector diversification)

---

## 🎯 Exit Strategy (Multi-Layer Protection)

### **Primary Exits (Exchange-Side)**
1. **Stop-Loss Hit:** -2% ROE → Exchange closes immediately
2. **Min-Profit Floor:** +2.5% ROE → Exchange closes for guaranteed profit
3. **Trailing TP:** Activated at +2.5% ROE, trails with 0.3% callback

### **Advanced Exits (Bot-Side)**
- **Quick Profit:** Exit at +2% ROE within 3 minutes
- **Marginal Exit:** Exit at +1.5% ROE within 5 minutes
- **Breakeven Exit:** Exit at 0% ROE after 10 minutes
- **Tripwires:** Adverse market conditions

### **Time-Based Safety**
- **24-hour time-stop:** Ultimate protection against extreme events
- **Critical logging:** Errors if positions close with losses

---

## ⚙️ Technical Implementation

### **Core Files**
- `institutional_live_trader.py`: Main trading logic and position management
- `src/bitget_trading/bitget_rest.py`: Exchange API client with TP/SL placement
- `trade_tracker.py`: Trade logging and performance analysis
- `position_manager.py`: Position tracking and risk management

### **Key Functions**

#### **Signal Generation** (`institutional_live_trader.py`)
```python
async def scan_for_signals(self, symbols: List[str]):
    """Scan symbols for trading signals using RSI momentum"""
    # RSI > 70/30 thresholds with ADX confirmation
    # Bollinger Band width filters
    # Volume and market structure confluence
```

#### **Order Placement** (`bitget_rest.py`)
```python
async def place_tpsl_order():
    """Place exchange-side TP/SL with verification"""
    # Fixed SL at -2% ROE
    # Min-profit floor at +2.5% ROE
    # Immediate verification after placement

async def place_trailing_take_profit_order():
    """Place exchange trailing TP"""
    # Activates at min-profit floor
    # 0.3% callback ratio
    # Automatic trailing by exchange
```

#### **Position Monitoring** (`institutional_live_trader.py`)
```python
async def monitor_positions(self):
    """Monitor positions every 2 seconds"""
    # Verify SL orders exist (every 60s)
    # Check tripwire conditions
    # Track peak performance
    # Detect external TP/SL execution
```

---

## 📈 Performance Targets

### **Per Trade Targets**
- **Target ROI:** +5% to +12% (2.5% minimum guaranteed)
- **Max Loss:** -2% ROE (0.08% price movement with 25x leverage)
- **Holding Time:** 1-10 minutes (ultra-short-term)
- **Win Rate:** 70-80% (with proper TP/SL execution)

### **Daily/Weekly Goals**
- **Trades per Day:** 20-50 (depending on market conditions)
- **Daily ROI Target:** +10-20%
- **Weekly ROI Target:** +50-100%
- **Drawdown Limit:** -5% (hard stop-loss at -10%)

---

## 🛡️ Risk Management

### **Capital Protection**
1. **Position Sizing:** Max 10% of capital per trade
2. **Concurrent Limit:** Max 8 positions (sector diversification)
3. **Sector Limits:** Max 2 positions per sector
4. **Daily Loss Limit:** Stop trading if -5% daily loss

### **Exchange-Side Safety**
- **SL Verification:** Orders checked every 60 seconds
- **Parameter Matching:** Trigger prices and sizes verified
- **Auto-Replacement:** Missing/invalid orders replaced immediately
- **Critical Logging:** All TP/SL failures logged with timestamps

### **Bot-Side Safety**
- **Crash Recovery:** Automatic position recovery on restart
- **Connection Monitoring:** API health checks
- **Error Recovery:** Automatic retry with exponential backoff
- **Manual Override:** Emergency stop capabilities

---

## 📊 Performance Monitoring

### **Real-Time Metrics**
- **Active Positions:** Current open trades with P&L
- **Win Rate:** Rolling 24-hour performance
- **ROI Distribution:** P&L histogram by trade
- **Sector Performance:** By market sector

### **Trade Analysis**
```json
{
  "trade_id": "ICPUSDT_short_20251113_165813",
  "symbol": "ICPUSDT",
  "side": "short",
  "exit_reason": "trailing_take_profit",
  "pnl_pct_capital": 10.78,
  "duration_seconds": 76.46,
  "exit_time": "2025-11-13T16:58:49.147597"
}
```

### **Error Detection**
- **SL Failures:** Logged when time-stop closes losing positions
- **TP Failures:** Missing exchange orders detected
- **API Issues:** Connection problems tracked
- **Performance Alerts:** Deviations from targets flagged

---

## 🔧 Configuration Parameters

### **Signal Parameters** (`institutional_live_trader.py`)
```python
rsi_overbought = 70
rsi_oversold = 30
adx_threshold = 25
bb_width_min = 0.02
leverage = 25
```

### **Risk Parameters**
```python
max_position_pct = 0.1  # 10% of capital per trade
max_concurrent = 8      # Max concurrent positions
sl_roe_pct = -0.02      # -2% ROE stop-loss
min_profit_roe = 0.025  # +2.5% ROE minimum
trailing_callback = 0.003  # 0.3% trailing callback
```

### **Time Parameters**
```python
time_stop_hours = 24    # 24-hour safety net
monitor_interval = 2    # Check positions every 2s
tpsl_verify_interval = 60  # Verify TP/SL every 60s
```

---

## 🚀 Scaling & Optimization

### **Signal Quality**
- **Entry Grade:** A/B/C ranking based on confluence
- **Confluence Score:** Weighted signal strength
- **Market Regime:** Trend vs ranging adaptation
- **Sector Momentum:** Sector rotation detection

### **Dynamic Parameters**
- **Trailing Callback:** Adjusted based on market volatility
- **Position Sizing:** Modified by signal confidence
- **Holding Time:** Extended in strong trends
- **Stop-Loss:** Tightened in high-conviction trades

### **Performance Adaptation**
- **Win Rate Tracking:** Adjust parameters for consistency
- **ROI Optimization:** Target achievement monitoring
- **Risk Adjustment:** Drawdown-responsive sizing
- **Market Condition:** Adapt to volatility regimes

---

## 📝 Documentation Update Protocol

**⚠️ CRITICAL:** When editing the strategy, ALWAYS update this document!

**Update Checklist:**
- [ ] New parameters added to configuration section
- [ ] Risk management changes documented
- [ ] Performance targets updated if changed
- [ ] Technical implementation details current
- [ ] Error handling and safety measures documented

**Documentation Location:** `TRADING_STRATEGY.md`

---

## 🎯 Summary

This strategy combines **ultra-short-term scalping** with **institutional-grade risk management** to achieve consistent, profitable trading while maintaining maximum safety through **exchange-side protection**. The system is designed for **24/7 operation** with comprehensive monitoring and automatic recovery.

**Key Success Factors:**
- ✅ **Exchange-side TP/SL protection** (works offline)
- ✅ **Multi-layer exit strategy** (SL + TP + trailing)
- ✅ **SL verification system** (catches failures)
- ✅ **Real-time monitoring** (2-second position checks)
- ✅ **Comprehensive logging** (all events tracked)

**Last Updated:** November 13, 2025
**Strategy Version:** v3.0 - Exchange-Side Protection
