"""Multi-symbol state management and online statistics."""

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

import numpy as np

from bitget_trading.logger import get_logger
from bitget_trading.advanced_indicators import AdvancedIndicators, compute_composite_score

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
        
        # Price history for returns/volatility (extended for multi-timeframe)
        self.price_history: Deque[tuple[float, float]] = deque(maxlen=3600)  # 1 hour at 1Hz
        
        # Volume history
        self.volume_history: Deque[tuple[float, float]] = deque(maxlen=300)  # (timestamp, volume)
        
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
        
        # Advanced indicators
        self.advanced_indicators = AdvancedIndicators()

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
        timestamp = time.time()
        self.price_history.append((timestamp, self.mid_price))
        
        # Update volume history
        self.volume_history.append((timestamp, self.volume_24h))
        
        # Update advanced indicators
        self.advanced_indicators.update(
            price=self.mid_price if self.mid_price > 0 else self.last_price,
            volume=self.volume_24h,
            timestamp=timestamp,
            bid_volume=self.total_bid_depth,
            ask_volume=self.total_ask_depth,
        )

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
        Compute all features for this symbol including MULTI-TIMEFRAME.
        
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
        
        # Multi-timeframe returns and volatility
        if len(self.price_history) >= 2:
            prices = np.array([p for _, p in self.price_history])
            times = np.array([t for t, _ in self.price_history])
            
            # MULTIPLE TIMEFRAMES (confluence analysis)
            timeframes = {
                "5s": 5,
                "15s": 15,
                "30s": 30,
                "60s": 60,
                "5min": 300,
                "15min": 900,
                "1hr": 3600,
            }
            
            for name, window in timeframes.items():
                if len(prices) > window:
                    ret = (prices[-1] - prices[-window]) / prices[-window]
                    features[f"return_{name}"] = ret
            
            # Multi-timeframe volatility
            if len(prices) >= 30:
                returns = np.diff(prices) / prices[:-1]
                features["volatility_30s"] = np.std(returns[-30:])
                features["volatility_60s"] = np.std(returns[-60:]) if len(returns) >= 60 else np.std(returns[-30:])
                features["volatility_5min"] = np.std(returns[-300:]) if len(returns) >= 300 else features["volatility_60s"]
        
        # Volume analysis
        if len(self.volume_history) >= 2:
            volumes = np.array([v for _, v in self.volume_history])
            if len(volumes) >= 60:
                avg_volume = np.mean(volumes[-300:]) if len(volumes) >= 300 else np.mean(volumes)
                current_volume = volumes[-1]
                features["volume_ratio"] = current_volume / (avg_volume + 1e-8)
            else:
                features["volume_ratio"] = 1.0
        else:
            features["volume_ratio"] = 1.0
        
        # Online statistics
        features["win_rate"] = self.get_win_rate()
        features["avg_return"] = self.get_avg_return()
        features["return_std"] = self.get_return_std()
        features["sharpe_estimate"] = self.get_sharpe_estimate()
        features["n_trades"] = float(self.n_trades)
        
        # ADVANCED INDICATORS (World-class technical analysis)
        try:
            # RSI (multiple timeframes)
            features["rsi_2s"] = self.advanced_indicators.compute_rsi(period=2)
            features["rsi_5s"] = self.advanced_indicators.compute_rsi(period=5)
            features["rsi_15s"] = self.advanced_indicators.compute_rsi(period=15)
            features["rsi_30s"] = self.advanced_indicators.compute_rsi(period=30)
            
            # MACD (ultra-fast scalping params)
            macd_line, macd_signal, macd_hist = self.advanced_indicators.compute_macd(fast=3, slow=7, signal=2)
            features["macd_line"] = macd_line
            features["macd_signal"] = macd_signal
            features["macd_histogram"] = macd_hist
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = self.advanced_indicators.compute_bollinger_bands(period=20, std_dev=2.0)
            features["bb_upper"] = bb_upper
            features["bb_middle"] = bb_middle
            features["bb_lower"] = bb_lower
            if bb_upper > bb_lower:
                # Position within bands: -1 (at lower) to +1 (at upper)
                features["bb_position"] = (self.mid_price - bb_middle) / ((bb_upper - bb_middle) + 1e-8)
            else:
                features["bb_position"] = 0.0
            
            # EMA Crossovers
            ema_crosses = self.advanced_indicators.compute_ema_crossovers()
            bullish_count = sum(1 for _, _, signal in ema_crosses.values() if signal == "bullish")
            bearish_count = sum(1 for _, _, signal in ema_crosses.values() if signal == "bearish")
            features["ema_bullish_count"] = bullish_count
            features["ema_bearish_count"] = bearish_count
            
            # VWAP Deviation
            vwap, vwap_dev = self.advanced_indicators.compute_vwap_deviation(period=300)
            features["vwap"] = vwap
            features["vwap_deviation"] = vwap_dev
            
            # Enhanced Order Flow
            features["order_flow_imbalance"] = self.advanced_indicators.compute_order_flow_imbalance()
            
            # Price Action Patterns
            pattern_name, pattern_confidence = self.advanced_indicators.detect_price_action_pattern()
            features["price_action_pattern"] = hash(pattern_name) % 1000  # Encode as number
            features["price_action_confidence"] = pattern_confidence
            if pattern_name == "uptrend":
                features["price_action_direction"] = 1
            elif pattern_name == "downtrend":
                features["price_action_direction"] = -1
            else:
                features["price_action_direction"] = 0
            
            # Liquidity Sweep Detection
            is_sweep, sweep_dir = self.advanced_indicators.detect_liquidity_sweep()
            features["liquidity_sweep"] = 1.0 if is_sweep else 0.0
            if sweep_dir == "up":
                features["sweep_direction"] = -1  # Fade the move (bearish after up sweep)
            elif sweep_dir == "down":
                features["sweep_direction"] = 1  # Fade the move (bullish after down sweep)
            else:
                features["sweep_direction"] = 0
            
            # Tick Momentum
            features["tick_momentum"] = self.advanced_indicators.compute_tick_momentum()
            
            # COMPOSITE SCORE (master signal)
            composite_score, component_scores = compute_composite_score(features)
            features["composite_score"] = composite_score
            for comp_name, comp_score in component_scores.items():
                features[f"score_{comp_name}"] = comp_score
                
        except Exception as e:
            logger.warning(f"Failed to compute advanced indicators for {self.symbol}: {e}")
            # Set default values
            for key in ["rsi_2s", "rsi_5s", "rsi_15s", "rsi_30s", "macd_histogram", "bb_position",
                        "ema_bullish_count", "vwap_deviation", "order_flow_imbalance", "tick_momentum",
                        "composite_score"]:
                features.setdefault(key, 0.0)
        
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

