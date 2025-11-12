"""
Launch Institutional Live Trading
Entry point for live trading with safety checks
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import logging

from institutional_live_trader import InstitutionalLiveTrader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)7s | %(name)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def check_environment():
    """Check environment and API credentials"""
    logger.info("🔍 Checking environment...")
    
    # Check API credentials
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        logger.error("❌ Missing API credentials!")
        logger.error("   Set environment variables:")
        logger.error("   - BITGET_API_KEY")
        logger.error("   - BITGET_SECRET_KEY")
        logger.error("   - BITGET_PASSPHRASE")
        return False
    
    logger.info("✅ API credentials found")
    return True


def check_config():
    """Check configuration file"""
    logger.info("🔍 Checking config...")
    
    config_file = Path("institutional_strategy_config.json")
    
    if not config_file.exists():
        logger.error(f"❌ Config file not found: {config_file}")
        return None
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Check live trading is enabled
    if not config.get('mode', {}).get('live_enabled', False):
        logger.error("❌ Live trading is DISABLED in config")
        logger.error("   Set 'live_enabled': true in institutional_strategy_config.json")
        logger.error("   ⚠️  Only enable after successful backtesting!")
        return None
    
    logger.info("✅ Config loaded")
    logger.info(f"  Leverage: {config.get('leverage', 25)}x")
    logger.info(f"  Margin per trade: {config.get('margin_fraction_per_trade', 0.10)*100:.0f}%")
    logger.info(f"  Max symbols: {config.get('concurrency', {}).get('max_symbols', 3)}")
    
    return config


def get_trading_symbols():
    """Get list of symbols to trade"""
    # Start with majors only
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    logger.info(f"📋 Trading symbols: {', '.join(symbols)}")
    
    return symbols


async def main():
    """Main entry point"""
    logger.info("="*80)
    logger.info("🏦 INSTITUTIONAL LIVE TRADING LAUNCHER")
    logger.info("25x Leverage | LSVR + VWAP-MR + Trend")
    logger.info("="*80)
    
    # Pre-flight checks
    if not check_environment():
        sys.exit(1)
    
    config = check_config()
    if not config:
        sys.exit(1)
    
    symbols = get_trading_symbols()
    
    # Safety confirmation
    logger.warning("\n⚠️  SAFETY CHECK")
    logger.warning("="*80)
    logger.warning("  You are about to start LIVE TRADING with REAL MONEY")
    logger.warning(f"  Leverage: {config.get('leverage', 25)}x")
    logger.warning(f"  Risk per trade: {config.get('margin_fraction_per_trade', 0.10)*100:.0f}% of equity")
    logger.warning("="*80)
    
    # Auto-confirmation (remove in production)
    response = input("\nType 'START' to begin live trading (or Ctrl+C to cancel): ")
    
    if response.strip().upper() != 'START':
        logger.info("❌ Launch cancelled")
        sys.exit(0)
    
    # Get credentials
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    # Create trader
    logger.info("\n🚀 Initializing trader...")
    trader = InstitutionalLiveTrader(config, api_key, secret_key, passphrase)
    
    # Run
    try:
        await trader.run(symbols, scan_interval_seconds=60)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info("\n✅ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Goodbye!")
        sys.exit(0)

