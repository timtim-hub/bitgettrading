"""Multi-symbol universe management for Bitget USDT-M futures."""

import asyncio
from typing import Any

import aiohttp

from bitget_trading.logger import get_logger

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
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status != 200:
                        logger.error("failed_to_fetch_contracts", status=response.status)
                        return []

                    data = await response.json()

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
                # Configure timeout
                timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(endpoint, params=params) as response:
                        if response.status != 200:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)
                                continue
                            return {}

                        data = await response.json()

                        if data.get("code") != "00000":
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)
                                continue
                            return {}

                        tickers = data.get("data", [])

                        ticker_map = {}
                        for ticker in tickers:
                            symbol = ticker.get("symbol")
                            if symbol:
                                # Handle None values properly
                                last_price = ticker.get("lastPr") or 0
                                bid_price = ticker.get("bidPr") or 0
                                ask_price = ticker.get("askPr") or 0
                                volume_24h = ticker.get("baseVolume") or 0
                                quote_volume = ticker.get("quoteVolume") or 0
                                open_interest = ticker.get("openInterest") or 0
                                
                                # Skip symbols with no valid price data
                                if last_price == 0 or bid_price == 0 or ask_price == 0:
                                    continue
                                
                                ticker_map[symbol] = {
                                    "last_price": float(last_price),
                                    "bid_price": float(bid_price),
                                    "ask_price": float(ask_price),
                                    "volume_24h": float(volume_24h),
                                    "quote_volume_24h": float(quote_volume),
                                    "open_interest": float(open_interest),
                                }

                        return ticker_map
            
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"fetch_tickers_attempt_{attempt+1}_failed", error=str(e))
                    await asyncio.sleep(2)  # Wait longer between retries
                    continue
                else:
                    logger.error("fetch_tickers_error", error=str(e))
                    return {}

    async def get_tradeable_universe(self) -> list[str]:
        """
        Get filtered list of tradeable symbols based on liquidity criteria.
        
        Returns:
            List of filtered symbol names
        """
        # Fetch contracts if not already done
        if not self.symbols:
            await self.fetch_all_contracts()

        # Fetch current market data
        tickers = await self.fetch_tickers()

        if not tickers:
            logger.warning("no_ticker_data")
            return self.symbols  # Return all if can't filter

        # Filter based on criteria
        filtered = []
        for symbol in self.symbols:
            ticker = tickers.get(symbol)
            if not ticker:
                continue

            # Volume filter
            if ticker["quote_volume_24h"] < self.min_volume_24h:
                continue

            # Spread filter
            bid = ticker["bid_price"]
            ask = ticker["ask_price"]
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2
                spread_bps = ((ask - bid) / mid) * 10000
                if spread_bps > self.max_spread_bps:
                    continue

            filtered.append(symbol)

        logger.info(
            "universe_filtered",
            total=len(self.symbols),
            filtered=len(filtered),
            min_volume=self.min_volume_24h,
        )

        return filtered

    def get_contract_info(self, symbol: str) -> dict[str, Any] | None:
        """Get contract specifications for a symbol."""
        return self.contract_info.get(symbol)

    def get_min_order_size(self, symbol: str) -> float:
        """Get minimum order size for symbol."""
        info = self.get_contract_info(symbol)
        return info.get("min_trade_num", 0.001) if info else 0.001

    def get_max_leverage(self, symbol: str) -> int:
        """Get maximum leverage for symbol."""
        info = self.get_contract_info(symbol)
        return info.get("max_leverage", 125) if info else 125

