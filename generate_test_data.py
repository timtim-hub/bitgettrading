#!/usr/bin/env python3
"""Generate synthetic market data for testing."""

from pathlib import Path

import numpy as np
import pandas as pd

from src.bitget_trading.config import get_config
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


def generate_realistic_market_data(n_samples: int = 10000, seed: int = 42) -> pd.DataFrame:
    """
    Generate realistic market microstructure data.
    
    Args:
        n_samples: Number of samples to generate
        seed: Random seed
    
    Returns:
        DataFrame with features
    """
    np.random.seed(seed)
    
    # Base price with trend and cycles
    base_price = 45000.0  # BTC price
    trend = np.linspace(0, 0.05, n_samples)  # 5% trend
    cycles = 0.02 * np.sin(np.linspace(0, 20 * np.pi, n_samples))
    random_walk = np.cumsum(np.random.randn(n_samples) * 0.0005)
    
    mid_prices = base_price * (1 + trend + cycles + random_walk)
    
    # Timestamps (1 second intervals)
    timestamps = pd.date_range("2025-01-01", periods=n_samples, freq="1S")
    
    # Spread (varies between 2-10 bps)
    spread_bps = 3.0 + 2.0 * np.abs(np.random.randn(n_samples))
    
    # Order book imbalances
    imbalance_1 = np.random.randn(n_samples) * 0.3
    imbalance_3 = imbalance_1 + np.random.randn(n_samples) * 0.1
    imbalance_5 = imbalance_3 + np.random.randn(n_samples) * 0.05
    
    # Depth features
    depth_bid = 100000 + 20000 * np.abs(np.random.randn(n_samples))
    depth_ask = 98000 + 22000 * np.abs(np.random.randn(n_samples))
    depth_5bps_bid = depth_bid * 0.6
    depth_10bps_bid = depth_bid * 0.8
    depth_5bps_ask = depth_ask * 0.6
    depth_10bps_ask = depth_ask * 0.8
    depth_ratio = depth_bid / depth_ask
    
    # Volume
    volume_24h = 50000 + 10000 * np.abs(np.random.randn(n_samples))
    quote_volume_24h = volume_24h * mid_prices
    
    # Funding rate (small, realistic)
    funding_rate = 0.0001 * np.sin(np.linspace(0, 8 * np.pi, n_samples))
    mark_index_spread_bps = 0.5 * np.random.randn(n_samples)
    
    # Best bid/ask
    best_bid = mid_prices * (1 - spread_bps / 20000)
    best_ask = mid_prices * (1 + spread_bps / 20000)
    
    # Rolling features
    returns_1s = np.concatenate([[0], np.diff(mid_prices) / mid_prices[:-1]])
    returns_5s = np.concatenate([[0] * 5, (mid_prices[5:] - mid_prices[:-5]) / mid_prices[:-5]])
    returns_10s = np.concatenate([[0] * 10, (mid_prices[10:] - mid_prices[:-10]) / mid_prices[:-10]])
    returns_20s = np.concatenate([[0] * 20, (mid_prices[20:] - mid_prices[:-20]) / mid_prices[:-20]])
    returns_30s = np.concatenate([[0] * 30, (mid_prices[30:] - mid_prices[:-30]) / mid_prices[:-30]])
    
    # Volatility
    volatility_10s = pd.Series(returns_1s).rolling(10, min_periods=1).std().values
    volatility_20s = pd.Series(returns_1s).rolling(20, min_periods=1).std().values
    volatility_30s = pd.Series(returns_1s).rolling(30, min_periods=1).std().values
    
    # Spread stats
    spread_mean_10s = pd.Series(spread_bps).rolling(10, min_periods=1).mean().values
    spread_std_10s = pd.Series(spread_bps).rolling(10, min_periods=1).std().fillna(0).values
    
    # Imbalance stats
    imbalance_mean_10s = pd.Series(imbalance_5).rolling(10, min_periods=1).mean().values
    imbalance_std_10s = pd.Series(imbalance_5).rolling(10, min_periods=1).std().fillna(0).values
    
    # Momentum
    momentum_10_20 = returns_10s - returns_20s
    
    # Create DataFrame
    df = pd.DataFrame({
        "timestamp": timestamps,
        "mid_price": mid_prices,
        "spread_bps": spread_bps,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "imbalance_1": imbalance_1,
        "imbalance_3": imbalance_3,
        "imbalance_5": imbalance_5,
        "depth_total_bid": depth_bid,
        "depth_total_ask": depth_ask,
        "depth_5bps_bid": depth_5bps_bid,
        "depth_10bps_bid": depth_10bps_bid,
        "depth_5bps_ask": depth_5bps_ask,
        "depth_10bps_ask": depth_10bps_ask,
        "depth_ratio": depth_ratio,
        "volume_24h": volume_24h,
        "quote_volume_24h": quote_volume_24h,
        "funding_rate": funding_rate,
        "mark_index_spread_bps": mark_index_spread_bps,
        "return_1s": returns_1s,
        "return_5s": returns_5s,
        "return_10s": returns_10s,
        "return_20s": returns_20s,
        "return_30s": returns_30s,
        "volatility_10s": volatility_10s,
        "volatility_20s": volatility_20s,
        "volatility_30s": volatility_30s,
        "spread_mean_10s": spread_mean_10s,
        "spread_std_10s": spread_std_10s,
        "imbalance_mean_10s": imbalance_mean_10s,
        "imbalance_std_10s": imbalance_std_10s,
        "momentum_10_20": momentum_10_20,
    })
    
    return df


def main() -> None:
    """Generate test data."""
    config = get_config()
    
    logger.info("generating_test_data")
    
    # Generate 10,000 samples (~2.7 hours at 1Hz)
    df = generate_realistic_market_data(n_samples=10000)
    
    logger.info(f"generated_{len(df)}_samples with {len(df.columns)}_columns")
    
    # Save
    output_path = Path(config.data_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use CSV instead of parquet (no extra dependencies needed)
    output_path_csv = output_path.with_suffix(".csv")
    df.to_csv(output_path_csv, index=False)
    
    logger.info(f"data_saved to {output_path_csv}")
    logger.info(f"Price range: ${df['mid_price'].min():.2f} - ${df['mid_price'].max():.2f}")
    logger.info(f"Columns: {list(df.columns)}")


if __name__ == "__main__":
    main()

