"""Bitget REST API client with HMAC authentication."""

import base64
import hmac
import time
from hashlib import sha256
from typing import Any

import aiohttp
import orjson

from bitget_trading.logger import get_logger

logger = get_logger()


class BitgetRestClient:
    """
    Bitget REST API client for USDT-M futures.
    
    Handles HMAC signing and order placement.
    """

    BASE_URL = "https://api.bitget.com"
    SANDBOX_URL = "https://demo.bitget.com"  # Bitget sandbox

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        sandbox: bool = True,
    ) -> None:
        """
        Initialize REST client.
        
        Args:
            api_key: Bitget API key
            api_secret: Bitget API secret
            passphrase: Bitget passphrase
            sandbox: Use sandbox environment
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = self.SANDBOX_URL if sandbox else self.BASE_URL

    def _sign_request(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = "",
    ) -> str:
        """
        Create HMAC signature for Bitget API.
        
        Args:
            timestamp: Unix timestamp in milliseconds
            method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path
            body: Request body (for POST requests)
        
        Returns:
            HMAC signature (passphrase is sent as plain text)
        """
        # Create prehash string
        prehash = timestamp + method.upper() + request_path + body
        
        # Sign with HMAC SHA256
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                prehash.encode("utf-8"),
                sha256,
            ).digest()
        ).decode()
        
        return signature

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make authenticated HTTP request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
        
        Returns:
            Response JSON
        """
        timestamp = str(int(time.time() * 1000))
        
        # Build request path
        request_path = endpoint
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            request_path += f"?{query_string}"
        
        # Build body
        body = ""
        if data:
            body = orjson.dumps(data).decode()
        
        # Sign request
        signature = self._sign_request(
            timestamp, method, request_path, body
        )
        
        # Headers (passphrase is sent as plain text, NOT signed!)
        headers = {
            "Content-Type": "application/json",
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,  # Plain text, not signed!
        }
        
        # Make request
        url = self.base_url + request_path
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=headers,
                data=body if body else None,
            ) as response:
                response_text = await response.text()
                
                if response.status != 200:
                    logger.error(
                        "api_request_failed",
                        status=response.status,
                        response=response_text[:200],
                    )
                    raise Exception(f"API error: {response.status} - {response_text}")
                
                return orjson.loads(response_text)

    async def get_account_balance(self, product_type: str = "USDT-FUTURES") -> dict[str, Any]:
        """Get account balance."""
        endpoint = f"/api/v2/mix/account/accounts"
        params = {"productType": product_type}
        
        response = await self._request("GET", endpoint, params=params)
        
        logger.debug("account_balance_fetched", response=response)
        return response

    async def get_positions(
        self, symbol: str, product_type: str = "USDT-FUTURES"
    ) -> list[dict[str, Any]]:
        """Get open positions."""
        endpoint = "/api/v2/mix/position/all-position"
        params = {
            "productType": product_type,
            "marginCoin": "USDT",
        }
        
        response = await self._request("GET", endpoint, params=params)
        
        if response.get("code") == "00000" and "data" in response:
            positions = response["data"]
            # Filter for specific symbol
            return [p for p in positions if p.get("symbol") == symbol]
        
        return []

    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: float,
        order_type: str = "market",
        price: float | None = None,
        reduce_only: bool = False,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Place order.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "buy" or "sell"
            size: Order size in contracts
            order_type: "market" or "limit"
            price: Limit price (required for limit orders)
            reduce_only: Reduce-only flag
            product_type: Product type
        
        Returns:
            Order response
        """
        endpoint = "/api/v2/mix/order/place-order"
        
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "side": side,
            "orderType": order_type,
            "size": str(size),
        }
        
        if price:
            data["price"] = str(price)
        
        if reduce_only:
            data["reduceOnly"] = "YES"
        
        response = await self._request("POST", endpoint, data=data)
        
        logger.info(
            "order_placed",
            symbol=symbol,
            side=side,
            size=size,
            order_type=order_type,
            response=response,
        )
        
        return response

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """Set leverage for symbol."""
        endpoint = "/api/v2/mix/account/set-leverage"
        
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": "USDT",
            "leverage": str(leverage),
            "holdSide": "long",  # Set for both sides
        }
        
        response = await self._request("POST", endpoint, data=data)
        
        # Also set for short side
        data["holdSide"] = "short"
        await self._request("POST", endpoint, data=data)
        
        logger.info("leverage_set", symbol=symbol, leverage=leverage)
        return response

    async def get_ticker(
        self, symbol: str, product_type: str = "USDT-FUTURES"
    ) -> dict[str, Any]:
        """Get ticker data (REST fallback)."""
        endpoint = "/api/v2/mix/market/ticker"
        params = {
            "symbol": symbol,
            "productType": product_type,
        }
        
        response = await self._request("GET", endpoint, params=params)
        return response

    async def get_funding_rate(
        self, symbol: str, product_type: str = "USDT-FUTURES"
    ) -> dict[str, Any]:
        """Get current funding rate."""
        endpoint = "/api/v2/mix/market/current-fund-rate"
        params = {
            "symbol": symbol,
            "productType": product_type,
        }
        
        response = await self._request("GET", endpoint, params=params)
        return response

