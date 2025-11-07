"""Bitget REST API client with HMAC authentication."""

import base64
import hmac
import time
from hashlib import sha256
from typing import Any

import aiohttp
import orjson
import asyncio

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
        
        # Make request with timeout settings
        url = self.base_url + request_path
        
        # - total: 60s max for the entire request
        # - connect: 10s max to establish connection
        # - sock_read: 20s max to read response
        timeout = aiohttp.ClientTimeout(total=60, connect=20, sock_read=40)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
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
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"API error: {response.status} - {response_text}",
                            headers=response.headers,
                        )
                    
                    return orjson.loads(response_text)
        except asyncio.TimeoutError:
            logger.error(f"❌ API request timeout: {method} {url}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"❌ API client error: {method} {url} - {e}")
            raise

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

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
        product_type: str = "USDT-FUTURES",
        hold_side: str = "long",
    ) -> dict[str, Any]:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading pair
            leverage: Leverage value
            product_type: Product type
            hold_side: "long" or "short" for one-way mode
        
        Returns:
            API response
        """
        endpoint = "/api/v2/mix/account/set-leverage"
        
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": "USDT",
            "leverage": str(leverage),
            "holdSide": hold_side,  # For one-way mode
        }
        
        response = await self._request("POST", endpoint, data=data)
        
        logger.info(
            "leverage_set",
            symbol=symbol,
            leverage=leverage,
            hold_side=hold_side,
        )
        
        return response

    async def set_margin_mode(
        self,
        symbol: str,
        margin_mode: str,  # "isolated" or "crossed"
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Set margin mode for a symbol.
        
        Args:
            symbol: Trading pair
            margin_mode: "isolated" or "crossed"
            product_type: Product type
        
        Returns:
            API response
        """
        endpoint = "/api/v2/mix/account/set-margin-mode"
        
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": "USDT",
            "marginMode": margin_mode,
        }
        
        response = await self._request("POST", endpoint, data=data)
        
        logger.info(
            "margin_mode_set",
            symbol=symbol,
            margin_mode=margin_mode,
        )
        
        return response

    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: float,
        order_type: str = "market",
        price: float | None = None,
        reduce_only: bool = False,
        product_type: str = "USDT-FUTURES",
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Place order - SIMPLIFIED for isolated margin.
        
        🚨 CRITICAL UPDATE: Now includes atomic TP/SL placement.
        """
        endpoint = "/api/v2/mix/order/place-order"
        
        # 🚨 FORCE MARKET ORDERS - OVERRIDE ANY PARAMETER!
        # User reports limit orders still being placed
        # This forces "market" no matter what's passed
        order_type = "market"  # FORCE IT!
        
        logger.info(
            f"🔍 [BITGET_REST] place_order called: symbol={symbol}, side={side}, "
            f"order_type={order_type} (FORCED TO MARKET!), size={size}"
        )
        
        # SIMPLIFIED: Just basic parameters for isolated margin
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "side": side,
            "orderType": order_type,  # Will ALWAYS be "market" now!
            "size": str(size),
        }
        
        if price:
            data["price"] = str(price)
        
        if reduce_only:
            data["reduceOnly"] = "YES"
            
        # 🚨 NEW: Add atomic TP/SL prices directly to the order
        if take_profit_price:
            data["presetTakeProfitPrice"] = str(take_profit_price)
            # Ensure TP executes as market when triggered
            data["executeTakeProfitPrice"] = "0"
        if stop_loss_price:
            data["presetStopLossPrice"] = str(stop_loss_price)
            # Ensure SL executes as market when triggered
            data["executeStopLossPrice"] = "0"
        
        # Log EXACT data being sent to API
        logger.info(
            f"🚨 [API REQUEST] Sending to Bitget: {data}"
        )
        
        response = await self._request("POST", endpoint, data=data)
        
        logger.info(
            f"✅ [API RESPONSE] Order placed: symbol={symbol}, side={side}, "
            f"order_type={order_type}, response={response}"
        )
        
        logger.info(
            "order_placed",
            symbol=symbol,
            side=side,
            size=size,
            order_type=order_type,
            response=response,
        )
        
        return response
    
    async def cancel_all_pending_orders(
        self,
        symbol: str,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Cancel ALL pending (stuck) LIMIT orders for a symbol.
        
        CRITICAL: Use to clear stuck limit orders that never executed!
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            product_type: Product type
        
        Returns:
            Cancellation response
        """
        endpoint = "/api/v2/mix/order/cancel-order"
        
        # Query existing pending orders first
        try:
            query_endpoint = "/api/v2/mix/order/orders-pending"
            params = {
                "symbol": symbol,
                "productType": product_type,
            }
            pending_orders = await self._request("GET", query_endpoint, params=params)
            
            orders = pending_orders.get("data", {}).get("entrustedList", [])
            if not orders:
                logger.info(f"no_pending_orders_for_{symbol}")
                return {"code": "00000", "msg": "No orders to cancel"}
            
            # Cancel each pending order
            cancelled_count = 0
            for order in orders:
                order_id = order.get("orderId")
                if order_id:
                    try:
                        data = {
                            "symbol": symbol,
                            "productType": product_type,
                            "marginCoin": "USDT",
                            "orderId": order_id,
                        }
                        await self._request("POST", endpoint, data=data)
                        cancelled_count += 1
                    except Exception as e:
                        logger.warning(f"failed_to_cancel_order_{order_id}", error=str(e))
            
            logger.info(
                "cancelled_stuck_orders",
                symbol=symbol,
                count=cancelled_count,
            )
            return {"code": "00000", "msg": f"Cancelled {cancelled_count} stuck orders"}
            
        except Exception as e:
            logger.error("cancel_orders_error", symbol=symbol, error=str(e))
            return {"code": "error", "msg": str(e)}
    
    async def cancel_all_tpsl_orders(
        self,
        symbol: str,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Cancel ALL TP/SL orders for a symbol.
        
        CRITICAL: Use this on startup to clear old TP/SL orders with wrong values!
        Old exchange-side orders override bot-side monitoring.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            product_type: Product type
        
        Returns:
            Cancellation response
        """
        endpoint = "/api/v2/mix/order/cancel-plan-order"
        
        # Query existing TP/SL orders first
        try:
            query_endpoint = "/api/v2/mix/order/orders-plan-pending"
            params = {
                "symbol": symbol,
                "productType": product_type,
                "planType": "profit_loss",  # TP/SL orders
            }
            pending_orders = await self._request("GET", query_endpoint, params=params)
            
            orders = pending_orders.get("data", {}).get("entrustedList", [])
            if not orders:
                logger.info(f"no_pending_tpsl_orders_for_{symbol}")
                return {"code": "00000", "msg": "No orders to cancel"}
            
            # Cancel each TP/SL order
            cancelled_count = 0
            for order in orders:
                order_id = order.get("orderId")
                if order_id:
                    try:
                        data = {
                            "symbol": symbol,
                            "productType": product_type,
                            "marginCoin": "USDT",
                            "orderId": order_id,
                            "planType": "profit_loss",
                        }
                        await self._request("POST", endpoint, data=data)
                        cancelled_count += 1
                    except Exception as e:
                        logger.warning(f"failed_to_cancel_tpsl_order_{order_id}", error=str(e))
            
            logger.info(
                "cancelled_tpsl_orders",
                symbol=symbol,
                count=cancelled_count,
            )
            return {"code": "00000", "msg": f"Cancelled {cancelled_count} TP/SL orders"}
            
        except Exception as e:
            logger.error("cancel_tpsl_error", symbol=symbol, error=str(e))
            return {"code": "error", "msg": str(e)}
    
    async def place_tpsl_order(
        self,
        symbol: str,
        hold_side: str,  # "long" or "short"
        size: float,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        product_type: str = "USDT-FUTURES",
        trigger_type: str = "mark_price",
        market_execute: bool = True,
    ) -> dict[str, Any]:
        """Place exchange-side TP/SL orders.

        If market_execute=True, executePrice is set to "0" so Bitget executes
        the order at market when triggered.
        """
        endpoint = "/api/v2/mix/order/place-tpsl-order"
        results: dict[str, Any] = {"sl": None, "tp": None}

        if stop_loss_price is None and take_profit_price is None:
            return {"code": "error", "msg": "No TP/SL provided"}

        if stop_loss_price is not None:
            sl_data = {
                "symbol": symbol,
                "productType": product_type,
                "marginMode": "isolated",
                "marginCoin": "USDT",
                "planType": "loss_plan",
                "holdSide": hold_side,
                "triggerPrice": str(stop_loss_price),
                "triggerType": trigger_type,
                "executePrice": "0" if market_execute else str(stop_loss_price),
                "size": str(size),
            }
            try:
                results["sl"] = await self._request("POST", endpoint, data=sl_data)
                logger.info(
                    f"✅ [EXCHANGE SL] {symbol} @ {stop_loss_price} | code={results['sl'].get('code')}"
                )
            except Exception as e:
                logger.error(f"❌ SL placement failed for {symbol}: {e}")
                results["sl"] = {"code": "error", "msg": str(e)}

        if take_profit_price is not None:
            tp_data = {
                "symbol": symbol,
                "productType": product_type,
                "marginMode": "isolated",
                "marginCoin": "USDT",
                "planType": "profit_plan",
                "holdSide": hold_side,
                "triggerPrice": str(take_profit_price),
                "triggerType": trigger_type,
                "executePrice": "0" if market_execute else str(take_profit_price),
                "size": str(size),
            }
            try:
                results["tp"] = await self._request("POST", endpoint, data=tp_data)
                logger.info(
                    f"✅ [EXCHANGE TP] {symbol} @ {take_profit_price} | code={results['tp'].get('code')}"
                )
            except Exception as e:
                logger.error(f"❌ TP placement failed for {symbol}: {e}")
                results["tp"] = {"code": "error", "msg": str(e)}

        return results

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
    
    async def get_historical_candles(
        self,
        symbol: str,
        granularity: str = "1m",  # 1m, 3m, 5m, 15m, 30m, 1H, 4H, 1D
        limit: int = 200,  # Max 200 per request
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Get historical candlestick data (INSTANT data loading!).
        
        This replaces the 60-second wait time by fetching historical data directly.
        Bitget returns up to 200 candles per request.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            granularity: Candle interval (1m, 3m, 5m, 15m, 30m, 1H, 4H, 1D)
            limit: Number of candles to fetch (max 200)
            product_type: Product type
        
        Returns:
            Response with candle data [timestamp, open, high, low, close, volume, ...]
        """
        endpoint = "/api/v2/mix/market/candles"
        params = {
            "symbol": symbol,
            "productType": product_type,
            "granularity": granularity,
            "limit": str(limit),
        }
        
        response = await self._request("GET", endpoint, params=params)
        
        logger.info(
            "fetched_historical_candles",
            symbol=symbol,
            granularity=granularity,
            count=len(response.get("data", [])) if response.get("code") == "00000" else 0,
        )
        
        return response
