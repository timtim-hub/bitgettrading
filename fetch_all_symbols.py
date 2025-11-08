"""
Fetch ALL tradable symbols from Bitget (like the live trading bot does)
"""

import asyncio
import aiohttp
from typing import List


async def fetch_all_bitget_symbols() -> List[str]:
    """Fetch all USDT-M futures symbols from Bitget API."""
    base_url = "https://api.bitget.com"
    endpoint = f"{base_url}/api/v2/mix/market/contracts"
    params = {"productType": "USDT-FUTURES"}
    
    print("🌐 Fetching ALL symbols from Bitget...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as response:
                if response.status != 200:
                    print(f"❌ Failed: HTTP {response.status}")
                    return []
                
                data = await response.json()
                
                if data.get("code") != "00000":
                    print(f"❌ API Error: {data.get('msg')}")
                    return []
                
                contracts = data.get("data", [])
                
                # Filter to active contracts only
                symbols = [
                    contract.get("symbol")
                    for contract in contracts
                    if contract.get("symbolStatus") == "normal" and contract.get("symbol")
                ]
                
                print(f"✅ Found {len(symbols)} active symbols")
                return symbols
                
    except Exception as e:
        print(f"❌ Exception: {e}")
        return []


async def fetch_and_filter_by_volume(min_volume_usd: float = 1_000_000) -> List[str]:
    """Fetch symbols and filter by 24h volume (like live bot)."""
    
    # Get all symbols
    all_symbols = await fetch_all_bitget_symbols()
    if not all_symbols:
        return []
    
    # Fetch ticker data to get volumes
    base_url = "https://api.bitget.com"
    endpoint = f"{base_url}/api/v2/mix/market/tickers"
    params = {"productType": "USDT-FUTURES"}
    
    print(f"\n📊 Filtering by volume (min ${min_volume_usd:,.0f} daily)...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as response:
                if response.status != 200:
                    print(f"⚠️ Could not fetch volumes, using all {len(all_symbols)} symbols")
                    return all_symbols
                
                data = await response.json()
                
                if data.get("code") != "00000":
                    print(f"⚠️ Could not fetch volumes, using all {len(all_symbols)} symbols")
                    return all_symbols
                
                tickers = data.get("data", [])
                
                # Create volume map
                volume_map = {}
                for ticker in tickers:
                    symbol = ticker.get("symbol")
                    quote_volume = ticker.get("quoteVolume") or 0
                    if symbol:
                        volume_map[symbol] = float(quote_volume)
                
                # Filter by volume
                filtered = [
                    symbol for symbol in all_symbols
                    if volume_map.get(symbol, 0) >= min_volume_usd
                ]
                
                # Sort by volume (highest first)
                filtered.sort(key=lambda s: volume_map.get(s, 0), reverse=True)
                
                print(f"✅ Filtered to {len(filtered)} liquid symbols (>$1M volume)")
                print(f"\nTop 10 by volume:")
                for i, symbol in enumerate(filtered[:10], 1):
                    vol = volume_map.get(symbol, 0)
                    print(f"  {i:2d}. {symbol:15s} ${vol:>15,.0f}")
                
                return filtered
                
    except Exception as e:
        print(f"⚠️ Exception: {e}, using all {len(all_symbols)} symbols")
        return all_symbols


async def main():
    """Fetch and save all symbols."""
    symbols = await fetch_and_filter_by_volume(min_volume_usd=1_000_000)
    
    if symbols:
        # Save to file
        with open("all_bitget_symbols.txt", "w") as f:
            for symbol in symbols:
                f.write(f"{symbol}\n")
        
        print(f"\n✅ Saved {len(symbols)} symbols to all_bitget_symbols.txt")
        print(f"\nThese are the symbols your live bot trades:")
        print(", ".join(symbols[:20]) + f"... (+{len(symbols)-20} more)")
    else:
        print("\n❌ No symbols fetched")


if __name__ == "__main__":
    asyncio.run(main())

