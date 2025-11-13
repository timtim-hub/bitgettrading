# Margin Calculation Fix for 10x Leverage Tokens

## Date: November 13, 2025

## Issue

User reported: "the margin still gets calculated wrong for the few 10x tokens we are trading"

### Root Cause

The `RiskManager.calculate_position_size()` method was using a **fixed 25x leverage** from config for all position sizing calculations, regardless of the actual leverage available for each symbol.

**Problem**:
- Most tokens support 25x leverage
- Some tokens (e.g., TAO, ONDO, etc.) only support 10x leverage
- When calculating margin: `margin = notional / leverage`
- Using wrong leverage causes wrong margin calculation

**Example**:
```python
# For a 10x token with $250 notional:
# WRONG (using 25x):
margin = $250 / 25 = $10 ❌

# CORRECT (using 10x):
margin = $250 / 10 = $25 ✅
```

This explains why some positions had ~$10 margin when they should have ~$25 margin.

## Solution

### Changes to `institutional_risk.py`

1. **Added `actual_leverage` parameter** to `calculate_position_size()`:
```python
def calculate_position_size(
    self, 
    symbol: str, 
    side: str, 
    entry_price: float, 
    stop_price: float, 
    equity_usdt: float,
    lot_size: float = 0.001, 
    min_qty: float = 0.001,
    actual_leverage: Optional[int] = None  # NEW PARAMETER
) -> PositionSize:
```

2. **Use actual leverage throughout the method**:
```python
# Use actual leverage if provided, otherwise fall back to config default
leverage_to_use = actual_leverage if actual_leverage is not None else self.leverage

# Calculate margin with correct leverage
margin = notional / leverage_to_use  # Not self.leverage!

# Calculate liquidation price with correct leverage
liq_price = self.calculate_liquidation_price(side, entry_price, leverage_to_use, mmr)

# Return correct leverage in PositionSize object
return PositionSize(
    ...
    leverage=leverage_to_use,  # Not self.leverage!
    ...
)
```

### Changes to `institutional_live_trader.py`

**Pass actual leverage** from `adjusted_prices` to `calculate_position_size()`:
```python
# Calculate position size with ACTUAL leverage (10x or 25x for this symbol)
position_size = self.risk_manager.calculate_position_size(
    symbol=symbol,
    side=signal.side,
    entry_price=signal.entry_price,
    stop_price=signal.stop_price,
    equity_usdt=equity,
    lot_size=0.001,
    min_qty=0.001,
    actual_leverage=adjusted_prices.leverage  # Use actual leverage from exchange!
)
```

The `adjusted_prices.leverage` comes from the `LeverageManager`, which fetches the actual max leverage for each symbol from the Bitget API.

## Expected Results

### Before Fix
- **25x tokens**: Correct margin (~$10 for $250 notional)
- **10x tokens**: Wrong margin (~$10 instead of ~$25 for $250 notional)
- Inconsistent margin sizes across positions

### After Fix
- **25x tokens**: Correct margin (~$10 for $250 notional with 25x)
- **10x tokens**: Correct margin (~$25 for $250 notional with 10x)
- **Consistent** margin calculation: Always 10% of equity, regardless of leverage
- **Notional** adjusts based on leverage: 25x tokens have 2.5x larger notional than 10x tokens

## Margin Calculation Formula

```
Target Margin = 10% of Equity
Target Notional = Target Margin × Actual Leverage
Position Size = Target Notional / Entry Price
Actual Margin = Actual Notional / Actual Leverage
```

**Examples** (assuming $250 equity):
```
10x Token:
- Target Margin: $250 × 10% = $25
- Target Notional: $25 × 10 = $250
- Actual Margin: $250 / 10 = $25 ✅

25x Token:
- Target Margin: $250 × 10% = $25
- Target Notional: $25 × 25 = $625
- Actual Margin: $625 / 25 = $25 ✅
```

Both use $25 margin (10% of $250 equity), but 25x tokens get larger notional.

## Verification

After bot restart, check logs for:
1. `📊 Leverage-adjusted | 10x` - Confirms 10x tokens detected
2. `📊 Leverage-adjusted | 25x` - Confirms 25x tokens detected
3. Position margin should be **consistent** at ~10% of equity for all tokens
4. Notional should be **larger** for 25x tokens vs 10x tokens

## Deployment

- Fixed files: `institutional_risk.py`, `institutional_live_trader.py`
- Bot restart required: YES
- Status: READY TO DEPLOY

