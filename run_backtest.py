#!/usr/bin/env python3
"""Run backtest on historical data."""

import asyncio
from pathlib import Path

from src.bitget_trading.backtest import run_backtest
from src.bitget_trading.config import get_config
from src.bitget_trading.data_fetcher import fetch_and_save
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.trainer import train_model
import pandas as pd


async def main() -> None:
    """Run backtest."""
    config = get_config()
    logger = setup_logging(config.log_level)

    logger.info("backtest_starting", leverage=config.leverage)

    # Check for model
    model_path = Path(config.model_path)
    if not model_path.exists():
        logger.error("model_not_found", path=str(model_path))
        logger.error("Please train a model first:")
        logger.error("  poetry run python train_model.py")
        return

    # Fetch historical data
    data_dir = Path("data")
    data_file = data_dir / f"{config.symbol.replace('/', '_')}_30d.csv"

    if not data_file.exists():
        logger.info("fetching_historical_data")
        data_file = await fetch_and_save(config, days=30)
    else:
        logger.info("using_existing_data", path=str(data_file))

    # Run backtest
    logger.info("running_backtest", leverage=config.leverage)
    metrics, trades_df = run_backtest(
        data_file,
        config,
        initial_balance=10000.0,
        save_results=True,
    )

    # Print results
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Leverage: {config.leverage}x")
    logger.info(f"Total Trades: {metrics.total_trades}")
    logger.info(f"Win Rate: {metrics.win_rate:.2%}")
    logger.info(f"Total PnL: ${metrics.total_pnl:.2f} ({metrics.total_pnl_pct:.2f}%)")
    logger.info(f"ROI: {metrics.roi:.2f}%")
    logger.info(f"Max Drawdown: ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)")
    logger.info(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    logger.info(f"Sortino Ratio: {metrics.sortino_ratio:.2f}")
    logger.info(f"Profit Factor: {metrics.profit_factor:.2f}")
    logger.info(f"Avg Win: ${metrics.avg_win:.2f}")
    logger.info(f"Avg Loss: ${metrics.avg_loss:.2f}")
    logger.info(f"Final Balance: ${metrics.final_balance:.2f}")
    logger.info("=" * 60)

    if not trades_df.empty:
        logger.info(f"\nFirst 10 trades:\n{trades_df.head(10).to_string()}")


if __name__ == "__main__":
    asyncio.run(main())

