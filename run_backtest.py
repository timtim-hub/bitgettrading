#!/usr/bin/env python3
"""Run backtest on collected data."""

from pathlib import Path

import pandas as pd

from src.bitget_trading.backtest import Backtester
from src.bitget_trading.config import get_config
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.model import TradingModel

logger = setup_logging()


def main() -> None:
    """Run backtest."""
    config = get_config()
    
    # Load data
    data_path = Path(config.data_path)
    if not data_path.exists():
        logger.error(f"data_not_found: {data_path}")
        logger.error("Run: python collect_data.py first")
        return
    
    # Load model
    model_path = Path(config.model_path)
    if not model_path.exists():
        logger.error(f"model_not_found: {model_path}")
        logger.error("Run: python train_model.py first")
        return
    
    logger.info(f"loading_data from {data_path}")
    df = pd.read_csv(data_path)
    
    # Convert timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Get feature columns
    feature_cols = [c for c in df.columns if c not in ["timestamp", "mid_price"]]
    
    logger.info(f"loading_model from {model_path}")
    model = TradingModel(config)
    model.load(model_path)
    
    # Run backtest
    logger.info(f"running_backtest with {config.leverage}x leverage")
    backtester = Backtester(config, model)
    
    metrics, trades_df = backtester.run(
        df,
        feature_cols,
        initial_balance=10000.0,
    )
    
    # Save results
    results_dir = Path("backtest_results")
    results_dir.mkdir(exist_ok=True)
    
    trades_df.to_csv(results_dir / "trades.csv", index=False)
    
    # Print results
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Leverage: {config.leverage}x")
    logger.info(f"Symbol: {config.symbol}")
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
    logger.info(f"Total Fees: ${metrics.total_fees:.2f}")
    logger.info(f"Total Slippage: ${metrics.total_slippage:.2f}")
    logger.info(f"Avg Trade Duration: {metrics.avg_trade_duration_sec:.1f}s")
    logger.info(f"Final Balance: ${metrics.final_balance:.2f}")
    logger.info("=" * 60)
    
    if not trades_df.empty:
        logger.info(f"\nFirst 10 trades:\n{trades_df.head(10).to_string()}")


if __name__ == "__main__":
    main()

