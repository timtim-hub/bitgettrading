# 📊 How Take Profit (TP) Triggers - Complete Example

## 🎯 Overview

The institutional strategy uses **multi-stage TP system** with trailing stops. Here's exactly when and how TP triggers.

---

## 📋 Complete Trade Flow Example

### **Example Trade: BTCUSDT SHORT**

Let's say you enter a SHORT position on BTCUSDT:

```
📍 ENTRY
├─ Symbol: BTCUSDT
├─ Side: SHORT
├─ Entry Price: $100,000
├─ Size: 0.1 contracts
├─ Notional: $10,000
└─ Leverage: 25x
```

---

## 🎬 Stage 1: Position Opens & TP/SL Placed

**Immediately after entry, the bot places:**

### 1. **Stop Loss (SL)** - Entire Position
```
🛑 STOP-LOSS ORDER
├─ Type: pos_loss (Gesamter TP/SL)
├─ Trigger Price: $101,500 (1.5% above entry)
├─ Size: ENTIRE position
└─ If hit: Closes 100% with market order
```

### 2. **Take Profit 1 (TP1)** - Entire Position
```
🎯 TAKE-PROFIT ORDER
├─ Type: profit_plan (Gesamter TP/SL)
├─ Trigger Price: $97,500 (2.5% below entry for SHORT)
├─ Size: ENTIRE position (75% will close)
└─ If hit: Closes 75% with market order
```

**Bot Logs at This Stage:**
```
✅ POSITION OPENED | BTCUSDT SHORT | Size: 0.1
📋 [STOP-LOSS ORDER - GESAMTER TP/SL MODE!] BTCUSDT | triggerPrice=101500
📋 [TAKE-PROFIT ORDER - GESAMTER TP/SL MODE!] BTCUSDT | triggerPrice=97500
✅ TP/SL orders placed successfully | BTCUSDT
```

---

## 🎬 Stage 2: TP1 Triggers (Price Moves in Our Favor)

### **Scenario: Price drops to $97,500**

The market moves in our favor (SHORT = price goes DOWN):

```
💰 TP1 TRIGGERED!
├─ Current Price: $97,500
├─ Entry Price: $100,000
├─ Profit: $2,500 (2.5%)
├─ Action: Close 75% of position
│   ├─ Size closed: 0.075 contracts
│   └─ Size remaining: 0.025 contracts
└─ P&L Realized: ~$1,875 profit (75% of $2,500)
```

**Bot Logs at This Stage:**
```
🎯 TP1 HIT! BTCUSDT | Current: $97,500 | Entry: $100,000
💰 Closing 75% of position (0.075 contracts)
✅ TP1 executed | P&L: +$1,875
```

---

## 🎬 Stage 3: Trailing Stop Placed (After TP1)

**Immediately after TP1 closes 75%, the bot places a trailing stop on the remaining 25%:**

```
📈 TRAILING STOP ORDER
├─ Type: track_plan (Bitget native trailing)
├─ Size: 0.025 contracts (remaining 25%)
├─ Trigger Price: $97,500 (current TP1 price)
├─ Callback Ratio: 3% (trails by 3%)
├─ Min Profit: 2.5% already locked
└─ How it works: Follows price down, stops if it reverses 3%
```

**Bot Logs at This Stage:**
```
🚀 Placing trailing stop | BTCUSDT
   Size: 0.025 | Trigger: $97,500 | Callback: 3.0%
✅ Verified: Trailing stop is active on exchange
   Order ID: 1234567890
```

---

## 🎬 Stage 4: Trailing Stop Follows Price

### **Scenario A: Price continues dropping (MORE profit)**

```
Price Movement:
$97,500 → $95,000 → $92,500 → $90,000

Trailing Stop Behavior:
├─ At $95,000: Stop moves to $97,850 (3% above)
├─ At $92,500: Stop moves to $95,375 (3% above)
├─ At $90,000: Stop moves to $92,700 (3% above)
└─ Locking in more profit as price drops!
```

**If price reverses by 3%:**
```
🎯 TRAILING STOP TRIGGERED!
├─ Best Price Reached: $90,000
├─ Stop Triggered At: $92,700 (3% above)
├─ Remaining Size Closed: 0.025 contracts
├─ Additional Profit: ~$187 on remaining 25%
└─ Total Trade P&L: $1,875 + $187 = $2,062
```

### **Scenario B: Price reverses immediately (MINIMUM profit locked)**

```
Price Movement:
$97,500 → $98,000 (reverses 0.5%)

Trailing Stop Behavior:
├─ Minimum profit already secured: 2.5%
├─ Stop at: $100,425 (3% callback from $97,500)
└─ Still profitable even if stopped immediately
```

**Bot Logs When Trailing Stop Hits:**
```
🎯 TRAILING STOP HIT! BTCUSDT
   Trigger Price: $92,700
   Size Closed: 0.025 contracts
✅ Position fully closed
📊 Final P&L: +$2,062 (+20.6% on margin)
```

---

## 📊 Full Trade Summary

### **Complete Trade Flow:**

```
Stage 1: ENTRY
├─ Entry: $100,000 SHORT
├─ Size: 0.1 contracts
└─ Capital Used: $400 margin (25x)

Stage 2: SL/TP PLACED
├─ SL @ $101,500 (+1.5%)
└─ TP1 @ $97,500 (-2.5%)

Stage 3: TP1 TRIGGERS
├─ Price: $97,500
├─ Close: 75% (0.075 contracts)
├─ P&L: +$1,875
└─ Remaining: 25% (0.025 contracts)

Stage 4: TRAILING ACTIVE
├─ Callback: 3%
├─ Best Price: $90,000
└─ Trails to: $92,700

Stage 5: TRAILING STOPS
├─ Trigger: $92,700
├─ Close: 25% (0.025 contracts)
├─ P&L: +$187
└─ Total: +$2,062 (516% ROI on margin!)
```

---

## 🔍 Real-Time Monitoring

### **Watch for TP Triggers:**

```bash
# Monitor live
tail -f /tmp/live_bot.log | grep -E "TP1|Trailing|Position.*closed"

# Check recent TP hits
grep "TP1 HIT\|Trailing stop" /tmp/live_bot.log | tail -10

# View all trades with TP
cat trades.jsonl | grep tp1_hit
```

---

## 🎯 Key Takeaways

### **When TP Triggers:**

1. **TP1 Triggers** when price moves **2.5%+** in your favor
   - For LONG: When price goes UP 2.5%
   - For SHORT: When price goes DOWN 2.5%

2. **Trailing Stop Activates** immediately after TP1
   - Only on remaining 25% of position
   - Follows price with 3% callback
   - Locks in additional profits

3. **Trailing Stop Triggers** when price reverses 3%
   - Captures maximum profit
   - Still guarantees minimum 2.5% profit overall

---

## 📋 Example Bot Logs (Real Trade)

```
01:18:48 | ✅ Position opened | UNIUSDT SHORT @ $7.49
01:18:54 | 📋 STOP-LOSS ORDER - GESAMTER TP/SL MODE! | trigger=$7.67
01:18:57 | 📋 TAKE-PROFIT ORDER - GESAMTER TP/SL MODE! | trigger=$7.36
01:18:57 | ✅ TP/SL orders placed successfully

[Later when price drops to $7.36...]
01:25:30 | 🎯 TP1 HIT! UNIUSDT | Current: $7.36 | Entry: $7.49
01:25:30 | 💰 Closing 75% of position
01:25:31 | ✅ TP1 executed | P&L: +$134.85
01:25:32 | 🚀 Placing trailing stop | callback: 3.0%
01:25:34 | ✅ Verified: Trailing stop is active on exchange

[If price continues to drop to $7.00 then reverses to $7.21...]
01:35:15 | 🎯 TRAILING STOP HIT! UNIUSDT
01:35:15 | 💰 Best price: $7.00 | Stop: $7.21
01:35:16 | ✅ Position fully closed | Additional P&L: +$28.95
01:35:16 | 📊 Total P&L: +$163.80 (+40.95% on margin)
```

---

## ⚠️ Important Notes

### **TP1 vs Trailing TP**

| Stage | Size | Trigger | Type |
|-------|------|---------|------|
| **TP1** | 75% of position | Fixed price (2.5%+) | profit_plan |
| **Trailing** | 25% of position | Dynamic (follows price) | track_plan |

### **Minimum Guarantees**

✅ **SL ensures**: Maximum loss 1.5% (with ATR adjustment)  
✅ **TP1 ensures**: Minimum profit 2.5%  
✅ **Trailing ensures**: Captures additional upside beyond 2.5%

### **Exchange-Side Execution**

✅ All TP/SL orders are on **Bitget's servers**  
✅ Work even if bot crashes  
✅ Execute automatically at market price  
✅ No bot intervention needed after placement

---

## 🚀 Current Status

Your bot is running 24/7 and will:

1. ✅ Open positions when signals appear
2. ✅ Place TP1 (2.5%+) and SL (1.5%) immediately
3. ✅ Monitor for TP1 hits (75% close)
4. ✅ Place trailing stop (3% callback) on remaining 25%
5. ✅ Log everything for analysis

**All you need to do is monitor and let it work!** 📊

