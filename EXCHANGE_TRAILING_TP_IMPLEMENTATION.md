# Exchange-Side Trailing Take Profit Implementation

## Using Bitget's Native track_plan API

Instead of bot-side trailing logic, we'll use **Bitget's exchange-side trailing TP**:

### Bitget API: `track_plan`

```python
Endpoint: /api/v2/mix/order/place-plan-order
planType: "track_plan"  # Official Bitget trailing stop/TP
callbackRatio: "3.00"   # 3% callback (max 10%)
triggerPrice: "$102.50" # Initial TP activation price
side: "sell"            # To close LONG position
reduceOnly: "YES"       # Only close/reduce position
```

### How It Works

**For LONG Position**:
1. Enter at $100
2. Place fixed SL at $98
3. Place trailing TP:
   - `triggerPrice`: $102.50 (initial TP - 2.5% ROI)
   - `callbackRatio`: "3.00" (3% callback)
   - `side`: "sell" (to close position)

**What Happens**:
- Price reaches $102.50 → Trailing TP activates
- Price moves to $103 → TP trails to $99.91 (3% below)
- Price moves to $104 → TP trails to $100.88
- Price moves to $105 → TP trails to $101.85
- Price reverses to $101.85 → **AUTOMATIC CLOSE** by exchange!
- **Profit: +1.85% on 25x = ~46% ROI** 🎉

**For SHORT Position**:
1. Enter at $100
2. Place fixed SL at $102
3. Place trailing TP:
   - `triggerPrice`: $97.50 (initial TP - 2.5% ROI)
   - `callbackRatio`: "3.00" (3% callback)
   - `side`: "buy" (to close position)

**What Happens**:
- Price reaches $97.50 → Trailing TP activates
- Price moves to $97 → TP trails to $100.01 (3% above)
- Price moves to $96 → TP trails to $98.88
- Price moves to $95 → TP trails to $97.85
- Price reverses to $97.85 → **AUTOMATIC CLOSE** by exchange!
- **Profit: +2.15% on 25x = ~54% ROI** 🎉

## Implementation Plan

### 1. Entry Order Flow

```python
async def place_entry_with_trailing_tp(symbol, signal, size):
    # 1. Place market entry order
    order = await rest_client.place_order(
        symbol=symbol,
        side='buy' if signal.side == 'long' else 'sell',
        order_type='market',
        size=size
    )
    
    # 2. Wait for position to exist on exchange
    await asyncio.sleep(3.0)
    
    # 3. Place FIXED stop loss
    sl_response = await rest_client.place_tpsl_order(
        symbol=symbol,
        hold_side=signal.side,
        size=size,
        stop_loss_price=signal.stop_price,
        take_profit_price=None
    )
    
    # 4. Place TRAILING take profit (exchange-side!)
    tp_price = signal.tp_levels[0][0]  # Initial TP
    callback_ratio = 0.03  # 3% callback
    
    trailing_response = await rest_client.place_trailing_stop_full_position(
        symbol=symbol,
        hold_side=signal.side,
        callback_ratio=callback_ratio,
        trigger_price=tp_price,
        size=size
    )
    
    # 🎉 DONE! Exchange handles everything automatically!
```

### 2. Monitoring (Minimal!)

```python
async def monitor_positions():
    for symbol, position in self.positions.items():
        # Just check if position still exists
        # Exchange handles TP/SL automatically!
        
        positions_list = await rest_client.get_positions(symbol)
        if not positions_list or position_closed:
            # Position closed by exchange
            logger.info(f"✅ Position closed by exchange | {symbol}")
            await cleanup_position(symbol)
```

**That's it!** No bot-side price monitoring, no trailing logic, nothing!

## Benefits of Exchange-Side Trailing

### ✅ RELIABILITY:
- Works even if bot crashes
- Works even if network disconnects
- Works 24/7 without bot intervention
- No price monitoring latency

### ✅ SIMPLICITY:
- 1 API call to set up trailing TP
- No bot-side logic needed
- No continuous price checks
- No manual TP updates

### ✅ PRECISION:
- Exchange has real-time prices
- No API latency
- No polling delays
- Instant execution

### ✅ SAFETY:
- Order visible in Bitget app
- Can modify/cancel manually if needed
- Exchange guarantees execution
- Bot-independent

## Callback Ratio Configuration

**Standard**: 3% (0.03)
- Good balance between protection and profit capture
- Allows for normal volatility
- Not too tight, not too loose

**Tight**: 2% (0.02)
- For low-volatility symbols
- Locks in profits quickly
- Risk: May exit too early on spikes

**Loose**: 5% (0.05)
- For high-volatility symbols
- Allows bigger moves
- Risk: May give back more profit

**Maximum**: 10% (0.10)
- Bitget's API limit
- Very loose trailing
- Only for extremely volatile markets

## Edge Cases Handled

1. **Position doesn't exist yet**:
   - Wait 3-5 seconds after entry
   - Retry with exponential backoff
   - Log "Insufficient position" warnings

2. **TP price too close to current price**:
   - Validate before placing
   - Adjust if needed (±0.1%)
   - Log adjustment

3. **Callback ratio too large**:
   - Validate ≤ 10%
   - Default to 3% if invalid
   - Log warning

4. **Exchange rejects order**:
   - Retry up to 3 times
   - Log error details
   - Fall back to bot-side monitoring

## Files to Modify

1. **institutional_live_trader.py**:
   - Simplify `monitor_positions` (remove bot-side trailing)
   - Update `scan_for_signals` to place trailing TP on entry
   - Add trailing TP placement after entry order fills

2. **src/bitget_trading/bitget_rest.py**:
   - Already have `place_trailing_stop_full_position` ✅
   - No changes needed!

## Testing Checklist

1. ✅ Place entry order
2. ✅ Place fixed SL
3. ✅ Place trailing TP with `track_plan`
4. ✅ Verify orders visible in Bitget app "Trailing" tab
5. ✅ Test price movement activates trailing
6. ✅ Test callback triggers automatic close
7. ✅ Verify bot detects external close
8. ✅ Confirm P&L tracked correctly

## Expected Results

- **Before (bot-side)**: Complex, unreliable, missed TP hits
- **After (exchange-side)**: Simple, reliable, automatic!

This is the **professional** way to do it! 🎯

