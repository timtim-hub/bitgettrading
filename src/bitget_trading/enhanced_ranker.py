"""Enhanced cross-sectional ranking with multi-timeframe confluence and smart sizing."""

import numpy as np

from bitget_trading.logger import get_logger
from bitget_trading.multi_symbol_state import MultiSymbolStateManager, SymbolState
from bitget_trading.regime_detector import MarketRegime, RegimeDetector

logger = get_logger()


class EnhancedRanker:
    """
    Enhanced ranking system with:
    - Multi-timeframe confluence
    - Smart position sizing
    - Volume filtering
    - Funding rate bias
    - Correlation awareness
    """

    def __init__(
        self,
        momentum_weight: float = 0.4,
        imbalance_weight: float = 0.3,
        volatility_weight: float = 0.2,
        liquidity_weight: float = 0.1,
        bandit_alpha: float = 0.5,
        ucb_exploration: float = 2.0,
    ) -> None:
        """Initialize enhanced ranker."""
        self.momentum_weight = momentum_weight
        self.imbalance_weight = imbalance_weight
        self.volatility_weight = volatility_weight
        self.liquidity_weight = liquidity_weight
        self.bandit_alpha = bandit_alpha
        self.ucb_exploration = ucb_exploration
        
        # NEW: Regime detector
        self.regime_detector = RegimeDetector()
        
        # NEW: BTC correlation tracking (for diversification)
        self.btc_correlations: dict[str, float] = {}

    def check_multi_timeframe_confluence(self, features: dict[str, float]) -> tuple[bool, str, float]:
        """
        SMART: Use available timeframes with quality requirement.
        
        If 60s data available: Require 2/3 agreement
        If only 5s-15s available: Use what we have with higher threshold
        
        Returns:
            (has_confluence, direction, strength)
        """
        # Get all available returns
        return_5s = features.get("return_5s", None)
        return_15s = features.get("return_15s", None)
        return_60s = features.get("return_60s", None)
        
        # Filter to available returns
        available_timeframes = []
        if return_5s is not None and return_5s != 0:
            available_timeframes.append(("5s", return_5s))
        if return_15s is not None and return_15s != 0:
            available_timeframes.append(("15s", return_15s))
        if return_60s is not None and return_60s != 0:
            available_timeframes.append(("60s", return_60s))
        
        if len(available_timeframes) == 0:
            return False, "neutral", 0.0
        
        # Count bullish/bearish
        bullish_count = sum(1 for _, r in available_timeframes if r > 0)
        bearish_count = sum(1 for _, r in available_timeframes if r < 0)
        
        total_timeframes = len(available_timeframes)
        
        # Adaptive threshold based on data available
        if total_timeframes == 1:
            required_agreement = 1  # With only 1 timeframe, accept it if strong
        elif total_timeframes == 2:
            required_agreement = 2  # Need both to agree
        else:
            required_agreement = 2  # Need 2 out of 3+
        
        if bullish_count >= required_agreement:
            # Bullish confluence
            avg_return = sum(r for _, r in available_timeframes) / total_timeframes
            strength = abs(avg_return)
            return True, "long", strength
        elif bearish_count >= required_agreement:
            # Bearish confluence
            avg_return = sum(r for _, r in available_timeframes) / total_timeframes
            strength = abs(avg_return)
            return True, "short", strength
        
        return False, "neutral", 0.0

    def compute_enhanced_score(
        self, state: SymbolState, features: dict[str, float], btc_return: float = 0.0
    ) -> tuple[float, str, dict]:
        """
        Compute enhanced score with all improvements.
        
        Returns:
            (score, predicted_side, metadata)
        """
        # 1. Multi-timeframe confluence CHECK
        has_confluence, direction, confluence_strength = self.check_multi_timeframe_confluence(features)
        
        if not has_confluence:
            # No confluence = skip this symbol
            return 0.0, "neutral", {"reason": "no_confluence"}
        
        # 2. Volume filter CHECK (RELAXED from 1.2 to 1.0)
        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio < 0.8:  # Only skip if significantly below average
            return 0.0, "neutral", {"reason": "low_volume"}
        
        # 3. Detect market regime
        price_history = list(state.price_history)
        volatility = features.get("volatility_60s", 0.01)
        regime = self.regime_detector.detect_regime(price_history, volatility * 100, volume_ratio)
        
        # 4. Base momentum score (Sharpe-like)
        return_15s = features.get("return_15s", 0.0)
        volatility_60s = features.get("volatility_60s", 1.0)
        
        if volatility_60s > 1e-6:
            momentum_score = return_15s / volatility_60s
        else:
            momentum_score = 0.0
        
        # 5. Order book imbalance
        ob_imbalance = features.get("ob_imbalance", 0.0)
        
        # 6. Volatility factor
        volatility_30s = features.get("volatility_30s", 0.0)
        optimal_vol = 0.002
        if volatility_30s > 0:
            vol_ratio = min(volatility_30s / optimal_vol, optimal_vol / volatility_30s)
            volatility_score = vol_ratio
        else:
            volatility_score = 0.0
        
        # 7. Liquidity score
        spread_bps = features.get("spread_bps", 100.0)
        spread_score = max(0, 1 - spread_bps / 50.0)
        
        # 8. Funding rate bias (EXPLOIT FUNDING!)
        funding_rate = features.get("funding_rate", 0.0)
        funding_bias = 0.0
        if direction == "long" and funding_rate < 0:  # Longs get paid
            funding_bias = 0.2  # Boost long score
        elif direction == "short" and funding_rate > 0:  # Shorts get paid
            funding_bias = 0.2  # Boost short score
        
        # Combine all scores
        base_score = (
            self.momentum_weight * momentum_score +
            self.imbalance_weight * ob_imbalance +
            self.volatility_weight * volatility_score +
            self.liquidity_weight * spread_score +
            funding_bias
        )
        
        # 9. Boost by confluence strength
        base_score *= (1 + confluence_strength)
        
        # 10. Boost by volume ratio
        base_score *= (1 + (volume_ratio - 1) * 0.5)  # 50% of excess volume
        
        # 11. UCB bandit overlay
        bandit_score = state.get_ucb_score(1000, c=self.ucb_exploration)
        if np.isfinite(bandit_score):
            bandit_norm = np.clip(bandit_score, -100, 100) / 100.0
        else:
            bandit_norm = 1.0
        
        # Combined final score
        final_score = (
            self.bandit_alpha * np.clip(base_score, -5, 5) / 5.0 +
            (1 - self.bandit_alpha) * bandit_norm
        )
        
        metadata = {
            "regime": regime,
            "confluence": confluence_strength,
            "volume_ratio": volume_ratio,
            "funding_rate": funding_rate,
        }
        
        return final_score, direction, metadata

    def calculate_smart_position_size(
        self,
        base_size: float,
        signal_strength: float,
        regime: str,
        volatility: float,
    ) -> float:
        """
        Calculate position size based on signal quality and market regime.
        
        Args:
            base_size: Base position size (10% of capital)
            signal_strength: Signal strength (0-1)
            regime: Market regime
            volatility: Current volatility
        
        Returns:
            Adjusted position size
        """
        # Start with base size
        size = base_size
        
        # 1. Scale by signal strength
        if signal_strength > 0.8:
            size *= 1.3  # 30% larger for very strong signals
        elif signal_strength > 0.7:
            size *= 1.15  # 15% larger for strong signals
        elif signal_strength < 0.6:
            size *= 0.7  # 30% smaller for weak signals
        
        # 2. Adjust for regime
        regime_params = self.regime_detector.get_regime_parameters(regime)
        size *= regime_params["position_size_multiplier"]
        
        # 3. Reduce in high volatility (risk management)
        if volatility > 0.03:  # > 3% volatility
            size *= 0.7
        elif volatility > 0.05:  # > 5% volatility
            size *= 0.5
        
        # Cap at 15% max, 3% min
        size = np.clip(size, base_size * 0.3, base_size * 1.5)
        
        return size

    def rank_symbols_enhanced(
        self,
        state_manager: MultiSymbolStateManager,
        top_k: int = 10,
    ) -> list[dict]:
        """
        Enhanced ranking with all improvements.
        
        Returns:
            List of dicts with symbol, score, side, metadata, position_size_multiplier
        """
        all_features = state_manager.get_all_features()
        
        logger.debug(f"🔍 Analyzing {len(all_features)} symbols for ranking")
        
        # Get BTC return for correlation check
        btc_features = all_features.get("BTCUSDT", {})
        btc_return = btc_features.get("return_5min", 0.0)
        
        scored_symbols = []
        skip_reasons = {"no_confluence": 0, "low_volume": 0, "low_score": 0}
        
        for symbol, features in all_features.items():
            state = state_manager.get_state(symbol)
            if not state:
                continue
            
            # Compute enhanced score
            score, direction, metadata = self.compute_enhanced_score(state, features, btc_return)
            
            if score <= 0:
                # Track why symbols are being skipped
                reason = metadata.get("reason", "low_score")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                continue
            
            # Calculate position size multiplier
            volatility = features.get("volatility_60s", 0.01)
            size_multiplier = self.calculate_smart_position_size(
                base_size=1.0,  # Will be multiplied by actual capital later
                signal_strength=score,
                regime=metadata["regime"],
                volatility=volatility,
            )
            
            scored_symbols.append({
                "symbol": symbol,
                "score": score,
                "predicted_side": direction,
                "position_size_multiplier": size_multiplier,
                "regime": metadata["regime"],
                "confluence": metadata["confluence"],
                "volume_ratio": metadata["volume_ratio"],
                "funding_rate": metadata["funding_rate"],
                "volatility": volatility,
            })
        
        # Sort by score
        scored_symbols.sort(key=lambda x: x["score"], reverse=True)
        
        # Correlation filter: Limit BTC-correlated positions
        if btc_return != 0:
            filtered = self._apply_correlation_filter(scored_symbols, all_features, top_k)
        else:
            filtered = scored_symbols[:top_k]
        
        logger.info(
            "enhanced_ranking_complete",
            total_analyzed=len(all_features),
            scored=len(scored_symbols),
            after_filters=len(filtered),
            skip_reasons=skip_reasons,
        )
        
        if filtered:
            logger.info(
                "top_ranked",
                top_3=[(s["symbol"], f"{s['score']:.3f}", s["regime"]) for s in filtered[:3]],
            )
        
        return filtered

    def _apply_correlation_filter(
        self,
        scored_symbols: list[dict],
        all_features: dict,
        top_k: int,
    ) -> list[dict]:
        """
        Apply correlation filter to ensure diversification.
        
        Limits highly BTC-correlated positions.
        """
        btc_return_5min = all_features.get("BTCUSDT", {}).get("return_5min", 0)
        
        selected = []
        btc_correlated_count = 0
        max_btc_correlated = top_k // 2  # Max 50% BTC-correlated
        
        for candidate in scored_symbols:
            if len(selected) >= top_k:
                break
            
            symbol = candidate["symbol"]
            
            # Check BTC correlation
            symbol_return = all_features.get(symbol, {}).get("return_5min", 0)
            
            if btc_return_5min != 0 and symbol_return != 0:
                # Simple correlation: same direction?
                is_correlated = (btc_return_5min * symbol_return) > 0
                
                if is_correlated and symbol != "BTCUSDT":
                    if btc_correlated_count >= max_btc_correlated:
                        logger.debug(f"Skipping {symbol} - too many BTC-correlated positions")
                        continue
                    btc_correlated_count += 1
            
            selected.append(candidate)
        
        return selected

