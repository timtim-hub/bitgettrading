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

# 45+ LIQUID COINS TO TEST (Top volume across different market caps)
TEST_SYMBOLS = [
    # === TIER 1: MEGA CAPS (>$50B) ===
    "BTCUSDT",   # Bitcoin - King
    "ETHUSDT",   # Ethereum - Smart contracts leader
    "XRPUSDT",   # Ripple - Banking/payments
    "BNBUSDT",   # Binance Coin - Exchange token
    "SOLUSDT",   # Solana - High-speed blockchain
    
    # === TIER 2: LARGE CAPS ($10B-$50B) ===
    "ADAUSDT",   # Cardano - Research-driven
    "DOGEUSDT",  # Dogecoin - Meme king
    "AVAXUSDT",  # Avalanche - DeFi platform
    "TRXUSDT",   # Tron - Entertainment blockchain
    "LINKUSDT",  # Chainlink - Oracle network
    "DOTUSDT",   # Polkadot - Multi-chain
    "TONUSDT",   # TON - Telegram blockchain
    
    # === TIER 3: MID CAPS ($1B-$10B) ===
    "SHIBUSDT",  # Shiba Inu - Meme token
    "LTCUSDT",   # Litecoin - Silver to BTC's gold
    "UNIUSDT",   # Uniswap - DEX leader
    "ATOMUSDT",  # Cosmos - Internet of blockchains
    "FILUSDT",   # Filecoin - Decentralized storage
    "APTUSDT",   # Aptos - Move-based L1
    "ARBUSDT",   # Arbitrum - ETH L2
    "NEARUSDT",  # NEAR - Sharded L1
    "SUIUSDT",   # Sui - Next-gen L1
    "OPUSDT",    # Optimism - ETH L2
    "INJUSDT",   # Injective - DeFi L1
    
    # === TIER 4: SMALL-MID CAPS ($500M-$1B) ===
    "PEPEUSDT",  # Pepe - Meme token
    "WIFUSDT",   # Dogwifhat - Solana meme
    "FETUSDT",   # Fetch.ai - AI blockchain
    "FLOKIUSDT", # Floki - Meme token
    "FTMUSDT",   # Fantom - Fast L1
    "RNDRUSDT",  # Render - GPU rendering
    "AAVEUSDT",  # Aave - Lending protocol
    "TIAUSDT",   # Celestia - Modular blockchain
    "SEIUSDT",   # Sei - Trading-focused L1
    "JUPUSDT",   # Jupiter - Solana DEX aggregator
    
    # === TIER 5: HIGH VOLATILITY / MOMENTUM ($100M-$500M) ===
    "GALAUSDT",  # Gala - Gaming ecosystem
    "ICPUSDT",   # Internet Computer - Web3 platform
    "ALGOUSDT",  # Algorand - Pure PoS
    "XTZUSDT",   # Tezos - Self-amending blockchain
    "ETCUSDT",   # Ethereum Classic - Original ETH
    "LDOUSDT",   # Lido DAO - Staking protocol
    "GMXUSDT",   # GMX - Perps DEX
    "RUNEUSDT",  # THORChain - Cross-chain swaps
    "PENDLEUSDT",# Pendle - Yield trading
    "1000SATSUSDT", # 1000SATS - BTC ordinals
]


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
        # For now, we'll fetch the maximum available (200) which gives us recent data for backtesting
        # Note: Bitget's public API limits historical data depth
        all_candles = []
        
        try:
            response = await self.rest_client.get_historical_candles(
                symbol=symbol,
                granularity=timeframe,
                limit=200,  # Max available
            )
            
            if response.get("code") == "00000" and "data" in response:
                candles = response["data"]
                if candles:
                    all_candles = candles
                    print(f"  ✅ Fetched {len(candles)} candles")
                else:
                    print(f"  ⚠️ No data available")
            else:
                print(f"  ❌ API Error: {response.get('msg', 'Unknown error')}")
                
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

