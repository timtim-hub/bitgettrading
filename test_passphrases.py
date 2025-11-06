#!/usr/bin/env python3
"""Test both passphrases to find the correct one."""

import asyncio

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def test_passphrase(api_key: str, secret_key: str, passphrase: str) -> bool:
    """Test a passphrase."""
    try:
        client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
        balance = await client.get_account_balance()

        if balance:
            available = float(balance.get("available", 0))
            equity = float(balance.get("equity", 0))
            logger.info(f"✅ SUCCESS with passphrase: '{passphrase}'")
            logger.info(f"   💰 Available: ${available:.2f} USDT")
            logger.info(f"   📊 Equity:    ${equity:.2f} USDT")
            return True
        else:
            logger.error(f"❌ FAILED with passphrase: '{passphrase}' (no data)")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED with passphrase: '{passphrase}' - {str(e)[:100]}")
        return False


async def main() -> None:
    """Test both passphrases."""
    api_key = "bg_f4892ab62882e9bac2f766c9db6d1ffd"
    secret_key = "69ce41f04af5be901e5196387939ba35c27b364b9e1305aa4f4312cc4ae1da5d"

    logger.info("=" * 70)
    logger.info("🔑 TESTING PASSPHRASES")
    logger.info("=" * 70)
    logger.info(f"API Key: {api_key}")
    logger.info(f"Secret:  {secret_key[:20]}...{secret_key[-10:]}")
    logger.info("=" * 70 + "\n")

    # Test passphrase 1
    logger.info("Test 1: Passphrase = 'LtLtLt2302'")
    logger.info("-" * 70)
    success1 = await test_passphrase(api_key, secret_key, "LtLtLt2302")
    logger.info("")

    # Test passphrase 2
    logger.info("Test 2: Passphrase = 'LtLtLt2302!'")
    logger.info("-" * 70)
    success2 = await test_passphrase(api_key, secret_key, "LtLtLt2302!")
    logger.info("")

    logger.info("=" * 70)
    if success1:
        logger.info("✅ CORRECT PASSPHRASE: 'LtLtLt2302'")
        logger.info("Saving to .env file...")
        with open(".env", "w") as f:
            f.write(f"""# Bitget API Credentials
BITGET_API_KEY={api_key}
BITGET_SECRET_KEY={secret_key}
BITGET_PASSPHRASE=LtLtLt2302

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
    elif success2:
        logger.info("✅ CORRECT PASSPHRASE: 'LtLtLt2302!'")
        logger.info("Saving to .env file...")
        with open(".env", "w") as f:
            f.write(f"""# Bitget API Credentials
BITGET_API_KEY={api_key}
BITGET_SECRET_KEY={secret_key}
BITGET_PASSPHRASE=LtLtLt2302!

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
    else:
        logger.error("❌ BOTH PASSPHRASES FAILED!")
        logger.error("Please verify your API credentials in Bitget dashboard.")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

