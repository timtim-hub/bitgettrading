"""Fast per-token backtesting engine using historical candles."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from bitget_trading.bitget_rest import BitgetRestClient
from bitget_trading.config import TradingConfig
from bitget_trading.enhanced_ranker import EnhancedRanker
from bitget_trading.logger import get_logger
from bitget_trading.multi_symbol_state import MultiSymbolStateManager, SymbolState
from bitget_trading.regime_detector import RegimeDetector

logger = get_logger()


@dataclass
class BacktestResult:
    """Backtest result for a single symbol."""

    symbol: str
    timestamp: datetime
    win_rate: float
    roi: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    total_pnl: float
    net_pnl: float


class SymbolBacktester:
    """
    Fast per-token backtesting engine.
    
    Simulates current strategy using historical candles.
    Optimized for speed: <1 second per token.
    """

    def __init__(
        self,
        config: TradingConfig,
        rest_client: BitgetRestClient,
        enhanced_ranker: EnhancedRanker,
        state_manager: MultiSymbolStateManager,
    ) -> None:
        """
        Initialize backtester.
        
        Args:
            config: Trading configuration
            rest_client: Bitget REST API client
            enhanced_ranker: Enhanced ranker for signal generation
            state_manager: Multi-symbol state manager
        """
        self.config = config
        self.rest_client = rest_client
        self.enhanced_ranker = enhanced_ranker
        self.state_manager = state_manager
        self.regime_detector = RegimeDetector()

    async def backtest_symbol(
        self,
        symbol: str,
        lookback_days: int = 7,
        min_trades: int = 10,
    ) -> BacktestResult | None:
        """
        Backtest a single symbol using historical candles.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            lookback_days: Number of days of history to use
            min_trades: Minimum trades required for valid backtest
            
        Returns:
            BacktestResult or None if insufficient data
        """
        try:
            # 🚀 OPTIMIZATION: Use 5m candles instead of 1m for faster backtesting
            # 5m candles = 12 per hour, 288 per day, ~2000 for 7 days
            # But we only need 200 candles (200 * 5m = 16.7 hours) for fast backtest
            # This reduces API calls from 5 batches to 1 batch per symbol!
            all_candles = []
            
            # Fetch 5m candles (faster, fewer API calls)
            response = await self.rest_client.get_historical_candles(
                symbol=symbol,
                granularity="5m",  # Changed from 1m to 5m for speed
                limit=200,  # 200 * 5m = 16.7 hours of data (enough for backtest)
            )
            
            if response.get("code") != "00000":
                logger.debug(f"⚠️ Failed to fetch candles for {symbol}: {response.get('msg')}")
                return None
            
            candles = response.get("data", [])
            if not candles:
                logger.debug(f"⚠️ No candles available for {symbol}")
                return None
            
            all_candles.extend(candles)
            
            if not all_candles:
                logger.debug(f"⚠️ No candles available for {symbol}")
                return None
            
            # Reverse to get oldest -> newest
            all_candles.reverse()
            
            # Simulate trading
            trades = []
            position: dict[str, Any] | None = None
            balance = 1000.0  # Starting balance for simulation
            peak_balance = 1000.0
            equity_curve = [1000.0]
            
            # Initialize state manager for this symbol
            self.state_manager.add_symbol(symbol)
            state = self.state_manager.get_state(symbol)
            if not state:
                logger.warning(f"⚠️ Failed to initialize state for {symbol}")
                return None
            
            # Process candles
            for candle in all_candles:
                # Each candle: [timestamp, open, high, low, close, volume, ...]
                timestamp_ms = int(candle[0])
                open_price = float(candle[1])
                high_price = float(candle[2])
                low_price = float(candle[3])
                close_price = float(candle[4])
                volume = float(candle[5]) if len(candle) > 5 else 0.0
                
                # Add price point to state
                self.state_manager.add_price_point(symbol, close_price, timestamp_ms, volume)
                
                # Update state with latest price
                state = self.state_manager.get_state(symbol)
                if not state:
                    continue
                
                # Compute features
                features = state.compute_features()
                if not features:
                    continue
                
                # Get BTC return for correlation
                btc_state = self.state_manager.get_state("BTCUSDT")
                btc_return = 0.0
                if btc_state:
                    btc_features = btc_state.compute_features()
                    if btc_features:
                        btc_return = btc_features.get("return_15s", 0.0)
                
                # Compute enhanced score (simulates current strategy)
                score, predicted_side, metadata = self.enhanced_ranker.compute_enhanced_score(
                    state, features, btc_return
                )
                
                # Skip if no signal
                if predicted_side == "neutral" or score <= 0:
                    # Check if we should close existing position
                    if position:
                        # Close position if signal is neutral
                        pnl = self._close_position(
                            position, close_price, timestamp_ms, balance
                        )
                        balance += pnl
                        trades.append({
                            "entry_time": position["entry_time"],
                            "exit_time": timestamp_ms,
                            "side": position["side"],
                            "entry_price": position["entry_price"],
                            "exit_price": close_price,
                            "pnl": pnl,
                            "pnl_pct": (pnl / position["position_value"]) * 100,
                        })
                        position = None
                    continue
                
                # Check if we should open a position
                if not position:
                    # Open position if signal is strong enough
                    if score > 0.5:  # Minimum score threshold
                        position = {
                            "side": predicted_side,
                            "entry_price": close_price,
                            "entry_time": timestamp_ms,
                            "position_value": balance * 0.10,  # 10% of balance
                            "leverage": self.config.leverage,
                        }
                else:
                    # Check if we should close position (opposite signal or stop-loss/take-profit)
                    should_close = False
                    exit_reason = ""
                    
                    # Opposite signal
                    if position["side"] != predicted_side:
                        should_close = True
                        exit_reason = "opposite_signal"
                    
                    # Stop-loss / Take-profit (simplified)
                    if position["side"] == "long":
                        price_change_pct = (close_price - position["entry_price"]) / position["entry_price"]
                        return_on_capital = price_change_pct * position["leverage"]
                        
                        # Stop-loss: -50% capital
                        if return_on_capital <= -0.50:
                            should_close = True
                            exit_reason = "stop_loss"
                        # Take-profit: +16% capital (trailing TP activation)
                        elif return_on_capital >= 0.16:
                            # Check trailing stop (4% callback)
                            if return_on_capital >= 0.20:  # 16% + 4% = 20% max
                                should_close = True
                                exit_reason = "trailing_tp"
                    else:  # short
                        price_change_pct = (position["entry_price"] - close_price) / position["entry_price"]
                        return_on_capital = price_change_pct * position["leverage"]
                        
                        # Stop-loss: -50% capital
                        if return_on_capital <= -0.50:
                            should_close = True
                            exit_reason = "stop_loss"
                        # Take-profit: +16% capital (trailing TP activation)
                        elif return_on_capital >= 0.16:
                            # Check trailing stop (4% callback)
                            if return_on_capital >= 0.20:  # 16% + 4% = 20% max
                                should_close = True
                                exit_reason = "trailing_tp"
                    
                    if should_close:
                        pnl = self._close_position(position, close_price, timestamp_ms, balance)
                        balance += pnl
                        trades.append({
                            "entry_time": position["entry_time"],
                            "exit_time": timestamp_ms,
                            "side": position["side"],
                            "entry_price": position["entry_price"],
                            "exit_price": close_price,
                            "pnl": pnl,
                            "pnl_pct": (pnl / position["position_value"]) * 100,
                            "exit_reason": exit_reason,
                        })
                        position = None
                
                # Update equity curve
                current_equity = balance
                if position:
                    # Calculate unrealized PnL
                    if position["side"] == "long":
                        price_change_pct = (close_price - position["entry_price"]) / position["entry_price"]
                    else:
                        price_change_pct = (position["entry_price"] - close_price) / position["entry_price"]
                    unrealized_pnl = position["position_value"] * price_change_pct * position["leverage"]
                    current_equity += unrealized_pnl
                
                equity_curve.append(current_equity)
                peak_balance = max(peak_balance, current_equity)
            
            # Close any remaining position
            if position and all_candles:
                final_candle = all_candles[-1]
                final_price = float(final_candle[4])
                final_timestamp = int(final_candle[0])
                pnl = self._close_position(position, final_price, final_timestamp, balance)
                balance += pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": final_timestamp,
                    "side": position["side"],
                    "entry_price": position["entry_price"],
                    "exit_price": final_price,
                    "pnl": pnl,
                    "pnl_pct": (pnl / position["position_value"]) * 100,
                    "exit_reason": "end_of_data",
                })
            
            # Check if we have enough trades
            if len(trades) < min_trades:
                logger.debug(f"⚠️ {symbol}: Only {len(trades)} trades (min: {min_trades})")
                return None
            
            # Calculate metrics
            winning_trades = [t for t in trades if t["pnl"] > 0]
            losing_trades = [t for t in trades if t["pnl"] <= 0]
            
            win_rate = len(winning_trades) / len(trades) if trades else 0.0
            avg_win = np.mean([t["pnl"] for t in winning_trades]) if winning_trades else 0.0
            avg_loss = np.mean([t["pnl"] for t in losing_trades]) if losing_trades else 0.0
            
            total_pnl = sum(t["pnl"] for t in trades)
            net_pnl = balance - 1000.0  # Final balance - initial balance
            roi = (net_pnl / 1000.0) * 100  # ROI in percentage
            
            # Profit factor
            gross_profit = sum(t["pnl"] for t in winning_trades) if winning_trades else 0.0
            gross_loss = abs(sum(t["pnl"] for t in losing_trades)) if losing_trades else 0.0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
            
            # Sharpe ratio (simplified)
            returns = [t["pnl_pct"] / 100.0 for t in trades]
            if len(returns) > 1:
                sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0.0
            else:
                sharpe_ratio = 0.0
            
            # Max drawdown
            max_drawdown = 0.0
            if equity_curve:
                peak = equity_curve[0]
                for equity in equity_curve:
                    if equity > peak:
                        peak = equity
                    drawdown = (peak - equity) / peak if peak > 0 else 0.0
                    max_drawdown = max(max_drawdown, drawdown)
            
            return BacktestResult(
                symbol=symbol,
                timestamp=datetime.now(),
                win_rate=win_rate,
                roi=roi,
                sharpe_ratio=sharpe_ratio,
                total_trades=len(trades),
                winning_trades=len(winning_trades),
                losing_trades=len(losing_trades),
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                max_drawdown=max_drawdown,
                total_pnl=total_pnl,
                net_pnl=net_pnl,
            )
            
        except Exception as e:
            logger.error(f"❌ Error backtesting {symbol}: {e}")
            return None
    
    def _close_position(
        self,
        position: dict[str, Any],
        exit_price: float,
        exit_time: int,
        balance: float,
    ) -> float:
        """
        Close a position and calculate PnL.
        
        Args:
            position: Position dictionary
            exit_price: Exit price
            exit_time: Exit timestamp
            balance: Current balance
            
        Returns:
            PnL in USDT
        """
        if position["side"] == "long":
            price_change_pct = (exit_price - position["entry_price"]) / position["entry_price"]
        else:  # short
            price_change_pct = (position["entry_price"] - exit_price) / position["entry_price"]
        
        # Calculate PnL
        pnl = position["position_value"] * price_change_pct * position["leverage"]
        
        # Subtract fees (0.04% round-trip maker fees)
        fees = position["position_value"] * 0.0004
        pnl -= fees
        
        return pnl

