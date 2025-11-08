"""Cross-sectional ranking system for symbol selection."""

import numpy as np

from src.bitget_trading.logger import get_logger
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager, SymbolState

logger = get_logger()


class CrossSectionalRanker:
    """
    Ranks symbols cross-sectionally using rule-based scores and bandit overlay.
    
    Selects top K symbols without requiring training.
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
        """
        Initialize ranker.
        
        Args:
            momentum_weight: Weight for momentum signal
            imbalance_weight: Weight for order book imbalance
            volatility_weight: Weight for volatility factor
            liquidity_weight: Weight for liquidity
            bandit_alpha: Mix ratio (1=all rules, 0=all bandit)
            ucb_exploration: UCB exploration constant
        """
        self.momentum_weight = momentum_weight
        self.imbalance_weight = imbalance_weight
        self.volatility_weight = volatility_weight
        self.liquidity_weight = liquidity_weight
        self.bandit_alpha = bandit_alpha
        self.ucb_exploration = ucb_exploration

    def compute_rule_score(self, state: SymbolState, features: dict[str, float]) -> float:
        """
        Compute rule-based score for a symbol.
        
        Args:
            state: Symbol state
            features: Feature dictionary
        
        Returns:
            Rule-based score
        """
        score = 0.0
        
        # 1. Momentum component (Sharpe-like)
        return_15s = features.get("return_15s", 0.0)
        volatility_60s = features.get("volatility_60s", 1.0)
        
        if volatility_60s > 1e-6:
            momentum_score = return_15s / volatility_60s
        else:
            momentum_score = 0.0
        
        score += self.momentum_weight * momentum_score
        
        # 2. Order book imbalance component
        ob_imbalance = features.get("ob_imbalance", 0.0)
        # Imbalance in [-1, 1], positive means more bids (bullish)
        score += self.imbalance_weight * ob_imbalance
        
        # 3. Volatility factor (reward moderate volatility, penalize extremes)
        volatility_30s = features.get("volatility_30s", 0.0)
        
        # Optimal volatility range (normalized)
        optimal_vol = 0.001  # ~0.1% per bar
        if volatility_30s > 0:
            vol_ratio = min(volatility_30s / optimal_vol, optimal_vol / volatility_30s)
            volatility_score = vol_ratio  # In [0, 1], peaks at optimal_vol
        else:
            volatility_score = 0.0
        
        score += self.volatility_weight * volatility_score
        
        # 4. Liquidity component
        spread_bps = features.get("spread_bps", 100.0)
        total_depth = features.get("total_bid_depth", 0) + features.get("total_ask_depth", 0)
        
        # Tighter spread = better
        spread_score = max(0, 1 - spread_bps / 50.0)  # Normalize by 50bps
        
        # More depth = better (log scale)
        depth_score = np.log1p(total_depth) / 10.0  # Rough normalization
        
        liquidity_score = (spread_score + depth_score) / 2
        score += self.liquidity_weight * liquidity_score
        
        return score

    def rank_symbols(
        self,
        state_manager: MultiSymbolStateManager,
        top_k: int = 10,
        min_spread_bps: float = 100.0,
        min_depth: float = 1000.0,
    ) -> list[tuple[str, float]]:
        """
        Rank all symbols and return top K.
        
        Args:
            state_manager: Multi-symbol state manager
            top_k: Number of top symbols to return
            min_spread_bps: Filter out symbols with spread > this
            min_depth: Filter out symbols with depth < this
        
        Returns:
            List of (symbol, combined_score) tuples, sorted descending
        """
        scores = []
        
        # Get all features
        all_features = state_manager.get_all_features()
        
        for symbol, features in all_features.items():
            state = state_manager.get_state(symbol)
            if not state:
                continue
            
            # Apply filters
            if features.get("spread_bps", 1000) > min_spread_bps:
                continue
            
            total_depth = features.get("total_bid_depth", 0) + features.get("total_ask_depth", 0)
            if total_depth < min_depth:
                continue
            
            # Compute rule-based score
            rule_score = self.compute_rule_score(state, features)
            
            # Compute bandit score (UCB)
            bandit_score = state.get_ucb_score(
                state_manager.total_selections,
                c=self.ucb_exploration,
            )
            
            # Normalize and combine
            # Clip rule score for reasonable range
            rule_score_norm = np.clip(rule_score, -5, 5) / 5.0
            
            # Clip bandit score (avg return is in percentage)
            if np.isfinite(bandit_score):
                bandit_score_norm = np.clip(bandit_score, -100, 100) / 100.0
            else:
                bandit_score_norm = 1.0  # Unexplored = high priority
            
            # Combined score
            combined_score = (
                self.bandit_alpha * rule_score_norm +
                (1 - self.bandit_alpha) * bandit_score_norm
            )
            
            scores.append((symbol, combined_score, rule_score, bandit_score))
        
        # Sort by combined score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Log top symbols
        if scores:
            logger.debug(
                "ranking_completed",
                total_symbols=len(scores),
                top_5=[(s[0], f"{s[1]:.3f}") for s in scores[:5]],
            )
        
        # Return top K
        return [(s[0], s[1]) for s in scores[:top_k]]

    def allocate_capital(
        self,
        ranked_symbols: list[tuple[str, float]],
        total_capital: float,
        max_per_symbol_pct: float = 0.10,
    ) -> dict[str, float]:
        """
        Allocate capital proportionally to scores.
        
        Args:
            ranked_symbols: List of (symbol, score) tuples
            total_capital: Total capital to allocate
            max_per_symbol_pct: Max % of capital per symbol
        
        Returns:
            Dict mapping symbol to allocated capital
        """
        if not ranked_symbols:
            return {}
        
        # Clip negative scores to zero
        positive_scores = [(s, max(score, 0)) for s, score in ranked_symbols]
        
        # Total positive score
        total_score = sum(score for _, score in positive_scores)
        
        if total_score == 0:
            # Equal weight
            equal_weight = total_capital / len(positive_scores)
            return {s: equal_weight for s, _ in positive_scores}
        
        # Proportional allocation
        allocations = {}
        for symbol, score in positive_scores:
            proportion = score / total_score
            allocated = total_capital * proportion
            
            # Cap per symbol
            max_per_symbol = total_capital * max_per_symbol_pct
            allocated = min(allocated, max_per_symbol)
            
            allocations[symbol] = allocated
        
        return allocations

