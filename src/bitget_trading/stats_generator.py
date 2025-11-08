"""Generate human-readable stats file for token performance."""

from datetime import datetime
from pathlib import Path
from typing import Any

from src.bitget_trading.logger import get_logger
from src.bitget_trading.symbol_performance_tracker import SymbolPerformance, SymbolPerformanceTracker

logger = get_logger()


class StatsGenerator:
    """
    Generate human-readable stats file showing:
    - Per-token backtesting results
    - Filtered tokens list
    - Dynamic parameter adjustments
    - Live trading results
    """

    def __init__(
        self,
        performance_tracker: SymbolPerformanceTracker,
        data_dir: Path | str = "data",
    ) -> None:
        """
        Initialize stats generator.
        
        Args:
            performance_tracker: Performance tracker instance
            data_dir: Directory to store stats file
        """
        self.performance_tracker = performance_tracker
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.stats_file = self.data_dir / "symbol_performance_stats.txt"

    def generate_stats(self) -> None:
        """Generate and save stats file."""
        try:
            all_perfs = self.performance_tracker.get_all_performances()
            
            if not all_perfs:
                self._write_empty_stats()
                return
            
            # Sort by combined score descending
            sorted_perfs = sorted(
                all_perfs.items(),
                key=lambda x: x[1].combined_score,
                reverse=True
            )
            
            # Group by tier
            tier1 = []
            tier2 = []
            tier3 = []
            tier4 = []
            filtered = []
            
            for symbol, perf in sorted_perfs:
                # Check if filtered
                should_filter, reason = self.performance_tracker.should_filter_symbol(symbol)
                if should_filter:
                    # Token should be filtered (excluded from trading)
                    filtered.append((symbol, perf, reason))
                else:
                    # Token passed filter (can be traded)
                    tier = perf.tier or "tier3"
                    if tier == "tier1":
                        tier1.append((symbol, perf))
                    elif tier == "tier2":
                        tier2.append((symbol, perf))
                    elif tier == "tier4":
                        tier4.append((symbol, perf))
                    else:
                        tier3.append((symbol, perf))
            
            # Generate stats
            lines = []
            lines.append("=" * 80)
            lines.append("SYMBOL PERFORMANCE STATS")
            lines.append("=" * 80)
            lines.append(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # Get last backtest time
            last_backtest = None
            for perf in all_perfs.values():
                if perf.last_backtest:
                    if last_backtest is None or perf.last_backtest > last_backtest:
                        last_backtest = perf.last_backtest
            
            if last_backtest:
                lines.append(f"Last Backtest: {last_backtest.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                lines.append("Last Backtest: Never")
            
            lines.append("")
            
            # Tier 1 (Top 20% - Best Performers)
            if tier1:
                lines.append("=" * 80)
                lines.append("TOP PERFORMERS (Tier 1 - Best 20%)")
                lines.append("=" * 80)
                for symbol, perf in tier1[:20]:  # Top 20
                    lines.append(self._format_symbol_stats(symbol, perf, "tier1"))
                lines.append("")
            
            # Tier 2 (Top 50% - Good Performers)
            if tier2:
                lines.append("=" * 80)
                lines.append("GOOD PERFORMERS (Tier 2 - Top 50%)")
                lines.append("=" * 80)
                for symbol, perf in tier2[:30]:  # Top 30
                    lines.append(self._format_symbol_stats(symbol, perf, "tier2"))
                lines.append("")
            
            # Tier 3 (Average)
            if tier3:
                lines.append("=" * 80)
                lines.append("AVERAGE PERFORMERS (Tier 3)")
                lines.append("=" * 80)
                for symbol, perf in tier3[:20]:  # Top 20
                    lines.append(self._format_symbol_stats(symbol, perf, "tier3"))
                lines.append("")
            
            # Tier 4 (Bottom 20% - Poor Performers)
            if tier4:
                lines.append("=" * 80)
                lines.append("POOR PERFORMERS (Tier 4 - Bottom 20%)")
                lines.append("=" * 80)
                for symbol, perf in tier4[:20]:  # Top 20
                    lines.append(self._format_symbol_stats(symbol, perf, "tier4"))
                lines.append("")
            
            # Filtered tokens
            if filtered:
                lines.append("=" * 80)
                lines.append("FILTERED TOKENS (Not Trading)")
                lines.append("=" * 80)
                for symbol, perf, reason in filtered[:30]:  # Top 30
                    lines.append(self._format_filtered_symbol(symbol, perf, reason))
                lines.append("")
            
            # Summary
            lines.append("=" * 80)
            lines.append("SUMMARY")
            lines.append("=" * 80)
            lines.append(f"Total Symbols Tracked: {len(all_perfs)}")
            lines.append(f"Tier 1 (Best): {len(tier1)}")
            lines.append(f"Tier 2 (Good): {len(tier2)}")
            lines.append(f"Tier 3 (Average): {len(tier3)}")
            lines.append(f"Tier 4 (Poor): {len(tier4)}")
            lines.append(f"Filtered: {len(filtered)}")
            lines.append("")
            
            # Write to file
            with open(self.stats_file, "w") as f:
                f.write("\n".join(lines))
            
            logger.info(f"✅ Generated stats file: {self.stats_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to generate stats: {e}")

    def _format_symbol_stats(
        self,
        symbol: str,
        perf: SymbolPerformance,
        tier: str,
    ) -> str:
        """Format symbol stats for display."""
        # Get recent backtest results
        recent_backtests = perf.backtest_results[-3:] if perf.backtest_results else []
        
        if not recent_backtests:
            return f"  {symbol}: No backtest data"
        
        # Calculate averages
        avg_win_rate = sum(r["win_rate"] for r in recent_backtests) / len(recent_backtests)
        avg_roi = sum(r["roi"] for r in recent_backtests) / len(recent_backtests)
        avg_sharpe = sum(r["sharpe_ratio"] for r in recent_backtests) / len(recent_backtests)
        avg_trades = sum(r["total_trades"] for r in recent_backtests) / len(recent_backtests)
        
        # Get tier-based parameters
        trailing_tp = {
            "tier1": "6%",
            "tier2": "5%",
            "tier3": "4%",
            "tier4": "3%",
        }.get(tier, "4%")
        
        position_size = {
            "tier1": "1.3x",
            "tier2": "1.15x",
            "tier3": "1.0x",
            "tier4": "0.8x",
        }.get(tier, "1.0x")
        
        # Format line
        line = (
            f"  {symbol}: Win Rate {avg_win_rate:.1%} | "
            f"ROI {avg_roi:.2f}% | "
            f"Sharpe {avg_sharpe:.2f} | "
            f"Trades {avg_trades:.0f}"
        )
        
        # Add live results if available
        if perf.live_results:
            if isinstance(perf.live_results, dict):
                live_win_rate = perf.live_results.get("win_rate", 0.0)
                live_pnl = perf.live_results.get("total_pnl", 0.0)
            else:
                live_win_rate = perf.live_results.win_rate
                live_pnl = perf.live_results.total_pnl
            line += (
                f" | Live: WR {live_win_rate:.1%} | "
                f"PnL ${live_pnl:.2f}"
            )
        
        # Add dynamic parameters
        line += f"\n    → Trailing TP: {trailing_tp} callback | Position Size: {position_size}"
        
        return line

    def _format_filtered_symbol(
        self,
        symbol: str,
        perf: SymbolPerformance,
        reason: str,
    ) -> str:
        """Format filtered symbol for display."""
        # Get recent backtest results
        recent_backtests = perf.backtest_results[-3:] if perf.backtest_results else []
        
        if not recent_backtests:
            return f"  {symbol}: No backtest data | Reason: {reason}"
        
        # Calculate averages
        avg_win_rate = sum(r["win_rate"] for r in recent_backtests) / len(recent_backtests)
        avg_roi = sum(r["roi"] for r in recent_backtests) / len(recent_backtests)
        avg_sharpe = sum(r["sharpe_ratio"] for r in recent_backtests) / len(recent_backtests)
        avg_trades = sum(r["total_trades"] for r in recent_backtests) / len(recent_backtests)
        
        return (
            f"  {symbol}: Win Rate {avg_win_rate:.1%} | "
            f"ROI {avg_roi:.2f}% | "
            f"Sharpe {avg_sharpe:.2f} | "
            f"Trades {avg_trades:.0f} | "
            f"Reason: {reason}"
        )

    def _write_empty_stats(self) -> None:
        """Write empty stats file."""
        lines = [
            "=" * 80,
            "SYMBOL PERFORMANCE STATS",
            "=" * 80,
            f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "Last Backtest: Never",
            "",
            "No performance data available yet.",
            "Run backtests to generate stats.",
        ]
        
        with open(self.stats_file, "w") as f:
            f.write("\n".join(lines))

