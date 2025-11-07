"""Market regime detection for adaptive trading strategies."""

import numpy as np
import pandas as pd

from bitget_trading.logger import get_logger

logger = get_logger()


class MarketRegime:
    """Market regime types."""
    
    TRENDING = "trending"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    VOLATILE = "volatile"


class RegimeDetector:
    """
    Detect market regime to adapt trading parameters.
    
    Different regimes require different strategies:
    - TRENDING: Wide stops, let winners run
    - RANGING: Tight stops, quick profits
    - BREAKOUT: Aggressive entries
    - VOLATILE: Reduce position sizes
    """

    def __init__(
        self,
        adx_threshold: float = 25.0,
        volatility_threshold_high: float = 3.0,
        volatility_threshold_low: float = 1.0,
    ) -> None:
        """
        Initialize regime detector.
        
        Args:
            adx_threshold: ADX above this = trending
            volatility_threshold_high: Volatility above this = volatile
            volatility_threshold_low: Volatility below this = ranging
        """
        self.adx_threshold = adx_threshold
        self.volatility_threshold_high = volatility_threshold_high
        self.volatility_threshold_low = volatility_threshold_low

    def calculate_adx(self, price_history: list[tuple[float, float]], period: int = 14) -> float:
        """
        Calculate ADX (Average Directional Index).
        
        Args:
            price_history: List of (timestamp, price) tuples
            period: ADX period
        
        Returns:
            ADX value (0-100)
        """
        if len(price_history) < period + 1:
            return 0.0
        
        prices = np.array([p for _, p in price_history[-period-1:]])
        
        # Calculate directional movements
        high_low_diff = np.diff(prices)
        
        # Positive and negative directional movements
        pos_dm = np.where(high_low_diff > 0, high_low_diff, 0)
        neg_dm = np.where(high_low_diff < 0, -high_low_diff, 0)
        
        # Smooth with EMA
        alpha = 1.0 / period
        pos_di = pd.Series(pos_dm).ewm(alpha=alpha).mean().iloc[-1]
        neg_di = pd.Series(neg_dm).ewm(alpha=alpha).mean().iloc[-1]
        
        # Calculate DX and ADX
        if pos_di + neg_di == 0:
            return 0.0
        
        dx = abs(pos_di - neg_di) / (pos_di + neg_di) * 100
        
        return dx  # Simplified ADX

    def detect_regime(
        self,
        price_history: list[tuple[float, float]],
        volatility: float,
        volume_ratio: float = 1.0,
    ) -> str:
        """
        Detect current market regime.
        
        Args:
            price_history: List of (timestamp, price) tuples
            volatility: Current volatility (%)
            volume_ratio: Current volume / average volume
        
        Returns:
            Regime type (TRENDING, RANGING, BREAKOUT, VOLATILE)
        """
        if len(price_history) < 20:
            return MarketRegime.RANGING  # Default to ranging
        
        # Calculate trend strength
        adx = self.calculate_adx(price_history)
        
        # Check for breakout (high volume + volatility spike)
        if volume_ratio > 2.0 and volatility > self.volatility_threshold_high:
            return MarketRegime.BREAKOUT
        
        # Check for high volatility
        if volatility > self.volatility_threshold_high:
            return MarketRegime.VOLATILE
        
        # Check for trending
        if adx > self.adx_threshold:
            return MarketRegime.TRENDING
        
        # Default to ranging
        if volatility < self.volatility_threshold_low:
            return MarketRegime.RANGING
        
        # Medium volatility, medium trend
        return MarketRegime.RANGING

    def get_regime_parameters(self, regime: str) -> dict[str, float]:
        """
        Get trading parameters for a regime.
        
        Returns:
            Dict with stop_loss_pct, take_profit_pct, trailing_stop_pct, position_size_multiplier
        """
        if regime == MarketRegime.TRENDING:
            return {
                "stop_loss_pct": 0.20,      # 20% capital (0.8% price @ 25x) - WIDER ROOM!
                "take_profit_pct": 0.14,    # 14% capital (0.56% price @ 25x) - WITH trailing protection!
                "trailing_stop_pct": 0.04,  # 4% capital (0.16% price @ 25x) - ACTIVE!
                "position_size_multiplier": 1.5,  # 50% larger for trending (was 1.2)
            }
        
        elif regime == MarketRegime.RANGING:
            return {
                "stop_loss_pct": 0.20,      # 20% capital (0.8% price @ 25x) - WIDER ROOM!
                "take_profit_pct": 0.14,    # 14% in ranging (0.56% price @ 25x) - WITH trailing!
                "trailing_stop_pct": 0.04,  # 4% trailing (0.16% price @ 25x)
                "position_size_multiplier": 1.0,  # Normal size for ranging (was 0.8)
            }
        
        elif regime == MarketRegime.BREAKOUT:
            return {
                "stop_loss_pct": 0.20,      # 20% capital (0.8% price @ 25x) - WIDER ROOM!
                "take_profit_pct": 0.14,    # 14% for breakouts (0.56% price @ 25x) - WITH trailing!
                "trailing_stop_pct": 0.04,  # 4% trailing (0.16% price @ 25x) - ACTIVE!
                "position_size_multiplier": 1.3,  # 30% larger for breakouts (high conviction)
            }
        
        elif regime == MarketRegime.VOLATILE:
            return {
                "stop_loss_pct": 0.20,      # 20% capital (0.8% price @ 25x) - WIDER ROOM!
                "take_profit_pct": 0.14,    # 14% in volatile (0.56% price @ 25x) - WITH trailing!
                "trailing_stop_pct": 0.04,  # 4% trailing (0.16% price @ 25x) - ACTIVE!
                "position_size_multiplier": 0.8,  # 20% smaller in volatile (risk reduction)
            }
        
        else:  # Default
            return {
                "stop_loss_pct": 0.20,      # 20% capital (0.8% price @ 25x) - WIDER ROOM!
                "take_profit_pct": 0.14,    # 14% default (0.56% price @ 25x) - WITH trailing!
                "trailing_stop_pct": 0.04,  # OPTIMIZED: Same 4% trailing
                "position_size_multiplier": 1.0,
            }

