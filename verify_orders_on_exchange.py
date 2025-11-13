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
    
    print("🔍 Checking open positions on Bitget Exchange...\n")
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'UNIUSDT']
    
    for symbol in symbols:
        try:
            # Get positions for this symbol
            pos_response = await client.get_positions(symbol=symbol)
            if pos_response.get('code') == '00000':
                positions = pos_response.get('data', [])
                if positions:
                    for pos in positions:
                        total = float(pos.get('total', 0))
                        if total > 0:
                            side = pos.get('holdSide')
                            available = pos.get('available')
                            locked = pos.get('locked')
                            unrealized_pnl = pos.get('unrealizedPL')
                            leverage = pos.get('leverage')
                            
                            print(f"✅ {symbol} {side.upper()} Position:")
                            print(f"   Size: {total} contracts")
                            print(f"   Available: {available} | Locked: {locked}")
                            print(f"   Unrealized P&L: ${unrealized_pnl}")
                            print(f"   Leverage: {leverage}x")
                            print()
        except Exception as e:
            print(f"⚠️  {symbol}: {e}")
    
    print("\n" + "="*60)
    print("🎯 Checking TP/SL Orders...")
    print("="*60 + "\n")
    
    for symbol in symbols:
        try:
            # Correct endpoint and parameters for V2 API
            response = await client._request(
                'GET',
                '/api/v2/mix/order/orders-plan-pending',
                params={
                    'productType': 'USDT-FUTURES',  # Try uppercase
                    'symbol': symbol
                }
            )
            if response.get('code') == '00000':
                data = response.get('data', {})
                orders = data.get('entrustedList', [])
                if orders:
                    print(f"📋 {symbol} - {len(orders)} pending plan orders:")
                    for order in orders:
                        plan_type = order.get('planType')
                        trigger_price = order.get('triggerPrice')
                        size = order.get('size', '0')
                        order_id = order.get('orderId')
                        status = order.get('status')
                        
                        type_emoji = "🛑" if plan_type == "pos_loss" else "🎯" if plan_type == "profit_plan" else "📈"
                        type_name = "STOP-LOSS" if plan_type == "pos_loss" else "TAKE-PROFIT" if plan_type == "profit_plan" else plan_type
                        
                        print(f"   {type_emoji} {type_name}")
                        print(f"      Trigger: ${trigger_price} | Size: {size} | Status: {status}")
                        print(f"      Order ID: {order_id}")
                        print()
                else:
                    print(f"  {symbol}: No pending orders\n")
            else:
                print(f"  {symbol}: API Error - {response.get('msg')}\n")
        except Exception as e:
            print(f"  {symbol}: Error - {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
