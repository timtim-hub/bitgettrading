#!/usr/bin/env python3
"""Diagnose Bitget API connection issues."""

import asyncio
import os

from dotenv import load_dotenv

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def test_both_environments() -> None:
    """Test both demo and production environments."""
    load_dotenv()

    api_key = os.getenv("BITGET_API_KEY", "")
    secret_key = os.getenv("BITGET_SECRET_KEY", "")
    passphrase = os.getenv("BITGET_PASSPHRASE", "")

    logger.info("=" * 70)
    logger.info("🔍 BITGET API DIAGNOSTIC TOOL")
    logger.info("=" * 70)
    logger.info(f"API Key: {api_key}")
    logger.info(f"Secret:  {secret_key[:20]}...{secret_key[-10:]}")
    logger.info(f"Pass:    {passphrase}")
    logger.info("=" * 70 + "\n")

    # Test 1: Production API
    logger.info("Test 1: PRODUCTION API (api.bitget.com)")
    logger.info("-" * 70)
    try:
        client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
        balance = await client.get_account_balance()

        if balance:
            logger.info("✅ PRODUCTION API: SUCCESS!")
            logger.info(f"   💰 Available: ${float(balance.get('available', 0)):.2f} USDT")
            logger.info(f"   📊 Equity:    ${float(balance.get('equity', 0)):.2f} USDT")
        else:
            logger.error("❌ PRODUCTION API: Failed (no data returned)")
    except Exception as e:
        logger.error(f"❌ PRODUCTION API: Failed - {e}")

    logger.info("")

    # Test 2: Demo API
    logger.info("Test 2: DEMO API (demo.bitget.com)")
    logger.info("-" * 70)
    try:
        client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=True)
        balance = await client.get_account_balance()

        if balance:
            logger.info("✅ DEMO API: SUCCESS!")
            logger.info(f"   💰 Available: ${float(balance.get('available', 0)):.2f} USDT")
            logger.info(f"   📊 Equity:    ${float(balance.get('equity', 0)):.2f} USDT")
        else:
            logger.error("❌ DEMO API: Failed (no data returned)")
    except Exception as e:
        logger.error(f"❌ DEMO API: Failed - {e}")

    logger.info("\n" + "=" * 70)
    logger.info("DIAGNOSIS COMPLETE")
    logger.info("=" * 70)
    logger.info("If both failed, please verify:")
    logger.info("1. API Key is correct")
    logger.info("2. Secret Key is correct")
    logger.info("3. Passphrase is correct (case-sensitive!)")
    logger.info("4. API has 'Read' and 'Trade (Futures)' permissions")
    logger.info("5. No IP restrictions or your IP is whitelisted")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_both_environments())

