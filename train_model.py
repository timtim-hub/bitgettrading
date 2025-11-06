#!/usr/bin/env python3
"""Train LightGBM model on collected data."""

from pathlib import Path

import pandas as pd

from src.bitget_trading.config import get_config
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.model import TradingModel

logger = setup_logging()


def main() -> None:
    """Train model."""
    config = get_config()
    
    # Load data
    data_path = Path(config.data_path)
    if not data_path.exists():
        logger.error(f"data_not_found: {data_path}")
        logger.error("Run: python collect_data.py first")
        return
    
    logger.info(f"loading_data from {data_path}")
    df = pd.read_csv(data_path)
    
    logger.info(f"loaded_{len(df)}_samples with {len(df.columns)}_columns")
    
    # Get feature columns (exclude timestamp and mid_price)
    feature_cols = [c for c in df.columns if c not in ["timestamp", "mid_price"]]
    
    if "mid_price" not in df.columns:
        logger.error("mid_price column not found in data")
        return
    
    logger.info(f"using_{len(feature_cols)}_features")
    
    # Initialize model
    model = TradingModel(config)
    
    # Train
    metrics = model.train(df, feature_cols, test_size=0.2)
    
    # Save model
    model.save(config.model_path)
    
    # Print feature importance
    importance = model.get_feature_importance(top_n=15)
    logger.info(f"\nTop 15 features:\n{importance.to_string()}")
    
    logger.info("training_completed successfully")


if __name__ == "__main__":
    main()

