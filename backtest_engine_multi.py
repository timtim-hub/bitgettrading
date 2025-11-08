"""
Multi-Position Backtest Engine - Support for 30-50 simultaneous positions

Major enhancements:
- Multiple simultaneous positions
- Correlation risk calculation
- Slippage modeling (volume-based)
- Position queue management
- Per-position tracking
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')


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
    exit_reason: str  # "tp", "sl", "signal", "reversal", "end"
    slippage_cost: float = 0.0  # Cost from slippage
    
    def duration_hours(self) -> float:
        """Calculate trade duration in hours."""
        return (self.exit_time - self.entry_time) / (1000 * 3600)


@dataclass
class Position:
    """Represents an open position."""
    position_id: int
    side: str
    entry_price: float
    entry_time: int
    entry_idx: int
    size_usd: float
    peak_price: float
    leverage: int


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
    max_concurrent_positions: int = 0  # Track max positions held
    correlation_violations: int = 0  # Times correlation risk was exceeded
    total_slippage_cost: float = 0.0  # Total slippage costs
    
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


class MultiPositionBacktestEngine:
    """
    Enhanced backtest engine supporting multiple simultaneous positions.
    
    Features:
    - 30-50 simultaneous positions
    - Correlation risk management
    - Slippage modeling based on volume
    - Position queue management
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
        
        # Trading fees (Bitget)
        self.taker_fee_pct = 0.0006  # 0.06% taker fee
        self.maker_fee_pct = 0.0002  # 0.02% maker fee (rebate)
        # Use maker fee when possible (limit orders), taker when urgent (market orders)
        # For high leverage, we'll try to use maker fees more often
        self.use_maker_fee_probability = 0.6  # 60% chance to use maker fee (limit order)
        self.fee_per_trade_taker = self.taker_fee_pct * 2  # Entry + Exit = 0.12%
        self.fee_per_trade_maker = self.maker_fee_pct * 2  # Entry + Exit = 0.04%
        # Average fee (weighted)
        self.fee_per_trade = (self.fee_per_trade_taker * 0.4) + (self.fee_per_trade_maker * 0.6)  # ~0.064%
        
        # Slippage parameters (based on volume and volatility)
        self.high_volume_slippage = 0.0002  # 0.02% for high volume tokens
        self.low_volume_slippage = 0.0005   # 0.05% for low volume tokens
        
        # Position tracking
        self.next_position_id = 0
        
        # Correlation tracking (simplified - track long/short ratio)
        self.max_correlation_ratio = 0.8  # Max 80% in same direction
    
    def estimate_slippage(self, df: pd.DataFrame, idx: int, size_usd: float) -> float:
        """
        Estimate slippage based on volume and trade size.
        
        Logic:
        - High volume tokens: 0.02% slippage
        - Low volume tokens: 0.05% slippage
        - Larger trades: More slippage
        
        Args:
            df: DataFrame with OHLCV data
            idx: Current index
            size_usd: Trade size in USD
            
        Returns:
            Slippage percentage
        """
        if idx < 20:
            return self.high_volume_slippage
        
        # Get recent volume
        recent_volume = df['volume'].iloc[max(0, idx-20):idx].mean()
        current_volume = df['volume'].iloc[idx]
        
        # Volume ratio
        volume_ratio = current_volume / (recent_volume + 1e-10)
        
        # Base slippage
        if volume_ratio > 1.5:  # High volume
            base_slippage = self.high_volume_slippage
        else:  # Lower volume
            base_slippage = self.low_volume_slippage
        
        # Adjust for trade size (larger trades = more slippage)
        # Assuming average volume is ~$1M, adjust proportionally
        size_factor = min(size_usd / 10000, 2.0)  # Cap at 2x
        
        return base_slippage * size_factor
    
    def calculate_correlation_risk(self, positions: List[Position]) -> float:
        """
        Calculate correlation risk of current positions.
        
        Simplified approach: Check long/short ratio.
        If >80% in same direction, correlation risk is high.
        
        Args:
            positions: List of current open positions
            
        Returns:
            Correlation risk score (0-1, higher = more risky)
        """
        if not positions:
            return 0.0
        
        long_count = sum(1 for p in positions if p.side == "long")
        short_count = sum(1 for p in positions if p.side == "short")
        total = len(positions)
        
        # Calculate directional concentration
        max_directional = max(long_count, short_count)
        concentration = max_directional / total
        
        # Risk is 0 if balanced, 1 if all same direction
        risk = max(0, (concentration - 0.5) / 0.5)
        
        return risk
    
    def can_open_position(
        self,
        positions: List[Position],
        new_side: str,
        capital: float
    ) -> bool:
        """
        Check if we can open a new position.
        
        Checks:
        - Max positions not exceeded
        - Correlation risk acceptable
        - Sufficient capital
        
        Args:
            positions: Current open positions
            new_side: Side of new position ("long" or "short")
            capital: Available capital
            
        Returns:
            True if can open position
        """
        # Check max positions
        if len(positions) >= self.max_positions:
            return False
        
        # Check capital
        if capital <= 0:
            return False
        
        # Check correlation risk
        # Simulate adding new position and check risk
        temp_positions = positions.copy()
        temp_pos = Position(
            position_id=0,
            side=new_side,
            entry_price=0,
            entry_time=0,
            entry_idx=0,
            size_usd=0,
            peak_price=0,
            leverage=self.leverage
        )
        temp_positions.append(temp_pos)
        
        correlation_risk = self.calculate_correlation_risk(temp_positions)
        
        # If correlation risk > 0.8, only allow if it reduces concentration
        if correlation_risk > 0.8:
            # Check if new position reduces concentration
            long_count = sum(1 for p in positions if p.side == "long")
            short_count = sum(1 for p in positions if p.side == "short")
            
            # Allow if new position is minority direction
            if new_side == "long" and long_count >= short_count:
                return False
            if new_side == "short" and short_count >= long_count:
                return False
        
        return True
    
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
            score = bullish_signals * 0.5
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
    
    def run_backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 50.0
    ) -> BacktestResult:
        """
        Run backtest with multiple simultaneous positions.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading pair symbol
            initial_capital: Starting capital in USD
            
        Returns:
            BacktestResult object with all trades and metrics
        """
        capital = initial_capital
        positions: List[Position] = []  # Active positions
        trades = []
        equity_curve = []
        max_concurrent = 0
        correlation_violations = 0
        total_slippage = 0.0
        
        for idx in range(len(df)):
            timestamp = int(df.iloc[idx]['timestamp'])
            current_price = float(df.iloc[idx]['close'])
            
            # Calculate total unrealized PnL
            total_unrealized_pnl = 0.0
            for pos in positions:
                if pos.side == "long":
                    unrealized = (current_price / pos.entry_price - 1) * pos.size_usd * pos.leverage
                else:  # short
                    unrealized = (pos.entry_price / current_price - 1) * pos.size_usd * pos.leverage
                total_unrealized_pnl += unrealized
            
            current_equity = capital + total_unrealized_pnl
            equity_curve.append((timestamp, current_equity))
            
            # Update max concurrent positions
            max_concurrent = max(max_concurrent, len(positions))
            
            # Check exits for all positions
            positions_to_close = []
            
            for pos in positions:
                entry_price = pos.entry_price
                side = pos.side
                size_usd = pos.size_usd
                
                # Calculate price change
                if side == "long":
                    price_change = (current_price / entry_price - 1)
                    stop_price = entry_price * (1 - self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 + self.take_profit_pct / self.leverage)
                    
                    # Update peak for trailing
                    if current_price > pos.peak_price:
                        pos.peak_price = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price <= stop_price:
                        exit_reason = "sl"
                    elif current_price >= tp_price:
                        # Check trailing
                        trailing_stop = pos.peak_price * (1 - self.trailing_callback)
                        if current_price <= trailing_stop:
                            exit_reason = "tp_trailing"
                        else:
                            exit_reason = "tp"
                
                else:  # short
                    price_change = (entry_price / current_price - 1)
                    stop_price = entry_price * (1 + self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 - self.take_profit_pct / self.leverage)
                    
                    # Update peak (min for shorts)
                    if current_price < pos.peak_price:
                        pos.peak_price = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price >= stop_price:
                        exit_reason = "sl"
                    elif current_price <= tp_price:
                        # Check trailing
                        trailing_stop = pos.peak_price * (1 + self.trailing_callback)
                        if current_price >= trailing_stop:
                            exit_reason = "tp_trailing"
                        else:
                            exit_reason = "tp"
                
                # Check for reversal signal
                signal_direction, signal_score = self.calculate_signal(df, idx)
                if signal_direction == ("short" if side == "long" else "long"):
                    if signal_score >= self.entry_threshold * 1.5:
                        exit_reason = "reversal"
                
                # Mark for closing if exit reason found
                if exit_reason:
                    # Calculate slippage
                    slippage = self.estimate_slippage(df, idx, size_usd)
                    slippage_cost = size_usd * self.leverage * slippage
                    total_slippage += slippage_cost
                    
                    # Calculate gross PnL
                    pnl_usd = price_change * size_usd * self.leverage
                    
                    # Try to use maker fee for exit (limit order)
                    import random
                    use_maker_exit = random.random() < self.use_maker_fee_probability
                    exit_fee_pct = self.maker_fee_pct if use_maker_exit else self.taker_fee_pct
                    
                    # Calculate fees (entry was already deducted, now deduct exit)
                    notional_value = size_usd * self.leverage
                    exit_fee = notional_value * exit_fee_pct
                    fee_usd = exit_fee  # Only exit fee (entry already deducted)
                    
                    # Net PnL after fees and slippage
                    net_pnl_usd = pnl_usd - fee_usd - slippage_cost
                    net_pnl_pct = (net_pnl_usd / size_usd) * 100
                    
                    trade = Trade(
                        entry_time=pos.entry_time,
                        exit_time=timestamp,
                        entry_price=entry_price,
                        exit_price=current_price,
                        side=side,
                        size_usd=size_usd,
                        leverage=self.leverage,
                        pnl_usd=net_pnl_usd,
                        pnl_pct=net_pnl_pct,
                        exit_reason=exit_reason,
                        slippage_cost=slippage_cost,
                    )
                    trades.append(trade)
                    capital += net_pnl_usd
                    positions_to_close.append(pos)
            
            # Remove closed positions
            for pos in positions_to_close:
                positions.remove(pos)
            
            # Check for new entries
            signal_direction, signal_score = self.calculate_signal(df, idx)
            
            if signal_direction in ["long", "short"]:
                # Check if we can open position
                if self.can_open_position(positions, signal_direction, capital):
                    # Calculate position size
                    position_size_usd = capital * self.position_size_pct
                    
                    # Ensure we don't exceed available capital
                    total_allocated = sum(p.size_usd for p in positions)
                    available = capital - total_allocated
                    position_size_usd = min(position_size_usd, available * 0.9)  # Leave 10% buffer
                    
                    if position_size_usd > 0:
                        # Calculate slippage for entry
                        slippage = self.estimate_slippage(df, idx, position_size_usd)
                        slippage_cost = position_size_usd * self.leverage * slippage
                        total_slippage += slippage_cost
                        
                        # Try to use maker fee (limit order) - reduces fees by 67%!
                        import random
                        use_maker = random.random() < self.use_maker_fee_probability
                        entry_fee_pct = self.maker_fee_pct if use_maker else self.taker_fee_pct
                        
                        # Entry fee
                        entry_fee = position_size_usd * self.leverage * entry_fee_pct
                        capital -= entry_fee  # Deduct entry fee
                        capital -= slippage_cost  # Deduct slippage
                        
                        # Open position
                        new_pos = Position(
                            position_id=self.next_position_id,
                            side=signal_direction,
                            entry_price=current_price,
                            entry_time=timestamp,
                            entry_idx=idx,
                            size_usd=position_size_usd,
                            peak_price=current_price,
                            leverage=self.leverage,
                        )
                        positions.append(new_pos)
                        self.next_position_id += 1
                else:
                    # Track correlation violations
                    if len(positions) < self.max_positions:
                        correlation_risk = self.calculate_correlation_risk(positions)
                        if correlation_risk > 0.8:
                            correlation_violations += 1
        
        # Close any remaining positions at end
        if positions:
            current_price = float(df.iloc[-1]['close'])
            timestamp = int(df.iloc[-1]['timestamp'])
            
            for pos in positions:
                entry_price = pos.entry_price
                side = pos.side
                size_usd = pos.size_usd
                
                if side == "long":
                    price_change = (current_price / entry_price - 1)
                else:
                    price_change = (entry_price / current_price - 1)
                
                # Calculate slippage
                slippage = self.estimate_slippage(df, len(df)-1, size_usd)
                slippage_cost = size_usd * self.leverage * slippage
                total_slippage += slippage_cost
                
                # Calculate PnL
                pnl_usd = price_change * size_usd * self.leverage
                
                # Exit fee (entry was already deducted)
                import random
                use_maker_exit = random.random() < self.use_maker_fee_probability
                exit_fee_pct = self.maker_fee_pct if use_maker_exit else self.taker_fee_pct
                notional_value = size_usd * self.leverage
                fee_usd = notional_value * exit_fee_pct
                
                net_pnl_usd = pnl_usd - fee_usd - slippage_cost
                net_pnl_pct = (net_pnl_usd / size_usd) * 100
                
                trade = Trade(
                    entry_time=pos.entry_time,
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=current_price,
                    side=side,
                    size_usd=size_usd,
                    leverage=self.leverage,
                    pnl_usd=net_pnl_usd,
                    pnl_pct=net_pnl_pct,
                    exit_reason="end",
                    slippage_cost=slippage_cost,
                )
                trades.append(trade)
                capital += net_pnl_usd
        
        result = BacktestResult(
            strategy_id=self.strategy['id'],
            strategy_name=self.strategy['name'],
            symbol=symbol,
            initial_capital=initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
            max_concurrent_positions=max_concurrent,
            correlation_violations=correlation_violations,
            total_slippage_cost=total_slippage,
        )
        
        return result


# Alias for backward compatibility
BacktestEngine = MultiPositionBacktestEngine

