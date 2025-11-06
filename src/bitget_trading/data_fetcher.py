"""Fetch historical data from Bitget exchange."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import ccxt.pro as ccxtpro
import pandas as pd

from bitget_trading.config import TradingConfig
from bitget_trading.logger import get_logger

logger = get_logger()


async def fetch_historical_data(
    symbol: str,
    timeframe: str,
    days: int = 30,
    save_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Fetch historical OHLCV data from Bitget.

    Args:
        symbol: Trading pair symbol (e.g., "SOL/USDT:USDT")
        timeframe: Timeframe (e.g., "1m", "5m", "1h")
        days: Number of days of historical data
        save_path: Optional path to save data as CSV

    Returns:
        DataFrame with OHLCV data
    """
    exchange = ccxtpro.bitget(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
    )

    try:
        logger.info(
            "fetching_data",
            symbol=symbol,
            timeframe=timeframe,
            days=days,
        )

        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        # Fetch data in chunks
        all_candles = []
        current_time = int(start_time.timestamp() * 1000)
        end_timestamp = int(end_time.timestamp() * 1000)

        while current_time < end_timestamp:
            try:
                candles = await exchange.fetch_ohlcv(
                    symbol, timeframe, since=current_time, limit=1000
                )

                if not candles:
                    break

                all_candles.extend(candles)
                current_time = candles[-1][0] + 1

                # Rate limiting
                await asyncio.sleep(exchange.rateLimit / 1000)

                logger.debug(
                    "fetched_chunk",
                    candles=len(candles),
                    total=len(all_candles),
                )

            except Exception as e:
                logger.error("fetch_chunk_error", error=str(e))
                await asyncio.sleep(5)
                continue

        # Convert to DataFrame
        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        logger.info("data_fetched", rows=len(df), start=df.iloc[0]["timestamp"], end=df.iloc[-1]["timestamp"])

        # Save to CSV
        if save_path:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False)
            logger.info("data_saved", path=str(path))

        return df

    finally:
        await exchange.close()


async def fetch_and_save(
    config: TradingConfig, days: int = 30, output_dir: str = "data"
) -> Path:
    """
    Fetch historical data and save to CSV.

    Args:
        config: Trading configuration
        days: Number of days of data
        output_dir: Directory to save data

    Returns:
        Path to saved CSV file
    """
    output_path = Path(output_dir) / f"{config.symbol.replace('/', '_')}_{days}d.csv"
    await fetch_historical_data(
        config.symbol, config.timeframe, days, output_path
    )
    return output_path

