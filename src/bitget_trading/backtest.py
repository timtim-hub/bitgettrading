"""Realistic backtesting engine with Bitget-specific costs."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from src.bitget_trading.config import TradingConfig
from src.bitget_trading.logger import get_logger
from src.bitget_trading.model import TradingModel

logger = get_logger()


@dataclass
class Trade:
    """Individual trade record."""

    entry_time: datetime
    exit_time: datetime | None
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float | None
    size: float
    pnl: float
    pnl_pct: float
    fees_paid: float
    slippage_cost: float
    funding_paid: float


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_pnl_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    total_fees: float
    total_slippage: float
    total_funding: float
    net_pnl: float
    final_balance: float
    roi: float
    avg_trade_duration_sec: float


class Backtester:
    """
    Realistic backtesting engine for ultra-short-term strategies.
    
    Includes:
    - Taker/maker fees
    - Slippage
    - Funding costs (if holding across funding times)
    - Spread costs
    """

    def __init__(
        self,
        config: TradingConfig,
        model: TradingModel,
    ) -> None:
        """
        Initialize backtester.
        
        Args:
            config: Trading configuration
            model: Trained trading model
        """
        self.config = config
        self.model = model
        
        # State
        self.trades: list[Trade] = []
        self.position: str = "flat"  # "flat", "long", "short"
        self.position_size: float = 0.0
        self.entry_price: float = 0.0
        self.entry_time: datetime | None = None
        
        # Equity tracking
        self.equity_curve: list[float] = []
        self.timestamps: list[datetime] = []

    def run(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        initial_balance: float = 10000.0,
    ) -> tuple[BacktestMetrics, pd.DataFrame]:
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with features and mid_price
            feature_cols: List of feature column names
            initial_balance: Starting capital in USDT
        
        Returns:
            Tuple of (metrics, trades_df)
        """
        logger.info(
            "backtest_started",
            initial_balance=initial_balance,
            leverage=self.config.leverage,
            data_points=len(df),
        )
        
        balance = initial_balance
        peak_balance = initial_balance
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            
            # Get features for prediction
            features_df = pd.DataFrame([row[feature_cols]])
            
            # Get trading signal
            signal, confidence, probs = self.model.predict_signal(features_df)
            
            current_price = row["mid_price"]
            current_time = row.get("timestamp", idx)
            
            if isinstance(current_time, (int, float)):
                current_time = pd.to_datetime(current_time, unit="ms")
            
            spread_bps = row.get("spread_bps", 5.0)  # Default 5bps if missing
            
            # Calculate position size based on risk
            risk_amount = min(
                balance * self.config.daily_loss_limit / 10,  # Conservative
                self.config.max_position_usd,
            )
            position_value = risk_amount * self.config.leverage
            size = position_value / current_price
            
            # Trading logic
            if signal == "long" and self.position != "long":
                # Close short if exists
                if self.position == "short":
                    pnl = self._close_position(current_price, current_time, spread_bps)
                    balance += pnl
                
                # Open long
                self.position = "long"
                self.entry_price = current_price * (1 + spread_bps / 20000)  # Pay half spread
                self.entry_time = current_time
                self.position_size = size
                
                # Pay entry fee
                entry_fee = position_value * self.config.taker_fee
                balance -= entry_fee
                
                logger.debug(
                    "position_opened",
                    side="long",
                    price=self.entry_price,
                    size=size,
                )
            
            elif signal == "short" and self.position != "short":
                # Close long if exists
                if self.position == "long":
                    pnl = self._close_position(current_price, current_time, spread_bps)
                    balance += pnl
                
                # Open short
                self.position = "short"
                self.entry_price = current_price * (1 - spread_bps / 20000)  # Pay half spread
                self.entry_time = current_time
                self.position_size = size
                
                # Pay entry fee
                entry_fee = position_value * self.config.taker_fee
                balance -= entry_fee
                
                logger.debug(
                    "position_opened",
                    side="short",
                    price=self.entry_price,
                    size=size,
                )
            
            elif signal == "flat" and self.position != "flat":
                # Close position
                pnl = self._close_position(current_price, current_time, spread_bps)
                balance += pnl
            
            # Calculate current equity (including unrealized PnL)
            current_equity = balance
            if self.position != "flat":
                unrealized_pnl = self._calculate_pnl(current_price)
                current_equity += unrealized_pnl
            
            # Track equity
            self.equity_curve.append(current_equity)
            self.timestamps.append(current_time)
            
            # Update peak
            peak_balance = max(peak_balance, current_equity)
            
            # Check drawdown limit
            drawdown_pct = (peak_balance - current_equity) / peak_balance
            if drawdown_pct >= self.config.max_drawdown_pct:
                logger.warning(
                    "max_drawdown_hit",
                    drawdown_pct=drawdown_pct,
                    step=idx,
                )
                # Force close position
                if self.position != "flat":
                    pnl = self._close_position(current_price, current_time, spread_bps)
                    balance += pnl
                break
        
        # Close any remaining position
        if self.position != "flat":
            final_price = df.iloc[-1]["mid_price"]
            final_time = df.iloc[-1].get("timestamp", len(df) - 1)
            final_spread = df.iloc[-1].get("spread_bps", 5.0)
            pnl = self._close_position(final_price, final_time, final_spread)
            balance += pnl
        
        # Calculate metrics
        metrics = self._calculate_metrics(initial_balance, balance)
        
        # Create trades DataFrame
        trades_df = pd.DataFrame(
            [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "size": t.size,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "fees": t.fees_paid,
                    "slippage": t.slippage_cost,
                    "funding": t.funding_paid,
                }
                for t in self.trades
            ]
        )
        
        logger.info(
            "backtest_completed",
            total_trades=metrics.total_trades,
            win_rate=f"{metrics.win_rate:.2%}",
            total_pnl=f"${metrics.total_pnl:.2f}",
            roi=f"{metrics.roi:.2f}%",
        )
        
        return metrics, trades_df

    def _calculate_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL for current position."""
        if self.position == "flat":
            return 0.0
        
        price_change = current_price - self.entry_price
        
        if self.position == "short":
            price_change = -price_change
        
        pnl = price_change * self.position_size * self.config.leverage
        return pnl

    def _close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        spread_bps: float,
    ) -> float:
        """Close current position and record trade."""
        if self.position == "flat":
            return 0.0
        
        # Adjust exit price for spread (pay other half)
        if self.position == "long":
            actual_exit_price = exit_price * (1 - spread_bps / 20000)
        else:  # short
            actual_exit_price = exit_price * (1 + spread_bps / 20000)
        
        # Calculate PnL
        gross_pnl = self._calculate_pnl(actual_exit_price)
        
        # Calculate costs
        position_value = self.position_size * actual_exit_price
        
        # Exit fee
        exit_fee = position_value * self.config.taker_fee
        
        # Slippage
        slippage_cost = position_value * (self.config.slippage_bps / 10000)
        
        # Funding (simplified - assume 0 for ultra-short-term)
        funding_cost = 0.0
        
        # Net PnL
        net_pnl = gross_pnl - exit_fee - slippage_cost - funding_cost
        
        # Record trade
        trade = Trade(
            entry_time=self.entry_time or exit_time,
            exit_time=exit_time,
            side=self.position,
            entry_price=self.entry_price,
            exit_price=actual_exit_price,
            size=self.position_size,
            pnl=net_pnl,
            pnl_pct=(net_pnl / (position_value / self.config.leverage)) * 100,
            fees_paid=exit_fee,
            slippage_cost=slippage_cost,
            funding_paid=funding_cost,
        )
        self.trades.append(trade)
        
        logger.debug(
            "position_closed",
            side=self.position,
            entry=self.entry_price,
            exit=actual_exit_price,
            pnl=net_pnl,
        )
        
        # Reset position
        self.position = "flat"
        self.entry_price = 0.0
        self.position_size = 0.0
        self.entry_time = None
        
        return net_pnl

    def _calculate_metrics(
        self, initial_balance: float, final_balance: float
    ) -> BacktestMetrics:
        """Calculate comprehensive performance metrics."""
        if not self.trades:
            return BacktestMetrics(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_pnl_pct=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                total_fees=0.0,
                total_slippage=0.0,
                total_funding=0.0,
                net_pnl=0.0,
                final_balance=final_balance,
                roi=0.0,
                avg_trade_duration_sec=0.0,
            )
        
        trade_pnls = [t.pnl for t in self.trades]
        winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in trade_pnls if pnl < 0]
        
        total_pnl = sum(trade_pnls)
        win_rate = len(winning_trades) / len(self.trades)
        
        # Drawdown
        equity_array = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = peak - equity_array
        max_drawdown = np.max(drawdown)
        max_drawdown_pct = (max_drawdown / initial_balance) * 100
        
        # Sharpe & Sortino
        returns = np.diff(equity_array) / equity_array[:-1]
        sharpe_ratio = (
            (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24 * 3600)
            if np.std(returns) > 0
            else 0.0
        )
        
        negative_returns = returns[returns < 0]
        downside_std = np.std(negative_returns) if len(negative_returns) > 0 else 1e-8
        sortino_ratio = (np.mean(returns) / downside_std) * np.sqrt(252 * 24 * 3600)
        
        # Profit factor
        gross_profit = sum(winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1e-8
        profit_factor = gross_profit / gross_loss
        
        # Trade duration
        durations = []
        for t in self.trades:
            if t.entry_time and t.exit_time:
                duration = (t.exit_time - t.entry_time).total_seconds()
                durations.append(duration)
        avg_duration = np.mean(durations) if durations else 0.0
        
        return BacktestMetrics(
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_pct=(total_pnl / initial_balance) * 100,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            avg_win=np.mean(winning_trades) if winning_trades else 0.0,
            avg_loss=np.mean(losing_trades) if losing_trades else 0.0,
            largest_win=max(winning_trades) if winning_trades else 0.0,
            largest_loss=min(losing_trades) if losing_trades else 0.0,
            total_fees=sum(t.fees_paid for t in self.trades),
            total_slippage=sum(t.slippage_cost for t in self.trades),
            total_funding=sum(t.funding_paid for t in self.trades),
            net_pnl=total_pnl,
            final_balance=final_balance,
            roi=((final_balance - initial_balance) / initial_balance) * 100,
            avg_trade_duration_sec=avg_duration,
        )

