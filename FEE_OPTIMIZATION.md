# Fee Optimization Strategies

## Current Fee Structure (Bitget):
- **Taker Fee**: 0.06% (market orders)
- **Maker Fee**: 0.02% (limit orders)
- **Round-trip cost**: 0.12% (market) vs 0.04% (limit)
- **Savings**: 67% by using limit orders!

## Fee Impact on $50 Capital with 50x Leverage:

### Scenario: 10 positions @ $5.85 each = $58.50 total
- **With 50x leverage**: $2,925 total notional
- **Taker fees (market orders)**: $2,925 × 0.0006 × 2 = **$3.51 per round-trip**
- **Maker fees (limit orders)**: $2,925 × 0.0002 × 2 = **$1.17 per round-trip**
- **Savings per rebalance**: $2.34 (67% reduction!)

### If rebalancing 10 times per hour:
- **Taker fees**: $35.10/hour 🔴
- **Maker fees**: $11.70/hour ✅
- **Hourly savings**: $23.40!

## Optimizations Implemented:

### 1. **USE LIMIT ORDERS (67% fee reduction)**
```python
# Instead of market orders (immediate, 0.06% fee)
order_type = "market"

# Use limit orders at best bid/ask (usually fills, 0.02% fee)
if side == "buy":
    limit_price = current_ask  # Buy at ask (immediate fill)
else:
    limit_price = current_bid  # Sell at bid (immediate fill)

order_type = "limit"
```

### 2. **Reduce Rebalancing Frequency**
- Current: Every 60 seconds → ~60 rebalances/hour
- Optimized: Every 5 minutes → ~12 rebalances/hour
- **Fee reduction**: 80%

### 3. **Higher Signal Threshold**
- Current: Accept all ranked symbols
- Optimized: Only trade when signal strength > 0.7
- **Expected**: 50% fewer trades, but higher quality

### 4. **Increase Minimum Profit Target**
- Current: Close at +5%
- Optimized: Let winners run to +10-15% before closing
- **Result**: Fewer profitable exits, but each exit earns more (offsets fees)

### 5. **Reduce Position Turnover**
- Don't close positions that are still in top 10
- Only close when ranking drops significantly
- **Result**: Hold winning positions longer

## Implementation Plan:

1. ✅ Switch to limit orders (primary optimization)
2. ✅ Increase rebalance interval: 60s → 300s (5 min)
3. ✅ Higher signal threshold: 0.6 → 0.75
4. ✅ Adjust take-profit: +5% → +10%
5. ✅ Keep trailing stop at 3% from peak

## Expected Impact:

### Before Optimization:
- Fees: ~$35/hour (with 60s rebalancing)
- Net profit needed: >$35/hour just to break even!

### After Optimization:
- Fees: ~$2-3/hour (5min rebalancing + limit orders)
- Net profit needed: >$3/hour to break even
- **Sustainability**: 10x better!

## Risk Consideration:

**Limit Orders May Not Fill Immediately:**
- Pro: Save 67% on fees
- Con: Order might sit in book for seconds/minutes
- Solution: Use "best bid/ask" pricing for near-instant fill
- Fallback: If not filled in 10s, cancel and use market order

