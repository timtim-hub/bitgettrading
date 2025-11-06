#!/usr/bin/env python3
"""Generate sample OHLCV data for backtesting."""

from pathlib import Path

import numpy as np
import pandas as pd


def generate_realistic_ohlcv(
    n_samples: int = 43200, base_price: float = 150.0, seed: int = 42
) -> pd.DataFrame:
    """
    Generate realistic OHLCV data for SOL/USDT.

    Args:
        n_samples: Number of candles (43200 = 30 days of 1m candles)
        base_price: Starting price
        seed: Random seed

    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(seed)

    # Generate price movement with trends and volatility
    # Add trend component
    trend = np.linspace(0, 0.2, n_samples)  # 20% uptrend over period

    # Add cyclical component (simulates market cycles)
    cycles = 0.1 * np.sin(np.linspace(0, 8 * np.pi, n_samples))

    # Add random walk
    random_walk = np.cumsum(np.random.randn(n_samples) * 0.008)

    # Combine components
    price_multiplier = 1 + trend + cycles + random_walk
    # Ensure price multiplier is always positive
    price_multiplier = np.maximum(price_multiplier, 0.5)
    close_prices = base_price * price_multiplier

    # Generate OHLC from close
    opens = close_prices * (1 + np.random.randn(n_samples) * 0.002)
    highs = np.maximum(opens, close_prices) * (1 + np.abs(np.random.randn(n_samples)) * 0.005)
    lows = np.minimum(opens, close_prices) * (1 - np.abs(np.random.randn(n_samples)) * 0.005)

    # Generate volume with correlation to price movement
    price_change = np.abs(np.diff(close_prices, prepend=close_prices[0]))
    base_volume = 100000
    volume = base_volume * (1 + price_change / close_prices) * np.abs(np.random.randn(n_samples) * 0.5 + 1)

    # Create DataFrame
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n_samples, freq="1min"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close_prices,
            "volume": volume,
        }
    )

    # Ensure OHLC validity
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


if __name__ == "__main__":
    # Create data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Generate 30 days of 1-minute data
    print("Generating sample SOLUSDT data...")
    df = generate_realistic_ohlcv(n_samples=43200, base_price=150.0)

    # Save to CSV
    output_path = data_dir / "SOL_USDT:USDT_30d.csv"
    df.to_csv(output_path, index=False)

    print(f"Generated {len(df)} candles")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    print(f"Saved to: {output_path}")

