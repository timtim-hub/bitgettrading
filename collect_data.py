#!/usr/bin/env python3
"""Collect historical market data from Bitget."""

import asyncio
from pathlib import Path

import pandas as pd

from src.bitget_trading.bitget_ws import BitgetWebSocketClient
from src.bitget_trading.config import get_config
from src.bitget_trading.features import MicrostructureFeatures
from src.bitget_trading.logger import setup_logging

logger = setup_logging()


async def collect_data(duration_minutes: int = 60) -> pd.DataFrame:
    """
    Collect real-time market data for training.
    
    Args:
        duration_minutes: How long to collect data
    
    Returns:
        DataFrame with features
    """
    config = get_config()
    
    # Initialize WebSocket client
    ws_client = BitgetWebSocketClient(
        symbol=config.symbol,
        product_type=config.product_type,
        orderbook_levels=config.orderbook_levels,
    )
    
    # Initialize feature engine
    feature_engine = MicrostructureFeatures(
        feature_window_sec=config.feature_window_sec,
        feature_interval_ms=config.feature_interval_ms,
    )
    
    # Storage for features
    features_list = []
    
    # Callbacks
    def on_ticker(ticker: dict) -> None:
        feature_engine.update_ticker(ticker)
    
    def on_orderbook(orderbook: dict) -> None:
        feature_engine.update_orderbook(orderbook)
        
        # Compute features
        features = feature_engine.compute_features()
        if features:
            features_list.append(features)
            
            if len(features_list) % 60 == 0:
                logger.info(f"collected_{len(features_list)}_samples")
    
    ws_client.on_ticker = on_ticker
    ws_client.on_orderbook = on_orderbook
    
    # Start collection
    logger.info(f"collecting_data_for_{duration_minutes}_minutes")
    
    try:
        # Run for specified duration
        await asyncio.wait_for(
            ws_client.run(),
            timeout=duration_minutes * 60,
        )
    except asyncio.TimeoutError:
        logger.info("collection_timeout_reached")
    finally:
        await ws_client.close()
    
    # Convert to DataFrame
    df = pd.DataFrame(features_list)
    
    logger.info(f"collected_{len(df)}_feature_samples")
    
    return df


async def main() -> None:
    """Main collection loop."""
    config = get_config()
    
    # Collect data
    df = await collect_data(duration_minutes=60)
    
    # Save to disk
    output_path = Path(config.data_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_parquet(output_path, index=False)
    
    logger.info(f"data_saved", path=str(output_path), samples=len(df))
    logger.info(f"Feature columns: {list(df.columns)}")


if __name__ == "__main__":
    asyncio.run(main())

