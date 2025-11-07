"""Dynamic parameter adjustment based on token performance."""

from typing import Any

from bitget_trading.logger import get_logger
from bitget_trading.symbol_performance_tracker import SymbolPerformance, SymbolPerformanceTracker

logger = get_logger()


class DynamicParams:
    """
    Calculate dynamic trading parameters based on token performance.
    
    Adjusts:
    - Trailing TP callback rate (4% -> 6% for best tokens)
    - Position size multiplier (1.0x -> 1.3x for best tokens)
    - Entry threshold (lower for best tokens = more trades)
    """

    def __init__(
        self,
        performance_tracker: SymbolPerformanceTracker,
        enabled: bool = True,
    ) -> None:
        """
        Initialize dynamic params calculator.
        
        Args:
            performance_tracker: Performance tracker instance
            enabled: Whether dynamic params are enabled
        """
        self.performance_tracker = performance_tracker
        self.enabled = enabled
        
        # Performance tiers
        self.tier_thresholds = {
            "tier1": 0.80,  # Top 20% (best performers)
            "tier2": 0.50,  # Top 50% (good performers)
            "tier3": 0.20,  # Bottom 20% (poor performers)
        }

    def get_performance_tier(self, symbol: str) -> str:
        """
        Get performance tier for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Tier: "tier1", "tier2", "tier3", "tier4" (default)
        """
        if not self.enabled:
            return "tier3"  # Default tier
        
        perf = self.performance_tracker.get_performance(symbol)
        if not perf:
            return "tier3"  # Default tier
        
        # Get all performances to calculate percentiles
        all_perfs = self.performance_tracker.get_all_performances()
        if not all_perfs:
            return "tier3"
        
        # Calculate combined scores
        scores = [
            (s, p.combined_score)
            for s, p in all_perfs.items()
            if p.combined_score > 0
        ]
        
        if not scores:
            return "tier3"
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Find symbol's rank
        symbol_score = perf.combined_score
        rank = next(
            (i for i, (s, score) in enumerate(scores) if s == symbol),
            len(scores)
        )
        
        percentile = 1.0 - (rank / len(scores)) if scores else 0.0
        
        # Determine tier
        if percentile >= self.tier_thresholds["tier1"]:
            return "tier1"
        elif percentile >= self.tier_thresholds["tier2"]:
            return "tier2"
        elif percentile < self.tier_thresholds["tier3"]:
            return "tier4"
        else:
            return "tier3"

    def get_trailing_tp_callback(
        self,
        symbol: str,
        default_callback: float = 0.04,
    ) -> float:
        """
        Get trailing TP callback rate for a symbol.
        
        Args:
            symbol: Trading pair
            default_callback: Default callback rate (4% = 0.04)
            
        Returns:
            Callback rate (0.03-0.06)
        """
        if not self.enabled:
            return default_callback
        
        tier = self.get_performance_tier(symbol)
        
        # Tier-based callback rates
        callback_rates = {
            "tier1": 0.06,  # 6% for best tokens (top 20%)
            "tier2": 0.05,  # 5% for good tokens (top 50%)
            "tier3": default_callback,  # 4% default
            "tier4": 0.03,  # 3% for poor tokens (bottom 20%)
        }
        
        callback = callback_rates.get(tier, default_callback)
        
        logger.debug(
            f"📊 [DYNAMIC PARAMS] {symbol} | Tier: {tier} | "
            f"Trailing TP callback: {callback:.2%}"
        )
        
        return callback

    def get_position_size_multiplier(
        self,
        symbol: str,
        default_multiplier: float = 1.0,
    ) -> float:
        """
        Get position size multiplier for a symbol.
        
        Args:
            symbol: Trading pair
            default_multiplier: Default multiplier (1.0x)
            
        Returns:
            Position size multiplier (0.8x-1.3x)
        """
        if not self.enabled:
            return default_multiplier
        
        tier = self.get_performance_tier(symbol)
        
        # Tier-based multipliers
        multipliers = {
            "tier1": 1.3,  # 30% larger for best tokens
            "tier2": 1.15,  # 15% larger for good tokens
            "tier3": default_multiplier,  # Default
            "tier4": 0.8,  # 20% smaller for poor tokens
        }
        
        multiplier = multipliers.get(tier, default_multiplier)
        
        logger.debug(
            f"📊 [DYNAMIC PARAMS] {symbol} | Tier: {tier} | "
            f"Position size multiplier: {multiplier:.2f}x"
        )
        
        return multiplier

    def get_entry_threshold(
        self,
        symbol: str,
        default_threshold: float = 0.5,
    ) -> float:
        """
        Get entry threshold for a symbol.
        
        Lower threshold = more trades (for best tokens).
        Higher threshold = fewer trades (for poor tokens).
        
        Args:
            symbol: Trading pair
            default_threshold: Default threshold (0.5)
            
        Returns:
            Entry threshold (0.3-0.7)
        """
        if not self.enabled:
            return default_threshold
        
        tier = self.get_performance_tier(symbol)
        
        # Tier-based thresholds
        thresholds = {
            "tier1": 0.3,  # Lower threshold = more trades for best tokens
            "tier2": 0.4,  # Slightly lower for good tokens
            "tier3": default_threshold,  # Default
            "tier4": 0.7,  # Higher threshold = fewer trades for poor tokens
        }
        
        threshold = thresholds.get(tier, default_threshold)
        
        logger.debug(
            f"📊 [DYNAMIC PARAMS] {symbol} | Tier: {tier} | "
            f"Entry threshold: {threshold:.2f}"
        )
        
        return threshold

    def get_all_params(
        self,
        symbol: str,
        default_callback: float = 0.04,
        default_multiplier: float = 1.0,
        default_threshold: float = 0.5,
    ) -> dict[str, Any]:
        """
        Get all dynamic parameters for a symbol.
        
        Args:
            symbol: Trading pair
            default_callback: Default trailing TP callback
            default_multiplier: Default position size multiplier
            default_threshold: Default entry threshold
            
        Returns:
            Dict with trailing_tp_callback, position_size_multiplier, entry_threshold, tier
        """
        tier = self.get_performance_tier(symbol)
        
        return {
            "tier": tier,
            "trailing_tp_callback": self.get_trailing_tp_callback(symbol, default_callback),
            "position_size_multiplier": self.get_position_size_multiplier(symbol, default_multiplier),
            "entry_threshold": self.get_entry_threshold(symbol, default_threshold),
        }

