"""
Backtest Engine - Core logic for simulating trades on historical data
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trade:
    """Represents a single trade."""
    entry_time: int  # timestamp in ms
    exit_time: int  # timestamp in ms
    entry_price: float
    exit_price: float
    side: str  # "long" or "short"
    size_usd: float
    leverage: int
    pnl_usd: float
    pnl_pct: float  # % of capital
    exit_reason: str  # "tp", "sl", "signal"
    
    def duration_hours(self) -> float:
        """Calculate trade duration in hours."""
        return (self.exit_time - self.entry_time) / (1000 * 3600)


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    strategy_id: int
    strategy_name: str
    symbol: str
    initial_capital: float
    final_capital: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[int, float]] = field(default_factory=list)  # (timestamp, equity)
    
    def total_trades(self) -> int:
        return len(self.trades)
    
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_usd > 0)
    
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_usd < 0)
    
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return self.winning_trades() / len(self.trades)
    
    def total_pnl(self) -> float:
        return self.final_capital - self.initial_capital
    
    def roi_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.final_capital - self.initial_capital) / self.initial_capital * 100


class BacktestEngine:
    """
    Simplified backtest engine that simulates trading based on price momentum and strategy parameters.
    
    This is a FAST backtester optimized for testing many strategy variations.
    """
    
    def __init__(self, strategy: Dict[str, Any]):
        """Initialize the backtest engine with a strategy configuration."""
        self.strategy = strategy
        self.entry_threshold = strategy["entry_threshold"]
        self.stop_loss_pct = strategy["stop_loss_pct"]  # Capital %
        self.take_profit_pct = strategy["take_profit_pct"]  # Capital %
        self.trailing_callback = strategy["trailing_callback"]
        self.volume_ratio = strategy["volume_ratio"]
        self.confluence_required = strategy["confluence_required"]
        self.position_size_pct = strategy["position_size_pct"]
        self.leverage = strategy["leverage"]
        self.max_positions = strategy["max_positions"]
        
        # Trading fees (Bitget taker fee: 0.06% per side)
        self.taker_fee_pct = 0.0006  # 0.06%
        self.fee_per_trade = self.taker_fee_pct * 2  # Entry + Exit = 0.12%
    
    def calculate_signal(self, df: pd.DataFrame, idx: int) -> Tuple[str, float]:
        """
        Calculate trading signal based on simplified momentum indicators.
        
        Returns:
            (direction, score) where direction is "long", "short", or "neutral"
            and score is the signal strength (0.0-5.0)
        """
        if idx < 20:  # Need history for indicators
            return "neutral", 0.0
        
        # Get recent price data
        prices = df['close'].iloc[max(0, idx-20):idx+1].values
        volumes = df['volume'].iloc[max(0, idx-20):idx+1].values
        current_price = prices[-1]
        
        if len(prices) < 10:
            return "neutral", 0.0
        
        # Calculate simple indicators
        sma_10 = np.mean(prices[-10:])
        sma_20 = np.mean(prices[-20:]) if len(prices) >= 20 else sma_10
        volume_avg = np.mean(volumes[-10:])
        current_volume = volumes[-1]
        
        # Price momentum
        returns_5 = (prices[-1] / prices[-6] - 1) if len(prices) >= 6 else 0
        returns_10 = (prices[-1] / prices[-11] - 1) if len(prices) >= 11 else 0
        returns_20 = (prices[-1] / prices[-20] - 1) if len(prices) >= 20 else 0
        
        # Simplified RSI
        changes = np.diff(prices[-14:]) if len(prices) >= 14 else np.diff(prices)
        gains = changes[changes > 0].sum() if len(changes[changes > 0]) > 0 else 0.0001
        losses = abs(changes[changes < 0].sum()) if len(changes[changes < 0]) > 0 else 0.0001
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        
        # Check confluence (simplified)
        bullish_signals = 0
        bearish_signals = 0
        
        # 1. SMA crossover
        if current_price > sma_10 > sma_20:
            bullish_signals += 1
        elif current_price < sma_10 < sma_20:
            bearish_signals += 1
        
        # 2. RSI
        if rsi < 40:
            bullish_signals += 1
        elif rsi > 60:
            bearish_signals += 1
        
        # 3. Volume confirmation
        if current_volume > volume_avg * self.volume_ratio:
            if returns_5 > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # 4. Short-term momentum
        if returns_5 > 0.01:  # +1%
            bullish_signals += 1
        elif returns_5 < -0.01:  # -1%
            bearish_signals += 1
        
        # 5. Medium-term momentum
        if returns_10 > 0.02:  # +2%
            bullish_signals += 1
        elif returns_10 < -0.02:  # -2%
            bearish_signals += 1
        
        # 6. Long-term momentum
        if returns_20 > 0.03:  # +3%
            bullish_signals += 1
        elif returns_20 < -0.03:  # -3%
            bearish_signals += 1
        
        # Determine signal direction and score
        if bullish_signals >= self.confluence_required:
            direction = "long"
            score = bullish_signals * 0.5  # Scale: 0-3 signals → 0-1.5 score
        elif bearish_signals >= self.confluence_required:
            direction = "short"
            score = bearish_signals * 0.5
        else:
            direction = "neutral"
            score = 0.0
        
        # Apply entry threshold
        if score < self.entry_threshold:
            return "neutral", score
        
        return direction, score
    
    def run_backtest(self, df: pd.DataFrame, symbol: str, initial_capital: float = 50.0) -> BacktestResult:
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading pair symbol
            initial_capital: Starting capital in USD
            
        Returns:
            BacktestResult object with all trades and metrics
        """
        capital = initial_capital
        position = None  # Current position: {side, entry_price, entry_idx, size_usd, peak_price}
        trades = []
        equity_curve = []
        
        for idx in range(len(df)):
            timestamp = int(df.iloc[idx]['timestamp'])
            current_price = float(df.iloc[idx]['close'])
            
            # Record equity
            if position:
                # Calculate unrealized PnL
                if position['side'] == "long":
                    unrealized_pnl = (current_price / position['entry_price'] - 1) * position['size_usd'] * self.leverage
                else:  # short
                    unrealized_pnl = (position['entry_price'] / current_price - 1) * position['size_usd'] * self.leverage
                current_equity = capital + unrealized_pnl
            else:
                current_equity = capital
            
            equity_curve.append((timestamp, current_equity))
            
            # Check for exit if in position
            if position:
                entry_price = position['entry_price']
                side = position['side']
                size_usd = position['size_usd']
                
                # Calculate price change and PnL
                if side == "long":
                    price_change = (current_price / entry_price - 1)
                    pnl_pct = price_change * self.leverage * 100  # % of capital
                    stop_price = entry_price * (1 - self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 + self.take_profit_pct / self.leverage)
                    
                    # Update peak for trailing
                    if current_price > position.get('peak_price', entry_price):
                        position['peak_price'] = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price <= stop_price:
                        exit_reason = "sl"
                    elif current_price >= tp_price:
                        # Check trailing
                        peak = position.get('peak_price', entry_price)
                        trailing_stop = peak * (1 - self.trailing_callback)
                        if current_price <= trailing_stop:
                            exit_reason = "tp_trailing"
                        elif current_price >= tp_price:
                            exit_reason = "tp"
                    
                else:  # short
                    price_change = (entry_price / current_price - 1)
                    pnl_pct = price_change * self.leverage * 100  # % of capital
                    stop_price = entry_price * (1 + self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 - self.take_profit_pct / self.leverage)
                    
                    # Update peak (min for shorts)
                    if current_price < position.get('peak_price', entry_price):
                        position['peak_price'] = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price >= stop_price:
                        exit_reason = "sl"
                    elif current_price <= tp_price:
                        # Check trailing
                        peak = position.get('peak_price', entry_price)
                        trailing_stop = peak * (1 + self.trailing_callback)
                        if current_price >= trailing_stop:
                            exit_reason = "tp_trailing"
                        elif current_price <= tp_price:
                            exit_reason = "tp"
                
                # Check for opposite signal (momentum reversal)
                signal_direction, signal_score = self.calculate_signal(df, idx)
                if signal_direction == ("short" if side == "long" else "long"):
                    if signal_score >= self.entry_threshold * 1.5:  # Strong opposite signal
                        exit_reason = "reversal"
                
                # Exit if reason found
                if exit_reason:
                    # Calculate gross PnL
                    pnl_usd = price_change * size_usd * self.leverage
                    
                    # Deduct fees (0.06% entry + 0.06% exit = 0.12% total on position size)
                    # Fee is calculated on notional value (size_usd * leverage)
                    notional_value = size_usd * self.leverage
                    fee_usd = notional_value * self.fee_per_trade
                    
                    # Net PnL after fees
                    net_pnl_usd = pnl_usd - fee_usd
                    capital += net_pnl_usd
                    
                    # Recalculate PnL % based on net PnL (after fees)
                    net_pnl_pct = (net_pnl_usd / size_usd) * 100
                    
                    trade = Trade(
                        entry_time=df.iloc[position['entry_idx']]['timestamp'],
                        exit_time=timestamp,
                        entry_price=entry_price,
                        exit_price=current_price,
                        side=side,
                        size_usd=size_usd,
                        leverage=self.leverage,
                        pnl_usd=net_pnl_usd,  # Store net PnL after fees
                        pnl_pct=net_pnl_pct,  # Store net PnL % after fees
                        exit_reason=exit_reason,
                    )
                    trades.append(trade)
                    position = None
            
            # Check for entry if no position
            if not position and capital > 0:
                signal_direction, signal_score = self.calculate_signal(df, idx)
                
                if signal_direction in ["long", "short"]:
                    # Calculate position size
                    position_size_usd = capital * self.position_size_pct
                    
                    # Enter position
                    position = {
                        'side': signal_direction,
                        'entry_price': current_price,
                        'entry_idx': idx,
                        'size_usd': position_size_usd,
                        'peak_price': current_price,
                    }
        
        # Close any remaining position at end
        if position:
            current_price = float(df.iloc[-1]['close'])
            entry_price = position['entry_price']
            side = position['side']
            size_usd = position['size_usd']
            
            if side == "long":
                price_change = (current_price / entry_price - 1)
            else:
                price_change = (entry_price / current_price - 1)
            
            # Calculate gross PnL
            pnl_usd = price_change * size_usd * self.leverage
            
            # Deduct fees
            notional_value = size_usd * self.leverage
            fee_usd = notional_value * self.fee_per_trade
            
            # Net PnL after fees
            net_pnl_usd = pnl_usd - fee_usd
            net_pnl_pct = (net_pnl_usd / size_usd) * 100
            capital += net_pnl_usd
            
            trade = Trade(
                entry_time=df.iloc[position['entry_idx']]['timestamp'],
                exit_time=int(df.iloc[-1]['timestamp']),
                entry_price=entry_price,
                exit_price=current_price,
                side=side,
                size_usd=size_usd,
                leverage=self.leverage,
                pnl_usd=net_pnl_usd,
                pnl_pct=net_pnl_pct,
                exit_reason="end",
            )
            trades.append(trade)
        
        result = BacktestResult(
            strategy_id=self.strategy['id'],
            strategy_name=self.strategy['name'],
            symbol=symbol,
            initial_capital=initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
        )
        
        return result

