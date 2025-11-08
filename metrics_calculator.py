"""
Metrics Calculator - Comprehensive performance metrics for backtests
"""

import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from backtest_engine import BacktestResult, Trade


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest."""
    # Strategy info
    strategy_id: int
    strategy_name: str
    symbol: str
    
    # Trade metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_win_usd: float
    avg_loss_usd: float
    best_trade_usd: float
    worst_trade_usd: float
    profit_factor: float  # Gross profit / Gross loss
    
    # Frequency metrics
    trades_per_day: float
    trades_per_hour: float
    avg_time_in_position_hours: float
    max_time_in_position_hours: float
    
    # Return metrics
    initial_capital: float
    final_capital: float
    total_pnl_usd: float
    total_roi_pct: float
    roi_per_day_pct: float
    roi_per_week_pct: float
    roi_per_month_pct: float
    
    # Risk metrics
    max_drawdown_pct: float
    max_drawdown_duration_hours: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float  # Return / Max DD
    var_95_pct: float  # Value at Risk 95%
    
    # Consistency metrics
    win_streak: int  # Max consecutive wins
    loss_streak: int  # Max consecutive losses
    profitable_days_pct: float
    recovery_factor: float  # Net profit / Max DD
    
    # Capital growth at intervals
    capital_24h: float
    capital_1week: float
    
    # Daily/Weekly stats
    daily_return_mean_pct: float
    daily_return_std_pct: float
    weekly_return_mean_pct: float
    weekly_return_std_pct: float


class MetricsCalculator:
    """Calculate comprehensive performance metrics from backtest results."""
    
    @staticmethod
    def calculate_all_metrics(result: BacktestResult) -> PerformanceMetrics:
        """Calculate all performance metrics for a backtest result."""
        trades = result.trades
        
        if not trades:
            # Return zero metrics if no trades
            return MetricsCalculator._zero_metrics(result)
        
        # Calculate timespan
        start_time = result.equity_curve[0][0]
        end_time = result.equity_curve[-1][0]
        duration_hours = (end_time - start_time) / (1000 * 3600)
        duration_days = duration_hours / 24
        
        # === TRADE METRICS ===
        winning_trades = [t for t in trades if t.pnl_usd > 0]
        losing_trades = [t for t in trades if t.pnl_usd < 0]
        
        total_trades = len(trades)
        num_wins = len(winning_trades)
        num_losses = len(losing_trades)
        win_rate_pct = (num_wins / total_trades * 100) if total_trades > 0 else 0.0
        
        avg_win_usd = np.mean([t.pnl_usd for t in winning_trades]) if winning_trades else 0.0
        avg_loss_usd = np.mean([t.pnl_usd for t in losing_trades]) if losing_trades else 0.0
        best_trade_usd = max([t.pnl_usd for t in trades])
        worst_trade_usd = min([t.pnl_usd for t in trades])
        
        gross_profit = sum(t.pnl_usd for t in winning_trades)
        gross_loss = abs(sum(t.pnl_usd for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0
        
        # === FREQUENCY METRICS ===
        trades_per_day = total_trades / duration_days if duration_days > 0 else 0.0
        trades_per_hour = total_trades / duration_hours if duration_hours > 0 else 0.0
        
        trade_durations = [t.duration_hours() for t in trades]
        avg_time_in_position_hours = np.mean(trade_durations) if trade_durations else 0.0
        max_time_in_position_hours = max(trade_durations) if trade_durations else 0.0
        
        # === RETURN METRICS ===
        initial_capital = result.initial_capital
        final_capital = result.final_capital
        total_pnl_usd = final_capital - initial_capital
        total_roi_pct = (total_pnl_usd / initial_capital * 100) if initial_capital > 0 else 0.0
        
        roi_per_day_pct = (total_roi_pct / duration_days) if duration_days > 0 else 0.0
        roi_per_week_pct = roi_per_day_pct * 7
        roi_per_month_pct = roi_per_day_pct * 30
        
        # Capital at intervals
        capital_24h = MetricsCalculator._get_capital_at_hour(result.equity_curve, 24)
        capital_1week = MetricsCalculator._get_capital_at_hour(result.equity_curve, 24 * 7)
        
        # === RISK METRICS ===
        max_drawdown_pct, max_dd_duration_hours = MetricsCalculator._calculate_drawdown(result.equity_curve)
        
        # Returns for Sharpe/Sortino
        returns_pct = [t.pnl_pct for t in trades]
        sharpe_ratio = MetricsCalculator._calculate_sharpe(returns_pct)
        sortino_ratio = MetricsCalculator._calculate_sortino(returns_pct)
        
        calmar_ratio = (total_roi_pct / abs(max_drawdown_pct)) if max_drawdown_pct != 0 else 0.0
        var_95_pct = np.percentile(returns_pct, 5) if returns_pct else 0.0  # 5th percentile (95% VaR)
        
        # === CONSISTENCY METRICS ===
        win_streak, loss_streak = MetricsCalculator._calculate_streaks(trades)
        
        daily_returns = MetricsCalculator._group_returns_by_day(trades, start_time, end_time)
        profitable_days = sum(1 for r in daily_returns if r > 0)
        profitable_days_pct = (profitable_days / len(daily_returns) * 100) if daily_returns else 0.0
        
        recovery_factor = (total_pnl_usd / abs(max_drawdown_pct * initial_capital / 100)) if max_drawdown_pct != 0 else 0.0
        
        # Daily/Weekly stats
        daily_return_mean_pct = np.mean(daily_returns) if daily_returns else 0.0
        daily_return_std_pct = np.std(daily_returns) if daily_returns else 0.0
        
        weekly_returns = MetricsCalculator._group_returns_by_week(trades, start_time, end_time)
        weekly_return_mean_pct = np.mean(weekly_returns) if weekly_returns else 0.0
        weekly_return_std_pct = np.std(weekly_returns) if weekly_returns else 0.0
        
        return PerformanceMetrics(
            strategy_id=result.strategy_id,
            strategy_name=result.strategy_name,
            symbol=result.symbol,
            total_trades=total_trades,
            winning_trades=num_wins,
            losing_trades=num_losses,
            win_rate_pct=win_rate_pct,
            avg_win_usd=avg_win_usd,
            avg_loss_usd=avg_loss_usd,
            best_trade_usd=best_trade_usd,
            worst_trade_usd=worst_trade_usd,
            profit_factor=profit_factor,
            trades_per_day=trades_per_day,
            trades_per_hour=trades_per_hour,
            avg_time_in_position_hours=avg_time_in_position_hours,
            max_time_in_position_hours=max_time_in_position_hours,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_pnl_usd=total_pnl_usd,
            total_roi_pct=total_roi_pct,
            roi_per_day_pct=roi_per_day_pct,
            roi_per_week_pct=roi_per_week_pct,
            roi_per_month_pct=roi_per_month_pct,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_duration_hours=max_dd_duration_hours,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            var_95_pct=var_95_pct,
            win_streak=win_streak,
            loss_streak=loss_streak,
            profitable_days_pct=profitable_days_pct,
            recovery_factor=recovery_factor,
            capital_24h=capital_24h,
            capital_1week=capital_1week,
            daily_return_mean_pct=daily_return_mean_pct,
            daily_return_std_pct=daily_return_std_pct,
            weekly_return_mean_pct=weekly_return_mean_pct,
            weekly_return_std_pct=weekly_return_std_pct,
        )
    
    @staticmethod
    def _zero_metrics(result: BacktestResult) -> PerformanceMetrics:
        """Return zero metrics for backtests with no trades."""
        return PerformanceMetrics(
            strategy_id=result.strategy_id,
            strategy_name=result.strategy_name,
            symbol=result.symbol,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            avg_win_usd=0.0,
            avg_loss_usd=0.0,
            best_trade_usd=0.0,
            worst_trade_usd=0.0,
            profit_factor=0.0,
            trades_per_day=0.0,
            trades_per_hour=0.0,
            avg_time_in_position_hours=0.0,
            max_time_in_position_hours=0.0,
            initial_capital=result.initial_capital,
            final_capital=result.final_capital,
            total_pnl_usd=0.0,
            total_roi_pct=0.0,
            roi_per_day_pct=0.0,
            roi_per_week_pct=0.0,
            roi_per_month_pct=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration_hours=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            var_95_pct=0.0,
            win_streak=0,
            loss_streak=0,
            profitable_days_pct=0.0,
            recovery_factor=0.0,
            capital_24h=result.initial_capital,
            capital_1week=result.initial_capital,
            daily_return_mean_pct=0.0,
            daily_return_std_pct=0.0,
            weekly_return_mean_pct=0.0,
            weekly_return_std_pct=0.0,
        )
    
    @staticmethod
    def _calculate_drawdown(equity_curve: List[tuple]) -> tuple:
        """Calculate maximum drawdown and its duration."""
        if not equity_curve:
            return 0.0, 0.0
        
        peak = equity_curve[0][1]
        max_dd = 0.0
        max_dd_duration_hours = 0.0
        dd_start_time = None
        
        for timestamp, equity in equity_curve:
            if equity > peak:
                peak = equity
                dd_start_time = None
            else:
                dd_pct = (peak - equity) / peak * 100
                if dd_pct > max_dd:
                    max_dd = dd_pct
                
                if dd_start_time is None:
                    dd_start_time = timestamp
                else:
                    dd_duration = (timestamp - dd_start_time) / (1000 * 3600)
                    if dd_duration > max_dd_duration_hours:
                        max_dd_duration_hours = dd_duration
        
        return max_dd, max_dd_duration_hours
    
    @staticmethod
    def _calculate_sharpe(returns_pct: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio."""
        if not returns_pct or len(returns_pct) < 2:
            return 0.0
        
        mean_return = np.mean(returns_pct)
        std_return = np.std(returns_pct)
        
        if std_return == 0:
            return 0.0
        
        return (mean_return - risk_free_rate) / std_return
    
    @staticmethod
    def _calculate_sortino(returns_pct: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio (uses downside deviation only)."""
        if not returns_pct or len(returns_pct) < 2:
            return 0.0
        
        mean_return = np.mean(returns_pct)
        downside_returns = [r for r in returns_pct if r < 0]
        
        if not downside_returns:
            return float('inf') if mean_return > 0 else 0.0
        
        downside_std = np.std(downside_returns)
        
        if downside_std == 0:
            return 0.0
        
        return (mean_return - risk_free_rate) / downside_std
    
    @staticmethod
    def _calculate_streaks(trades: List[Trade]) -> tuple:
        """Calculate maximum winning and losing streaks."""
        if not trades:
            return 0, 0
        
        win_streak = 0
        loss_streak = 0
        current_win_streak = 0
        current_loss_streak = 0
        
        for trade in trades:
            if trade.pnl_usd > 0:
                current_win_streak += 1
                current_loss_streak = 0
                win_streak = max(win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                loss_streak = max(loss_streak, current_loss_streak)
        
        return win_streak, loss_streak
    
    @staticmethod
    def _group_returns_by_day(trades: List[Trade], start_time: int, end_time: int) -> List[float]:
        """Group trade returns by day."""
        if not trades:
            return []
        
        # Create daily buckets
        duration_days = int((end_time - start_time) / (1000 * 86400)) + 1
        daily_pnl = [0.0] * duration_days
        
        for trade in trades:
            day_idx = int((trade.exit_time - start_time) / (1000 * 86400))
            if 0 <= day_idx < duration_days:
                daily_pnl[day_idx] += trade.pnl_pct
        
        return [pnl for pnl in daily_pnl if pnl != 0]  # Only return days with trades
    
    @staticmethod
    def _group_returns_by_week(trades: List[Trade], start_time: int, end_time: int) -> List[float]:
        """Group trade returns by week."""
        if not trades:
            return []
        
        # Create weekly buckets
        duration_weeks = int((end_time - start_time) / (1000 * 86400 * 7)) + 1
        weekly_pnl = [0.0] * duration_weeks
        
        for trade in trades:
            week_idx = int((trade.exit_time - start_time) / (1000 * 86400 * 7))
            if 0 <= week_idx < duration_weeks:
                weekly_pnl[week_idx] += trade.pnl_pct
        
        return [pnl for pnl in weekly_pnl if pnl != 0]  # Only return weeks with trades
    
    @staticmethod
    def _get_capital_at_hour(equity_curve: List[tuple], target_hours: float) -> float:
        """Get capital at a specific time offset (in hours) from start."""
        if not equity_curve:
            return 0.0
        
        start_time = equity_curve[0][0]
        target_time = start_time + (target_hours * 3600 * 1000)
        
        # Find closest equity point
        for timestamp, equity in equity_curve:
            if timestamp >= target_time:
                return equity
        
        # If target is beyond data, return final capital
        return equity_curve[-1][1]

