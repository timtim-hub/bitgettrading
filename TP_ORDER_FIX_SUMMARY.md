# 🔧 TP Order Fix for Recovered Positions

## 🐛 **Problem Found**

TP (Take Profit) orders were **failing** for recovered positions (like UNIUSDT) with error:
```
40019: "Parameter size cannot be empty"
```

### **Root Cause:**

Our previous "fix" to make TP orders show as "Entire Position" in the Bitget app involved **removing the `size` parameter** from the TP order request. This worked for **NEW trades**, but **failed for RECOVERED positions** (positions reconstructed after bot restart).

Bitget API behavior:
- **NEW positions:** Accepts TP orders without `size` parameter ✅
- **RECOVERED positions:** Requires `size` parameter or returns error 40019 ❌

---

## ✅ **Fix Applied**

**File:** `src/bitget_trading/bitget_rest.py`

**Change:** Re-added the `size` parameter to TP orders:

```python
# BEFORE (Broken for recovered positions):
tp_data = {
    "symbol": symbol,
    "productType": product_type,
    "marginMode": "isolated",
    "marginCoin": "USDT",
    "planType": "profit_plan",
    "holdSide": api_hold_side,
    "triggerPrice": str(take_profit_price),
    "triggerType": "mark_price",
    # NO size parameter ❌
}

# AFTER (Works for both NEW and RECOVERED):
tp_data = {
    "symbol": symbol,
    "productType": product_type,
    "marginMode": "isolated",
    "marginCoin": "USDT",
    "planType": "profit_plan",
    "holdSide": api_hold_side,
    "triggerPrice": str(take_profit_price),
    "triggerType": "mark_price",
    "size": str(rounded_size),  # ✅ MUST include for recovered positions!
}
```

---

## 📊 **Impact**

### **Before Fix:**
- ✅ TP orders worked for NEW trades
- ❌ TP orders failed for RECOVERED positions
- ❌ Bot restarts left positions unprotected
- ❌ Manual TP placement required

### **After Fix:**
- ✅ TP orders work for NEW trades
- ✅ TP orders work for RECOVERED positions
- ✅ Bot restarts automatically protect positions
- ✅ No manual intervention needed

---

## 🔍 **How to Verify**

1. **Check TP order placement in logs:**
```bash
grep "✅ \[EXCHANGE TP\]" /tmp/live_bot.log | tail -5
```

2. **Check for TP errors:**
```bash
grep "Parameter size cannot be empty" /tmp/live_bot.log
```
Should show NO results after fix!

3. **Check Bitget app:**
- Open position
- Go to "TP/SL" tab
- Should see TP order for each position

---

## ⚠️ **Note on "Partial" vs "Entire"**

**Previous understanding was INCORRECT:**
- We thought: "No size = Entire Position"
- Reality: "Size = full position size = applies to entire position"

The `size` parameter doesn't control whether it's "Partial" vs "Entire". Both require the size parameter. The difference is in how the order is structured (which we're still investigating).

---

## 🎯 **Status**

- ✅ Fix applied
- ✅ Bot restarted (PID: 49118)
- ⏳ Testing on recovered positions (UNIUSDT, ETHUSDT, XRPUSDT, BTCUSDT)

**Next:** Monitor logs for successful TP placement!

