import sys
import asyncio
sys.path.insert(0, 'src')

from bitget_trading.bitget_rest import BitgetRestClient
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = BitgetRestClient(
        api_key=os.getenv('BITGET_API_KEY'),
        api_secret=os.getenv('BITGET_SECRET_KEY'),
        passphrase=os.getenv('BITGET_PASSPHRASE'),
        sandbox=False
    )
    
    print("🔍 Checking open positions and orders...\n")
    
    # Get positions
    try:
        positions_response = await client.get_positions()
        if positions_response.get('code') == '00000':
            positions = positions_response.get('data', [])
            print(f"📊 OPEN POSITIONS: {len(positions)}")
            for pos in positions:
                symbol = pos.get('symbol')
                side = pos.get('holdSide')
                size = pos.get('total')
                print(f"  • {symbol} {side.upper()}: {size} contracts")
        else:
            print(f"❌ Failed to get positions: {positions_response}")
    except Exception as e:
        print(f"❌ Error getting positions: {e}")
    
    print()
    
    # Get pending plan orders (TP/SL)
    try:
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'UNIUSDT']
        for symbol in symbols:
            response = await client._request(
                'GET',
                '/api/v2/mix/order/orders-plan-pending',
                params={
                    'symbol': symbol,
                    'productType': 'usdt-futures'
                }
            )
            if response.get('code') == '00000':
                orders = response.get('data', {}).get('entrustedList', [])
                if orders:
                    print(f"📋 {symbol} - {len(orders)} pending orders:")
                    for order in orders:
                        plan_type = order.get('planType')
                        trigger_price = order.get('triggerPrice')
                        size = order.get('size', 'N/A')
                        order_id = order.get('orderId')
                        print(f"  • {plan_type}: Trigger=${trigger_price}, Size={size}, ID={order_id}")
    except Exception as e:
        print(f"❌ Error getting pending orders: {e}")

if __name__ == "__main__":
    asyncio.run(main())
