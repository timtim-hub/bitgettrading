"""
FAST SCANNING VERSION: Parallel symbol processing for sub-5s scans
This is a performance-optimized version with parallel processing
"""

# Import the base trader
from institutional_live_trader import InstitutionalLiveTrader, logger
import asyncio
from typing import List
from datetime import datetime


class FastInstitutionalLiveTrader(InstitutionalLiveTrader):
    """Enhanced live trader with parallel scanning for speed"""
    
    async def scan_for_signals_parallel(self, symbols: List[str]):
        """
        FAST PARALLEL version of scan_for_signals
        Processes multiple symbols concurrently for maximum speed
        """
        if self.in_funding_blackout:
            logger.debug("⏸️ In funding blackout - skipping scan")
            return
        
        logger.info(f"🔍 FAST SCAN: {len(symbols)} symbols, {len(self.positions)} open positions")
        
        stats = {'checked': 0, 'gates_failed': 0, 'data_failed': 0, 'no_signal': 0, 'signals_found': 0}
        stats_lock = asyncio.Lock()
        
        # Semaphore to limit concurrent processing
        max_concurrent = self.scheduling_config.get('parallel_scan_workers', 20)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scan_one_symbol(symbol: str):
            """Scan a single symbol (runs in parallel with others)"""
            async with semaphore:
                try:
                    async with stats_lock:
                        stats['checked'] += 1
                    
                    # Check if can open position
                    if not await self.can_open_position(symbol, 'any'):
                        return
                    
                    # Check universe gates (TEMPORARILY DISABLED FOR TESTING)
                    # passes, reason = await self.passes_universe_gates_with_reason(symbol)
                    # if not passes:
                    #     async with stats_lock:
                    #         stats['gates_failed'] += 1
                    #     return
                    
                    # Get data (enough for 15m resampling and EMA200)
                    df_5m = await self.fetch_candles(symbol, timeframe='5m', days=7)  # ~2000 bars
                    if df_5m is None or len(df_5m) < 500:
                        async with stats_lock:
                            stats['data_failed'] += 1
                        return
                    
                    # Calculate indicators
                    df_5m = self.indicators.calculate_all_indicators(df_5m, timeframe='5m')
                    
                    # Get 15m for regime
                    df_15m = df_5m.resample('15min').agg({
                        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                    }).dropna()
                    df_15m = self.indicators.calculate_all_indicators(df_15m, timeframe='15m')
                    
                    # Classify regime
                    bucket = self.universe_filter.get_bucket(symbol)
                    regime_data = self.regime_classifier.classify_from_indicators(df_15m, bucket, -1)
                    
                    # Generate signal
                    signal = None
                    
                    if regime_data.regime == 'Range':
                        # Try LSVR first
                        from institutional_strategies import LSVRStrategy, VWAPMRStrategy
                        lsvr = LSVRStrategy(self.config, bucket)
                        levels = self._get_levels(df_5m)
                        signal = lsvr.generate_signal(df_5m, levels, -1)
                        
                        # Try VWAP-MR if no LSVR
                        if not signal:
                            vwap_mr = VWAPMRStrategy(self.config, bucket)
                            signal = vwap_mr.generate_signal(df_5m, -1)
                    
                    elif regime_data.regime == 'Trend':
                        from institutional_strategies import TrendStrategy
                        trend = TrendStrategy(self.config)
                        signal = trend.generate_signal(df_15m, -1)
                    
                    if not signal:
                        async with stats_lock:
                            stats['no_signal'] += 1
                        return
                    
                    # Found a signal! Continue with entry logic
                    logger.info(f"🎯 SIGNAL CANDIDATE: {symbol} {signal.side.upper()} | {signal.strategy} | {regime_data.regime} regime")
                    
                    # Get account equity
                    equity = await self.get_account_equity()
                    if equity == 0:
                        logger.error("❌ Could not get account equity")
                        return
                    
                    # Calculate position size
                    position_size = self.risk_manager.calculate_position_size(
                        symbol=symbol,
                        side=signal.side,
                        entry_price=signal.entry_price,
                        stop_price=signal.stop_price,
                        equity_usdt=equity,
                        lot_size=0.001,
                        min_qty=0.001
                    )
                    
                    if not position_size.passed_liq_guards:
                        logger.warning(f"⚠️ {symbol}: Signal rejected - liq guards: {position_size.reason}")
                        return
                    
                    # Place entry order (rest of logic from parent class)
                    # Call the parent's entry placement logic
                    # This includes all the TP/SL placement, position tracking, etc.
                    # For now, just log the signal
                    async with stats_lock:
                        stats['signals_found'] += 1
                    logger.info(f"✅ FAST SCAN SIGNAL: {symbol} {signal.side.upper()} | Strategy: {signal.strategy}")
                    
                    # TODO: Call parent's place_entry_order and position management
                    # For now, we'll use the original sequential logic for actual execution
                    # to avoid race conditions with position management
                
                except Exception as e:
                    logger.debug(f"⚠️ Error scanning {symbol}: {e}")
        
        # Launch all scans in parallel
        scan_start = datetime.now()
        await asyncio.gather(*[scan_one_symbol(symbol) for symbol in symbols], return_exceptions=True)
        scan_duration = (datetime.now() - scan_start).total_seconds()
        
        # Summary
        logger.info(
            f"⚡ FAST SCAN complete in {scan_duration:.1f}s: checked={stats['checked']}, "
            f"gates_failed={stats['gates_failed']}, "
            f"data_failed={stats['data_failed']}, "
            f"no_signal={stats['no_signal']}, "
            f"signals_found={stats['signals_found']}"
        )
        
        # For any found signals, execute them sequentially to avoid race conditions
        # (This is where we'd call the original scan_for_signals for specific symbols)


# Simple usage wrapper
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # This module extends the base trader with parallel scanning
    # To use: Import FastInstitutionalLiveTrader instead of InstitutionalLiveTrader
    logger.info("✅ Fast scanning module loaded")
    logger.info("   Use FastInstitutionalLiveTrader.scan_for_signals_parallel() for max speed")

