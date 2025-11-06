#!/usr/bin/env python3
"""Run live trading bot."""

import asyncio
import signal
from pathlib import Path

from src.bitget_trading.config import get_config
from src.bitget_trading.live_trader import LiveTrader
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.model import load_model


async def main() -> None:
    """Run live trader."""
    config = get_config()
    logger = setup_logging(config.log_level)

    logger.info("live_trader_starting", mode="SANDBOX" if config.sandbox else "LIVE")

    # Load model
    model_path = Path(config.model_path)
    if not model_path.exists():
        logger.error("model_not_found", path=str(model_path))
        logger.error("Please run 'poetry run python run_backtest.py' first to train the model")
        return

    model = load_model(
        model_path,
        n_features=config.n_features,
        lstm_hidden=config.lstm_hidden,
        gru_hidden=config.gru_hidden,
        dropout=config.dropout,
    )

    # Initialize trader
    trader = LiveTrader(config, model)

    # Handle shutdown gracefully
    def signal_handler(sig: int, frame: object) -> None:
        logger.info("shutdown_signal_received")
        asyncio.create_task(trader.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start trading
    try:
        await trader.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
        await trader.stop()
    except Exception as e:
        logger.error("trader_error", error=str(e))
        await trader.stop()


if __name__ == "__main__":
    asyncio.run(main())

