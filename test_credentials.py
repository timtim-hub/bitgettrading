#!/usr/bin/env python3
"""Test Bitget API credentials."""

import asyncio
import os

from dotenv import load_dotenv

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def test_credentials() -> None:
    """Test API credentials."""
    # Load .env
    load_dotenv()

    api_key = os.getenv("BITGET_API_KEY", "")
    secret_key = os.getenv("BITGET_SECRET_KEY", "")
    passphrase = os.getenv("BITGET_PASSPHRASE", "")

    logger.info("=" * 70)
    logger.info("🔑 TESTING BITGET API CREDENTIALS")
    logger.info("=" * 70)
    logger.info(f"API Key: {api_key[:20]}...")
    logger.info(f"Secret:  {secret_key[:20]}...")
    logger.info(f"Pass:    {'*' * len(passphrase)}")
    logger.info("=" * 70 + "\n")

    if not api_key or not secret_key or not passphrase:
        logger.error("❌ Missing credentials in .env file!")
        return

    # Create client (sandbox=False for production API)
    client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)

    # Test 1: Get account balance
    logger.info("Test 1: Fetching account balance...")
    try:
        balance = await client.get_account_balance()
        if balance:
            available = float(balance.get("available", 0))
            equity = float(balance.get("equity", 0))
            frozen = float(balance.get("frozen", 0))

            logger.info("✅ Account balance fetched successfully!")
            logger.info(f"   💰 Available: ${available:.2f} USDT")
            logger.info(f"   📊 Equity:    ${equity:.2f} USDT")
            logger.info(f"   🔒 Frozen:    ${frozen:.2f} USDT")
        else:
            logger.error("❌ Failed to fetch balance - check credentials!")
            return
    except Exception as e:
        logger.error(f"❌ Balance fetch error: {e}")
        return

    # Test 2: Get current positions
    logger.info("\nTest 2: Fetching current positions...")
    try:
        positions = await client.get_positions()
        logger.info(f"✅ Positions fetched: {len(positions)} open positions")

        if positions:
            for pos in positions[:5]:  # Show first 5
                symbol = pos.get("symbol", "?")
                side = pos.get("holdSide", "?")
                size = float(pos.get("total", 0))
                pnl = float(pos.get("unrealizedPL", 0))
                logger.info(f"   📍 {symbol} {side}: {size:.4f} (PnL: ${pnl:.2f})")
    except Exception as e:
        logger.error(f"❌ Positions fetch error: {e}")

    # Test 3: Fetch available symbols
    logger.info("\nTest 3: Fetching available trading symbols...")
    try:
        from src.bitget_trading.universe import UniverseManager

        universe = UniverseManager()
        symbols = await universe.fetch_contracts()
        logger.info(f"✅ Found {len(symbols)} USDT-M futures contracts")

        # Show top 10 by volume
        logger.info("\n📊 Top 10 by 24h volume:")
        tickers = await universe.fetch_tickers()
        sorted_tickers = sorted(
            tickers, key=lambda x: float(x.get("baseVolume", 0)), reverse=True
        )
        for i, ticker in enumerate(sorted_tickers[:10], 1):
            symbol = ticker.get("symbol", "?")
            volume = float(ticker.get("baseVolume", 0))
            price = float(ticker.get("lastPr", 0))
            change = float(ticker.get("change24h", 0)) * 100
            logger.info(
                f"   {i:2d}. {symbol:15s} | ${price:>10.4f} | "
                f"Vol: ${volume:>12,.0f} | {change:>+6.2f}%"
            )

    except Exception as e:
        logger.error(f"❌ Symbols fetch error: {e}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ CREDENTIAL TEST COMPLETE")
    logger.info("=" * 70)
    logger.info("Your API credentials are working correctly!")
    logger.info("You can now start trading.")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_credentials())

