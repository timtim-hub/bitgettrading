"""Performance tracking and storage for per-token backtesting."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.bitget_trading.logger import get_logger
from src.bitget_trading.symbol_backtester import BacktestResult

logger = get_logger()


@dataclass
class LiveResult:
    """Live trading result for a symbol."""

    win_rate: float
    total_trades: int
    total_pnl: float
    last_updated: datetime


@dataclass
class SymbolPerformance:
    """Performance data for a single symbol."""

    symbol: str
    backtest_results: list[dict[str, Any]]
    live_results: dict[str, Any] | None
    combined_score: float
    last_backtest: datetime | None
    tier: str | None = None  # "tier1", "tier2", "tier3", "tier4"


class SymbolPerformanceTracker:
    """
    Track and store per-token backtesting and live trading performance.
    
    Persists to JSON file for durability.
    """

    def __init__(self, data_dir: Path | str = "data") -> None:
        """
        Initialize performance tracker.
        
        Args:
            data_dir: Directory to store performance data
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / "symbol_performance.json"
        
        # In-memory cache
        self.performance_data: dict[str, SymbolPerformance] = {}
        
        # Load existing data
        self.load()

    def load(self) -> None:
        """Load performance data from JSON file."""
        if not self.data_file.exists():
            logger.info(f"📊 No existing performance data found, starting fresh")
            return
        
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
            
            for symbol, perf_data in data.items():
                # Convert backtest results
                backtest_results = perf_data.get("backtest_results", [])
                
                # Convert live results
                live_results = perf_data.get("live_results")
                if live_results:
                    if isinstance(live_results, dict) and live_results.get("last_updated"):
                        # Convert string to datetime
                        if isinstance(live_results["last_updated"], str):
                            live_results["last_updated"] = datetime.fromisoformat(
                                live_results["last_updated"]
                            )
                        # Convert dict to LiveResult dataclass
                        live_results = LiveResult(
                            win_rate=live_results.get("win_rate", 0.0),
                            total_trades=live_results.get("total_trades", 0),
                            total_pnl=live_results.get("total_pnl", 0.0),
                            last_updated=live_results.get("last_updated", datetime.now()),
                        )
                
                # Convert last_backtest
                last_backtest = perf_data.get("last_backtest")
                if last_backtest:
                    last_backtest = datetime.fromisoformat(last_backtest)
                
                self.performance_data[symbol] = SymbolPerformance(
                    symbol=symbol,
                    backtest_results=backtest_results,
                    live_results=live_results,
                    combined_score=perf_data.get("combined_score", 0.0),
                    last_backtest=last_backtest,
                    tier=perf_data.get("tier"),
                )
            
            logger.info(f"✅ Loaded performance data for {len(self.performance_data)} symbols")
            
        except Exception as e:
            logger.error(f"❌ Failed to load performance data: {e}")
            self.performance_data = {}

    def save(self) -> None:
        """Save performance data to JSON file."""
        try:
            data = {}
            for symbol, perf in self.performance_data.items():
                # Convert to dict
                perf_dict = {
                    "backtest_results": perf.backtest_results,
                    "live_results": None,
                    "combined_score": perf.combined_score,
                    "last_backtest": None,
                    "tier": perf.tier,
                }
                
                # Convert live results
                if perf.live_results and isinstance(perf.live_results, LiveResult):
                    live_dict = asdict(perf.live_results)
                    if live_dict.get("last_updated"):
                        live_dict["last_updated"] = live_dict["last_updated"].isoformat()
                    perf_dict["live_results"] = live_dict
                elif perf.live_results:
                    # Already a dict
                    live_dict = perf.live_results.copy()
                    if live_dict.get("last_updated") and isinstance(live_dict["last_updated"], datetime):
                        live_dict["last_updated"] = live_dict["last_updated"].isoformat()
                    perf_dict["live_results"] = live_dict
                
                # Convert last_backtest
                if perf.last_backtest:
                    perf_dict["last_backtest"] = perf.last_backtest.isoformat()
                
                data[symbol] = perf_dict
            
            with open(self.data_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.debug(f"💾 Saved performance data for {len(self.performance_data)} symbols")
            
        except Exception as e:
            logger.error(f"❌ Failed to save performance data: {e}")

    def add_backtest_result(self, result: BacktestResult) -> None:
        """
        Add a backtest result for a symbol.
        
        Args:
            result: Backtest result
        """
        if result.symbol not in self.performance_data:
            self.performance_data[result.symbol] = SymbolPerformance(
                symbol=result.symbol,
                backtest_results=[],
                live_results=None,
                combined_score=0.0,
                last_backtest=None,
            )
        
        perf = self.performance_data[result.symbol]
        
        # Convert result to dict
        result_dict = {
            "timestamp": result.timestamp.isoformat(),
            "win_rate": result.win_rate,
            "roi": result.roi,
            "sharpe_ratio": result.sharpe_ratio,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "avg_win": result.avg_win,
            "avg_loss": result.avg_loss,
            "profit_factor": result.profit_factor,
            "max_drawdown": result.max_drawdown,
            "total_pnl": result.total_pnl,
            "net_pnl": result.net_pnl,
        }
        
        # Add to backtest results (keep last 30 results)
        perf.backtest_results.append(result_dict)
        if len(perf.backtest_results) > 30:
            perf.backtest_results.pop(0)
        
        # Update last_backtest
        perf.last_backtest = result.timestamp
        
        # Recalculate combined score
        self._update_combined_score(result.symbol)
        
        # Save
        self.save()

    def update_live_result(
        self,
        symbol: str,
        win_rate: float,
        total_trades: int,
        total_pnl: float,
    ) -> None:
        """
        Update live trading result for a symbol.
        
        Args:
            symbol: Trading pair
            win_rate: Win rate (0-1)
            total_trades: Total number of trades
            total_pnl: Total PnL in USDT
        """
        if symbol not in self.performance_data:
            self.performance_data[symbol] = SymbolPerformance(
                symbol=symbol,
                backtest_results=[],
                live_results=None,
                combined_score=0.0,
                last_backtest=None,
            )
        
        perf = self.performance_data[symbol]
        
        # Update live results
        perf.live_results = LiveResult(
            win_rate=win_rate,
            total_trades=total_trades,
            total_pnl=total_pnl,
            last_updated=datetime.now(),
        )
        
        # Recalculate combined score
        self._update_combined_score(symbol)
        
        # Save
        self.save()

    def _update_combined_score(self, symbol: str) -> None:
        """
        Update combined score for a symbol.
        
        Combines backtest and live results with weights.
        
        Args:
            symbol: Trading pair
        """
        perf = self.performance_data.get(symbol)
        if not perf:
            return
        
        # Calculate average backtest metrics (last 7 results)
        recent_backtests = perf.backtest_results[-7:] if perf.backtest_results else []
        
        if not recent_backtests and not perf.live_results:
            perf.combined_score = 0.0
            return
        
        # Weight: 60% backtest, 40% live (if available)
        backtest_score = 0.0
        live_score = 0.0
        
        if recent_backtests:
            avg_win_rate = sum(r["win_rate"] for r in recent_backtests) / len(recent_backtests)
            avg_roi = sum(r["roi"] for r in recent_backtests) / len(recent_backtests)
            avg_sharpe = sum(r["sharpe_ratio"] for r in recent_backtests) / len(recent_backtests)
            
            # Normalize to 0-1 scale
            backtest_score = (
                0.4 * avg_win_rate +  # 40% win rate
                0.3 * min(avg_roi / 20.0, 1.0) +  # 30% ROI (cap at 20%)
                0.3 * min(avg_sharpe / 2.0, 1.0)  # 30% Sharpe (cap at 2.0)
            )
        
        if perf.live_results:
            # Normalize to 0-1 scale
            live_score = (
                0.5 * perf.live_results.win_rate +  # 50% win rate
                0.5 * min(perf.live_results.total_pnl / 100.0, 1.0)  # 50% PnL (cap at $100)
            )
        
        # Combine scores
        if recent_backtests and perf.live_results:
            perf.combined_score = 0.6 * backtest_score + 0.4 * live_score
        elif recent_backtests:
            perf.combined_score = backtest_score
        elif perf.live_results:
            perf.combined_score = live_score
        else:
            perf.combined_score = 0.0

    def get_performance(self, symbol: str) -> SymbolPerformance | None:
        """
        Get performance data for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            SymbolPerformance or None
        """
        return self.performance_data.get(symbol)

    def get_all_performances(self) -> dict[str, SymbolPerformance]:
        """
        Get all performance data.
        
        Returns:
            Dict mapping symbol -> SymbolPerformance
        """
        return self.performance_data.copy()

    def should_filter_symbol(
        self,
        symbol: str,
        min_win_rate: float = 0.50,
        min_roi: float = 0.0,
        min_sharpe: float = 0.5,
        min_profit_factor: float = 1.0,
    ) -> tuple[bool, str]:
        """
        Check if a symbol should be filtered out.
        
        Args:
            symbol: Trading pair
            min_win_rate: Minimum win rate (0-1)
            min_roi: Minimum ROI (%)
            min_sharpe: Minimum Sharpe ratio
            min_profit_factor: Minimum profit factor
            
        Returns:
            (should_filter, reason)
        """
        perf = self.performance_data.get(symbol)
        if not perf:
            return False, "no_data"  # Don't filter if no data
        
        # Check recent backtest results
        recent_backtests = perf.backtest_results[-3:] if perf.backtest_results else []
        
        if not recent_backtests:
            return False, "no_backtest_data"
        
        # Calculate averages
        avg_win_rate = sum(r["win_rate"] for r in recent_backtests) / len(recent_backtests)
        avg_roi = sum(r["roi"] for r in recent_backtests) / len(recent_backtests)
        avg_sharpe = sum(r["sharpe_ratio"] for r in recent_backtests) / len(recent_backtests)
        avg_profit_factor = sum(r["profit_factor"] for r in recent_backtests) / len(recent_backtests)
        
        # Check filters
        if avg_win_rate < min_win_rate:
            return True, f"win_rate_{avg_win_rate:.2%}_below_{min_win_rate:.2%}"
        
        if avg_roi < min_roi:
            return True, f"roi_{avg_roi:.2f}%_below_{min_roi:.2f}%"
        
        if avg_sharpe < min_sharpe:
            return True, f"sharpe_{avg_sharpe:.2f}_below_{min_sharpe:.2f}"
        
        if avg_profit_factor < min_profit_factor:
            return True, f"profit_factor_{avg_profit_factor:.2f}_below_{min_profit_factor:.2f}"
        
        return False, "passed"

