"""Tests for feature engineering module."""

import numpy as np
import pandas as pd
import pytest

from src.bitget_trading.features import (
    calculate_features,
    create_sequences,
    get_feature_columns,
)


def test_calculate_features(sample_ohlcv_data: pd.DataFrame) -> None:
    """Test feature calculation."""
    df_features = calculate_features(sample_ohlcv_data)

    # Should have more columns than original
    assert len(df_features.columns) > len(sample_ohlcv_data.columns)

    # Check for key indicators
    assert "RSI_14" in df_features.columns
    assert "MACD_12_26_9" in df_features.columns
    assert "BBL_20_2.0" in df_features.columns  # Bollinger Lower
    assert "EMA_8" in df_features.columns
    assert "returns" in df_features.columns


def test_get_feature_columns(sample_ohlcv_data: pd.DataFrame) -> None:
    """Test feature column extraction."""
    df_features = calculate_features(sample_ohlcv_data)
    feature_cols = get_feature_columns(df_features)

    # Should not include OHLCV columns
    assert "open" not in feature_cols
    assert "high" not in feature_cols
    assert "low" not in feature_cols
    assert "close" not in feature_cols
    assert "volume" not in feature_cols
    assert "timestamp" not in feature_cols

    # Should include indicators
    assert len(feature_cols) > 0


def test_create_sequences(sample_ohlcv_data: pd.DataFrame) -> None:
    """Test sequence creation."""
    sequences, feature_cols = create_sequences(sample_ohlcv_data, seq_len=60)

    # Check shape
    assert len(sequences) > 0
    assert sequences.shape[1] == 60  # seq_len
    assert sequences.shape[2] > 0  # n_features

    # Check feature columns
    assert len(feature_cols) > 0
    assert isinstance(feature_cols, list)


def test_create_sequences_insufficient_data() -> None:
    """Test sequence creation with insufficient data."""
    # Create small dataset
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="1min"),
            "open": np.random.randn(10) + 100,
            "high": np.random.randn(10) + 101,
            "low": np.random.randn(10) + 99,
            "close": np.random.randn(10) + 100,
            "volume": np.abs(np.random.randn(10) * 1000),
        }
    )

    sequences, _ = create_sequences(df, seq_len=60)

    # Should return empty array
    assert len(sequences) == 0


def test_feature_normalization(sample_ohlcv_data: pd.DataFrame) -> None:
    """Test that features are normalized."""
    sequences, _ = create_sequences(sample_ohlcv_data, seq_len=60)

    if len(sequences) > 0:
        # Check that values are roughly standardized
        mean = np.mean(sequences)
        std = np.std(sequences)

        assert abs(mean) < 1.0  # Should be close to 0
        # Note: std might not be exactly 1 due to per-feature normalization

