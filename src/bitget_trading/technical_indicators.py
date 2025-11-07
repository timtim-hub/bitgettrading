"""
Advanced Technical Indicators for Ultra-Short-Term Trading.

Implements:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- EMA Crossovers
- VWAP (Volume-Weighted Average Price)
- ADX (Average Directional Index) - NEW
- Stochastic Oscillator - NEW
- ATR (Average True Range) - NEW
- Order Flow Imbalance - NEW
"""

import numpy as np
from typing import Literal


class TechnicalIndicators:
    """Advanced technical indicators for trading signals."""
    
    def __init__(self):
        """Initialize technical indicators."""
        pass
    
    def calculate_rsi(
        self,
        prices: np.ndarray,
        period: int = 14
    ) -> float:
        """
        Calculate RSI (Relative Strength Index).
        
        RSI measures momentum and overbought/oversold conditions.
        - RSI < 30: Oversold (potential buy)
        - RSI > 70: Overbought (potential sell)
        - RSI 30-70: Neutral
        
        Args:
            prices: Array of recent prices
            period: RSI calculation period (default: 14)
        
        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral if not enough data
        
        # Calculate price changes
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Calculate average gain and loss
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0  # All gains, no losses
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(
        self,
        prices: np.ndarray,
        fast_period: int = 3,
        slow_period: int = 7,
        signal_period: int = 2
    ) -> dict:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        MACD signals:
        - MACD line crosses above signal line: Bullish
        - MACD line crosses below signal line: Bearish
        - Histogram expansion: Strong trend
        
        Args:
            prices: Array of recent prices
            fast_period: Fast EMA period (default: 3)
            slow_period: Slow EMA period (default: 7)
            signal_period: Signal line period (default: 2)
        
        Returns:
            {
                "macd": float,
                "signal": float,
                "histogram": float,
                "is_bullish": bool,
                "is_bearish": bool
            }
        """
        if len(prices) < slow_period + signal_period:
            return {
                "macd": 0.0,
                "signal": 0.0,
                "histogram": 0.0,
                "is_bullish": False,
                "is_bearish": False
            }
        
        # Calculate EMAs
        fast_ema = self._calculate_ema(prices, fast_period)
        slow_ema = self._calculate_ema(prices, slow_period)
        
        # MACD line = Fast EMA - Slow EMA
        macd_line = fast_ema - slow_ema
        
        # Signal line = EMA of MACD line
        macd_values = np.array([macd_line] * len(prices))
        signal_line = self._calculate_ema(macd_values, signal_period)
        
        # Histogram = MACD - Signal
        histogram = macd_line - signal_line
        
        # Determine direction
        is_bullish = macd_line > signal_line and histogram > 0
        is_bearish = macd_line < signal_line and histogram < 0
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
            "is_bullish": is_bullish,
            "is_bearish": is_bearish
        }
    
    def calculate_bollinger_bands(
        self,
        prices: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0
    ) -> dict:
        """
        Calculate Bollinger Bands.
        
        Bollinger Bands signals:
        - Price touches lower band + RSI < 30: Buy
        - Price touches upper band + RSI > 70: Sell
        - Bollinger squeeze (low volatility): Breakout imminent
        
        Args:
            prices: Array of recent prices
            period: Moving average period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
        
        Returns:
            {
                "upper_band": float,
                "middle_band": float,
                "lower_band": float,
                "bandwidth": float,
                "is_squeeze": bool
            }
        """
        if len(prices) < period:
            current_price = prices[-1] if len(prices) > 0 else 0
            return {
                "upper_band": current_price,
                "middle_band": current_price,
                "lower_band": current_price,
                "bandwidth": 0.0,
                "is_squeeze": False
            }
        
        # Calculate moving average (middle band)
        middle_band = np.mean(prices[-period:])
        
        # Calculate standard deviation
        std = np.std(prices[-period:])
        
        # Calculate bands
        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)
        
        # Calculate bandwidth (volatility measure)
        bandwidth = (upper_band - lower_band) / middle_band
        
        # Bollinger squeeze: low bandwidth = low volatility = breakout imminent
        is_squeeze = bandwidth < 0.01  # 1% bandwidth threshold
        
        return {
            "upper_band": upper_band,
            "middle_band": middle_band,
            "lower_band": lower_band,
            "bandwidth": bandwidth,
            "is_squeeze": is_squeeze
        }
    
    def calculate_ema_crossovers(
        self,
        prices: np.ndarray,
        fast_period: int = 3,
        slow_period: int = 7
    ) -> dict:
        """
        Calculate EMA crossover signals.
        
        EMA crossover signals:
        - Fast EMA crosses above slow EMA: Bullish
        - Fast EMA crosses below slow EMA: Bearish
        - All pairs agree: High confidence
        
        Args:
            prices: Array of recent prices
            fast_period: Fast EMA period (default: 3)
            slow_period: Slow EMA period (default: 7)
        
        Returns:
            {
                "fast_ema": float,
                "slow_ema": float,
                "is_bullish": bool,
                "is_bearish": bool,
                "crossover_signal": "bullish" | "bearish" | "neutral"
            }
        """
        if len(prices) < slow_period:
            return {
                "fast_ema": prices[-1] if len(prices) > 0 else 0,
                "slow_ema": prices[-1] if len(prices) > 0 else 0,
                "is_bullish": False,
                "is_bearish": False,
                "crossover_signal": "neutral"
            }
        
        # Calculate EMAs
        fast_ema = self._calculate_ema(prices, fast_period)
        slow_ema = self._calculate_ema(prices, slow_period)
        
        # Determine direction
        is_bullish = fast_ema > slow_ema
        is_bearish = fast_ema < slow_ema
        
        if is_bullish:
            crossover_signal = "bullish"
        elif is_bearish:
            crossover_signal = "bearish"
        else:
            crossover_signal = "neutral"
        
        return {
            "fast_ema": fast_ema,
            "slow_ema": slow_ema,
            "is_bullish": is_bullish,
            "is_bearish": is_bearish,
            "crossover_signal": crossover_signal
        }
    
    def calculate_vwap(
        self,
        prices: np.ndarray,
        volumes: np.ndarray | None = None,
        period: int = 20
    ) -> dict:
        """
        Calculate VWAP (Volume-Weighted Average Price).
        
        VWAP signals:
        - Price > VWAP + high volume: Bullish
        - Price < VWAP + high volume: Bearish
        - Deviation bands: ±0.5%, ±1%, ±2%
        
        Args:
            prices: Array of recent prices
            volumes: Array of recent volumes (optional)
            period: VWAP calculation period (default: 20)
        
        Returns:
            {
                "vwap": float,
                "deviation_pct": float,
                "is_above": bool,
                "is_below": bool
            }
        """
        if len(prices) < period:
            current_price = prices[-1] if len(prices) > 0 else 0
            return {
                "vwap": current_price,
                "deviation_pct": 0.0,
                "is_above": False,
                "is_below": False
            }
        
        # If volumes not provided, use equal weights (simple average)
        if volumes is None or len(volumes) < period:
            vwap = np.mean(prices[-period:])
        else:
            # Calculate VWAP: sum(price * volume) / sum(volume)
            price_volume = prices[-period:] * volumes[-period:]
            vwap = np.sum(price_volume) / np.sum(volumes[-period:])
        
        # Current price
        current_price = prices[-1]
        
        # Calculate deviation
        deviation_pct = ((current_price - vwap) / vwap) * 100
        
        # Determine position
        is_above = current_price > vwap
        is_below = current_price < vwap
        
        return {
            "vwap": vwap,
            "deviation_pct": deviation_pct,
            "is_above": is_above,
            "is_below": is_below
        }
    
    def _calculate_ema(
        self,
        prices: np.ndarray,
        period: int
    ) -> float:
        """
        Calculate Exponential Moving Average (EMA).
        
        Args:
            prices: Array of prices
            period: EMA period
        
        Returns:
            EMA value
        """
        if len(prices) < period:
            return np.mean(prices) if len(prices) > 0 else 0.0
        
        # Calculate smoothing factor
        alpha = 2.0 / (period + 1)
        
        # Start with SMA
        ema = np.mean(prices[:period])
        
        # Calculate EMA for remaining prices
        for price in prices[period:]:
            ema = (alpha * price) + ((1 - alpha) * ema)
        
        return ema
    
    def calculate_adx(
        self,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        close_prices: np.ndarray,
        period: int = 14
    ) -> dict:
        """
        Calculate ADX (Average Directional Index) - measures trend strength.
        
        ADX signals:
        - ADX > 25: Strong trend (good for directional trades)
        - ADX < 20: Weak trend (avoid directional trades, use mean reversion)
        - ADX 20-25: Moderate trend
        
        Args:
            high_prices: Array of high prices
            low_prices: Array of low prices
            close_prices: Array of close prices
            period: ADX calculation period (default: 14)
        
        Returns:
            {
                "adx": float,
                "plus_di": float,  # +DI (directional indicator)
                "minus_di": float,  # -DI (directional indicator)
                "trend_strength": str,  # "strong", "moderate", "weak"
                "trend_direction": str  # "bullish", "bearish", "neutral"
            }
        """
        if len(high_prices) < period + 1 or len(low_prices) < period + 1 or len(close_prices) < period + 1:
            return {
                "adx": 0.0,
                "plus_di": 0.0,
                "minus_di": 0.0,
                "trend_strength": "weak",
                "trend_direction": "neutral"
            }
        
        # Calculate True Range (TR)
        tr_list = []
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr = max(tr1, tr2, tr3)
            tr_list.append(tr)
        
        # Calculate Directional Movement (+DM and -DM)
        plus_dm_list = []
        minus_dm_list = []
        for i in range(1, len(high_prices)):
            move_up = high_prices[i] - high_prices[i-1]
            move_down = low_prices[i-1] - low_prices[i]
            
            if move_up > move_down and move_up > 0:
                plus_dm_list.append(move_up)
            else:
                plus_dm_list.append(0.0)
            
            if move_down > move_up and move_down > 0:
                minus_dm_list.append(move_down)
            else:
                minus_dm_list.append(0.0)
        
        # Calculate smoothed TR, +DM, -DM
        atr = np.mean(tr_list[-period:])
        plus_dm = np.mean(plus_dm_list[-period:])
        minus_dm = np.mean(minus_dm_list[-period:])
        
        # Calculate +DI and -DI
        if atr > 0:
            plus_di = 100 * (plus_dm / atr)
            minus_di = 100 * (minus_dm / atr)
        else:
            plus_di = 0.0
            minus_di = 0.0
        
        # Calculate DX (Directional Index)
        di_sum = plus_di + minus_di
        if di_sum > 0:
            dx = 100 * abs(plus_di - minus_di) / di_sum
        else:
            dx = 0.0
        
        # ADX is smoothed DX (simplified - using current DX as ADX)
        adx = dx
        
        # Determine trend strength
        if adx > 25:
            trend_strength = "strong"
        elif adx > 20:
            trend_strength = "moderate"
        else:
            trend_strength = "weak"
        
        # Determine trend direction
        if plus_di > minus_di:
            trend_direction = "bullish"
        elif minus_di > plus_di:
            trend_direction = "bearish"
        else:
            trend_direction = "neutral"
        
        return {
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "trend_strength": trend_strength,
            "trend_direction": trend_direction
        }
    
    def calculate_stochastic(
        self,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        close_prices: np.ndarray,
        k_period: int = 14,
        d_period: int = 3
    ) -> dict:
        """
        Calculate Stochastic Oscillator - measures momentum.
        
        Stochastic signals:
        - %K > 80: Overbought (potential sell)
        - %K < 20: Oversold (potential buy)
        - %K crosses above %D: Bullish signal
        - %K crosses below %D: Bearish signal
        
        Args:
            high_prices: Array of high prices
            low_prices: Array of low prices
            close_prices: Array of close prices
            k_period: %K period (default: 14)
            d_period: %D period (default: 3)
        
        Returns:
            {
                "k_percent": float,  # %K (0-100)
                "d_percent": float,  # %D (0-100)
                "is_overbought": bool,
                "is_oversold": bool,
                "signal": str  # "bullish", "bearish", "neutral"
            }
        """
        if len(high_prices) < k_period or len(low_prices) < k_period or len(close_prices) < k_period:
            return {
                "k_percent": 50.0,
                "d_percent": 50.0,
                "is_overbought": False,
                "is_oversold": False,
                "signal": "neutral"
            }
        
        # Calculate %K
        lowest_low = np.min(low_prices[-k_period:])
        highest_high = np.max(high_prices[-k_period:])
        current_close = close_prices[-1]
        
        if highest_high - lowest_low > 0:
            k_percent = 100 * ((current_close - lowest_low) / (highest_high - lowest_low))
        else:
            k_percent = 50.0
        
        # Calculate %D (simple moving average of %K)
        if len(close_prices) >= k_period + d_period:
            # Calculate %K for last d_period values
            k_values = []
            for i in range(d_period):
                idx = len(close_prices) - d_period + i
                period_low = np.min(low_prices[idx-k_period:idx+1])
                period_high = np.max(high_prices[idx-k_period:idx+1])
                period_close = close_prices[idx]
                if period_high - period_low > 0:
                    k_val = 100 * ((period_close - period_low) / (period_high - period_low))
                else:
                    k_val = 50.0
                k_values.append(k_val)
            d_percent = np.mean(k_values)
        else:
            d_percent = k_percent
        
        # Determine signals
        is_overbought = k_percent > 80
        is_oversold = k_percent < 20
        
        # Determine crossover signal
        if k_percent > d_percent and k_percent < 80:
            signal = "bullish"
        elif k_percent < d_percent and k_percent > 20:
            signal = "bearish"
        else:
            signal = "neutral"
        
        return {
            "k_percent": k_percent,
            "d_percent": d_percent,
            "is_overbought": is_overbought,
            "is_oversold": is_oversold,
            "signal": signal
        }
    
    def calculate_atr(
        self,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        close_prices: np.ndarray,
        period: int = 14
    ) -> dict:
        """
        Calculate ATR (Average True Range) - measures volatility.
        
        ATR signals:
        - High ATR: High volatility (wider stops needed)
        - Low ATR: Low volatility (tighter stops possible)
        - ATR expansion: Volatility increasing (breakout potential)
        - ATR contraction: Volatility decreasing (consolidation)
        
        Args:
            high_prices: Array of high prices
            low_prices: Array of low prices
            close_prices: Array of close prices
            period: ATR calculation period (default: 14)
        
        Returns:
            {
                "atr": float,
                "atr_pct": float,  # ATR as % of price
                "volatility_level": str,  # "high", "moderate", "low"
                "is_expanding": bool,
                "is_contracting": bool
            }
        """
        if len(high_prices) < period + 1 or len(low_prices) < period + 1 or len(close_prices) < period + 1:
            current_price = close_prices[-1] if len(close_prices) > 0 else 0
            return {
                "atr": 0.0,
                "atr_pct": 0.0,
                "volatility_level": "low",
                "is_expanding": False,
                "is_contracting": False
            }
        
        # Calculate True Range (TR)
        tr_list = []
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr = max(tr1, tr2, tr3)
            tr_list.append(tr)
        
        # Calculate ATR (average of TR)
        atr = np.mean(tr_list[-period:])
        
        # Calculate ATR as % of current price
        current_price = close_prices[-1]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0.0
        
        # Determine volatility level
        if atr_pct > 2.0:
            volatility_level = "high"
        elif atr_pct > 1.0:
            volatility_level = "moderate"
        else:
            volatility_level = "low"
        
        # Check if ATR is expanding or contracting
        if len(tr_list) >= period * 2:
            recent_atr = np.mean(tr_list[-period:])
            previous_atr = np.mean(tr_list[-period*2:-period])
            is_expanding = recent_atr > previous_atr * 1.1  # 10% increase
            is_contracting = recent_atr < previous_atr * 0.9  # 10% decrease
        else:
            is_expanding = False
            is_contracting = False
        
        return {
            "atr": atr,
            "atr_pct": atr_pct,
            "volatility_level": volatility_level,
            "is_expanding": is_expanding,
            "is_contracting": is_contracting
        }
    
    def calculate_order_flow_imbalance(
        self,
        bid_volumes: np.ndarray | None = None,
        ask_volumes: np.ndarray | None = None,
        prices: np.ndarray | None = None,
        volumes: np.ndarray | None = None,
        period: int = 20
    ) -> dict:
        """
        Calculate Order Flow Imbalance - measures buying vs selling pressure.
        
        Order Flow signals:
        - Positive imbalance: More buying pressure (bullish)
        - Negative imbalance: More selling pressure (bearish)
        - High imbalance: Strong directional pressure
        - Low imbalance: Balanced market (consolidation)
        
        Args:
            bid_volumes: Array of bid volumes (optional)
            ask_volumes: Array of ask volumes (optional)
            prices: Array of prices (for price-weighted imbalance)
            volumes: Array of volumes (for volume-weighted imbalance)
            period: Calculation period (default: 20)
        
        Returns:
            {
                "imbalance": float,  # -1 to +1 (negative = bearish, positive = bullish)
                "imbalance_pct": float,  # -100% to +100%
                "pressure": str,  # "strong_buy", "buy", "neutral", "sell", "strong_sell"
                "is_balanced": bool
            }
        """
        # If we have bid/ask volumes, use them directly
        if bid_volumes is not None and ask_volumes is not None and len(bid_volumes) >= period and len(ask_volumes) >= period:
            total_bid = np.sum(bid_volumes[-period:])
            total_ask = np.sum(ask_volumes[-period:])
            total_volume = total_bid + total_ask
            
            if total_volume > 0:
                imbalance = (total_bid - total_ask) / total_volume
                imbalance_pct = imbalance * 100
            else:
                imbalance = 0.0
                imbalance_pct = 0.0
        
        # Otherwise, use price/volume data to infer imbalance
        elif prices is not None and volumes is not None and len(prices) >= period and len(volumes) >= period:
            # Calculate price-weighted volume (up vs down)
            up_volume = 0.0
            down_volume = 0.0
            
            for i in range(1, len(prices[-period:])):
                idx = len(prices) - period + i
                if prices[idx] > prices[idx-1]:
                    up_volume += volumes[idx]
                elif prices[idx] < prices[idx-1]:
                    down_volume += volumes[idx]
            
            total_volume = up_volume + down_volume
            if total_volume > 0:
                imbalance = (up_volume - down_volume) / total_volume
                imbalance_pct = imbalance * 100
            else:
                imbalance = 0.0
                imbalance_pct = 0.0
        else:
            imbalance = 0.0
            imbalance_pct = 0.0
        
        # Determine pressure level
        if imbalance_pct > 50:
            pressure = "strong_buy"
        elif imbalance_pct > 20:
            pressure = "buy"
        elif imbalance_pct < -50:
            pressure = "strong_sell"
        elif imbalance_pct < -20:
            pressure = "sell"
        else:
            pressure = "neutral"
        
        is_balanced = abs(imbalance_pct) < 10
        
        return {
            "imbalance": imbalance,
            "imbalance_pct": imbalance_pct,
            "pressure": pressure,
            "is_balanced": is_balanced
        }

