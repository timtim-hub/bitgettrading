"""Multi-symbol state management and online statistics."""

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

import numpy as np

from bitget_trading.logger import get_logger

logger = get_logger()


@dataclass
class Trade:
    """Individual trade record."""
    
    timestamp: float
    pnl: float
    return_pct: float


class SymbolState:
    """
    Per-symbol state including market data and online statistics.
    
    Maintains rolling statistics without batch training.
    """

    def __init__(self, symbol: str, window_size: int = 200) -> None:
        """
        Initialize symbol state.
        
        Args:
            symbol: Symbol name
            window_size: Rolling window size for statistics
        """
        self.symbol = symbol
        self.window_size = window_size
        
        # Market data (latest)
        self.last_price: float = 0.0
        self.bid_price: float = 0.0
        self.ask_price: float = 0.0
        self.mid_price: float = 0.0
        self.spread_bps: float = 0.0
        self.volume_24h: float = 0.0
        self.funding_rate: float = 0.0
        
        # Order book
        self.bids: list[tuple[float, float]] = []
        self.asks: list[tuple[float, float]] = []
        self.total_bid_depth: float = 0.0
        self.total_ask_depth: float = 0.0
        self.ob_imbalance: float = 0.0
        
        # Price history for returns/volatility
        self.price_history: Deque[tuple[float, float]] = deque(maxlen=300)  # (timestamp, price)
        
        # Online trade statistics
        self.trades: Deque[Trade] = deque(maxlen=window_size)
        self.n_trades: int = 0
        self.n_wins: int = 0
        self.n_losses: int = 0
        self.total_pnl: float = 0.0
        
        # Bandit statistics (UCB)
        self.avg_return: float = 0.0
        self.return_variance: float = 0.0
        self.last_update_time: float = 0.0
        
        # Feature cache
        self.features: dict[str, float] = {}

    def update_ticker(self, ticker_data: dict) -> None:
        """Update from ticker data."""
        self.last_price = ticker_data.get("last_price", self.last_price)
        self.bid_price = ticker_data.get("bid_price", self.bid_price)
        self.ask_price = ticker_data.get("ask_price", self.ask_price)
        self.volume_24h = ticker_data.get("volume_24h", self.volume_24h)
        self.funding_rate = ticker_data.get("funding_rate", self.funding_rate)
        
        if self.bid_price > 0 and self.ask_price > 0:
            self.mid_price = (self.bid_price + self.ask_price) / 2
            self.spread_bps = ((self.ask_price - self.bid_price) / self.mid_price) * 10000
        
        # Update price history
        self.price_history.append((time.time(), self.mid_price))

    def update_orderbook(self, orderbook_data: dict) -> None:
        """Update from order book data."""
        self.bids = orderbook_data.get("bids", [])
        self.asks = orderbook_data.get("asks", [])
        
        # Calculate depths
        self.total_bid_depth = sum(size for _, size in self.bids)
        self.total_ask_depth = sum(size for _, size in self.asks)
        
        # Order book imbalance
        total_depth = self.total_bid_depth + self.total_ask_depth
        if total_depth > 0:
            self.ob_imbalance = (self.total_bid_depth - self.total_ask_depth) / total_depth
        else:
            self.ob_imbalance = 0.0

    def add_trade(self, pnl: float, return_pct: float) -> None:
        """
        Add a completed trade to online statistics.
        
        Args:
            pnl: Trade PnL in USDT
            return_pct: Return as percentage
        """
        trade = Trade(
            timestamp=time.time(),
            pnl=pnl,
            return_pct=return_pct,
        )
        
        self.trades.append(trade)
        self.n_trades += 1
        
        if pnl > 0:
            self.n_wins += 1
        elif pnl < 0:
            self.n_losses += 1
        
        self.total_pnl += pnl
        
        # Update online mean and variance (Welford's algorithm)
        delta = return_pct - self.avg_return
        self.avg_return += delta / self.n_trades
        delta2 = return_pct - self.avg_return
        self.return_variance += delta * delta2
        
        self.last_update_time = time.time()

    def get_win_rate(self) -> float:
        """Get rolling win rate."""
        if not self.trades:
            return 0.5  # Neutral prior
        
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades)

    def get_avg_return(self) -> float:
        """Get rolling average return."""
        if not self.trades:
            return 0.0
        
        return sum(t.return_pct for t in self.trades) / len(self.trades)

    def get_return_std(self) -> float:
        """Get rolling return standard deviation."""
        if len(self.trades) < 2:
            return 1.0  # Default
        
        variance = self.return_variance / (len(self.trades) - 1)
        return np.sqrt(max(variance, 0))

    def get_sharpe_estimate(self) -> float:
        """Get estimated Sharpe ratio from recent trades."""
        avg_ret = self.get_avg_return()
        std_ret = self.get_return_std()
        
        if std_ret > 0:
            return avg_ret / std_ret
        return 0.0

    def get_ucb_score(self, total_selections: int, c: float = 2.0) -> float:
        """
        Get UCB (Upper Confidence Bound) score for bandit selection.
        
        Args:
            total_selections: Total number of selections across all symbols
            c: Exploration constant
        
        Returns:
            UCB score
        """
        if self.n_trades == 0:
            return float('inf')  # Explore unvisited symbols first
        
        exploration_term = c * np.sqrt(np.log(total_selections + 1) / self.n_trades)
        
        return self.avg_return + exploration_term

    def compute_features(self) -> dict[str, float]:
        """
        Compute all features for this symbol.
        
        Returns:
            Feature dictionary
        """
        features = {
            # Price features
            "mid_price": self.mid_price,
            "spread_bps": self.spread_bps,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            
            # Order book
            "ob_imbalance": self.ob_imbalance,
            "total_bid_depth": self.total_bid_depth,
            "total_ask_depth": self.total_ask_depth,
            "depth_ratio": self.total_bid_depth / (self.total_ask_depth + 1e-8),
            
            # Volume
            "volume_24h": self.volume_24h,
            "funding_rate": self.funding_rate,
        }
        
        # Compute returns if we have price history
        if len(self.price_history) >= 2:
            prices = np.array([p for _, p in self.price_history])
            times = np.array([t for t, _ in self.price_history])
            
            # Short-term returns
            for window in [5, 15, 30, 60]:
                if len(prices) > window:
                    ret = (prices[-1] - prices[-window]) / prices[-window]
                    features[f"return_{window}s"] = ret
            
            # Volatility
            if len(prices) >= 30:
                returns = np.diff(prices) / prices[:-1]
                features["volatility_30s"] = np.std(returns[-30:])
                features["volatility_60s"] = np.std(returns[-60:]) if len(returns) >= 60 else np.std(returns[-30:])
        
        # Online statistics
        features["win_rate"] = self.get_win_rate()
        features["avg_return"] = self.get_avg_return()
        features["return_std"] = self.get_return_std()
        features["sharpe_estimate"] = self.get_sharpe_estimate()
        features["n_trades"] = float(self.n_trades)
        
        self.features = features
        return features


class MultiSymbolStateManager:
    """
    Manages state for all symbols in the universe.
    """

    def __init__(self) -> None:
        """Initialize multi-symbol state manager."""
        self.symbols: dict[str, SymbolState] = {}
        self.total_selections: int = 0

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol to track."""
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolState(symbol)
            logger.debug("symbol_added", symbol=symbol)

    def get_state(self, symbol: str) -> SymbolState | None:
        """Get state for a symbol."""
        return self.symbols.get(symbol)

    def update_ticker(self, symbol: str, ticker_data: dict) -> None:
        """Update ticker data for a symbol."""
        if symbol not in self.symbols:
            self.add_symbol(symbol)
        
        self.symbols[symbol].update_ticker(ticker_data)

    def update_orderbook(self, symbol: str, orderbook_data: dict) -> None:
        """Update order book for a symbol."""
        if symbol not in self.symbols:
            self.add_symbol(symbol)
        
        self.symbols[symbol].update_orderbook(orderbook_data)

    def record_trade(self, symbol: str, pnl: float, return_pct: float) -> None:
        """Record a completed trade."""
        if symbol in self.symbols:
            self.symbols[symbol].add_trade(pnl, return_pct)
            self.total_selections += 1

    def get_all_features(self) -> dict[str, dict[str, float]]:
        """Get features for all symbols."""
        return {
            symbol: state.compute_features()
            for symbol, state in self.symbols.items()
        }

    def get_active_symbols(self, min_price: float = 0.01) -> list[str]:
        """Get symbols with recent price data."""
        return [
            symbol for symbol, state in self.symbols.items()
            if state.mid_price > min_price
        ]

