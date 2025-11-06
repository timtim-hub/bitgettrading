#!/usr/bin/env python3
"""
Collect live market data from Bitget for backtesting.

Collects:
- Ticker data (price, volume, funding)
- Order book depth
- Price movements over time
"""

import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path

import aiohttp

from src.bitget_trading.logger import setup_logging

logger = setup_logging()


class LiveDataCollector:
    """Collect real-time market data from Bitget."""

    BASE_URL = "https://api.bitget.com"

    def __init__(self, symbols: list[str], duration_minutes: int = 60) -> None:
        """
        Initialize data collector.
        
        Args:
            symbols: List of symbols to track
            duration_minutes: How long to collect data
        """
        self.symbols = symbols
        self.duration_minutes = duration_minutes
        self.data: list[dict] = []
        
        # Create data directory
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)

    async def fetch_ticker(self, symbol: str) -> dict | None:
        """Fetch current ticker data for a symbol."""
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/ticker"
        params = {"productType": "USDT-FUTURES", "symbol": symbol}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    if data.get("code") != "00000":
                        return None
                    
                    ticker_list = data.get("data", [])
                    if not ticker_list:
                        return None
                    
                    ticker = ticker_list[0]
                    
                    # Parse safely
                    last_price = ticker.get("lastPr")
                    bid_price = ticker.get("bidPr")
                    ask_price = ticker.get("askPr")
                    
                    if not last_price or not bid_price or not ask_price:
                        return None
                    
                    return {
                        "symbol": symbol,
                        "last_price": float(last_price),
                        "bid_price": float(bid_price),
                        "ask_price": float(ask_price),
                        "volume_24h": float(ticker.get("baseVolume") or 0),
                        "open_price": float(ticker.get("openUtc") or last_price),
                        "high_price": float(ticker.get("high24h") or last_price),
                        "low_price": float(ticker.get("low24h") or last_price),
                        "funding_rate": float(ticker.get("fundingRate") or 0),
                    }
        
        except Exception as e:
            logger.error("fetch_ticker_error", symbol=symbol, error=str(e))
            return None

    async def fetch_orderbook(self, symbol: str) -> dict | None:
        """Fetch order book for a symbol."""
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/merge-depth"
        params = {
            "productType": "USDT-FUTURES",
            "symbol": symbol,
            "limit": "5",  # Top 5 levels
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    if data.get("code") != "00000":
                        return None
                    
                    book = data.get("data", {})
                    
                    return {
                        "bids": book.get("bids", []),
                        "asks": book.get("asks", []),
                    }
        
        except Exception as e:
            logger.error("fetch_orderbook_error", symbol=symbol, error=str(e))
            return None

    async def collect_snapshot(self) -> None:
        """Collect one snapshot of all symbols."""
        timestamp = datetime.now()
        
        for symbol in self.symbols:
            # Fetch ticker
            ticker = await self.fetch_ticker(symbol)
            if not ticker:
                continue
            
            # Fetch order book
            orderbook = await self.fetch_orderbook(symbol)
            
            # Calculate spread
            spread_pct = 0.0
            if ticker["bid_price"] > 0:
                spread_pct = ((ticker["ask_price"] - ticker["bid_price"]) / ticker["bid_price"]) * 100
            
            # Calculate return since open
            return_pct = 0.0
            if ticker["open_price"] > 0:
                return_pct = ((ticker["last_price"] - ticker["open_price"]) / ticker["open_price"]) * 100
            
            # Calculate order book imbalance
            ob_imbalance = 0.0
            if orderbook:
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                
                if bids and asks:
                    bid_volume = sum(float(b[1]) for b in bids[:3])
                    ask_volume = sum(float(a[1]) for a in asks[:3])
                    total_volume = bid_volume + ask_volume
                    
                    if total_volume > 0:
                        ob_imbalance = (bid_volume - ask_volume) / total_volume
            
            # Store data point
            data_point = {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol,
                "last_price": ticker["last_price"],
                "bid_price": ticker["bid_price"],
                "ask_price": ticker["ask_price"],
                "open_price": ticker["open_price"],
                "high_price": ticker["high_price"],
                "low_price": ticker["low_price"],
                "volume_24h": ticker["volume_24h"],
                "funding_rate": ticker["funding_rate"],
                "spread_pct": spread_pct,
                "return_pct": return_pct,
                "ob_imbalance": ob_imbalance,
            }
            
            self.data.append(data_point)
        
        logger.info(
            "snapshot_collected",
            symbols=len(self.symbols),
            total_points=len(self.data),
        )

    async def collect_data(self) -> None:
        """Collect data for specified duration."""
        logger.info("="*70)
        logger.info(f"COLLECTING LIVE DATA FROM BITGET")
        logger.info("="*70)
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info(f"Duration: {self.duration_minutes} minutes")
        logger.info(f"Collection interval: 60 seconds")
        logger.info("="*70 + "\n")
        
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        snapshot_count = 0
        
        while time.time() < end_time:
            await self.collect_snapshot()
            snapshot_count += 1
            
            elapsed = (time.time() - start_time) / 60
            remaining = (end_time - time.time()) / 60
            
            logger.info(
                f"Progress: {elapsed:.1f}min elapsed | {remaining:.1f}min remaining | "
                f"{snapshot_count} snapshots | {len(self.data)} data points"
            )
            
            # Wait 60 seconds before next snapshot
            await asyncio.sleep(60)
        
        # Final snapshot
        await self.collect_snapshot()
        
        logger.info("\n" + "="*70)
        logger.info("DATA COLLECTION COMPLETE")
        logger.info("="*70)
        logger.info(f"Total snapshots: {snapshot_count + 1}")
        logger.info(f"Total data points: {len(self.data)}")
        logger.info("="*70)
        
        # Save to CSV
        self.save_data()

    def save_data(self) -> None:
        """Save collected data to CSV."""
        if not self.data:
            logger.warning("No data to save")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.data_dir / f"live_data_{timestamp}.csv"
        
        # Write CSV
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.data[0].keys())
            writer.writeheader()
            writer.writerows(self.data)
        
        logger.info(f"Data saved to: {filename}")
        logger.info(f"File size: {filename.stat().st_size / 1024:.1f} KB")
        
        # Return filename for backtest
        return str(filename)


async def main() -> None:
    """Collect live data from Bitget."""
    # Top liquid symbols for 1-minute scalping
    symbols = [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "MATICUSDT",
    ]
    
    collector = LiveDataCollector(
        symbols=symbols,
        duration_minutes=60,  # Collect for 1 hour
    )
    
    await collector.collect_data()


if __name__ == "__main__":
    asyncio.run(main())

