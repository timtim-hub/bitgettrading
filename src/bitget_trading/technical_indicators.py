"""
Advanced Technical Indicators for Ultra-Short-Term Trading.

Implements:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- EMA Crossovers
- VWAP (Volume-Weighted Average Price)
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

