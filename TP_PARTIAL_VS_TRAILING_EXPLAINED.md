# 🎯 TP "Partial" Label vs Trailing Stops - Explained

## 🔍 **What You're Seeing:**

Your UNIUSDT position shows a "Partial" (Teilweise) TP order in the Bitget app.

---

## ❓ **Is It Trailing?**

**NO - It's NOT trailing yet!** Here's why:

### **Current TP Order Type:**
- **Order Type:** `profit_plan` (Regular Take Profit)
- **Behavior:** Fixed price target at **$7.49**
- **Size:** 14.0 (full position)
- **Trailing:** ❌ NO - it's a STATIC TP order

### **Why "Partial" Label?**
The "Partial" (Teilweise) label appears because we include the `size` parameter in the API request. This is just **Bitget's UI labeling** - it doesn't mean the order is actually partial. It will close the ENTIRE position when triggered.

---

## 🚀 **When Does Trailing Start?**

Trailing stops are **ONLY placed AFTER TP1 hits**. Here's the flow:

### **Phase 1: Initial Entry (CURRENT STATE for UNIUSDT)**
```
Position: SHORT UNIUSDT @ $7.5852
TP1 Order: profit_plan @ $7.49 (regular TP, NOT trailing)
SL Order: pos_loss @ $7.74 (static stop-loss)
Status: Waiting for price to hit $7.49
```

### **Phase 2: After TP1 Hits (NOT YET for UNIUSDT)**
```
Action: Close 75% of position (10.5 UNIUSDT) @ $7.49
Remaining: 25% of position (3.5 UNIUSDT)
New Order: track_plan (TRAILING STOP) with 3% callback
Status: Now it's truly trailing!
```

---

## 📋 **Order Type Comparison**

| Order Type | planType | Trailing? | When Used? | Label in App |
|------------|----------|-----------|------------|--------------|
| Regular TP | `profit_plan` | ❌ NO | Initial entry | "Teilweise" (Partial) |
| Regular SL | `pos_loss` | ❌ NO | Initial entry | "Gesamter" (Entire) |
| Trailing Stop | `track_plan` | ✅ YES | After TP1 hits | "Verfolgungsauftrag" |

---

## 🎯 **For Your UNIUSDT Position:**

### **Current Status:**
- ✅ Has **regular TP** at $7.49 (NOT trailing)
- ✅ Has **regular SL** at $7.74
- ❌ Does NOT have trailing stop yet
- ⏳ Waiting for TP1 to hit first

### **What Happens Next:**

1. **Price drops to $7.49** → TP1 triggers
2. **Bot closes 75%** (10.5 UNIUSDT) at market
3. **Bot places trailing stop** (`track_plan`) for remaining 25% (3.5 UNIUSDT)
4. **Trailing stop follows** price down with 3% callback
5. **If price reverses 3%** → Trailing stop triggers, closes remaining 25%

---

## ⚠️ **Why This Design?**

### **Risk Management:**
1. **Lock in TP1 profit first** (guaranteed 2.5%+ profit)
2. **Only then** use trailing stop to capture additional profit
3. **Prevents giving back gains** if price reverses before TP1

### **Traditional Trailing (DON'T DO THIS):**
```
❌ Place trailing stop from entry → might never lock profit!
❌ Price moves favorably → trails up
❌ Price reverses 3% → exits at breakeven or small loss
❌ Missed the guaranteed TP1 profit!
```

### **Our Strategy (BETTER):**
```
✅ TP1 @ +2.5% → LOCKS IN PROFIT (75% of position)
✅ Then trailing stop → captures EXTRA profit (25% of position)
✅ Even if trailing stop hits breakeven → still profitable overall!
✅ If price continues → can capture 10%+ on remaining 25%
```

---

## 🔧 **Action Items:**

### **For Recovered Positions (like UNIUSDT):**
- ✅ Regular TP/SL orders ARE placed
- ✅ Bot monitors for TP1 hit
- ✅ Will automatically place trailing stop after TP1
- ⏳ Just wait for price to reach TP1!

### **Verification:**
```bash
# Check if TP1 has hit yet:
grep "TP1 HIT" /tmp/live_bot.log | grep UNIUSDT

# Check for trailing stop placement:
grep "track_plan" /tmp/live_bot.log | grep UNIUSDT
```

If you see NO results → TP1 hasn't hit yet, so no trailing stop is active yet.

---

## 💡 **Summary:**

1. **"Partial" label** = Just Bitget UI quirk (ignore it)
2. **Current TP** = Regular fixed-price TP (NOT trailing)
3. **Trailing starts** = Only AFTER TP1 hits
4. **Your position** = Working as designed! Wait for TP1 to hit first.

**Bottom Line:** Your UNIUSDT position is NOT trailing yet because TP1 hasn't been hit. Once price reaches $7.49, it will close 75% and THEN activate trailing for the remaining 25%. This is intentional and better for risk management!

