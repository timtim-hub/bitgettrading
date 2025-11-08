"""
Filter Holy Grail Tokens by 25x Leverage Availability

Filters the 47 profitable tokens to only those with 25x leverage available.
"""

import asyncio
import json
from pathlib import Path
import aiohttp


async def get_max_leverage(symbol: str) -> int:
    """Get maximum leverage for symbol."""
    base_url = "https://api.bitget.com"
    endpoint = f"{base_url}/api/v2/mix/market/contracts"
    params = {"productType": "USDT-FUTURES"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as response:
                if response.status != 200:
                    return 0
                
                data = await response.json()
                if data.get("code") != "00000":
                    return 0
                
                contracts = data.get("data", [])
                for contract in contracts:
                    if contract.get("symbol") == symbol:
                        # Field name is "maxLever" (not "maxLeverage")
                        max_leverage = contract.get("maxLever")
                        try:
                            return int(max_leverage) if max_leverage else 0
                        except (ValueError, TypeError):
                            return 0
                
                return 0
    except Exception as e:
        print(f"⚠️ Error checking {symbol}: {e}")
        return 0

async def check_leverage_availability(symbol: str, target_leverage: int = 25) -> bool:
    """Check if symbol supports target leverage."""
    max_leverage = await get_max_leverage(symbol)
    return max_leverage >= target_leverage


async def filter_holy_grail_tokens():
    """Filter 47 profitable tokens to only those with 25x leverage."""
    
    # Load the 47 profitable tokens from backtest results
    results_file = Path("backtest_results/ML_ADX_Trend_5pct_plus_detailed_20251108_035029.json")
    
    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        return
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    profitable_tokens = [r['symbol'] for r in results]
    
    print("="*80)
    print("FILTERING HOLY GRAIL TOKENS BY 25X LEVERAGE")
    print("="*80)
    print(f"\n📊 Total profitable tokens: {len(profitable_tokens)}")
    print(f"🎯 Target leverage: 25x")
    print()
    
    # Check leverage for each token
    print("🔍 Checking leverage availability...")
    tokens_with_25x = []
    leverage_info = {}
    
    for idx, symbol in enumerate(profitable_tokens, 1):
        if idx % 10 == 0:
            print(f"   Progress: {idx}/{len(profitable_tokens)} tokens checked...")
        
        max_leverage = await get_max_leverage(symbol)
        leverage_info[symbol] = max_leverage
        
        if max_leverage >= 25:
            tokens_with_25x.append(symbol)
            print(f"  ✅ {symbol} (max: {max_leverage}x)")
        else:
            print(f"  ❌ {symbol} (max: {max_leverage}x, need 25x)")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.1)
    
    print()
    print("="*80)
    print(f"✅ FILTERING COMPLETE")
    print("="*80)
    print(f"\n📊 Results:")
    print(f"  - Total profitable tokens: {len(profitable_tokens)}")
    print(f"  - Tokens with 25x leverage: {len(tokens_with_25x)}")
    print(f"  - Tokens without 25x: {len(profitable_tokens) - len(tokens_with_25x)}")
    print()
    
    # Show leverage distribution
    leverage_counts = {}
    for symbol, max_lev in leverage_info.items():
        leverage_counts[max_lev] = leverage_counts.get(max_lev, 0) + 1
    
    print("📊 Leverage Distribution:")
    for lev in sorted(leverage_counts.keys(), reverse=True):
        count = leverage_counts[lev]
        print(f"  - {lev}x: {count} tokens")
    print()
    
    if tokens_with_25x:
        print("🎯 TOKENS TO TRADE (25x leverage available):")
        for i, symbol in enumerate(tokens_with_25x, 1):
            print(f"  {i:2d}. {symbol}")
        
        # Save filtered list
        output_file = Path("holy_grail_tokens_25x.txt")
        with open(output_file, 'w') as f:
            for symbol in tokens_with_25x:
                f.write(f"{symbol}\n")
        
        print(f"\n💾 Saved to: {output_file}")
        
        # Also save as JSON with token details
        token_details = []
        for r in results:
            if r['symbol'] in tokens_with_25x:
                token_details.append(r)
        
        json_file = Path("holy_grail_tokens_25x.json")
        with open(json_file, 'w') as f:
            json.dump(token_details, f, indent=2)
        
        print(f"💾 Token details saved to: {json_file}")
    else:
        print("❌ No tokens found with 25x leverage!")
    
    print()


if __name__ == "__main__":
    asyncio.run(filter_holy_grail_tokens())

