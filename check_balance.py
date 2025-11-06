#!/usr/bin/env python3
"""Check Bitget Futures account balance before trading."""

import asyncio
import os

from dotenv import load_dotenv

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def main() -> None:
    """Check account balance."""
    load_dotenv()

    api_key = os.getenv("BITGET_API_KEY", "")
    secret_key = os.getenv("BITGET_SECRET_KEY", "")
    passphrase = os.getenv("BITGET_PASSPHRASE", "")

    logger.info("=" * 70)
    logger.info("💰 CHECKING BITGET FUTURES ACCOUNT BALANCE")
    logger.info("=" * 70)

    client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)

    try:
        balance = await client.get_account_balance()

        if balance and balance.get("code") == "00000":
            data = balance.get("data", [{}])[0]
            available = float(data.get("available", 0))
            equity = float(data.get("equity", 0))
            frozen = float(data.get("frozen", 0))

            logger.info(f"💰 Available Balance: ${available:.2f} USDT")
            logger.info(f"📊 Total Equity:      ${equity:.2f} USDT")
            logger.info(f"🔒 Frozen:            ${frozen:.2f} USDT")
            logger.info("=" * 70)

            if available < 50:
                logger.error("\n⚠️  INSUFFICIENT FUNDS!")
                logger.error(f"Current balance: ${available:.2f} USDT")
                logger.error(f"Required minimum: $50.00 USDT")
                logger.error("\nPlease transfer funds to your Bitget USDT-M Futures account:")
                logger.error("1. Go to: https://www.bitget.com/account/wallet")
                logger.error("2. Transfer from Spot/Funding → USDT-M Futures")
                logger.error("3. Transfer at least $50 USDT")
                return False
            else:
                logger.info(f"\n✅ SUFFICIENT FUNDS: ${available:.2f} USDT")
                logger.info("Ready to start trading!")
                return True

        else:
            logger.error("❌ Failed to fetch balance")
            return False

    except Exception as e:
        logger.error(f"❌ Error checking balance: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

