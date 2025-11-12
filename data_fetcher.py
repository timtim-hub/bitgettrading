"""
Historical Data Fetcher for Backtesting
Fetches real OHLCV data from Bitget API with caching and rate limit handling.
"""

import asyncio
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.config import TradingConfig

# Load ALL 338 symbols from the full Bitget universe
try:
    with open("all_bitget_symbols.txt", "r") as f:
        TEST_SYMBOLS = [line.strip() for line in f if line.strip()]
    print(f"✅ Loaded {len(TEST_SYMBOLS)} symbols from all_bitget_symbols.txt")
except FileNotFoundError:
    print("❌ all_bitget_symbols.txt not found! Using minimal fallback...")
    TEST_SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # Fallback


class HistoricalDataFetcher:
    """Fetch and cache historical OHLCV data from Bitget."""
    
    def __init__(self, cache_dir: str = "backtest_data"):
        """Initialize the data fetcher."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.config = TradingConfig()
        self.rest_client = BitgetRestClient(
            api_key=self.config.bitget_api_key,
            api_secret=self.config.bitget_api_secret,
            passphrase=self.config.bitget_passphrase,
            sandbox=False,  # Use real API for historical data
        )
    
    def _get_cache_path(self, symbol: str, timeframe: str, days: int) -> Path:
        """Get cache file path for a symbol/timeframe/duration."""
        return self.cache_dir / f"{symbol}_{timeframe}_{days}d.pkl"
    
    def _is_cache_valid(self, cache_path: Path, max_age_hours: int = 24) -> bool:
        """Check if cached data is still valid."""
        if not cache_path.exists():
            return False
        
        cache_age = time.time() - cache_path.stat().st_mtime
        return cache_age < max_age_hours * 3600
    
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        days: int = 30,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch historical candles for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            timeframe: Candle timeframe ("1m", "5m", "15m", "1H", "4H", "1D")
            days: Number of days of history to fetch
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        cache_path = self._get_cache_path(symbol, timeframe, days)
        
        # Try to load from cache
        if use_cache and self._is_cache_valid(cache_path):
            print(f"📦 Loading {symbol} {timeframe} from cache...")
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        
        print(f"🌐 Fetching {symbol} {timeframe} from Bitget API ({days} days requested)...")
        
        # Bitget API returns max 200 candles per request
        # For 30 days, we need to make multiple requests
        # Calculate how many requests needed
        all_candles = []
        
        # Calculate candles needed for requested days
        if timeframe == "1m":
            candles_per_day = 1440  # 24 * 60
        elif timeframe == "5m":
            candles_per_day = 288  # 24 * 12
        elif timeframe == "15m":
            candles_per_day = 96  # 24 * 4
        elif timeframe == "1H":
            candles_per_day = 24
        elif timeframe == "4H":
            candles_per_day = 6
        elif timeframe == "1D":
            candles_per_day = 1
        else:
            candles_per_day = 24  # Default to 1H
        
        total_candles_needed = days * candles_per_day
        requests_needed = (total_candles_needed + 199) // 200  # Round up
        
        print(f"  📊 Need {total_candles_needed} candles ({days} days), making {requests_needed} requests...")
        
        try:
            # Make multiple requests to get enough historical data
            for i in range(requests_needed):
                # Calculate end time for this request (most recent first)
                # Each request gets 200 candles, going backwards in time
                response = await self.rest_client.get_historical_candles(
                    symbol=symbol,
                    granularity=timeframe,
                    limit=200,  # Max available per request
                )
                
                if response.get("code") == "00000" and "data" in response:
                    candles = response["data"]
                    if candles:
                        # Add new candles (avoid duplicates)
                        existing_timestamps = {c[0] for c in all_candles}
                        new_candles = [c for c in candles if c[0] not in existing_timestamps]
                        all_candles.extend(new_candles)
                        print(f"  ✅ Request {i+1}/{requests_needed}: Fetched {len(new_candles)} new candles (total: {len(all_candles)})")
                        
                        # If we got fewer than 200, we've reached the end of available data
                        if len(candles) < 200:
                            print(f"  ℹ️ Reached end of available historical data")
                            break
                    else:
                        print(f"  ⚠️ No data in response {i+1}")
                        break
                else:
                    print(f"  ❌ API Error in request {i+1}: {response.get('msg', 'Unknown error')}")
                    break
                
                # Small delay between requests to avoid rate limiting
                if i < requests_needed - 1:
                    await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"  ❌ Exception: {e}")
        
        if all_candles:
            print(f"✅ Total: {len(all_candles)} candles for {symbol}")
        
        # Convert to DataFrame
        if not all_candles:
            print(f"❌ No data fetched for {symbol}")
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {
                "timestamp": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in all_candles
        ])
        
        # Sort by timestamp and remove duplicates
        df = df.sort_values("timestamp").drop_duplicates(subset="timestamp")
        df = df.reset_index(drop=True)
        
        # Cache the data
        with open(cache_path, 'wb') as f:
            pickle.dump(df, f)
        print(f"💾 Cached data to {cache_path}")
        
        return df
    
    async def fetch_all_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1m",
        days: int = 30,
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical data for all symbols.
        
        Returns:
            Dictionary mapping symbol -> DataFrame
        """
        print(f"\n{'='*80}")
        print(f"FETCHING HISTORICAL DATA")
        print(f"{'='*80}")
        print(f"Symbols: {len(symbols)}")
        print(f"Timeframe: {timeframe}")
        print(f"Days: {days}")
        print(f"Use cache: {use_cache}")
        print(f"{'='*80}\n")
        
        data = {}
        
        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
            df = await self.fetch_candles(symbol, timeframe, days, use_cache)
            
            if not df.empty:
                data[symbol] = df
                print(f"  ✅ {symbol}: {len(df)} candles ({df['timestamp'].min()} to {df['timestamp'].max()})")
            else:
                print(f"  ❌ {symbol}: No data")
        
        print(f"\n{'='*80}")
        print(f"✅ Data fetch complete: {len(data)}/{len(symbols)} symbols")
        print(f"{'='*80}\n")
        
        return data
    
    def get_data_summary(self, data: Dict[str, pd.DataFrame]) -> Dict[str, any]:
        """Get summary statistics for fetched data."""
        if not data:
            return {}
        
        summary = {
            "num_symbols": len(data),
            "symbols": list(data.keys()),
            "candles_per_symbol": {sym: len(df) for sym, df in data.items()},
            "total_candles": sum(len(df) for df in data.values()),
            "date_range": {},
        }
        
        for symbol, df in data.items():
            if not df.empty:
                summary["date_range"][symbol] = {
                    "start": datetime.fromtimestamp(df['timestamp'].min() / 1000).isoformat(),
                    "end": datetime.fromtimestamp(df['timestamp'].max() / 1000).isoformat(),
                    "days": (df['timestamp'].max() - df['timestamp'].min()) / (1000 * 86400),
                }
        
        return summary


async def main():
    """Test the data fetcher."""
    fetcher = HistoricalDataFetcher()
    
    # Fetch historical data for all test symbols
    # Using 1H timeframe: 200 candles = 200 hours (~8.3 days) of data
    # This gives us enough data for meaningful backtesting while respecting API limits
    data = await fetcher.fetch_all_symbols(
        symbols=TEST_SYMBOLS,
        timeframe="1H",  # 1 hour candles for good data coverage
        days=30,  # Will get max available (200 candles = ~8 days)
        use_cache=True  # Set to False to force refresh
    )
    
    # Print summary
    summary = fetcher.get_data_summary(data)
    print("\n" + "="*80)
    print("DATA SUMMARY")
    print("="*80)
    print(f"Total symbols: {summary['num_symbols']}")
    print(f"Total candles: {summary['total_candles']:,}")
    print("\nCandles per symbol:")
    for sym, count in summary['candles_per_symbol'].items():
        print(f"  {sym}: {count:,} candles")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

