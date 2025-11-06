"""Backtesting engine with comprehensive performance metrics."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Literal

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from bitget_trading.config import TradingConfig
from bitget_trading.features import create_sequences
from bitget_trading.logger import get_logger
from bitget_trading.model import CNN_LSTM_GRU, load_model

logger = get_logger()

PositionType = Literal["long", "short", "flat"]


@dataclass
class Trade:
    """Individual trade record."""

    entry_time: datetime
    exit_time: datetime
    position_type: PositionType
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    leverage: int


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
    avg_trade_duration: float
    total_fees: float
    net_pnl: float
    final_balance: float
    roi: float


class Backtester:
    """
    Backtesting engine for trading strategies.

    Args:
        config: Trading configuration
        model: Trained neural network model
    """

    def __init__(self, config: TradingConfig, model: CNN_LSTM_GRU) -> None:
        """Initialize backtester."""
        self.config = config
        self.model = model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        self.model.eval()

        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.balance_history: List[float] = []
        self.position: PositionType = "flat"
        self.entry_price: float = 0.0
        self.position_size: float = 0.0

    def run(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
    ) -> tuple[BacktestMetrics, pd.DataFrame]:
        """
        Run backtest on historical data.

        Args:
            df: DataFrame with OHLCV data
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

        # Create sequences
        sequences, feature_cols = create_sequences(df, self.config.seq_len)

        if len(sequences) == 0:
            raise ValueError("Insufficient data for backtesting")

        # Prepare data
        dataset = TensorDataset(torch.tensor(sequences, dtype=torch.float32))
        dataloader = DataLoader(
            dataset, batch_size=self.config.batch_size, shuffle=False
        )

        # Generate predictions
        predictions = []
        with torch.no_grad():
            for batch in dataloader:
                batch_data = batch[0].to(self.device)
                outputs = self.model(batch_data)
                probs = torch.softmax(outputs, dim=1)
                predictions.extend(probs.cpu().numpy())

        predictions = np.array(predictions)
        signals = np.argmax(predictions, axis=1)  # 0=long, 1=short, 2=flat

        # Align predictions with price data
        price_data = df.iloc[self.config.seq_len - 1 :].reset_index(drop=True)

        # Run backtest
        balance = initial_balance
        peak_balance = initial_balance
        self.balance_history = [balance]

        for i in range(len(signals)):
            current_price = price_data.iloc[i]["close"]
            current_time = (
                price_data.iloc[i]["timestamp"]
                if "timestamp" in price_data.columns
                else price_data.iloc[i].name
            )
            signal = signals[i]

            # Calculate position size based on risk
            risk_amount = balance * self.config.risk_per_trade
            position_value = risk_amount * self.config.leverage
            size = position_value / current_price

            # Execute trades based on signals
            if signal == 0 and self.position != "long":  # Go long
                # Close existing position
                if self.position == "short":
                    self._close_position(current_price, current_time, balance)

                # Open long
                self.position = "long"
                self.entry_price = current_price
                self.position_size = size
                balance -= self._calculate_fees(position_value)

            elif signal == 1 and self.position != "short":  # Go short
                # Close existing position
                if self.position == "long":
                    self._close_position(current_price, current_time, balance)

                # Open short
                self.position = "short"
                self.entry_price = current_price
                self.position_size = size
                balance -= self._calculate_fees(position_value)

            elif signal == 2 and self.position != "flat":  # Close position
                pnl = self._close_position(current_price, current_time, balance)
                balance += pnl

            # Update balance with unrealized PnL
            if self.position != "flat":
                unrealized_pnl = self._calculate_pnl(current_price)
                current_balance = balance + unrealized_pnl
            else:
                current_balance = balance

            # Track equity curve
            self.balance_history.append(current_balance)
            peak_balance = max(peak_balance, current_balance)

            # Check daily loss limit (simplified)
            drawdown_pct = (peak_balance - current_balance) / peak_balance
            if drawdown_pct >= self.config.daily_loss_limit:
                logger.warning(
                    "daily_loss_limit_hit",
                    drawdown_pct=drawdown_pct,
                    step=i,
                )
                # Close position and stop trading for this simulation
                if self.position != "flat":
                    pnl = self._close_position(current_price, current_time, balance)
                    balance += pnl
                break

        # Close any remaining position
        if self.position != "flat":
            final_price = price_data.iloc[-1]["close"]
            final_time = (
                price_data.iloc[-1]["timestamp"]
                if "timestamp" in price_data.columns
                else price_data.iloc[-1].name
            )
            pnl = self._close_position(final_price, final_time, balance)
            balance += pnl

        # Calculate metrics
        metrics = self._calculate_metrics(initial_balance, balance)

        # Create trades DataFrame
        trades_df = pd.DataFrame(
            [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "position": t.position_type,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "size": t.size,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "leverage": t.leverage,
                }
                for t in self.trades
            ]
        )

        logger.info(
            "backtest_completed",
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            total_pnl=metrics.total_pnl,
            roi=metrics.roi,
        )

        return metrics, trades_df

    def _calculate_pnl(self, current_price: float) -> float:
        """Calculate PnL for current position."""
        if self.position == "flat":
            return 0.0

        price_change = current_price - self.entry_price

        if self.position == "short":
            price_change = -price_change

        pnl = price_change * self.position_size * self.config.leverage
        return pnl

    def _close_position(
        self, exit_price: float, exit_time: datetime, balance: float
    ) -> float:
        """Close current position and record trade."""
        if self.position == "flat":
            return 0.0

        pnl = self._calculate_pnl(exit_price)

        # Calculate fees
        position_value = self.position_size * exit_price
        fees = self._calculate_fees(position_value)
        net_pnl = pnl - fees

        # Calculate slippage
        slippage_cost = position_value * self.config.slippage
        net_pnl -= slippage_cost

        # Record trade
        trade = Trade(
            entry_time=datetime.now(),  # Would need to track entry time properly
            exit_time=exit_time,
            position_type=self.position,
            entry_price=self.entry_price,
            exit_price=exit_price,
            size=self.position_size,
            pnl=net_pnl,
            pnl_pct=(net_pnl / balance) * 100,
            leverage=self.config.leverage,
        )
        self.trades.append(trade)

        # Reset position
        self.position = "flat"
        self.entry_price = 0.0
        self.position_size = 0.0

        return net_pnl

    def _calculate_fees(self, position_value: float) -> float:
        """Calculate trading fees."""
        return position_value * self.config.fee

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
                avg_trade_duration=0.0,
                total_fees=0.0,
                net_pnl=0.0,
                final_balance=final_balance,
                roi=0.0,
            )

        trade_pnls = [t.pnl for t in self.trades]
        winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in trade_pnls if pnl < 0]

        total_pnl = sum(trade_pnls)
        win_rate = len(winning_trades) / len(self.trades) if self.trades else 0.0

        # Drawdown calculation
        balance_series = np.array(self.balance_history)
        peak = np.maximum.accumulate(balance_series)
        drawdown = peak - balance_series
        max_drawdown = np.max(drawdown)
        max_drawdown_pct = (max_drawdown / initial_balance) * 100

        # Sharpe & Sortino ratios
        returns = np.diff(balance_series) / balance_series[:-1]
        sharpe_ratio = (
            (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24 * 60)
            if np.std(returns) > 0
            else 0.0
        )

        negative_returns = returns[returns < 0]
        downside_std = np.std(negative_returns) if len(negative_returns) > 0 else 1e-8
        sortino_ratio = (np.mean(returns) / downside_std) * np.sqrt(252 * 24 * 60)

        # Profit factor
        gross_profit = sum(winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1e-8
        profit_factor = gross_profit / gross_loss

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
            avg_trade_duration=0.0,  # Would need proper time tracking
            total_fees=sum(
                self._calculate_fees(t.size * t.entry_price) * 2 for t in self.trades
            ),
            net_pnl=total_pnl,
            final_balance=final_balance,
            roi=((final_balance - initial_balance) / initial_balance) * 100,
        )


def run_backtest(
    data_path: str | Path,
    config: TradingConfig,
    initial_balance: float = 10000.0,
    save_results: bool = True,
) -> tuple[BacktestMetrics, pd.DataFrame]:
    """
    Run backtest from CSV data file.

    Args:
        data_path: Path to CSV file with OHLCV data
        config: Trading configuration
        initial_balance: Starting capital
        save_results: Whether to save results to disk

    Returns:
        Tuple of (metrics, trades_df)
    """
    # Load data
    df = pd.read_csv(data_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Load model
    model = load_model(
        config.model_path,
        n_features=config.n_features,
        lstm_hidden=config.lstm_hidden,
        gru_hidden=config.gru_hidden,
        dropout=config.dropout,
    )

    # Run backtest
    backtester = Backtester(config, model)
    metrics, trades_df = backtester.run(df, initial_balance)

    # Save results
    if save_results:
        results_dir = Path("backtest_results")
        results_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trades_df.to_csv(results_dir / f"trades_{timestamp}.csv", index=False)

        # Save metrics
        metrics_df = pd.DataFrame([metrics.__dict__])
        metrics_df.to_csv(results_dir / f"metrics_{timestamp}.csv", index=False)

        logger.info("backtest_results_saved", directory=str(results_dir))

    return metrics, trades_df

