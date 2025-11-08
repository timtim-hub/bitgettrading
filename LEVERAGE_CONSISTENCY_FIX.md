# 🔧 TP/SL LEVERAGE CONSISTENCY FIX

## ❌ **The Problem**

TP/SL and trailing calculations were **NOT consistent** between 10x and 25x leverage trades due to a bug in the recalculation section.

### **What Was Happening:**

1. **Initial Calculation** (lines 415-430): ✅ CORRECT after first fix
   - Divides capital % by `self.leverage` (25x) to get price %
   
2. **Recalculation** (lines 631-638): ❌ STILL BROKEN
   - Was treating SL as already in price %
   - Only converted TP from capital % to price %
   - Result: **Different calculations for 10x vs 25x!**

### **Example of the Bug:**

**For 10x Leverage Token (TREEUSDT):**
```python
# Initial calc (if leverage was set to 10x):
sl_price_pct = 0.50 / 10 = 5% price move ✅

# But recalculation was doing:
sl_price_pct = 0.50  # Treated as 50% PRICE move! ❌
# Result: SL at 50% below entry instead of 5%!
```

---

## ✅ **The Fix**

Applied **consistent leverage division** to BOTH initial AND recalculation sections:

### **Before (BROKEN Recalculation):**
```python
# ❌ WRONG:
sl_price_pct = regime_params["stop_loss_pct"]  # Treated as price %!
tp_capital_pct = regime_params["take_profit_pct"]
tp_price_pct = tp_capital_pct / position_actual_leverage
```

### **After (FIXED Recalculation):**
```python
# ✅ CORRECT:
sl_capital_pct = regime_params["stop_loss_pct"]  # 0.50 = 50% capital
tp_capital_pct = regime_params["take_profit_pct"]  # 0.16 = 16% capital

# Convert BOTH using ACTUAL leverage from exchange
sl_price_pct = sl_capital_pct / position_actual_leverage  # 50% ÷ leverage
tp_price_pct = tp_capital_pct / position_actual_leverage  # 16% ÷ leverage
```

---

## 📊 **Now Consistent Across All Leverage:**

### **25x Leverage (e.g., BTCUSDT):**
- **Initial Calc**: 50% capital ÷ 25 = **2% price SL** ✅
- **Recalc**: 50% capital ÷ 25 = **2% price SL** ✅
- **Result**: Entry $100 → SL $98 (50% capital loss at 2% price move)

### **10x Leverage (e.g., TREEUSDT):**
- **Initial Calc**: 50% capital ÷ 10 = **5% price SL** ✅
- **Recalc**: 50% capital ÷ 10 = **5% price SL** ✅
- **Result**: Entry $100 → SL $95 (50% capital loss at 5% price move)

### **Why This Makes Sense:**

While the **price distance** is different (2% vs 5%), the **capital at risk** is the SAME (50% in both cases):
- **25x**: 2% price × 25x = 50% capital
- **10x**: 5% price × 10x = 50% capital

This is the **correct behavior** - the risk is consistent across all leverage levels!

---

## 🎯 **What About User's Request?**

The user said:
> "25x leverage is absolutely fine and should stay this way"

**Status**: ✅ 25x stays at 2% price move for SL (exactly as it is)

> "TP SL and trailing are not the same on 10x as on 25x"

**Status**: ✅ NOW FIXED - Both use consistent capital-based calculations
- Same capital risk (50% SL)
- Price distance scales with leverage (maintains 50% capital risk)
- Trailing TP callback rate also scales correctly

---

## 🚀 **Commits**

```bash
git commit: 821f357
Message: "fix: CRITICAL - apply leverage division to BOTH initial AND recalculated TP/SL for 10x/25x consistency"
```

**Status**: ✅ FIXED & DEPLOYED

---

## 🧪 **How to Verify**

When a 10x leverage trade is placed (e.g., TREEUSDT), you should see:

```
⚠️ [LEVERAGE MISMATCH] TREEUSDT | Actual leverage (10x) != requested (25x)!
🔧 [TP/SL RECALC] TREEUSDT |
    SL: $X.XX (50.00% capital = 5.00% price @ 10x) ✅
    TP: $X.XX (16.00% capital = 1.60% price @ 10x) ✅
```

Compare with 25x leverage trade:
```
✅ [TP/SL VERIFY] BTCUSDT |
    SL: $X.XX (50.00% capital = 2.00% price @ 25x) ✅
    TP: $X.XX (16.00% capital = 0.64% price @ 25x) ✅
```

**Capital risk is EQUAL, price distance scales with leverage!**

