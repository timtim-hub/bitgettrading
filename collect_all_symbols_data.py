#!/usr/bin/env python3
"""
Collect real market data for ALL Bitget USDT-M futures.

ULTRA-FAST collection with parallel processing.
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

from src.bitget_trading.logger import setup_logging

logger = setup_logging()


class AllSymbolsDataCollector:
    """Collect real-time data for ALL Bitget futures."""

    BASE_URL = "https://api.bitget.com"

    def __init__(self, duration_minutes: int = 15) -> None:
        """
        Initialize collector.
        
        Args:
            duration_minutes: How long to collect (15 min for quick test)
        """
        self.duration_minutes = duration_minutes
        self.symbols: list[str] = []
        self.data: list[dict] = []
        
        # Create data directory
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)

    async def fetch_all_symbols(self) -> list[str]:
        """Fetch all USDT-M futures symbols."""
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/contracts"
        params = {"productType": "USDT-FUTURES"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return []
                    
                    data = await response.json()
                    
                    if data.get("code") != "00000":
                        return []
                    
                    contracts = data.get("data", [])
                    
                    # Filter active contracts
                    symbols = [
                        c.get("symbol")
                        for c in contracts
                        if c.get("symbolStatus") == "normal" and c.get("symbol")
                    ]
                    
                    return symbols
        
        except Exception as e:
            logger.error("fetch_symbols_error", error=str(e))
            return []

    async def fetch_all_tickers(self, session: aiohttp.ClientSession) -> dict[str, dict]:
        """Fetch ticker data for ALL symbols in one call (FAST - uses existing session)."""
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/tickers"
        params = {"productType": "USDT-FUTURES"}
        
        try:
            async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return {}
                
                data = await response.json()
                
                if data.get("code") != "00000":
                    return {}
                
                tickers = data.get("data", [])
                
                # PARALLEL PROCESSING: Process tickers concurrently
                ticker_map = {}
                for ticker in tickers:
                    symbol = ticker.get("symbol")
                    if not symbol:
                        continue
                    
                    # Handle None values
                    last_price = ticker.get("lastPr") or 0
                    bid_price = ticker.get("bidPr") or 0
                    ask_price = ticker.get("askPr") or 0
                    
                    # Skip invalid data
                    if last_price == 0 or bid_price == 0 or ask_price == 0:
                        continue
                    
                    ticker_map[symbol] = {
                        "last_price": float(last_price),
                        "bid_price": float(bid_price),
                        "ask_price": float(ask_price),
                        "open_price": float(ticker.get("openUtc") or last_price),
                        "high_price": float(ticker.get("high24h") or last_price),
                        "low_price": float(ticker.get("low24h") or last_price),
                        "volume_24h": float(ticker.get("baseVolume") or 0),
                        "quote_volume_24h": float(ticker.get("quoteVolume") or 0),
                        "funding_rate": float(ticker.get("fundingRate") or 0),
                        "open_interest": float(ticker.get("openInterest") or 0),
                    }
                
                return ticker_map
        
        except asyncio.TimeoutError:
            logger.error("fetch_tickers_timeout")
            return {}
        except Exception as e:
            logger.error("fetch_tickers_error", error=str(e))
            return {}

    def process_ticker_data(self, timestamp: datetime, snapshot_num: int, symbol: str, ticker: dict) -> dict:
        """Process a single ticker into data point (FAST - no I/O)."""
        # Calculate features
        spread_pct = 0.0
        if ticker["bid_price"] > 0:
            spread_pct = ((ticker["ask_price"] - ticker["bid_price"]) / ticker["bid_price"]) * 100
        
        return_pct = 0.0
        if ticker["open_price"] > 0:
            return_pct = ((ticker["last_price"] - ticker["open_price"]) / ticker["open_price"]) * 100
        
        volatility_pct = 0.0
        if ticker["low_price"] > 0:
            volatility_pct = ((ticker["high_price"] - ticker["low_price"]) / ticker["low_price"]) * 100
        
        # Return data point
        return {
            "timestamp": timestamp.isoformat(),
            "snapshot": snapshot_num,
            "symbol": symbol,
            "last_price": ticker["last_price"],
            "bid_price": ticker["bid_price"],
            "ask_price": ticker["ask_price"],
            "open_price": ticker["open_price"],
            "high_price": ticker["high_price"],
            "low_price": ticker["low_price"],
            "volume_24h": ticker["volume_24h"],
            "quote_volume_24h": ticker["quote_volume_24h"],
            "funding_rate": ticker["funding_rate"],
            "open_interest": ticker["open_interest"],
            "spread_pct": spread_pct,
            "return_pct": return_pct,
            "volatility_pct": volatility_pct,
        }

    async def collect_snapshot(self, session: aiohttp.ClientSession, snapshot_num: int) -> int:
        """Collect one snapshot of all symbols (ULTRA-FAST with parallel processing)."""
        timestamp = datetime.now()
        
        # Fetch all tickers at once (single API call)
        tickers = await self.fetch_all_tickers(session)
        
        if not tickers:
            logger.warning("No ticker data received")
            return 0
        
        # PARALLEL PROCESSING: Process all tickers concurrently
        tasks = [
            asyncio.create_task(
                asyncio.to_thread(self.process_ticker_data, timestamp, snapshot_num, symbol, ticker)
            )
            for symbol, ticker in tickers.items()
        ]
        
        # Wait for all processing to complete
        data_points = await asyncio.gather(*tasks)
        
        # Add to data list
        self.data.extend(data_points)
        
        return len(data_points)

    async def collect_data(self) -> str:
        """Collect data for specified duration (ULTRA-FAST with persistent session)."""
        logger.info("="*70)
        logger.info("COLLECTING REAL DATA - ALL BITGET FUTURES (PARALLEL MODE)")
        logger.info("="*70)
        
        # Fetch all symbols
        logger.info("Fetching symbol list...")
        self.symbols = await self.fetch_all_symbols()
        
        logger.info(f"✅ Found {len(self.symbols)} USDT-M futures contracts")
        logger.info(f"⏱️  Duration: {self.duration_minutes} minutes")
        logger.info(f"🔄 Collection interval: 60 seconds")
        logger.info(f"🚀 Parallel processing: ENABLED")
        logger.info("="*70 + "\n")
        
        # Use persistent session for all requests (MUCH FASTER)
        import time
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        snapshot_num = 0
        
        # Create persistent session
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            while time.time() < end_time:
                snapshot_start = time.time()
                count = await self.collect_snapshot(session, snapshot_num)
                snapshot_time = time.time() - snapshot_start
                
                snapshot_num += 1
                elapsed = (time.time() - start_time) / 60
                remaining = (end_time - time.time()) / 60
                
                logger.info(
                    f"[Snapshot {snapshot_num}] {count} symbols | "
                    f"⚡ {snapshot_time:.2f}s | "
                    f"{elapsed:.1f}min elapsed | {remaining:.1f}min remaining"
                )
                
                # Wait 60 seconds before next snapshot
                await asyncio.sleep(60)
            
            # Final snapshot
            count = await self.collect_snapshot(session, snapshot_num)
            logger.info(f"[Final snapshot] {count} symbols")
        
        logger.info("\n" + "="*70)
        logger.info("DATA COLLECTION COMPLETE")
        logger.info("="*70)
        logger.info(f"Total snapshots: {snapshot_num + 1}")
        logger.info(f"Total data points: {len(self.data)}")
        logger.info(f"Symbols tracked: {len(self.symbols)}")
        logger.info(f"Total time: {(time.time() - start_time) / 60:.1f} minutes")
        logger.info("="*70)
        
        # Save to CSV
        filename = self.save_data()
        return filename

    def save_data(self) -> str:
        """Save collected data to CSV."""
        if not self.data:
            logger.warning("No data to save")
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.data_dir / f"all_symbols_data_{timestamp}.csv"
        
        # Write CSV
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.data[0].keys())
            writer.writeheader()
            writer.writerows(self.data)
        
        logger.info(f"✅ Data saved to: {filename}")
        logger.info(f"📊 File size: {filename.stat().st_size / 1024:.1f} KB")
        logger.info(f"📈 Data points per symbol: {len(self.data) / len(set(d['symbol'] for d in self.data)):.1f}")
        
        return str(filename)


async def main() -> None:
    """Collect data for all Bitget futures."""
    # FAST collection: 5 snapshots = ~5 minutes
    collector = AllSymbolsDataCollector(duration_minutes=5)
    filename = await collector.collect_data()
    
    if filename:
        logger.info(f"\n✅ Ready for backtest! Run:")
        logger.info(f"   poetry run python real_data_backtest.py {filename}")
        return filename
    return None


if __name__ == "__main__":
    asyncio.run(main())

