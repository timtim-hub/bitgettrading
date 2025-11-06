"""Microstructure feature engineering for ultra-short-term trading."""

from collections import deque
from typing import Deque

import numpy as np
import pandas as pd

from bitget_trading.logger import get_logger

logger = get_logger()


def compute_order_book_imbalance(
    bid_sizes: np.ndarray, ask_sizes: np.ndarray
) -> float:
    """
    Compute order book imbalance.
    
    Args:
        bid_sizes: Array of bid sizes
        ask_sizes: Array of ask sizes
    
    Returns:
        Imbalance ratio: (VB - VA) / (VB + VA)
    """
    vb = np.sum(bid_sizes)
    va = np.sum(ask_sizes)
    total = vb + va
    
    if total > 0:
        return (vb - va) / total
    return 0.0


def compute_weighted_mid(
    bid_prices: np.ndarray,
    bid_sizes: np.ndarray,
    ask_prices: np.ndarray,
    ask_sizes: np.ndarray,
) -> float:
    """
    Compute volume-weighted mid price.
    
    Args:
        bid_prices: Array of bid prices
        bid_sizes: Array of bid sizes
        ask_prices: Array of ask prices
        ask_sizes: Array of ask sizes
    
    Returns:
        Weighted mid price
    """
    total_bid_vol = np.sum(bid_sizes)
    total_ask_vol = np.sum(ask_sizes)
    total_vol = total_bid_vol + total_ask_vol
    
    if total_vol > 0:
        best_bid = bid_prices[0] if len(bid_prices) > 0 else 0
        best_ask = ask_prices[0] if len(ask_prices) > 0 else 0
        
        return (best_bid * total_ask_vol + best_ask * total_bid_vol) / total_vol
    
    return (bid_prices[0] + ask_prices[0]) / 2 if len(bid_prices) > 0 and len(ask_prices) > 0 else 0


class MicrostructureFeatures:
    """
    Real-time microstructure feature computation.
    
    Maintains rolling windows of market data and computes features
    every feature_interval_ms milliseconds.
    """

    def __init__(
        self,
        feature_window_sec: int = 30,
        feature_interval_ms: int = 1000,
    ) -> None:
        """
        Initialize feature engine.
        
        Args:
            feature_window_sec: Rolling window size in seconds
            feature_interval_ms: Feature computation interval in milliseconds
        """
        self.feature_window_sec = feature_window_sec
        self.feature_interval_ms = feature_interval_ms
        
        # Rolling windows (store last N seconds of data)
        max_len = feature_window_sec * (1000 // feature_interval_ms)
        self.mid_prices: Deque[float] = deque(maxlen=max_len)
        self.timestamps: Deque[int] = deque(maxlen=max_len)
        self.spreads: Deque[float] = deque(maxlen=max_len)
        self.imbalances: Deque[float] = deque(maxlen=max_len)
        self.depths_bid: Deque[float] = deque(maxlen=max_len)
        self.depths_ask: Deque[float] = deque(maxlen=max_len)
        self.volumes: Deque[float] = deque(maxlen=max_len)
        
        # Latest orderbook snapshot
        self.last_orderbook: dict[str, any] | None = None
        self.last_ticker: dict[str, any] | None = None

    def update_ticker(self, ticker: dict[str, any]) -> None:
        """Update with new ticker data."""
        self.last_ticker = ticker

    def update_orderbook(self, orderbook: dict[str, any]) -> None:
        """Update with new orderbook snapshot."""
        self.last_orderbook = orderbook

    def compute_features(self) -> dict[str, float] | None:
        """
        Compute microstructure features from current state.
        
        Returns:
            Feature dictionary or None if insufficient data
        """
        if not self.last_orderbook or not self.last_ticker:
            return None
        
        bids = self.last_orderbook["bids"]
        asks = self.last_orderbook["asks"]
        
        if not bids or not asks:
            return None
        
        # Extract price and size arrays
        bid_prices = np.array([b[0] for b in bids])
        bid_sizes = np.array([b[1] for b in bids])
        ask_prices = np.array([a[0] for a in asks])
        ask_sizes = np.array([a[1] for a in asks])
        
        # Basic price features
        best_bid = bid_prices[0]
        best_ask = ask_prices[0]
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid
        spread_bps = (spread / mid) * 10000 if mid > 0 else 0
        
        # Store in rolling windows
        timestamp = self.last_orderbook["timestamp"]
        self.timestamps.append(timestamp)
        self.mid_prices.append(mid)
        self.spreads.append(spread_bps)
        
        # Order book imbalance features
        imb_1 = compute_order_book_imbalance(bid_sizes[:1], ask_sizes[:1])
        imb_3 = compute_order_book_imbalance(bid_sizes[:3], ask_sizes[:3])
        imb_5 = compute_order_book_imbalance(bid_sizes[:5], ask_sizes[:5])
        
        self.imbalances.append(imb_5)
        
        # Depth features
        total_bid_depth = np.sum(bid_sizes)
        total_ask_depth = np.sum(ask_sizes)
        
        self.depths_bid.append(total_bid_depth)
        self.depths_ask.append(total_ask_depth)
        
        # Depth within X bps
        depth_5bps_bid = self._compute_depth_within_bps(bid_prices, bid_sizes, mid, 5.0, is_bid=True)
        depth_10bps_bid = self._compute_depth_within_bps(bid_prices, bid_sizes, mid, 10.0, is_bid=True)
        depth_5bps_ask = self._compute_depth_within_bps(ask_prices, ask_sizes, mid, 5.0, is_bid=False)
        depth_10bps_ask = self._compute_depth_within_bps(ask_prices, ask_sizes, mid, 10.0, is_bid=False)
        
        # Price features (returns over multiple windows)
        features = {
            # Instantaneous
            "mid_price": mid,
            "spread_bps": spread_bps,
            "best_bid": best_bid,
            "best_ask": best_ask,
            
            # Imbalance
            "imbalance_1": imb_1,
            "imbalance_3": imb_3,
            "imbalance_5": imb_5,
            
            # Depth
            "depth_total_bid": total_bid_depth,
            "depth_total_ask": total_ask_depth,
            "depth_5bps_bid": depth_5bps_bid,
            "depth_10bps_bid": depth_10bps_bid,
            "depth_5bps_ask": depth_5bps_ask,
            "depth_10bps_ask": depth_10bps_ask,
            "depth_ratio": total_bid_depth / (total_ask_depth + 1e-8),
            
            # Volume
            "volume_24h": self.last_ticker.get("volume_24h", 0),
            "quote_volume_24h": self.last_ticker.get("quote_volume_24h", 0),
            
            # Funding
            "funding_rate": self.last_ticker.get("funding_rate", 0),
            "mark_index_spread_bps": self._compute_mark_index_spread_bps(),
            
            # Timestamp
            "timestamp": timestamp,
        }
        
        # Add rolling window features if we have enough data
        if len(self.mid_prices) >= 2:
            features.update(self._compute_rolling_features())
        
        return features

    def _compute_depth_within_bps(
        self,
        prices: np.ndarray,
        sizes: np.ndarray,
        mid: float,
        bps: float,
        is_bid: bool,
    ) -> float:
        """Compute total size within X basis points of mid."""
        threshold = mid * (1 - bps / 10000) if is_bid else mid * (1 + bps / 10000)
        
        total = 0.0
        for price, size in zip(prices, sizes):
            if is_bid:
                if price >= threshold:
                    total += size
                else:
                    break
            else:
                if price <= threshold:
                    total += size
                else:
                    break
        
        return total

    def _compute_mark_index_spread_bps(self) -> float:
        """Compute spread between mark and index price."""
        if not self.last_ticker:
            return 0.0
        
        mark = self.last_ticker.get("mark_price", 0)
        index = self.last_ticker.get("index_price", 0)
        
        if mark > 0 and index > 0:
            return ((mark - index) / index) * 10000
        return 0.0

    def _compute_rolling_features(self) -> dict[str, float]:
        """Compute features from rolling windows."""
        mid_prices = np.array(list(self.mid_prices))
        
        features = {}
        
        # Returns over different windows
        for window in [1, 5, 10, 20, 30]:
            if len(mid_prices) > window:
                ret = (mid_prices[-1] - mid_prices[-window-1]) / mid_prices[-window-1]
                features[f"return_{window}s"] = ret
        
        # Volatility (std of returns)
        if len(mid_prices) >= 10:
            returns = np.diff(mid_prices) / mid_prices[:-1]
            
            for window in [10, 20, 30]:
                if len(returns) >= window:
                    features[f"volatility_{window}s"] = np.std(returns[-window:])
        
        # Rolling mean spread
        if len(self.spreads) >= 10:
            spreads = np.array(list(self.spreads))
            features["spread_mean_10s"] = np.mean(spreads[-10:])
            features["spread_std_10s"] = np.std(spreads[-10:])
        
        # Rolling imbalance stats
        if len(self.imbalances) >= 10:
            imbalances = np.array(list(self.imbalances))
            features["imbalance_mean_10s"] = np.mean(imbalances[-10:])
            features["imbalance_std_10s"] = np.std(imbalances[-10:])
        
        # Momentum
        if len(mid_prices) >= 20:
            features["momentum_10_20"] = (mid_prices[-10] - mid_prices[-20]) / mid_prices[-20]
        
        return features

    def get_feature_names(self) -> list[str]:
        """Get list of all feature names."""
        # Generate a sample to get all feature names
        if not self.last_orderbook or not self.last_ticker:
            return []
        
        features = self.compute_features()
        if features:
            return [k for k in features.keys() if k != "timestamp"]
        return []

    def to_dataframe(self) -> pd.DataFrame:
        """Convert rolling windows to DataFrame for analysis."""
        if len(self.mid_prices) == 0:
            return pd.DataFrame()
        
        return pd.DataFrame({
            "timestamp": list(self.timestamps),
            "mid_price": list(self.mid_prices),
            "spread_bps": list(self.spreads),
            "imbalance": list(self.imbalances),
            "depth_bid": list(self.depths_bid),
            "depth_ask": list(self.depths_ask),
        })

