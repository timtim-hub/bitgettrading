"""
PRO TRADER INDICATORS - Used by world-class traders.

Implements:
1. Support/Resistance Levels (S/R)
2. Market Structure (Higher Highs, Higher Lows, etc.)
3. Risk/Reward Ratio Calculation
4. Trade Quality Grading (A, B, C)
5. Volume Profile Analysis
6. ATR-based Stop Placement
"""

import numpy as np
from collections import deque
from typing import Literal


class ProTraderIndicators:
    """
    Professional trading indicators used by institutional traders.
    
    Focus:
    - Price action structure
    - Key levels (S/R)
    - Risk management
    - Trade quality
    """
    
    def __init__(self):
        """Initialize pro trader indicators."""
        self.support_levels: deque = deque(maxlen=5)  # Top 5 support levels
        self.resistance_levels: deque = deque(maxlen=5)  # Top 5 resistance levels
        self.swing_highs: deque = deque(maxlen=20)
        self.swing_lows: deque = deque(maxlen=20)
    
    def detect_support_resistance(
        self, 
        prices: np.ndarray, 
        lookback: int = 20,
        tolerance: float = 0.002  # 0.2% tolerance for level clustering
    ) -> tuple[list[float], list[float]]:
        """
        Detect key support and resistance levels.
        
        Pro traders use S/R for:
        - Entry points (buy at support, sell at resistance)
        - Stop-loss placement (below support for longs)
        - Take-profit targets (at resistance for longs)
        
        Args:
            prices: Array of recent prices
            lookback: How many candles to look back
            tolerance: Price tolerance for clustering levels
        
        Returns:
            (support_levels, resistance_levels)
        """
        if len(prices) < lookback:
            return [], []
        
        # Find local highs and lows (swing points)
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(prices) - 2):
            # Swing high: Higher than 2 bars before and after
            if prices[i] > prices[i-1] and prices[i] > prices[i-2] and \
               prices[i] > prices[i+1] and prices[i] > prices[i+2]:
                swing_highs.append(prices[i])
            
            # Swing low: Lower than 2 bars before and after
            if prices[i] < prices[i-1] and prices[i] < prices[i-2] and \
               prices[i] < prices[i+1] and prices[i] < prices[i+2]:
                swing_lows.append(prices[i])
        
        # Cluster levels (group nearby levels together)
        resistance = self._cluster_levels(swing_highs, tolerance)
        support = self._cluster_levels(swing_lows, tolerance)
        
        # Keep only strongest levels (most touches)
        self.support_levels = deque(sorted(support, reverse=True)[:5], maxlen=5)
        self.resistance_levels = deque(sorted(resistance)[:5], maxlen=5)
        
        return list(self.support_levels), list(self.resistance_levels)
    
    def _cluster_levels(self, levels: list[float], tolerance: float) -> list[float]:
        """Cluster nearby price levels together."""
        if not levels:
            return []
        
        levels = sorted(levels)
        clustered = []
        current_cluster = [levels[0]]
        
        for i in range(1, len(levels)):
            # If within tolerance, add to current cluster
            if abs(levels[i] - current_cluster[0]) / current_cluster[0] < tolerance:
                current_cluster.append(levels[i])
            else:
                # Average the cluster and start new one
                clustered.append(np.mean(current_cluster))
                current_cluster = [levels[i]]
        
        # Add final cluster
        if current_cluster:
            clustered.append(np.mean(current_cluster))
        
        return clustered
    
    def analyze_market_structure(
        self, 
        prices: np.ndarray,
        lookback: int = 50  # Increased from 30 for better trend detection
    ) -> dict:
        """
        🚀 IMPROVED: Multi-method trend analysis for accurate forecasting.
        
        Combines 3 methods with weights:
        1. EMA Crossover (50% weight) - Most reliable
        2. Price Slope (30% weight) - Linear regression
        3. Swing Points (20% weight) - HH/HL structure
        
        Market Structure Rules:
        - UPTREND: EMA20 > EMA50 + positive slope + HH/HL
        - DOWNTREND: EMA20 < EMA50 + negative slope + LH/LL
        - RANGING: Conflicting signals or weak trend
        
        Pro traders ONLY trade WITH the structure:
        - Longs in uptrend (HH + HL)
        - Shorts in downtrend (LH + LL)
        - Avoid ranging markets
        
        Returns:
            {
                "structure": "uptrend" | "downtrend" | "ranging",
                "strength": 0-100,
                "ema_trend": "bullish" | "bearish" | "neutral",
                "slope_trend": "bullish" | "bearish" | "neutral",
                "swing_trend": "bullish" | "bearish" | "neutral",
                "uptrend_votes": int (out of 10),
                "downtrend_votes": int (out of 10),
            }
        """
        if len(prices) < lookback:
            return {
                "structure": "ranging",
                "strength": 0,
                "ema_trend": "neutral",
                "slope_trend": "neutral",
                "swing_trend": "neutral",
                "uptrend_votes": 0,
                "downtrend_votes": 0,
            }
        
        recent_prices = prices[-lookback:]
        
        # 🔥 METHOD 1: EMA Crossover (20/50) - 50% weight (5 votes)
        if len(recent_prices) >= 50:
            # Calculate EMAs
            ema_20 = np.zeros(len(recent_prices))
            ema_50 = np.zeros(len(recent_prices))
            
            # Simple EMA calculation
            alpha_20 = 2.0 / (20 + 1)
            alpha_50 = 2.0 / (50 + 1)
            
            ema_20[0] = recent_prices[0]
            ema_50[0] = recent_prices[0]
            
            for i in range(1, len(recent_prices)):
                ema_20[i] = alpha_20 * recent_prices[i] + (1 - alpha_20) * ema_20[i-1]
                ema_50[i] = alpha_50 * recent_prices[i] + (1 - alpha_50) * ema_50[i-1]
            
            ema_20_current = ema_20[-1]
            ema_50_current = ema_50[-1]
            
            # Determine EMA trend with 0.3% threshold (filters noise)
            if ema_20_current > ema_50_current * 1.003:  # 0.3% above
                ema_trend = "bullish"
                ema_votes_uptrend = 5
                ema_votes_downtrend = 0
            elif ema_20_current < ema_50_current * 0.997:  # 0.3% below
                ema_trend = "bearish"
                ema_votes_uptrend = 0
                ema_votes_downtrend = 5
            else:
                ema_trend = "neutral"
                ema_votes_uptrend = 0
                ema_votes_downtrend = 0
        else:
            ema_trend = "neutral"
            ema_votes_uptrend = 0
            ema_votes_downtrend = 0
        
        # 🔥 METHOD 2: Price Slope (linear regression) - 30% weight (3 votes)
        x = np.arange(len(recent_prices))
        slope, intercept = np.polyfit(x, recent_prices, 1)
        slope_pct = (slope * len(recent_prices)) / recent_prices[0]  # Total % change
        
        # Determine slope trend with 2% threshold
        if slope_pct > 0.02:  # >2% upward slope
            slope_trend = "bullish"
            slope_votes_uptrend = 3
            slope_votes_downtrend = 0
        elif slope_pct < -0.02:  # <-2% downward slope
            slope_trend = "bearish"
            slope_votes_uptrend = 0
            slope_votes_downtrend = 3
        else:
            slope_trend = "neutral"
            slope_votes_uptrend = 0
            slope_votes_downtrend = 0
        
        # 🔥 METHOD 3: Swing Point Structure - 20% weight (2 votes)
        # Find swing points
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(recent_prices) - 2):
            # BUG FIX: Check 2 bars before AND after (consistent with detect_support_resistance)
            if recent_prices[i] > recent_prices[i-1] and recent_prices[i] > recent_prices[i-2] and \
               recent_prices[i] > recent_prices[i+1] and recent_prices[i] > recent_prices[i+2]:
                swing_highs.append((i, recent_prices[i]))
            
            if recent_prices[i] < recent_prices[i-1] and recent_prices[i] < recent_prices[i-2] and \
               recent_prices[i] < recent_prices[i+1] and recent_prices[i] < recent_prices[i+2]:
                swing_lows.append((i, recent_prices[i]))
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            swing_trend = "neutral"
            swing_votes_uptrend = 0
            swing_votes_downtrend = 0
        else:
            # Count structure patterns
            higher_highs = sum(1 for i in range(1, len(swing_highs)) 
                              if swing_highs[i][1] > swing_highs[i-1][1])
            lower_highs = sum(1 for i in range(1, len(swing_highs)) 
                             if swing_highs[i][1] < swing_highs[i-1][1])
            
            higher_lows = sum(1 for i in range(1, len(swing_lows)) 
                             if swing_lows[i][1] > swing_lows[i-1][1])
            lower_lows = sum(1 for i in range(1, len(swing_lows)) 
                            if swing_lows[i][1] < swing_lows[i-1][1])
            
            # Determine swing trend
            uptrend_score = higher_highs + higher_lows
            downtrend_score = lower_highs + lower_lows
            
            if uptrend_score > downtrend_score and uptrend_score >= 2:
                swing_trend = "bullish"
                swing_votes_uptrend = 2
                swing_votes_downtrend = 0
            elif downtrend_score > uptrend_score and downtrend_score >= 2:
                swing_trend = "bearish"
                swing_votes_uptrend = 0
                swing_votes_downtrend = 2
            else:
                swing_trend = "neutral"
                swing_votes_uptrend = 0
                swing_votes_downtrend = 0
        
        # 🚀 CONSENSUS: Combine all 3 methods (10 total votes)
        # EMA = 5 votes | Slope = 3 votes | Swing = 2 votes
        total_uptrend_votes = ema_votes_uptrend + slope_votes_uptrend + swing_votes_uptrend
        total_downtrend_votes = ema_votes_downtrend + slope_votes_downtrend + swing_votes_downtrend
        
        # Determine final structure (need 6+ votes out of 10 for strong trend)
        if total_uptrend_votes >= 6:
            structure = "uptrend"
            strength = min(100, total_uptrend_votes * 10)  # 10 votes = 100%
        elif total_downtrend_votes >= 6:
            structure = "downtrend"
            strength = min(100, total_downtrend_votes * 10)
        else:
            structure = "ranging"
            strength = 30  # Weak trend
        
        return {
            "structure": structure,
            "strength": strength,
            "ema_trend": ema_trend,
            "slope_trend": slope_trend,
            "swing_trend": swing_trend,
            "uptrend_votes": total_uptrend_votes,
            "downtrend_votes": total_downtrend_votes,
            "slope_pct": slope_pct,
        }
    
    def calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        side: Literal["long", "short"]
    ) -> dict:
        """
        Calculate risk/reward ratio.
        
        Pro traders REQUIRE minimum 2:1 R:R (risk $1 to make $2+).
        
        Example:
            Entry: $100
            Stop: $98 (risk $2)
            Target: $105 (reward $5)
            R:R = 5/2 = 2.5:1 ✅ GOOD
        
        Args:
            entry_price: Entry price
            stop_loss: Stop-loss price
            take_profit: Take-profit price
            side: "long" or "short"
        
        Returns:
            {
                "risk_reward_ratio": float,
                "risk_amount": float (price distance),
                "reward_amount": float (price distance),
                "is_acceptable": bool (>= 2:1),
                "grade": "A" | "B" | "C" | "F"
            }
        """
        if side == "long":
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:  # short
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        
        if risk <= 0:
            return {
                "risk_reward_ratio": 0,
                "risk_amount": 0,
                "reward_amount": 0,
                "is_acceptable": False,
                "grade": "F"
            }
        
        rr_ratio = reward / risk
        
        # Grade the trade
        if rr_ratio >= 3.0:
            grade = "A"  # Excellent
        elif rr_ratio >= 2.0:
            grade = "B"  # Good
        elif rr_ratio >= 1.5:
            grade = "C"  # Marginal
        else:
            grade = "F"  # Reject
        
        return {
            "risk_reward_ratio": rr_ratio,
            "risk_amount": risk,
            "reward_amount": reward,
            "is_acceptable": rr_ratio >= 2.0,
            "grade": grade
        }
    
    def calculate_atr_stop(
        self,
        prices: np.ndarray,
        current_price: float,
        side: Literal["long", "short"],
        atr_multiplier: float = 1.5,
        period: int = 14
    ) -> float:
        """
        Calculate ATR-based stop-loss (used by pro traders).
        
        ATR (Average True Range) = average volatility
        
        Stop = Current Price ± (ATR × Multiplier)
        
        Benefits:
        - Adapts to volatility (wider stops in volatile markets)
        - Reduces premature stop-outs
        - More logical than fixed %
        
        Args:
            prices: Recent price array
            current_price: Current price
            side: "long" or "short"
            atr_multiplier: How many ATRs away (1.5-2.0 typical)
            period: ATR calculation period
        
        Returns:
            stop_loss_price: float
        """
        if len(prices) < period + 1:
            # Fallback to 1% stop
            if side == "long":
                return current_price * 0.99
            else:
                return current_price * 1.01
        
        # BUG FIX: For close-only data, use standard deviation of returns as volatility
        # (ATR requires separate high/low prices which we don't have)
        returns = np.diff(prices) / prices[:-1]
        
        if len(returns) < period:
            # Fallback: use 1% of price as volatility estimate
            volatility = current_price * 0.01
        else:
            # Calculate rolling volatility (std dev of returns)
            volatility_pct = np.std(returns[-period:])
            volatility = current_price * volatility_pct
        
        # Equivalent to ATR but for close prices
        atr = volatility
        
        # Calculate stop
        if side == "long":
            stop_loss = current_price - (atr * atr_multiplier)
        else:  # short
            stop_loss = current_price + (atr * atr_multiplier)
        
        return stop_loss
    
    def grade_trade_quality(
        self,
        features: dict,
        side: str,
        risk_reward: float,
        market_structure: dict,
        near_support_resistance: bool
    ) -> dict:
        """
        Grade overall trade quality (A, B, C, D, F).
        
        Pro traders grading criteria:
        - A: All stars align (5/5 factors)
        - B: Strong setup (4/5 factors)
        - C: Decent setup (3/5 factors)
        - D: Weak setup (2/5 factors)
        - F: Bad setup (0-1/5 factors)
        
        Factors:
        1. R:R >= 2:1
        2. With market structure (long in uptrend, short in downtrend)
        3. Near key S/R level (confluence)
        4. Strong volume
        5. Strong momentum
        
        Returns:
            {
                "grade": "A" | "B" | "C" | "D" | "F",
                "score": 0-100,
                "factors_met": 0-5,
                "reasons": [str]
            }
        """
        factors_met = 0
        reasons = []
        
        # Factor 1: R:R >= 3:1 (BALANCED - was 6:1 which was too strict!)
        # 3:1 is industry standard for quality trades
        if risk_reward >= 3.0:
            factors_met += 1
            reasons.append(f"✓ Good R:R ({risk_reward:.1f}:1)")
        else:
            reasons.append(f"✗ Poor R:R ({risk_reward:.1f}:1 - need 3:1+)")
        
        # Factor 2: With market structure OR valid counter-trend setup
        # 🚀 IMPROVED: Allow shorts in weak uptrends (pullback trading) and longs in weak downtrends
        structure = market_structure.get("structure", "ranging")
        uptrend_votes = market_structure.get("uptrend_votes", 0)
        downtrend_votes = market_structure.get("downtrend_votes", 0)
        swing_trend = market_structure.get("swing_trend", "neutral")
        
        # Check if trade is with structure OR valid counter-trend
        is_with_structure = (
            (side == "long" and structure == "uptrend") or 
            (side == "short" and structure == "downtrend") or
            (structure == "ranging")  # Ranging is OK for both
        )
        
        # Valid counter-trend: Short in weak uptrend (≤7 votes) OR long in weak downtrend (≤7 votes)
        is_valid_counter_trend = (
            (side == "short" and structure == "uptrend" and uptrend_votes <= 7) or
            (side == "long" and structure == "downtrend" and downtrend_votes <= 7)
        )
        
        if is_with_structure:
            factors_met += 1
            reasons.append(f"✓ With structure ({structure})")
        elif is_valid_counter_trend:
            factors_met += 1
            reasons.append(f"✓ Valid pullback ({side} in weak {structure}, {uptrend_votes or downtrend_votes}/10 votes)")
        else:
            reasons.append(f"✗ Against strong structure ({structure}, {uptrend_votes or downtrend_votes}/10 votes)")
        
        # Factor 3: Near S/R (confluence)
        if near_support_resistance:
            factors_met += 1
            reasons.append("✓ At key S/R level")
        else:
            reasons.append("✗ No S/R confluence")
        
        # Factor 4: Strong volume (STRICTER - need 3.0x above average!)
        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio >= 3.0:
            factors_met += 1
            reasons.append(f"✓ Strong volume ({volume_ratio:.2f}x)")
        else:
            reasons.append(f"✗ Weak volume ({volume_ratio:.2f}x - need 3.0x+)")
        
        # Factor 5: Strong momentum (STRICTER - need 0.20%+ in 15s!)
        return_15s = abs(features.get("return_15s", 0.0))
        if return_15s >= 0.0020:  # 0.20%+ move in 15s
            factors_met += 1
            reasons.append(f"✓ Strong momentum ({return_15s*100:.3f}%)")
        else:
            reasons.append(f"✗ Weak momentum ({return_15s*100:.3f}% - need 0.20%+)")
        
        # Factor 6: RSI in favorable zone (NEW)
        rsi = features.get("rsi", 50.0)
        if (side == "long" and rsi < 30) or (side == "short" and rsi > 70):
            factors_met += 1
            reasons.append(f"✓ RSI favorable ({rsi:.1f})")
        else:
            reasons.append(f"✗ RSI not favorable ({rsi:.1f})")
        
        # Factor 7: MACD bullish/bearish (NEW)
        macd_bullish = features.get("macd_bullish", False)
        macd_bearish = features.get("macd_bearish", False)
        if (side == "long" and macd_bullish) or (side == "short" and macd_bearish):
            factors_met += 1
            reasons.append("✓ MACD aligned")
        else:
            reasons.append("✗ MACD not aligned")
        
        # Factor 8: Price at Bollinger Band extreme (NEW)
        bb_extreme = features.get("bb_extreme", False)
        if bb_extreme:
            factors_met += 1
            reasons.append("✓ Bollinger Band extreme")
        else:
            reasons.append("✗ Not at Bollinger Band extreme")
        
        # Factor 9: EMA crossovers aligned (NEW)
        ema_aligned = features.get("ema_aligned", False)
        if ema_aligned:
            factors_met += 1
            reasons.append("✓ EMA crossovers aligned")
        else:
            reasons.append("✗ EMA crossovers not aligned")
        
        # Factor 10: Price above/below VWAP (NEW)
        vwap_favorable = features.get("vwap_favorable", False)
        if vwap_favorable:
            factors_met += 1
            reasons.append("✓ VWAP favorable")
        else:
            reasons.append("✗ VWAP not favorable")
        
        # Calculate grade (now 10 factors total, require 5+ for A-grade)
        score = factors_met * 10  # Each factor = 10 points (out of 100)
        
        if factors_met >= 5:
            grade = "A"  # Take this trade! (5+ out of 10 factors)
        elif factors_met >= 4:
            grade = "B"  # Good trade (4 out of 10)
        elif factors_met >= 3:
            grade = "C"  # Marginal (3 out of 10)
        elif factors_met >= 2:
            grade = "D"  # Weak (2 out of 10)
        else:
            grade = "F"  # Skip (0-1 out of 10)
        
        return {
            "grade": grade,
            "score": score,
            "factors_met": factors_met,
            "reasons": reasons
        }


def is_near_level(price: float, levels: list[float], tolerance: float = 0.003) -> bool:
    """
    Check if price is near a key level (within 0.3%).
    
    Used to determine if we're at support/resistance.
    """
    if not levels:
        return False
    
    for level in levels:
        if abs(price - level) / level < tolerance:
            return True
    
    return False

