"""Token filtering based on backtesting performance."""

from bitget_trading.logger import get_logger
from bitget_trading.symbol_performance_tracker import SymbolPerformanceTracker

logger = get_logger()


class SymbolFilter:
    """
    Filter tokens based on backtesting and live trading performance.
    
    Filters out tokens that consistently lose in backtesting.
    """

    def __init__(
        self,
        performance_tracker: SymbolPerformanceTracker,
        enabled: bool = True,
        min_win_rate: float = 0.50,
        min_roi: float = 0.0,
        min_sharpe: float = 0.5,
        min_profit_factor: float = 1.0,
    ) -> None:
        """
        Initialize symbol filter.
        
        Args:
            performance_tracker: Performance tracker instance
            enabled: Whether filtering is enabled
            min_win_rate: Minimum win rate (0-1)
            min_roi: Minimum ROI (%)
            min_sharpe: Minimum Sharpe ratio
            min_profit_factor: Minimum profit factor
        """
        self.performance_tracker = performance_tracker
        self.enabled = enabled
        self.min_win_rate = min_win_rate
        self.min_roi = min_roi
        self.min_sharpe = min_sharpe
        self.min_profit_factor = min_profit_factor

    def should_trade_symbol(self, symbol: str) -> tuple[bool, str]:
        """
        Check if a symbol should be traded.
        
        Args:
            symbol: Trading pair
            
        Returns:
            (should_trade, reason)
        """
        if not self.enabled:
            return True, "filtering_disabled"
        
        # Check if symbol should be filtered
        should_filter, reason = self.performance_tracker.should_filter_symbol(
            symbol=symbol,
            min_win_rate=self.min_win_rate,
            min_roi=self.min_roi,
            min_sharpe=self.min_sharpe,
            min_profit_factor=self.min_profit_factor,
        )
        
        if should_filter:
            logger.debug(
                f"🚫 [FILTERED] {symbol} | Reason: {reason} | "
                f"Min win rate: {self.min_win_rate:.2%} | "
                f"Min ROI: {self.min_roi:.2f}% | "
                f"Min Sharpe: {self.min_sharpe:.2f} | "
                f"Min profit factor: {self.min_profit_factor:.2f}"
            )
            return False, reason
        
        return True, "passed"

    def filter_symbols(self, symbols: list[str]) -> list[str]:
        """
        Filter a list of symbols.
        
        Args:
            symbols: List of trading pairs
            
        Returns:
            Filtered list of symbols
        """
        if not self.enabled:
            return symbols
        
        filtered = []
        for symbol in symbols:
            should_trade, reason = self.should_trade_symbol(symbol)
            if should_trade:
                filtered.append(symbol)
            else:
                logger.debug(f"🚫 Filtered {symbol}: {reason}")
        
        logger.info(
            f"🔍 [FILTER] Filtered {len(symbols)} symbols -> {len(filtered)} passed "
            f"({len(symbols) - len(filtered)} filtered out)"
        )
        
        return filtered

