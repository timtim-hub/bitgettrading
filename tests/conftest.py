"""Pytest configuration and fixtures."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from src.bitget_trading.config import TradingConfig
from src.bitget_trading.model import CNN_LSTM_GRU


@pytest.fixture
def sample_ohlcv_data() -> pd.DataFrame:
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n_samples = 500

    # Generate realistic price data
    base_price = 100.0
    returns = np.random.randn(n_samples) * 0.02
    prices = base_price * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n_samples, freq="1min"),
            "open": prices * (1 + np.random.randn(n_samples) * 0.001),
            "high": prices * (1 + np.abs(np.random.randn(n_samples)) * 0.005),
            "low": prices * (1 - np.abs(np.random.randn(n_samples)) * 0.005),
            "close": prices,
            "volume": np.abs(np.random.randn(n_samples) * 1000000),
        }
    )

    # Ensure OHLC relationships are valid
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


@pytest.fixture
def test_config() -> TradingConfig:
    """Create test configuration."""
    return TradingConfig(
        bitget_api_key="test_key",
        bitget_api_secret="test_secret",
        bitget_passphrase="test_pass",
        symbol="SOL/USDT:USDT",
        leverage=50,
        sandbox=True,
        seq_len=60,
        batch_size=32,
    )


@pytest.fixture
def sample_model() -> CNN_LSTM_GRU:
    """Create sample model for testing."""
    model = CNN_LSTM_GRU(
        n_features=68, lstm_hidden=178, gru_hidden=92, dropout=0.31
    )
    model.eval()
    return model


@pytest.fixture
def temp_model_path(tmp_path: Path) -> Path:
    """Create temporary model file."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    model_path = model_dir / "test_model.pth"

    # Create and save dummy model
    model = CNN_LSTM_GRU()
    torch.save(model.state_dict(), model_path)

    return model_path

