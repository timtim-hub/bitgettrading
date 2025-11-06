"""Technical indicator feature engineering."""

from typing import List

import numpy as np
import pandas as pd
import pandas_ta as ta

from bitget_trading.logger import get_logger

logger = get_logger()


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate technical indicators and features for the model.

    Args:
        df: DataFrame with OHLCV data (open, high, low, close, volume)

    Returns:
        DataFrame with all technical indicators added
    """
    df = df.copy()
    
    # Set timestamp as index if it exists
    if "timestamp" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index("timestamp")
    
    # Ensure index is DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # RSI (Relative Strength Index)
    df.ta.rsi(length=14, append=True)
    df.ta.rsi(length=7, append=True)
    df.ta.rsi(length=21, append=True)

    # MACD (Moving Average Convergence Divergence)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)

    # Bollinger Bands
    df.ta.bbands(length=20, std=2, append=True)

    # EMAs (Exponential Moving Averages)
    df.ta.ema(length=8, append=True)
    df.ta.ema(length=21, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)

    # Supertrend
    df.ta.supertrend(length=10, multiplier=3, append=True)

    # OBV (On-Balance Volume)
    df.ta.obv(append=True)

    # VWAP (Volume Weighted Average Price)
    try:
        df.ta.vwap(append=True)
    except Exception as e:
        logger.warning("vwap_calculation_failed", error=str(e))
        # Add a simple alternative if VWAP fails
        df["VWAP"] = (df["high"] + df["low"] + df["close"]) / 3

    # Stochastic Oscillator
    df.ta.stoch(k=14, d=3, smooth_k=3, append=True)

    # ADX (Average Directional Index)
    df.ta.adx(length=14, append=True)

    # CCI (Commodity Channel Index)
    df.ta.cci(length=20, append=True)

    # Williams %R
    df.ta.willr(length=14, append=True)

    # ATR (Average True Range)
    df.ta.atr(length=14, append=True)

    # Volume indicators
    df.ta.mfi(length=14, append=True)  # Money Flow Index

    # Price-based features
    df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
    df["hl2"] = (df["high"] + df["low"]) / 2
    df["ohlc4"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4

    # Returns and momentum
    df["returns"] = df["close"].pct_change()
    df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
    df["momentum_5"] = df["close"] / df["close"].shift(5) - 1
    df["momentum_10"] = df["close"] / df["close"].shift(10) - 1

    # Volatility
    df["volatility_5"] = df["returns"].rolling(5).std()
    df["volatility_10"] = df["returns"].rolling(10).std()
    df["volatility_20"] = df["returns"].rolling(20).std()

    # Volume changes
    df["volume_change"] = df["volume"].pct_change()
    df["volume_ma_5"] = df["volume"].rolling(5).mean()
    df["volume_ma_20"] = df["volume"].rolling(20).mean()

    # Price spreads
    df["hl_spread"] = (df["high"] - df["low"]) / df["close"]
    df["co_spread"] = (df["close"] - df["open"]) / df["open"]

    return df


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Get list of feature column names (excluding OHLCV and timestamp).

    Args:
        df: DataFrame with features

    Returns:
        List of feature column names
    """
    exclude_cols = {"timestamp", "open", "high", "low", "close", "volume", "datetime"}
    return [col for col in df.columns if col not in exclude_cols]


def create_sequences(
    df: pd.DataFrame, seq_len: int = 60
) -> tuple[np.ndarray, List[str]]:
    """
    Create sliding window sequences for model input.

    Args:
        df: DataFrame with features
        seq_len: Length of each sequence

    Returns:
        Tuple of (sequences array, feature column names)
    """
    # Calculate features
    data = calculate_features(df)
    
    # Forward fill then backfill NaN values to preserve data
    data = data.ffill().bfill()
    
    # Drop any remaining NaN rows
    data = data.dropna()

    if len(data) < seq_len:
        logger.warning(
            "insufficient_data",
            available=len(data),
            required=seq_len,
        )
        return np.array([]), []

    # Get feature columns
    feature_cols = get_feature_columns(data)
    
    if not feature_cols:
        logger.error("no_feature_columns_found")
        return np.array([]), []

    # Normalize features (z-score normalization)
    data_normalized = data.copy()
    for col in feature_cols:
        mean = data[col].mean()
        std = data[col].std()
        if std > 1e-8:  # Avoid division by zero
            data_normalized[col] = (data[col] - mean) / std
        else:
            data_normalized[col] = 0.0

    # Create sequences
    sequences = []
    for i in range(len(data_normalized) - seq_len + 1):
        seq = data_normalized[feature_cols].iloc[i : i + seq_len].values
        sequences.append(seq)

    sequences_array = np.array(sequences, dtype=np.float32)
    logger.debug(
        "sequences_created",
        n_sequences=len(sequences_array),
        seq_len=seq_len,
        n_features=len(feature_cols),
    )

    return sequences_array, feature_cols

