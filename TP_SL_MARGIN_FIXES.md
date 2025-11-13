# TP/SL and Margin Error Fixes

## Date: November 13, 2025

## Issues Identified

### 1. Invalid TP Prices for SHORT Positions (Error 40832)
**Symptom**: "The take profit price of short positions should be less than the current price"

**Root Cause**: TP price was validated once before the retry loop, but market movement during retries (which can take 10-20 seconds) caused the TP price to become invalid.

**Fix**: Modified `scan_for_signals` method to validate TP price on EACH retry attempt (lines 1419-1446 in `institutional_live_trader.py`):
```python
# 🚨 CRITICAL: Validate TP price on EACH retry (market moves during retries!)
# Re-fetch current price to ensure TP is still valid
if tp1_price:
    market_data = await self.get_market_data(symbol)
    if market_data:
        current_price = market_data.last_price
        
        if signal.side == 'short':
            # For SHORT: TP must be BELOW current price
            if tp1_price >= current_price:
                tp1_price = current_price * 0.999
                logger.warning(f"⚠️ [RETRY {attempt+1}] TP1 adjusted to {tp1_price:.4f}")
                position.tp_levels[0] = (tp1_price, position.tp_levels[0][1])
```

### 2. "Insufficient Position" Errors (Error 43023)
**Symptom**: Bot trying to place TP/SL orders for positions that don't exist

**Root Causes**:
1. Periodic monitoring trying to re-place TP/SL for positions that were already closed
2. Recovered positions (on bot startup) no longer existing by the time TP/SL placement is attempted

**Fix #1 - Periodic Monitoring**: Added position existence check before re-placing missing TP/SL orders (lines 1137-1154 in `institutional_live_trader.py`):
```python
# 🚨 CRITICAL: Before re-placing TP/SL, verify position STILL EXISTS!
# If position is closed, don't try to place orders (causes "Insufficient position" error)
position_still_exists = False
try:
    positions_list = await self.rest_client.get_positions(symbol)
    if positions_list:
        for pos in positions_list:
            if pos.get('symbol') == symbol:
                pos_size = float(pos.get('total', 0) or pos.get('available', 0))
                if pos_size > 0:
                    position_still_exists = True
                    break
except Exception as e:
    logger.debug(f"⚠️ Could not verify position exists for {symbol}: {e}")

if not position_still_exists:
    logger.warning(f"⚠️ Position {symbol} no longer exists on exchange, skipping TP/SL re-placement")
    # Don't try to re-place orders for a closed position!
```

**Fix #2 - Recovered Positions**: Added position existence check before placing TP/SL for recovered positions (lines 1669-1695 in `institutional_live_trader.py`):
```python
# 🚨 CRITICAL: Re-verify position STILL EXISTS before placing TP/SL!
# Position might have closed between fetch and now
position_still_exists = False
try:
    positions_list = await self.rest_client.get_positions(symbol)
    if positions_list:
        for pos in positions_list:
            if pos.get('symbol') == symbol:
                pos_size = float(pos.get('total', 0) or pos.get('available', 0))
                if pos_size > 0:
                    position_still_exists = True
                    # Update with actual size from exchange
                    position.size = pos_size
                    position.remaining_size = pos_size
                    break
except Exception as e:
    logger.debug(f"⚠️ Could not re-verify position {symbol}: {e}")

if not position_still_exists:
    logger.warning(f"⚠️ Position {symbol} no longer exists on exchange, skipping TP/SL placement")
    # Remove from tracking
    del self.positions[symbol]
    self.active_symbols.discard(symbol)
    sector = symbol[:3]
    self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
    continue  # Skip this position
```

### 3. Variable Margin Sizes (Some ~$5 USD, Others $10+)
**Issue**: User reported inconsistent margin sizes for different positions

**Possible Causes**:
1. Different leverage for different symbols (25x vs 10x)
2. Position sizing based on 10% equity, which varies with account balance
3. Potential duplicate position placement for the same symbol

**Status**: Monitoring required. The fixes above should prevent duplicate positions. If issue persists, need to check:
- Are symbols being scanned multiple times per scan cycle?
- Is `can_open_position` properly checking for existing positions?
- Are positions being properly tracked in `self.positions`?

## Expected Behavior After Fixes

1. **TP Prices**: Always valid relative to current market price, even during retries
2. **No "Insufficient Position" Errors**: Bot will check position existence before attempting TP/SL placement
3. **Clean Position Tracking**: Closed positions will be removed from tracking and won't have failed TP/SL attempts

## Monitoring Points

Watch logs for:
- ✅ `[RETRY X] TP1 adjusted` - TP price validation working
- ✅ `Position no longer exists on exchange, skipping TP/SL` - Position cleanup working
- ❌ `43023` errors - Should be eliminated
- ❌ `40832` errors - Should be eliminated
- Check margin consistency across all open positions

## Deployment

- Bot restarted at ~15:06:36
- PID: 29480
- All fixes active

