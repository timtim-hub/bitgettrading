"""Multi-symbol universe management for Bitget USDT-M futures."""

import asyncio
from typing import Any
import requests
import urllib3

from src.bitget_trading.logger import get_logger

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger()


class UniverseManager:
    """
    Manages the universe of tradable USDT-M futures symbols.
    
    Fetches all available contracts and filters based on liquidity criteria.
    """

    BASE_URL = "https://api.bitget.com"

    def __init__(
        self,
        min_volume_24h: float = 1_000_000,  # Min $1M daily volume
        max_spread_bps: float = 50.0,  # Max 50 bps spread
    ) -> None:
        """
        Initialize universe manager.
        
        Args:
            min_volume_24h: Minimum 24h volume in USDT
            max_spread_bps: Maximum allowed spread in basis points
        """
        self.min_volume_24h = min_volume_24h
        self.max_spread_bps = max_spread_bps
        self.symbols: list[str] = []
        self.contract_info: dict[str, dict[str, Any]] = {}

    async def fetch_all_contracts(self) -> list[str]:
        """
        Fetch all USDT-M futures contracts from Bitget.
        
        Returns:
            List of symbol names
        """
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/contracts"
        params = {"productType": "USDT-FUTURES"}

        try:
            # Use requests with SSL verification disabled (wrapped in asyncio.to_thread)
            response = await asyncio.to_thread(
                requests.get,
                endpoint,
                params=params,
                verify=False,
                timeout=(10, 30)
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch contracts: {response.status_code}")
                return []
            
            data = response.json()

            if data.get("code") != "00000":
                logger.error("api_error", code=data.get("code"), msg=data.get("msg"))
                return []

            contracts = data.get("data", [])

            # Store contract info
            for contract in contracts:
                symbol = contract.get("symbol")
                if symbol:
                    self.contract_info[symbol] = {
                        "base_coin": contract.get("baseCoin"),
                        "quote_coin": contract.get("quoteCoin"),
                        "size_multiplier": float(contract.get("sizeMultiplier", 1)),
                        "min_trade_num": float(contract.get("minTradeNum", 0)),
                        "price_place": int(contract.get("pricePlace", 2)),
                        "volume_place": int(contract.get("volumePlace", 4)),
                        "max_leverage": int(contract.get("maxLeverage", 125)),
                        "status": contract.get("symbolStatus"),
                    }

            # Filter to active contracts only
            self.symbols = [
                s for s, info in self.contract_info.items()
                if info.get("status") == "normal"
            ]

            logger.info(
                "contracts_fetched",
                total_contracts=len(contracts),
                active_symbols=len(self.symbols),
            )

            return self.symbols

        except Exception as e:
            logger.error("fetch_contracts_error", error=str(e))
            return []

    async def fetch_tickers(self) -> dict[str, dict[str, Any]]:
        """
        Fetch ticker data for all symbols to apply volume/spread filters.
        
        Returns:
            Dict mapping symbol to ticker data
        """
        endpoint = f"{self.BASE_URL}/api/v2/mix/market/tickers"
        params = {"productType": "USDT-FUTURES"}

        # Retry logic for network issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    endpoint,
                    params=params,
                    verify=False,
                    timeout=(30, 60)
                )

                if response.status_code != 200:
                    logger.error(f"ticker_fetch_failed_status", status=response.status_code, attempt=attempt + 1)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return {}

                data = response.json()

                if data.get("code") != "00000":
                    logger.error("ticker_api_error", code=data.get("code"), msg=data.get("msg"))
                    return {}

                tickers_list = data.get("data", [])
                tickers_dict = {}

                for ticker in tickers_list:
                    symbol = ticker.get("symbol")
                    if symbol:
                        tickers_dict[symbol] = {
                            "ask": float(ticker.get("bestAsk", 0)),
                            "bid": float(ticker.get("bestBid", 0)),
                            "last": float(ticker.get("last", 0)),
                            "volume_24h": float(ticker.get("usdtVolume", 0)),
                        }

                logger.info("tickers_fetched", count=len(tickers_dict))
                return tickers_dict

            except Exception as e:
                logger.error("ticker_fetch_error", error=str(e), attempt=attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return {}

        return {}

    async def get_filtered_universe(self) -> list[str]:
        """
        Get filtered list of symbols meeting liquidity and spread criteria.
        
        Returns:
            List of eligible symbols
        """
        # First fetch contracts
        await self.fetch_all_contracts()
        if not self.symbols:
            logger.warning("no_contracts_fetched")
            return []

        # Then fetch tickers
        tickers = await self.fetch_tickers()
        if not tickers:
            logger.warning("no_tickers_fetched")
            return self.symbols  # Return all symbols if no ticker data

        # Apply filters
        filtered = []
        for symbol in self.symbols:
            ticker = tickers.get(symbol)
            if not ticker:
                continue

            # Volume filter
            if ticker["volume_24h"] < self.min_volume_24h:
                continue

            # Spread filter
            if ticker["ask"] > 0 and ticker["bid"] > 0:
                mid = (ticker["ask"] + ticker["bid"]) / 2
                spread_bps = ((ticker["ask"] - ticker["bid"]) / mid) * 10000
                if spread_bps > self.max_spread_bps:
                    continue

            filtered.append(symbol)

        logger.info(
            "universe_filtered",
            total=len(self.symbols),
            filtered=len(filtered),
            min_volume=self.min_volume_24h,
            max_spread_bps=self.max_spread_bps,
        )

        return filtered
