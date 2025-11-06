#!/usr/bin/env python3
"""Test new API credentials."""

import asyncio

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def main() -> None:
    """Test new credentials."""
    api_key = "bg_e377adcce19a1c440ebb07ff0f557748"
    secret_key = "af212f98f6f11eb31a2ccbcafdffdccf06b4b95c3c969d1e286b1383765b6a9d"
    passphrase = "meinbitget"

    logger.info("=" * 70)
    logger.info("🔑 TESTING NEW API CREDENTIALS")
    logger.info("=" * 70)
    logger.info(f"API Key: {api_key}")
    logger.info(f"Secret:  {secret_key[:20]}...{secret_key[-10:]}")
    logger.info(f"Pass:    {passphrase}")
    logger.info("=" * 70 + "\n")

    # Test Production API
    logger.info("Testing PRODUCTION API (api.bitget.com)...")
    logger.info("-" * 70)
    try:
        client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
        balance = await client.get_account_balance()

        if balance:
            available = float(balance.get("available", 0))
            equity = float(balance.get("equity", 0))
            frozen = float(balance.get("frozen", 0))

            logger.info("✅ ✅ ✅ AUTHENTICATION SUCCESSFUL! ✅ ✅ ✅")
            logger.info("")
            logger.info(f"💰 Available Balance: ${available:.2f} USDT")
            logger.info(f"📊 Total Equity:      ${equity:.2f} USDT")
            logger.info(f"🔒 Frozen:            ${frozen:.2f} USDT")
            logger.info("")

            # Account info is enough for verification
            logger.info("Account verification complete!")

            logger.info("\n" + "=" * 70)
            logger.info("✅ API CREDENTIALS VERIFIED AND WORKING!")
            logger.info("=" * 70)
            logger.info("Saving to .env file...")

            # Save to .env
            with open(".env", "w") as f:
                f.write(f"""# Bitget API Credentials
BITGET_API_KEY={api_key}
BITGET_SECRET_KEY={secret_key}
BITGET_PASSPHRASE={passphrase}

# Trading Mode (paper = simulation, live = real money)
TRADING_MODE=paper
SANDBOX=false

# Risk Management
INITIAL_CAPITAL=50.0
LEVERAGE=50
POSITION_SIZE_PCT=0.10
MAX_POSITIONS=10
DAILY_LOSS_LIMIT=0.15
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.05

# Strategy
SIGNAL_LONG_THRESHOLD=0.65
SIGNAL_SHORT_THRESHOLD=0.65

# Logging
LOG_LEVEL=INFO
""")

            logger.info("✅ Credentials saved to .env")
            logger.info("")
            logger.info("🚀 READY TO START TRADING!")
            logger.info("=" * 70)
            return True

        else:
            logger.error("❌ Failed to fetch balance - no data returned")
            return False

    except Exception as e:
        logger.error(f"❌ Authentication failed: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

