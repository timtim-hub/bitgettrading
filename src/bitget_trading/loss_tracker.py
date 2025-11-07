"""
LOSS TRACKER - Identify and analyze why trades are losing money.

Tracks:
- Exit reasons (stop-loss, take-profit, time-based, manual)
- Entry quality metrics
- Market conditions at entry/exit
- Slippage and fees
- Time in trade
- PnL by symbol, time of day, market structure

Goal: Identify patterns in losing trades to improve strategy.
"""

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from bitget_trading.logger import get_logger

logger = get_logger()


@dataclass
class TradeRecord:
    """Detailed record of every trade for loss analysis."""
    
    # Trade identification
    trade_id: str
    symbol: str
    
    # Entry details
    entry_time: str
    entry_price: float
    entry_side: Literal["long", "short"]
    position_size_usd: float
    leverage: int
    
    # Entry quality
    entry_score: float  # Signal strength at entry
    entry_grade: str  # A/B/C/D/F trade quality
    entry_confluence: float
    entry_volume_ratio: float
    entry_market_structure: str  # uptrend/downtrend/ranging
    entry_near_sr: bool  # Near support/resistance?
    entry_rr_ratio: float  # Risk/reward ratio
    
    # Exit details
    exit_time: str
    exit_price: float
    exit_reason: str  # stop_loss, take_profit, trailing_stop, time_exit, manual, etc.
    time_in_trade_seconds: float
    
    # Performance
    pnl_usd: float
    pnl_pct_capital: float  # PnL as % of capital (leveraged)
    pnl_pct_price: float  # Actual price movement %
    fees_paid: float
    slippage_cost: float
    net_pnl: float  # PnL after fees and slippage
    
    # Market conditions
    exit_market_structure: str
    peak_pnl: float  # Highest PnL reached
    drawdown_from_peak: float  # How much we gave back
    
    # Outcomes
    is_win: bool
    is_loss: bool
    stopped_out: bool  # Hit stop-loss
    took_profit: bool  # Hit take-profit
    
    # Technical indicators at entry (for evaluation and improvement) - ALL with defaults at end
    entry_rsi: float = 50.0  # RSI value at entry
    entry_macd_line: float = 0.0  # MACD line at entry
    entry_macd_signal: float = 0.0  # MACD signal at entry
    entry_macd_histogram: float = 0.0  # MACD histogram at entry
    entry_bb_upper: float = 0.0  # Bollinger upper band
    entry_bb_middle: float = 0.0  # Bollinger middle band
    entry_bb_lower: float = 0.0  # Bollinger lower band
    entry_bb_position: float = 0.0  # Position within Bollinger bands (-1 to 1)
    entry_ema_bullish: int = 0  # Number of bullish EMA crossovers
    entry_ema_bearish: int = 0  # Number of bearish EMA crossovers
    entry_vwap: float = 0.0  # VWAP at entry
    entry_vwap_deviation: float = 0.0  # VWAP deviation at entry
    entry_momentum_5s: float = 0.0  # 5s momentum at entry
    entry_momentum_15s: float = 0.0  # 15s momentum at entry
    entry_volatility_30s: float = 0.0  # 30s volatility at entry
    entry_volatility_60s: float = 0.0  # 60s volatility at entry
    entry_spread_bps: float = 0.0  # Spread in basis points at entry
    entry_ob_imbalance: float = 0.0  # Order book imbalance at entry
    entry_funding_rate: float = 0.0  # Funding rate at entry
    
    def to_dict(self):
        """Convert to dictionary for logging."""
        return asdict(self)


class LossTracker:
    """
    Track all trades and analyze loss patterns.
    
    Provides insights like:
    - Win rate by entry grade (A vs B vs C)
    - Most common loss reasons
    - Average PnL by time in trade
    - Best/worst performing symbols
    - Optimal entry conditions
    """
    
    def __init__(self, log_file: str = "trades_detailed.jsonl"):
        """Initialize loss tracker."""
        self.log_file = Path(log_file)
        self.trades: list[TradeRecord] = []
        
        # Statistics
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_fees = 0.0
        
        # Loss reasons counter
        self.loss_reasons: dict[str, int] = {}
        self.win_by_grade: dict[str, tuple[int, int]] = {}  # grade -> (wins, total)
        
        logger.info(f"📊 Loss tracker initialized: {self.log_file}")
    
    def record_trade(self, trade: TradeRecord) -> None:
        """
        Record a completed trade.
        
        Args:
            trade: Complete trade record with all details
        """
        self.trades.append(trade)
        self.total_trades += 1
        
        # Update statistics
        if trade.is_win:
            self.wins += 1
        else:
            self.losses += 1
            # Track loss reason
            self.loss_reasons[trade.exit_reason] = self.loss_reasons.get(trade.exit_reason, 0) + 1
        
        self.total_pnl += trade.net_pnl
        self.total_fees += trade.fees_paid
        
        # Track win rate by grade
        if trade.entry_grade not in self.win_by_grade:
            self.win_by_grade[trade.entry_grade] = (0, 0)
        
        wins, total = self.win_by_grade[trade.entry_grade]
        if trade.is_win:
            self.win_by_grade[trade.entry_grade] = (wins + 1, total + 1)
        else:
            self.win_by_grade[trade.entry_grade] = (wins, total + 1)
        
        # Save to file (JSONL format - one trade per line)
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(trade.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write trade log: {e}")
        
        # Log detailed trade info
        win_emoji = "✅" if trade.is_win else "❌"
        logger.info(
            f"{win_emoji} TRADE COMPLETED",
            symbol=trade.symbol,
            side=trade.entry_side,
            pnl=f"${trade.net_pnl:.2f}",
            pnl_pct=f"{trade.pnl_pct_capital*100:.2f}%",
            reason=trade.exit_reason,
            time=f"{trade.time_in_trade_seconds:.0f}s",
            grade=trade.entry_grade,
            structure=trade.entry_market_structure
        )
        
        # LOSS ANALYSIS: Log detailed reason if loss
        if trade.is_loss:
            self._analyze_loss(trade)
    
    def _analyze_loss(self, trade: TradeRecord) -> None:
        """
        Detailed analysis of why a trade lost money.
        
        Identifies:
        - Poor entry (wrong structure, bad R:R)
        - Premature exit (stopped out early)
        - Gave back profits (hit peak but didn't exit)
        - Fee erosion (PnL too small vs fees)
        - Wrong direction (market structure changed)
        """
        reasons = []
        
        # 1. Check entry quality
        if trade.entry_grade in ["C", "D", "F"]:
            reasons.append(f"❌ Poor entry quality (grade {trade.entry_grade})")
        
        if not trade.entry_near_sr:
            reasons.append("❌ Not at S/R level (poor entry)")
        
        if trade.entry_rr_ratio < 2.0:
            reasons.append(f"❌ Bad R:R ratio ({trade.entry_rr_ratio:.1f}:1 < 2:1)")
        
        # 2. Check if traded against structure
        if (trade.entry_side == "long" and trade.entry_market_structure == "downtrend") or \
           (trade.entry_side == "short" and trade.entry_market_structure == "uptrend"):
            reasons.append(f"❌ Traded against structure ({trade.entry_side} in {trade.entry_market_structure})")
        
        # 3. Check if gave back profits
        if trade.peak_pnl > 0 and trade.drawdown_from_peak > trade.peak_pnl * 0.5:
            reasons.append(f"❌ Gave back {trade.drawdown_from_peak:.2f} from peak {trade.peak_pnl:.2f} (50%+ drawdown)")
        
        # 4. Check fee erosion
        if abs(trade.pnl_usd) < trade.fees_paid:
            reasons.append(f"❌ Fee erosion (|PnL| ${abs(trade.pnl_usd):.2f} < fees ${trade.fees_paid:.2f})")
        
        # 5. Check if stopped out prematurely
        if trade.stopped_out and trade.time_in_trade_seconds < 60:
            reasons.append("❌ Stopped out too fast (<1 min) - stop too tight?")
        
        # 6. Check if market structure changed
        if trade.entry_market_structure != trade.exit_market_structure:
            reasons.append(f"❌ Structure changed: {trade.entry_market_structure} → {trade.exit_market_structure}")
        
        # Log comprehensive loss analysis
        logger.warning(
            f"🔍 LOSS ANALYSIS: {trade.symbol}",
            entry_price=f"${trade.entry_price:.4f}",
            exit_price=f"${trade.exit_price:.4f}",
            pnl=f"${trade.net_pnl:.2f}",
            exit_reason=trade.exit_reason,
            time=f"{trade.time_in_trade_seconds:.0f}s",
            reasons=reasons if reasons else ["⚠️ No obvious reason - random volatility?"]
        )
    
    def get_summary(self) -> dict:
        """
        Get summary statistics.
        
        Returns:
            Summary with win rate, PnL, loss reasons, etc.
        """
        if self.total_trades == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "total_fees": 0.0,
                "net_pnl": 0.0
            }
        
        win_rate = self.wins / self.total_trades
        net_pnl = self.total_pnl
        
        # Calculate win rate by grade
        grade_stats = {}
        for grade, (wins, total) in self.win_by_grade.items():
            if total > 0:
                grade_stats[grade] = {
                    "win_rate": wins / total,
                    "total_trades": total,
                    "wins": wins,
                    "losses": total - wins
                }
        
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "total_fees": self.total_fees,
            "net_pnl": net_pnl,
            "avg_win": sum(t.net_pnl for t in self.trades if t.is_win) / self.wins if self.wins > 0 else 0,
            "avg_loss": sum(t.net_pnl for t in self.trades if t.is_loss) / self.losses if self.losses > 0 else 0,
            "loss_reasons": self.loss_reasons,
            "win_rate_by_grade": grade_stats
        }
    
    def print_summary(self) -> None:
        """Print human-readable summary."""
        summary = self.get_summary()
        
        logger.info("=" * 70)
        logger.info("📊 TRADING PERFORMANCE SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total Trades: {summary['total_trades']}")
        logger.info(f"Wins: {summary['wins']} | Losses: {summary['losses']}")
        logger.info(f"Win Rate: {summary['win_rate']*100:.1f}%")
        logger.info(f"Total PnL: ${summary['total_pnl']:.2f}")
        logger.info(f"Total Fees: ${summary['total_fees']:.2f}")
        logger.info(f"Net PnL: ${summary['net_pnl']:.2f}")
        logger.info(f"Avg Win: ${summary['avg_win']:.2f}")
        logger.info(f"Avg Loss: ${summary['avg_loss']:.2f}")
        
        logger.info("")
        logger.info("🔍 LOSS REASONS:")
        for reason, count in sorted(summary['loss_reasons'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {reason}: {count} times")
        
        logger.info("")
        logger.info("📈 WIN RATE BY ENTRY GRADE:")
        for grade, stats in sorted(summary['win_rate_by_grade'].items()):
            logger.info(
                f"  Grade {grade}: {stats['win_rate']*100:.1f}% "
                f"({stats['wins']}/{stats['total_trades']} trades)"
            )
        
        logger.info("=" * 70)

