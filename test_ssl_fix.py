"""Test SSL fix with direct API call"""
import sys
import asyncio

sys.path.insert(0, 'src')

from bitget_trading.bitget_rest import BitgetRestClient

async def test():
    print("🔧 Testing Bitget REST client with SSL fix...")
    
    # Create client with dummy credentials
    client = BitgetRestClient(
        api_key="test",
        api_secret="test",
        passphrase="test",
        sandbox=False
    )
    
    print("✅ Client created successfully")
    
    # Test fetching candles (public endpoint)
    try:
        result = await client.get_historical_candles(
            symbol="BTCUSDT",
            granularity="5m",
            limit=5
        )
        
        if result.get('code') == '00000':
            candles = result.get('data', [])
            print(f"✅ SUCCESS! Fetched {len(candles)} candles")
            print(f"   First candle: {candles[0] if candles else 'None'}")
            return True
        else:
            print(f"❌ API Error: {result.get('msg')}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)

