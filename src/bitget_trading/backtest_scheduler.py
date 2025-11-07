"""Automated backtesting scheduler."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from bitget_trading.bitget_rest import BitgetRestClient
from bitget_trading.config import TradingConfig
from bitget_trading.enhanced_ranker import EnhancedRanker
from bitget_trading.logger import get_logger
from bitget_trading.multi_symbol_state import MultiSymbolStateManager
from bitget_trading.symbol_backtester import SymbolBacktester
from bitget_trading.symbol_performance_tracker import SymbolPerformanceTracker
from bitget_trading.stats_generator import StatsGenerator

logger = get_logger()


class BacktestScheduler:
    """
    Automated backtesting scheduler.
    
    Runs backtests periodically on all tokens.
    Optimized for speed: parallel processing.
    """

    def __init__(
        self,
        config: TradingConfig,
        rest_client: BitgetRestClient,
        enhanced_ranker: EnhancedRanker,
        state_manager: MultiSymbolStateManager,
        performance_tracker: SymbolPerformanceTracker,
        stats_generator: StatsGenerator,
        symbols: list[str],
        interval_hours: int = 6,
        lookback_days: int = 7,
        min_trades: int = 10,
        parallel_tokens: int = 20,
    ) -> None:
        """
        Initialize backtesting scheduler.
        
        Args:
            config: Trading configuration
            rest_client: Bitget REST API client
            enhanced_ranker: Enhanced ranker for signal generation
            state_manager: Multi-symbol state manager
            performance_tracker: Performance tracker
            stats_generator: Stats generator
            symbols: List of symbols to backtest
            interval_hours: How often to run backtests (hours)
            lookback_days: How many days of history to use
            min_trades: Minimum trades required for valid backtest
            parallel_tokens: Number of tokens to process in parallel
        """
        self.config = config
        self.rest_client = rest_client
        self.enhanced_ranker = enhanced_ranker
        self.state_manager = state_manager
        self.performance_tracker = performance_tracker
        self.stats_generator = stats_generator
        self.symbols = symbols
        self.interval_hours = interval_hours
        self.lookback_days = lookback_days
        self.min_trades = min_trades
        self.parallel_tokens = parallel_tokens
        
        # State
        self.running = False
        self.last_backtest: datetime | None = None
        self.backtester = SymbolBacktester(
            config=config,
            rest_client=rest_client,
            enhanced_ranker=enhanced_ranker,
            state_manager=state_manager,
        )

    async def run_backtest(self) -> dict[str, Any]:
        """
        Run backtest on all symbols.
        
        Returns:
            Dict with results summary
        """
        logger.info(
            f"🔄 [BACKTEST] Starting backtest for {len(self.symbols)} symbols | "
            f"Lookback: {self.lookback_days} days | "
            f"Min trades: {self.min_trades}"
        )
        
        start_time = datetime.now()
        results = {
            "total": len(self.symbols),
            "successful": 0,
            "failed": 0,
            "insufficient_trades": 0,
            "duration_sec": 0.0,
        }
        
        # Process symbols in batches
        batch_size = self.parallel_tokens
        batches = [
            self.symbols[i : i + batch_size]
            for i in range(0, len(self.symbols), batch_size)
        ]
        
        for batch_idx, batch in enumerate(batches):
            logger.info(
                f"🔄 [BACKTEST] Processing batch {batch_idx + 1}/{len(batches)}: "
                f"{len(batch)} symbols"
            )
            
            # Process batch in parallel
            tasks = [
                self.backtester.backtest_symbol(
                    symbol=symbol,
                    lookback_days=self.lookback_days,
                    min_trades=self.min_trades,
                )
                for symbol in batch
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for symbol, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ [BACKTEST] {symbol}: Exception: {result}")
                    results["failed"] += 1
                elif result is None:
                    logger.debug(f"⚠️ [BACKTEST] {symbol}: Insufficient trades")
                    results["insufficient_trades"] += 1
                else:
                    # Add result to tracker
                    self.performance_tracker.add_backtest_result(result)
                    results["successful"] += 1
                    logger.debug(
                        f"✅ [BACKTEST] {symbol}: Win Rate {result.win_rate:.1%} | "
                        f"ROI {result.roi:.2f}% | "
                        f"Sharpe {result.sharpe_ratio:.2f} | "
                        f"Trades {result.total_trades}"
                    )
            
            # Small delay between batches to avoid rate limits
            if batch_idx < len(batches) - 1:
                await asyncio.sleep(1)
        
        # Generate stats file
        self.stats_generator.generate_stats()
        
        # Update last backtest time
        self.last_backtest = datetime.now()
        results["duration_sec"] = (self.last_backtest - start_time).total_seconds()
        
        logger.info(
            f"✅ [BACKTEST] Completed in {results['duration_sec']:.1f}s | "
            f"Successful: {results['successful']} | "
            f"Failed: {results['failed']} | "
            f"Insufficient trades: {results['insufficient_trades']}"
        )
        
        return results

    async def start(self) -> None:
        """Start the backtesting scheduler."""
        if self.running:
            logger.warning("⚠️ Backtesting scheduler already running")
            return
        
        self.running = True
        logger.info(
            f"🚀 [BACKTEST SCHEDULER] Started | "
            f"Interval: {self.interval_hours} hours | "
            f"Symbols: {len(self.symbols)}"
        )
        
        # Run initial backtest
        await self.run_backtest()
        
        # Schedule periodic backtests
        while self.running:
            # Wait for next interval
            await asyncio.sleep(self.interval_hours * 3600)
            
            if not self.running:
                break
            
            # Run backtest
            await self.run_backtest()

    def stop(self) -> None:
        """Stop the backtesting scheduler."""
        if not self.running:
            return
        
        self.running = False
        logger.info("🛑 [BACKTEST SCHEDULER] Stopped")

    async def run_once(self) -> dict[str, Any]:
        """
        Run backtest once (for manual triggering).
        
        Returns:
            Dict with results summary
        """
        return await self.run_backtest()

