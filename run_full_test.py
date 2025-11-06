#!/usr/bin/env python3
"""
Complete workflow: Collect real data + backtest.
"""

import asyncio
import subprocess
import sys

from collect_all_symbols_data import AllSymbolsDataCollector
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def main() -> None:
    """Run full workflow."""
    logger.info("\n" + "="*70)
    logger.info("FULL WORKFLOW: REAL DATA COLLECTION + BACKTEST")
    logger.info("="*70)
    logger.info("Step 1: Collect real market data (5 minutes - ULTRA-FAST)")
    logger.info("Step 2: Backtest on collected data")
    logger.info("🚀 Parallel processing enabled for maximum speed")
    logger.info("="*70 + "\n")
    
    # Step 1: Collect data (FAST - 5 minutes)
    logger.info("🔄 Starting data collection...")
    collector = AllSymbolsDataCollector(duration_minutes=5)
    filename = await collector.collect_data()
    
    if not filename:
        logger.error("❌ Data collection failed!")
        sys.exit(1)
    
    # Step 2: Run backtest
    logger.info(f"\n🔄 Running backtest on: {filename}")
    subprocess.run([
        sys.executable,
        "real_data_backtest.py",
        filename
    ])


if __name__ == "__main__":
    asyncio.run(main())

