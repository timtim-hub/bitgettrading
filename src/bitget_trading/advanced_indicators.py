"""Advanced technical indicators for ultra-short-term trading."""

import numpy as np
from collections import deque
from typing import Deque

from src.bitget_trading.logger import get_logger

logger = get_logger()


class AdvancedIndicators:
    """
    World-class technical indicators for short-term trading (seconds to 10 minutes).
    
    Includes:
    - RSI (multiple timeframes)
    - MACD (fast params for scalping)
    - Bollinger Bands
    - EMA crossovers
    - VWAP deviation
    - Enhanced order flow
    - Price action patterns
    - Liquidity sweep detection
    - Tick momentum
    """
    
    def __init__(self) -> None:
        """Initialize advanced indicators."""
        # Price history for indicator calculation
        self.prices: Deque[float] = deque(maxlen=3600)  # 1 hour at 1Hz
        self.volumes: Deque[float] = deque(maxlen=3600)
        self.timestamps: Deque[float] = deque(maxlen=3600)
        
        # Order book history for flow analysis
        self.bid_volumes: Deque[float] = deque(maxlen=300)
        self.ask_volumes: Deque[float] = deque(maxlen=300)
        
        # Tick data for microstructure
        self.up_ticks: Deque[float] = deque(maxlen=100)
        self.down_ticks: Deque[float] = deque(maxlen=100)
        
        # EMA caches (for efficiency)
        self.ema_cache: dict[int, float] = {}
    
    def update(
        self,
        price: float,
        volume: float,
        timestamp: float,
        bid_volume: float = 0.0,
        ask_volume: float = 0.0,
    ) -> None:
        """
        Update indicators with new data point.
        
        Args:
            price: Current price
            volume: Current volume
            timestamp: Current timestamp
            bid_volume: Bid side volume
            ask_volume: Ask side volume
        """
        self.prices.append(price)
        self.volumes.append(volume)
        self.timestamps.append(timestamp)
        
        if bid_volume > 0:
            self.bid_volumes.append(bid_volume)
        if ask_volume > 0:
            self.ask_volumes.append(ask_volume)
        
        # Track tick direction
        if len(self.prices) >= 2:
            if price > self.prices[-2]:
                self.up_ticks.append(timestamp)
            elif price < self.prices[-2]:
                self.down_ticks.append(timestamp)
    
    def compute_rsi(self, period: int = 14) -> float:
        """
        Compute RSI (Relative Strength Index).
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        
        Args:
            period: Lookback period (2, 5, 15, 30 for ultra-short-term)
        
        Returns:
            RSI value (0-100)
        """
        if len(self.prices) < period + 1:
            return 50.0  # Neutral
        
        prices = np.array(list(self.prices))
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Use EMA for smoothing (faster than SMA)
        if len(gains) < period:
            return 50.0
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def compute_macd(
        self, fast: int = 3, slow: int = 7, signal: int = 2
    ) -> tuple[float, float, float]:
        """
        Compute MACD (Moving Average Convergence Divergence).
        
        Ultra-fast params for scalping: 3/7/2 (vs traditional 12/26/9)
        
        Args:
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period
        
        Returns:
            (macd_line, signal_line, histogram)
        """
        if len(self.prices) < slow + signal:
            return 0.0, 0.0, 0.0
        
        prices = np.array(list(self.prices))
        
        # Compute EMAs
        ema_fast = self._compute_ema(prices, fast)
        ema_slow = self._compute_ema(prices, slow)
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA of MACD)
        if len(self.prices) < slow + signal:
            return macd_line, 0.0, macd_line
        
        # Get recent MACD values for signal line
        macd_values = []
        for i in range(signal, 0, -1):
            if len(prices) >= slow + i:
                ema_f = self._compute_ema(prices[:-i] if i > 1 else prices, fast)
                ema_s = self._compute_ema(prices[:-i] if i > 1 else prices, slow)
                macd_values.append(ema_f - ema_s)
        macd_values.append(macd_line)
        
        signal_line = np.mean(macd_values[-signal:])
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def compute_bollinger_bands(
        self, period: int = 20, std_dev: float = 2.0
    ) -> tuple[float, float, float]:
        """
        Compute Bollinger Bands.
        
        Args:
            period: Lookback period (10, 20 for scalping)
            std_dev: Standard deviations (2.0 standard)
        
        Returns:
            (upper_band, middle_band, lower_band)
        """
        if len(self.prices) < period:
            price = list(self.prices)[-1] if self.prices else 0.0
            return price, price, price
        
        prices = np.array(list(self.prices))
        recent = prices[-period:]
        
        middle = np.mean(recent)
        std = np.std(recent)
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, middle, lower
    
    def compute_ema_crossovers(
        self,
    ) -> dict[str, tuple[float, float, str]]:
        """
        Compute multiple EMA crossovers for micro-trend detection.
        
        Returns:
            Dict of {
                "3/7": (ema3, ema7, "bullish"/"bearish"/"neutral"),
                "5/15": (ema5, ema15, signal),
                "10/30": (ema10, ema30, signal),
            }
        """
        if len(self.prices) < 30:
            return {}
        
        prices = np.array(list(self.prices))
        
        result = {}
        pairs = [(3, 7), (5, 15), (10, 30)]
        
        for fast, slow in pairs:
            ema_fast = self._compute_ema(prices, fast)
            ema_slow = self._compute_ema(prices, slow)
            
            # Determine signal
            diff_pct = (ema_fast - ema_slow) / ema_slow
            if diff_pct > 0.0005:  # 0.05% above
                signal = "bullish"
            elif diff_pct < -0.0005:  # 0.05% below
                signal = "bearish"
            else:
                signal = "neutral"
            
            result[f"{fast}/{slow}"] = (ema_fast, ema_slow, signal)
        
        return result
    
    def compute_vwap_deviation(self, period: int = 300) -> tuple[float, float]:
        """
        Compute VWAP (Volume-Weighted Average Price) and deviation.
        
        Args:
            period: Lookback period in seconds (300 = 5min)
        
        Returns:
            (vwap, deviation_pct)
        """
        if len(self.prices) < 2 or len(self.volumes) < 2:
            return 0.0, 0.0
        
        prices = np.array(list(self.prices))
        volumes = np.array(list(self.volumes))
        
        # Use recent period
        n = min(period, len(prices))
        recent_prices = prices[-n:]
        recent_volumes = volumes[-n:]
        
        # VWAP = sum(price * volume) / sum(volume)
        if recent_volumes.sum() == 0:
            return prices[-1], 0.0
        
        vwap = np.sum(recent_prices * recent_volumes) / np.sum(recent_volumes)
        
        # Deviation from VWAP
        current_price = prices[-1]
        deviation_pct = (current_price - vwap) / vwap
        
        return vwap, deviation_pct
    
    def compute_order_flow_imbalance(self) -> float:
        """
        Compute enhanced order flow imbalance.
        
        Cumulative delta: buy volume - sell volume
        
        Returns:
            Flow imbalance (-1 to 1, positive = buying pressure)
        """
        if len(self.bid_volumes) < 2 or len(self.ask_volumes) < 2:
            return 0.0
        
        # Recent 30 data points
        bid_vol = np.array(list(self.bid_volumes)[-30:])
        ask_vol = np.array(list(self.ask_volumes)[-30:])
        
        total_bid = np.sum(bid_vol)
        total_ask = np.sum(ask_vol)
        
        if total_bid + total_ask == 0:
            return 0.0
        
        # Imbalance: positive = more buying
        imbalance = (total_bid - total_ask) / (total_bid + total_ask)
        
        return imbalance
    
    def detect_price_action_pattern(self) -> tuple[str, float]:
        """
        Detect price action patterns.
        
        Returns:
            (pattern_name, confidence)
            Patterns: "uptrend", "downtrend", "double_top", "double_bottom", "neutral"
        """
        if len(self.prices) < 30:
            return "neutral", 0.0
        
        prices = np.array(list(self.prices))
        recent = prices[-30:]
        
        # Detect trend using linear regression
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent, 1)[0]
        
        # Normalize slope
        avg_price = np.mean(recent)
        slope_pct = (slope / avg_price) * 100  # Slope as percentage
        
        # Classify pattern
        if slope_pct > 0.1:  # Strong uptrend
            return "uptrend", min(abs(slope_pct) / 0.5, 1.0)
        elif slope_pct < -0.1:  # Strong downtrend
            return "downtrend", min(abs(slope_pct) / 0.5, 1.0)
        
        # Check for double top/bottom
        # Find local maxima and minima
        if len(recent) >= 10:
            peaks = self._find_peaks(recent)
            troughs = self._find_troughs(recent)
            
            # Double top: 2 peaks at similar levels
            if len(peaks) >= 2:
                last_two_peaks = sorted(peaks[-2:])
                if abs(last_two_peaks[0] - last_two_peaks[1]) / avg_price < 0.01:  # Within 1%
                    return "double_top", 0.7
            
            # Double bottom: 2 troughs at similar levels
            if len(troughs) >= 2:
                last_two_troughs = sorted(troughs[-2:])
                if abs(last_two_troughs[0] - last_two_troughs[1]) / avg_price < 0.01:
                    return "double_bottom", 0.7
        
        return "neutral", 0.0
    
    def detect_liquidity_sweep(self) -> tuple[bool, str]:
        """
        Detect liquidity sweep (stop-loss hunt).
        
        Pattern:
        1. Sharp price spike (>0.2% in <5 seconds)
        2. Immediate reversal
        3. Volume surge
        
        Returns:
            (is_sweep, direction)  # direction: "up" or "down"
        """
        if len(self.prices) < 10 or len(self.volumes) < 10:
            return False, "none"
        
        prices = np.array(list(self.prices))
        volumes = np.array(list(self.volumes))
        
        # Check last 5 seconds
        recent_prices = prices[-5:]
        recent_volumes = volumes[-5:]
        
        # 1. Check for sharp spike
        price_range = (np.max(recent_prices) - np.min(recent_prices)) / np.mean(recent_prices)
        if price_range < 0.002:  # Less than 0.2% move
            return False, "none"
        
        # 2. Check for reversal
        if len(recent_prices) >= 3:
            # Up spike then down
            if recent_prices[-3] < recent_prices[-2] and recent_prices[-2] > recent_prices[-1]:
                # 3. Check volume surge
                avg_volume = np.mean(volumes[-30:])
                if recent_volumes[-2] > avg_volume * 1.5:  # 50% above average
                    return True, "up"
            
            # Down spike then up
            if recent_prices[-3] > recent_prices[-2] and recent_prices[-2] < recent_prices[-1]:
                avg_volume = np.mean(volumes[-30:])
                if recent_volumes[-2] > avg_volume * 1.5:
                    return True, "down"
        
        return False, "none"
    
    def compute_tick_momentum(self) -> float:
        """
        Compute tick momentum (microstructure signal).
        
        Returns:
            Tick momentum (-1 to 1, positive = bullish)
        """
        if len(self.up_ticks) == 0 and len(self.down_ticks) == 0:
            return 0.0
        
        # Count recent ticks (last 30 seconds)
        current_time = self.timestamps[-1] if self.timestamps else 0
        cutoff_time = current_time - 30
        
        up_count = sum(1 for t in self.up_ticks if t >= cutoff_time)
        down_count = sum(1 for t in self.down_ticks if t >= cutoff_time)
        
        total = up_count + down_count
        if total == 0:
            return 0.0
        
        # Momentum: positive = more up ticks
        momentum = (up_count - down_count) / total
        
        return momentum
    
    def _compute_ema(self, prices: np.ndarray, period: int) -> float:
        """
        Compute Exponential Moving Average.
        
        EMA = price * k + EMA_prev * (1 - k)
        k = 2 / (period + 1)
        """
        if len(prices) < period:
            return np.mean(prices)
        
        k = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = price * k + ema * (1 - k)
        
        return ema
    
    def _find_peaks(self, data: np.ndarray) -> list[float]:
        """Find local maxima in data."""
        peaks = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i-1] and data[i] > data[i+1]:
                peaks.append(data[i])
        return peaks
    
    def _find_troughs(self, data: np.ndarray) -> list[float]:
        """Find local minima in data."""
        troughs = []
        for i in range(1, len(data) - 1):
            if data[i] < data[i-1] and data[i] < data[i+1]:
                troughs.append(data[i])
        return troughs


def compute_composite_score(indicators: dict[str, any]) -> tuple[float, dict[str, float]]:
    """
    Compute composite score from all indicators.
    
    Score breakdown:
    - RSI: 15%
    - MACD: 15%
    - Bollinger: 10%
    - EMA Cross: 10%
    - VWAP: 10%
    - Order Flow: 15%
    - Price Action: 10%
    - Liquidity: 5%
    - Tick Momentum: 10%
    
    Args:
        indicators: Dict of all computed indicators
    
    Returns:
        (composite_score 0-100, component_scores)
    """
    component_scores = {}
    
    # 1. RSI Score (15%)
    rsi = indicators.get("rsi_5s", 50.0)
    if rsi < 30:  # Oversold = bullish
        rsi_score = (30 - rsi) / 30 * 100  # 0-100
    elif rsi > 70:  # Overbought = bearish (negative score)
        rsi_score = -(rsi - 70) / 30 * 100
    else:
        rsi_score = 0  # Neutral
    component_scores["rsi"] = rsi_score * 0.15
    
    # 2. MACD Score (15%)
    macd_hist = indicators.get("macd_histogram", 0.0)
    macd_score = np.clip(macd_hist * 10000, -100, 100)  # Normalize
    component_scores["macd"] = macd_score * 0.15
    
    # 3. Bollinger Score (10%)
    bb_position = indicators.get("bb_position", 0.0)  # -1 to 1
    component_scores["bollinger"] = bb_position * 100 * 0.10
    
    # 4. EMA Cross Score (10%)
    ema_bullish = indicators.get("ema_bullish_count", 0)  # 0-3
    ema_score = (ema_bullish / 3) * 100  # 0-100
    component_scores["ema_cross"] = ema_score * 0.10
    
    # 5. VWAP Score (10%)
    vwap_dev = indicators.get("vwap_deviation", 0.0)
    vwap_score = np.clip(vwap_dev * 10000, -100, 100)
    component_scores["vwap"] = vwap_score * 0.10
    
    # 6. Order Flow Score (15%)
    order_flow = indicators.get("order_flow_imbalance", 0.0)  # -1 to 1
    component_scores["order_flow"] = order_flow * 100 * 0.15
    
    # 7. Price Action Score (10%)
    pattern_confidence = indicators.get("price_action_confidence", 0.0)
    pattern_direction = indicators.get("price_action_direction", 0)  # -1, 0, 1
    component_scores["price_action"] = pattern_direction * pattern_confidence * 100 * 0.10
    
    # 8. Liquidity Sweep Score (5%)
    is_sweep = indicators.get("liquidity_sweep", False)
    sweep_direction = indicators.get("sweep_direction", 0)  # -1 or 1
    component_scores["liquidity"] = sweep_direction * 100 * 0.05 if is_sweep else 0
    
    # 9. Tick Momentum Score (10%)
    tick_momentum = indicators.get("tick_momentum", 0.0)  # -1 to 1
    component_scores["tick_momentum"] = tick_momentum * 100 * 0.10
    
    # Composite score
    composite = sum(component_scores.values())
    
    # Normalize to 0-100 (currently can be negative for bearish)
    # Positive = bullish, Negative = bearish, 0 = neutral
    
    return composite, component_scores

