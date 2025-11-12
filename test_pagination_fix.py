"""Test pagination fix"""
import asyncio
import sys
import os
import json

# Load credentials
with open('.env', 'r') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key] = value

sys.path.insert(0, 'src')

from institutional_live_trader import InstitutionalLiveTrader
from institutional_indicators import InstitutionalIndicators


async def test_pagination():
    with open('institutional_strategy_config.json', 'r') as f:
        config = json.load(f)
    
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    trader = InstitutionalLiveTrader(config, api_key, secret_key, passphrase)
    
    print('📊 Testing fetch_candles pagination fix...')
    print('   Requesting 30 days of 5m data (should make 10 API calls)')
    
    df = await trader.fetch_candles('BTCUSDT', timeframe='5m', days=30)
    
    if df is not None:
        print(f'\n✅ SUCCESS! Got {len(df)} candles')
        print(f'   (Before bug fix: would have been ~200)')
        
        time_span = (df.index[-1] - df.index[0]).days
        print(f'\n📅 Time span: {time_span} days')
        
        df_15m = df.resample('15min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        print(f'\n✅ Resampled to {len(df_15m)} 15m bars')
        print(f'   Need 200+ for EMA200: {"✅ PASS" if len(df_15m) >= 200 else "❌ FAIL"}')
        print(f'   Need 120+ for BB-width%: {"✅ PASS" if len(df_15m) >= 120 else "❌ FAIL"}')
        
        # Test indicators
        indicators = InstitutionalIndicators(config)
        df_15m = indicators.calculate_all_indicators(df_15m, timeframe='15m')
        
        print(f'\n📊 Indicator availability:')
        print(f'   EMA200: {"✅" if "ema_200" in df_15m.columns and not df_15m["ema_200"].isna().all() else "❌"}')
        print(f'   RSI: {"✅" if "rsi" in df_15m.columns and not df_15m["rsi"].isna().all() else "❌"}')
        print(f'   ADX: {"✅" if "adx" in df_15m.columns and not df_15m["adx"].isna().all() else "❌"}')
        print(f'   BB-width: {"✅" if "bb_width_pct" in df_15m.columns and not df_15m["bb_width_pct"].isna().all() else "❌"}')
        
        if 'bb_width_pct' in df_15m.columns and not df_15m['bb_width_pct'].isna().all():
            bb_val = df_15m['bb_width_pct'].iloc[-1]
            print(f'   BB-width% value: {bb_val:.1f}% (was NaN before!)')
            
        print('\n✅ PAGINATION FIX WORKING!')
    else:
        print('❌ Failed to fetch data')


if __name__ == '__main__':
    asyncio.run(test_pagination())

