"""Backtesting service integration with live trading."""

import asyncio
from typing import Any

from bitget_trading.backtest_scheduler import BacktestScheduler
from bitget_trading.bitget_rest import BitgetRestClient
from bitget_trading.config import TradingConfig
from bitget_trading.enhanced_ranker import EnhancedRanker
from bitget_trading.logger import get_logger
from bitget_trading.multi_symbol_state import MultiSymbolStateManager
from bitget_trading.stats_generator import StatsGenerator
from bitget_trading.symbol_performance_tracker import SymbolPerformanceTracker

logger = get_logger()


class BacktestService:
    """
    Backtesting service for live trading integration.
    
    Manages automated backtesting in the background.
    """

    def __init__(
        self,
        config: TradingConfig,
        rest_client: BitgetRestClient,
        enhanced_ranker: EnhancedRanker,
        state_manager: MultiSymbolStateManager,
        symbols: list[str],
        enabled: bool = True,
        interval_hours: int = 6,
        lookback_days: int = 7,
        min_trades: int = 10,
        parallel_tokens: int = 20,
    ) -> None:
        """
        Initialize backtesting service.
        
        Args:
            config: Trading configuration
            rest_client: Bitget REST API client
            enhanced_ranker: Enhanced ranker for signal generation
            state_manager: Multi-symbol state manager
            symbols: List of symbols to backtest
            enabled: Whether backtesting is enabled
            interval_hours: How often to run backtests (hours)
            lookback_days: How many days of history to use
            min_trades: Minimum trades required for valid backtest
            parallel_tokens: Number of tokens to process in parallel
        """
        self.config = config
        self.rest_client = rest_client
        self.enhanced_ranker = enhanced_ranker
        self.state_manager = state_manager
        self.symbols = symbols
        self.enabled = enabled
        
        # Initialize components
        self.performance_tracker = SymbolPerformanceTracker()
        self.stats_generator = StatsGenerator(self.performance_tracker)
        self.scheduler: BacktestScheduler | None = None
        
        if self.enabled:
            self.scheduler = BacktestScheduler(
                config=config,
                rest_client=rest_client,
                enhanced_ranker=enhanced_ranker,
                state_manager=state_manager,
                performance_tracker=self.performance_tracker,
                stats_generator=self.stats_generator,
                symbols=symbols,
                interval_hours=interval_hours,
                lookback_days=lookback_days,
                min_trades=min_trades,
                parallel_tokens=parallel_tokens,
            )

    async def start(self) -> None:
        """Start the backtesting service."""
        if not self.enabled:
            logger.info("⚠️ [BACKTEST SERVICE] Disabled")
            return
        
        if not self.scheduler:
            logger.error("❌ [BACKTEST SERVICE] Scheduler not initialized")
            return
        
        logger.info("🚀 [BACKTEST SERVICE] Starting...")
        
        # Start scheduler in background
        asyncio.create_task(self.scheduler.start())

    def stop(self) -> None:
        """Stop the backtesting service."""
        if self.scheduler:
            self.scheduler.stop()
            logger.info("🛑 [BACKTEST SERVICE] Stopped")

    async def run_backtest_now(self) -> dict[str, Any]:
        """
        Run backtest immediately (for manual triggering).
        
        Returns:
            Dict with results summary
        """
        if not self.enabled or not self.scheduler:
            logger.warning("⚠️ [BACKTEST SERVICE] Not enabled or not initialized")
            return {"error": "not_enabled"}
        
        return await self.scheduler.run_once()

    def get_performance_tracker(self) -> SymbolPerformanceTracker:
        """Get performance tracker instance."""
        return self.performance_tracker

    def get_stats_generator(self) -> StatsGenerator:
        """Get stats generator instance."""
        return self.stats_generator

