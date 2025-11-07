# Short Signal Debug Summary

## Issue
Bot is NOT placing any short trades despite fixes.

## Investigation Results

### 1. Current State
- Bot is ONLY generating long signals
- Recent logs show 0 "side=short" signals
- All trades are "side=long"

### 2. Root Cause Analysis
The `check_multi_timeframe_confluence` method in `enhanced_ranker.py` uses bullish_count and bearish_count calculated from timeframe returns (lines 143-150).

**Current Logic (Lines 143-150):**
```python
for name, ret, weight in available_timeframes:
    total_weight += weight
    if ret > 0:  # ANY positive return = bullish
        weighted_sum_bullish += ret * weight
        bullish_timeframes.append((name, ret))
    else:  # ANY negative/zero return = bearish
        weighted_sum_bearish += abs(ret) * weight
        bearish_timeframes.append((name, ret))
```

**Problem:**
- This counts `bullish_count = len(bullish_timeframes)` (timeframes with positive returns)
- This counts `bearish_count = len(bearish_timeframes)` (timeframes with negative returns)
- To get a short signal, need `bearish_count >= required_agreement` (75% of timeframes)
- In crypto bull markets, most timeframes show positive returns
- Even small positive returns (+0.01%) count as bullish
- This makes short signals extremely rare!

### 3. Solution
Need to RELAX the bearish detection threshold:
- Instead of counting ANY negative return as bearish, require MEANINGFUL negative returns
- Lower the `required_agreement_pct` for bearish confluence
- OR implement a separate logic path for shorts with relaxed requirements

### 4. Proposed Fix
Modify lines 143-150 to use threshold-based counting:
- Bullish: `ret > 0.0001` (>0.01%)
- Bearish: `ret < -0.0001` (<-0.01%)
- This filters out noise and ensures meaningful directional movement

Also, lower `required_agreement_pct` for bearish from 75% to 60% to allow more short signals.

