#!/usr/bin/env python3
"""Quick model training script."""

from pathlib import Path

import pandas as pd

from src.bitget_trading.config import get_config
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.trainer import train_model

logger = setup_logging()


def main() -> None:
    """Train model quickly."""
    config = get_config()
    
    logger.info("quick_training_started")
    
    # Load data
    data_file = Path("data/SOL_USDT:USDT_30d.csv")
    if not data_file.exists():
        logger.error("data_not_found", path=str(data_file))
        logger.error("Run: poetry run python generate_sample_data.py")
        return
    
    df = pd.read_csv(data_file)
    
    # Train with fewer epochs for speed
    logger.info("training_model", epochs=5)
    train_model(
        df,
        n_features=config.n_features,
        lstm_hidden=config.lstm_hidden,
        gru_hidden=config.gru_hidden,
        dropout=config.dropout,
        seq_len=config.seq_len,
        epochs=5,  # Quick training
        batch_size=config.batch_size,
        learning_rate=0.001,
        save_path=config.model_path,
    )
    
    logger.info("training_completed", model_path=config.model_path)
    logger.info("You can now run: poetry run python run_backtest.py")


if __name__ == "__main__":
    main()

