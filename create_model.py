#!/usr/bin/env python3
"""Create a functional initialized model for immediate use."""

from pathlib import Path

import torch

from src.bitget_trading.config import get_config
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.model import CNN_LSTM_GRU

logger = setup_logging()


def main() -> None:
    """Create initialized model."""
    config = get_config()
    model_path = Path(config.model_path)
    
    logger.info("creating_functional_model")
    
    # Create model with proper architecture
    model = CNN_LSTM_GRU(
        n_features=config.n_features,
        lstm_hidden=config.lstm_hidden,
        gru_hidden=config.gru_hidden,
        dropout=config.dropout,
    )
    
    # Initialize with Xavier/Kaiming initialization for better initial predictions
    for name, param in model.named_parameters():
        if 'weight' in name:
            if 'bn' in name or 'batch' in name:
                torch.nn.init.constant_(param, 1.0)
            elif len(param.shape) >= 2:
                torch.nn.init.xavier_uniform_(param)
        elif 'bias' in name:
            torch.nn.init.constant_(param, 0.0)
    
    # Save model
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_path)
    
    logger.info("model_created", path=str(model_path))
    logger.info("Model ready! Run: poetry run python run_backtest.py")


if __name__ == "__main__":
    main()

