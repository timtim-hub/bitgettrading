"""Bitget REST API client with HMAC authentication."""

import asyncio
import base64
import hmac
import time
from hashlib import sha256
from typing import Any

import orjson
import ssl
import os
import sys
import subprocess
import warnings
import requests
import urllib3

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try to install certificates programmatically on macOS
if sys.platform == 'darwin':
    try:
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        cert_command = f"/Applications/Python {python_version}/Install Certificates.command"
        if os.path.exists(cert_command):
            subprocess.run([cert_command], check=False, capture_output=True, timeout=10)
    except Exception:
        pass  # Silently fail if certificate installation doesn't work

# Try to use certifi for SSL certificates
try:
    import certifi
    CERTIFI_CA_BUNDLE = certifi.where()
except ImportError:
    CERTIFI_CA_BUNDLE = None

from .logger import get_logger

logger = get_logger()


class BitgetRestClient:
    """
    Bitget REST API client for USDT-M futures.

    Handles HMAC signing and order placement.
    
    Note: Uses unverified SSL context to bypass macOS certificate issues.
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
        
        # Use requests Session with SSL verification completely disabled
        self.session = requests.Session()
        self.session.verify = False
        
        # Configure urllib3 to skip SSL completely
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Create a custom HTTPAdapter that doesn't verify SSL
        from requests.adapters import HTTPAdapter
        from urllib3.poolmanager import PoolManager
        
        class NoSSLAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs['ssl_context'] = ssl.SSLContext()
                kwargs['ssl_context'].check_hostname = False
                kwargs['ssl_context'].verify_mode = ssl.CERT_NONE
                return super().init_poolmanager(*args, **kwargs)
        
        self.session.mount('https://', NoSSLAdapter())
        logger.warning("⚠️ Using requests library with SSL verification completely disabled (development mode)")
        logger.warning("🔧 MODULE LOADED: BitgetRestClient v3.0 - REQUESTS with NoSSLAdapter")

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
        signature = self._sign_request(timestamp, method, request_path, body)

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

        # Use requests library wrapped in async - more reliable SSL bypass on macOS
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Use requests Session with SSL verification disabled
                # Run in thread pool to avoid blocking
                response = await asyncio.to_thread(
                    self.session.request,
                    method,
                    url,
                    headers=headers,
                    data=body.encode('utf-8') if body else None,
                    timeout=(20, 40),  # (connect, read) timeouts
                )
                
                response_text = response.text

                if response.status_code != 200:
                    logger.error(
                        "api_request_failed",
                        status=response.status_code,
                        response=response_text[:200],
                    )
                    # Don't retry on 4xx client errors
                    if 400 <= response.status_code < 500:
                        raise Exception(f"API error: {response.status_code} - {response_text}")
                    # Retry on 5xx server errors
                    raise Exception(f"API error: {response.status_code} - {response_text}")

                return orjson.loads(response_text)
            except (TimeoutError, requests.exceptions.ConnectionError, requests.exceptions.RequestException, ConnectionError) as e:
                last_error = e
                error_msg = str(e)
                # Log the actual error type and message
                logger.debug(f"⚠️ Connection error type: {type(e).__name__}, message: {error_msg}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 0.5  # Exponential backoff: 0.5s, 1s, 2s
                    logger.debug(f"⚠️ Connection error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"❌ API connection failed after {max_retries} attempts: {method} {url} - {type(e).__name__}: {e}")
                    raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 0.5
                    logger.debug(f"⚠️ Unexpected error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"❌ An unexpected error occurred during API request: {e}", exc_info=True)
                    raise
        
        # Should never reach here, but just in case
        if last_error:
            raise last_error
        raise Exception("Request failed for unknown reason")

    async def get_account_balance(
        self, product_type: str = "USDT-FUTURES"
    ) -> dict[str, Any]:
        """Get account balance."""
        endpoint = "/api/v2/mix/account/accounts"
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
    
    async def get_symbol_info(
        self, symbol: str, product_type: str = "USDT-FUTURES"
    ) -> dict[str, Any]:
        """
        Get symbol contract info including max leverage.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            product_type: Product type
        
        Returns:
            Dict with symbol info including maxLeverage
        """
        endpoint = "/api/v2/mix/market/contracts"
        params = {
            "productType": product_type.lower().replace("_", "-"),
        }
        
        try:
            response = await self._request("GET", endpoint, params=params)
            
            if response.get("code") == "00000" and "data" in response:
                contracts = response["data"]
                
                # Log first contract for debugging
                if contracts and len(contracts) > 0:
                    logger.debug(f"📋 Sample contract format: {list(contracts[0].keys())}")
                
                for contract in contracts:
                    # Try multiple possible key names for symbol
                    contract_symbol = contract.get("symbol") or contract.get("symbolName") or contract.get("baseCoin", "") + contract.get("quoteCoin", "")
                    
                    if contract_symbol == symbol:
                        max_lev = contract.get("maxLeverage") or contract.get("leverage") or "25"
                        logger.debug(f"✅ Found {symbol}: maxLeverage={max_lev}")
                        return contract
                
                # Symbol not found - log available symbols for debugging
                available = [c.get("symbol", "?") for c in contracts[:5]]
                logger.warning(f"⚠️ {symbol} not found in {len(contracts)} contracts. Sample: {available}")
            else:
                logger.error(f"❌ API error: {response.get('code')} - {response.get('msg')}")
        except Exception as e:
            logger.error(f"❌ Error fetching symbol info for {symbol}: {e}")
        
        return {}

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

        # Log detailed response
        if response.get("code") == "00000":
            logger.info(
                f"✅ [LEVERAGE API] {symbol} {hold_side}: Set to {leverage}x successfully"
            )
        else:
            logger.error(
                f"❌ [LEVERAGE API] {symbol} {hold_side}: Failed to set {leverage}x | "
                f"Code: {response.get('code')} | Msg: {response.get('msg', 'Unknown error')} | "
                f"Data: {response}"
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

    async def get_order(
        self,
        symbol: str,
        order_id: str,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Get order details
        
        Args:
            symbol: Trading pair symbol
            order_id: Order ID to query
            product_type: Product type
            
        Returns:
            Order details including state (filled, partial_filled, live, etc.)
        """
        endpoint = "/api/v2/mix/order/detail"
        params = {
            "symbol": symbol,
            "orderId": order_id,
            "productType": product_type.lower().replace("_", "-"),
        }
        return await self._request("GET", endpoint, params=params)
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        product_type: str = "USDT-FUTURES",
    ) -> dict[str, Any]:
        """
        Cancel an open order
        
        Args:
            symbol: Trading pair symbol
            order_id: Order ID to cancel
            product_type: Product type
            
        Returns:
            Cancel response
        """
        endpoint = "/api/v2/mix/order/cancel-order"
        data = {
            "symbol": symbol,
            "orderId": order_id,
            "productType": product_type.lower().replace("_", "-"),
            "marginCoin": "USDT",
        }
        return await self._request("POST", endpoint, data=data)
    
    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: float,
        order_type: str = "market",
        price: float | None = None,
        reduce_only: bool = False,
        force: str | None = None,  # "post_only" for maker-only orders
        product_type: str = "USDT-FUTURES",
        stop_loss_price: float
        | None = None,  # DEPRECATED: Use place_tpsl_order() instead
        take_profit_price: float
        | None = None,  # DEPRECATED: Use place_tpsl_order() instead
    ) -> dict[str, Any]:
        """
        Place order - SIMPLIFIED for isolated margin.

        🚨 NOTE: TP/SL should be placed separately using place_tpsl_order()
        for visibility and guaranteed market execution.
        
        Args:
            force: "post_only" for maker-only orders (returns error if would take liquidity)
        """
        endpoint = "/api/v2/mix/order/place-order"

        # 🚀 ALLOW LIMIT ORDERS for better entry prices (reduces slippage)
        # Use the order_type passed in (limit or market)
        # Default to market if not specified
        if not order_type:
            order_type = "market"

        logger.info(
            f"🔍 [BITGET_REST] place_order called: symbol={symbol}, side={side}, "
            f"order_type={order_type}, size={size}, price={price}, force={force}"
        )

        # SIMPLIFIED: Just basic parameters for isolated margin
        data = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "side": side,
            "orderType": order_type,
            "size": str(size),
        }

        if price:
            data["price"] = str(price)

        if reduce_only:
            data["reduceOnly"] = "YES"
        
        # Add force parameter for post-only orders
        if force == "post_only":
            data["force"] = "post_only"

        # 🚨 NOTE: We use separate place_tpsl_order() for TP/SL (visible in app)
        # Atomic TP/SL (presetTakeProfitPrice/presetStopLossPrice) is NOT used
        # because it doesn't guarantee market execution or visibility

        # Log EXACT data being sent to API
        logger.info(f"🚨 [API REQUEST] Sending to Bitget: {data}")

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
                        logger.warning(
                            f"failed_to_cancel_order_{order_id}", error=str(e)
                        )

            logger.info(
                "cancelled_stuck_orders",
                symbol=symbol,
                count=cancelled_count,
            )
            return {"code": "00000", "msg": f"Cancelled {cancelled_count} stuck orders"}

        except Exception as e:
            logger.error("cancel_orders_error", symbol=symbol, error=str(e))
            return {"code": "error", "msg": str(e)}

    async def verify_stop_loss_order(
        self,
        symbol: str,
        expected_order_id: str | None = None,
        product_type: str = "usdt-futures",
    ) -> dict[str, Any]:
        """
        Verify that a stop-loss order is actually active on the exchange.
        
        This fixes the root cause of SAPIENUSDT (-42% loss) - stop-loss orders
        can be silently cancelled by the exchange, so we need to verify they exist!
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            expected_order_id: Expected order ID (optional, for verification)
            product_type: Product type (default: "usdt-futures")
            
        Returns:
            {
                "exists": bool,
                "order_id": str | None,
                "trigger_price": float | None,
                "orders": list  # All pending stop-loss orders
            }
        """
        try:
            query_endpoint = "/api/v2/mix/order/orders-plan-pending"
            params = {
                "symbol": symbol,
                "productType": product_type,
                "planType": "pos_loss",  # Stop-loss orders (pos_loss for full position)
            }
            response = await self._request("GET", query_endpoint, params=params)
            
            # Handle API errors gracefully (especially timing issues with Bitget API)
            if response.get("code") != "00000":
                error_code = response.get("code", "UNKNOWN")
                error_msg = response.get("msg", "Unknown error")
                # Error 40812 = "The condition planType is not met" - known timing issue
                # This can happen immediately after placing an order - it's not a critical error
                if error_code == "40812":
                    # This is a known Bitget API timing issue - order might not be registered yet
                    # Return exists=False but don't treat it as a critical error
                    return {"exists": False, "order_id": None, "trigger_price": None, "orders": [], "timing_issue": True}
                # Other errors are more serious
                return {"exists": False, "order_id": None, "trigger_price": None, "orders": []}
            
            orders = response.get("data", {}).get("entrustedList", [])
            
            # Filter for stop-loss orders (pos_loss plan type)
            sl_orders = [o for o in orders if o.get("planType") == "pos_loss"]
            
            if not sl_orders:
                return {"exists": False, "order_id": None, "trigger_price": None, "orders": []}
            
            # If expected_order_id provided, check if it exists
            if expected_order_id:
                for order in sl_orders:
                    if order.get("orderId") == expected_order_id:
                        return {
                            "exists": True,
                            "order_id": expected_order_id,
                            "trigger_price": float(order.get("triggerPrice", 0)),
                            "orders": sl_orders,
                        }
                # Expected order not found, but other orders exist
                first_order = sl_orders[0]
                return {
                    "exists": False,  # Expected order not found
                    "order_id": first_order.get("orderId"),
                    "trigger_price": float(first_order.get("triggerPrice", 0)),
                    "orders": sl_orders,
                }
            
            # No expected order ID, just return first stop-loss order
            first_order = sl_orders[0]
            return {
                "exists": True,
                "order_id": first_order.get("orderId"),
                "trigger_price": float(first_order.get("triggerPrice", 0)),
                "orders": sl_orders,
            }
            
        except Exception as e:
            logger.error(f"Failed to verify stop-loss order for {symbol}: {e}")
            return {"exists": False, "order_id": None, "trigger_price": None, "orders": []}

    async def cancel_all_tpsl_orders(
        self,
        symbol: str,
        product_type: str = "usdt-futures",  # FIXED: lowercase format required
    ) -> dict[str, Any]:
        """
        Cancel ALL TP/SL orders for a symbol.

        CRITICAL: Use this on startup to clear old TP/SL orders with wrong values!
        Old exchange-side orders override bot-side monitoring.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            product_type: Product type (default: "usdt-futures" - lowercase required!)

        Returns:
            Cancellation response
        """
        endpoint = "/api/v2/mix/order/cancel-plan-order"

        # Query existing TP/SL orders first
        try:
            query_endpoint = "/api/v2/mix/order/orders-plan-pending"
            params = {
                "symbol": symbol,
                "productType": product_type,  # "usdt-futures" (lowercase)
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
                        logger.warning(
                            f"failed_to_cancel_tpsl_order_{order_id}", error=str(e)
                        )

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
        hold_side: str,  # "long" or "short" - which position to protect (will be converted to "buy"/"sell")
        size: float,  # Position size in contracts
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        product_type: str = "usdt-futures",  # FIXED: lowercase format required by API
        size_precision: int
        | None = None,  # Size precision (decimal places) - if None, will round to 1 decimal
        force_plan_type: str | None = None,  # Optional: override planType for SL ('pos_loss' or 'loss_plan')
    ) -> dict[str, Any]:
        """
        Place exchange-side TP/SL plan orders that execute at MARKET on trigger.
        Visible under Conditional/Plan Orders in the app.

        🚨 CRITICAL: These execute on Bitget servers as MARKET orders when triggered!
        With 25x leverage, this prevents liquidations if bot crashes.

        Bitget requires SEPARATE orders for SL and TP - we place 2 orders.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            hold_side: "long" or "short" - which position to protect (converted to "buy"/"sell" for API)
            size: Position size in contracts (must match position size!)
            stop_loss_price: Stop loss trigger price (optional)
            take_profit_price: Take profit trigger price (optional)
            product_type: Product type (default: "usdt-futures" - lowercase required!)

        Returns:
            Dict with results of both orders
        """
        endpoint = "/api/v2/mix/order/place-tpsl-order"
        results: dict[str, Any] = {"sl": None, "tp": None}

        # Fetch symbol contract info for correct size/price scales
        volume_places = None
        price_places = None
        price_end_step: float | None = None
        try:
            contract = await self.get_symbol_info(symbol, product_type="USDT-FUTURES")
            if contract:
                # Bitget uses 'volumePlace' for size decimals, 'pricePlace' for price decimals
                if contract.get("volumePlace") is not None:
                    try:
                        volume_places = int(contract.get("volumePlace"))
                    except Exception:
                        volume_places = None
                if contract.get("pricePlace") is not None:
                    try:
                        price_places = int(contract.get("pricePlace"))
                    except Exception:
                        price_places = None
                # priceEndStep is the minimum tick size
                if contract.get("priceEndStep") is not None:
                    try:
                        price_end_step = float(contract.get("priceEndStep"))
                    except Exception:
                        price_end_step = None
        except Exception:
            pass

        # Determine size precision
        if size_precision is None:
            if volume_places is not None:
                size_precision = max(0, int(volume_places))
            else:
                # Fallback: infer from value
                size_str = f"{size:.10f}".rstrip('0').rstrip('.')
                size_precision = len(size_str.split('.')[1]) if '.' in size_str else 0
        rounded_size = round(size, size_precision)

        # Round trigger prices to price precision if available
        def _round_price(val: float | None) -> float | None:
            if val is None:
                return None
            places = int(price_places) if price_places is not None else 4
            try:
                return round(float(val), places)
            except Exception:
                return round(float(val), 4)
        stop_loss_price = _round_price(stop_loss_price)
        take_profit_price = _round_price(take_profit_price)

        # Helper to derive a tick size if priceEndStep unavailable
        def _tick_size() -> float:
            if price_end_step and price_end_step > 0:
                return float(price_end_step)
            places = int(price_places) if price_places is not None else 4
            return 10 ** (-places)

        # Helper to fetch a robust current price (prefer mark)
        async def _get_current_price() -> float | None:
            try:
                t = await self.get_ticker(symbol, product_type="USDT-FUTURES")
                if t.get("code") == "00000":
                    data = t.get("data") or {}
                    # Try common keys in order of preference
                    for k in (
                        "markPr",
                        "markPrice",
                        "lastPr",
                        "last",
                        "close",
                        "bestAsk",
                        "bestBid",
                        "price",
                    ):
                        v = data.get(k)
                        if v is None:
                            continue
                        try:
                            return float(v)
                        except Exception:
                            try:
                                # Some fields may be nested strings
                                return float(str(v))
                            except Exception:
                                continue
            except Exception:
                return None
            return None

        # 🚨 EXTENSIVE LOGGING: Log all input parameters
        logger.info(
            f"🔍 [TP/SL START] {symbol} | "
            f"hold_side: {hold_side} | size: {size} → rounded: {rounded_size} (precision: {size_precision}) | "
            f"SL price: {stop_loss_price} | TP price: {take_profit_price} | "
            f"product_type: {product_type}"
        )

        # 🚨 CRITICAL FIX: Convert "long"/"short" to "buy"/"sell" for one-way mode
        # According to Bitget API docs, holdSide should be "buy" for long, "sell" for short in one-way mode
        api_hold_side = "buy" if hold_side == "long" else "sell"

        logger.info(
            f"🔧 [TP/SL CONVERSION] {symbol} | hold_side: {hold_side} → API holdSide: {api_hold_side}"
        )

        # Helper to post plan order with fallback triggerType and size precision
        async def _post_plan(
            data: dict[str, str], order_type: str, original_size: float
        ) -> dict[str, Any]:
            # Log EXACT data being sent
            logger.info(
                f"📤 [TP/SL REQUEST] {symbol} | {order_type} | " f"Data: {data}"
            )

            # First try mark_price (safer)
            data["triggerType"] = "mark_price"
            try:
                logger.info(
                    f"🔄 [TP/SL TRY] {symbol} | {order_type} | triggerType: mark_price"
                )
                response = await self._request("POST", endpoint, data=data)
                logger.info(
                    f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                    f"Full response: {response}"
                )
                return response
            except Exception as e:
                error_msg = str(e)
                # If take profit validation error, nudge trigger to valid side vs current price
                if any(code in error_msg for code in ("45135", "40832", "40915")):
                    try:
                        cur_px = await _get_current_price()
                        if cur_px:
                            hold = data.get("holdSide")  # 'buy' for long, 'sell' for short
                            trig = float(data.get("triggerPrice", "0"))
                            tick = _tick_size()
                            if hold == "buy":
                                # LONG: TP must be ABOVE current price
                                if trig <= cur_px:
                                    trig = cur_px + tick
                            else:
                                # SHORT: TP must be BELOW current price
                                if trig >= cur_px:
                                    trig = cur_px - tick
                            # Round to exchange precision
                            trig = _round_price(trig) or trig
                            data["triggerPrice"] = str(trig)
                            logger.info(
                                f"🔧 [TP VALIDATION ADJUST] {symbol} | New TP trigger={trig} (tick={tick}, cur={cur_px})"
                            )
                            # Retry once immediately after adjustment
                            response = await self._request("POST", endpoint, data=data)
                            logger.info(
                                f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                                f"Retry after validation adjust: {response}"
                            )
                            return response
                    except Exception as _adj_err:
                        logger.debug(f"TP adjust failed: {_adj_err}")
                # Check if it's a checkScale error - try different precision
                if "checkBDScale" in error_msg or "checkScale" in error_msg:
                    logger.warning(
                        f"⚠️  [TP/SL PRECISION ERROR] {symbol} | {order_type} | "
                        f"checkScale error: {error_msg} | Trying different precision..."
                    )
                    # Try to adapt trigger price rounding to the required checkScale decimals if present
                    import re as _re
                    m = _re.search(r"checkScale=([0-9]+)", error_msg)
                    new_price_places: int | None = None
                    if m:
                        try:
                            new_price_places = int(m.group(1))
                        except Exception:
                            new_price_places = None
                    # If we detected a required price scale, round triggerPrice accordingly and retry once
                    if new_price_places is not None and "triggerPrice" in data:
                        try:
                            tp_val = float(data.get("triggerPrice", "0"))
                            tp_rounded = round(tp_val, new_price_places)
                            if tp_rounded <= 0 and tp_val > 0:
                                # Ensure we don't zero out; nudge minimally
                                tp_rounded = float(f"{tp_val:.{new_price_places}f}")
                            data["triggerPrice"] = str(tp_rounded)
                            logger.info(
                                f"🔧 [TP/SL RETRY] {symbol} | {order_type} | "
                                f"Adjusted triggerPrice to {tp_rounded} (checkScale={new_price_places})"
                            )
                            response = await self._request("POST", endpoint, data=data)
                            logger.info(
                                f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                                f"Retry with adjusted triggerPrice successful: {response}"
                            )
                            return response
                        except Exception as e_adj:
                            logger.warning(
                                f"⚠️ [TP/SL PRICE ROUND RETRY FAILED] {symbol} | {order_type} | "
                                f"error={e_adj}"
                            )
                    # Try a range of reasonable precisions based on volume_places
                    candidates = []
                    base = size_precision if size_precision is not None else 0
                    # Build candidate precision list: [volume_places, base, base-1..0, base+1..base+3]
                    if volume_places is not None:
                        candidates.append(max(0, int(volume_places)))
                    if base not in candidates:
                        candidates.append(max(0, int(base)))
                    for p in range(max(0, base - 3), base + 4):
                        if p not in candidates and p >= 0:
                            candidates.append(p)
                    for new_precision in candidates:
                        try:
                            new_rounded_size = round(original_size, new_precision)
                            logger.info(
                                f"🔄 [TP/SL RETRY] {symbol} | {order_type} | "
                                f"Trying precision {new_precision} (rounded size: {new_rounded_size})"
                            )
                            data["size"] = str(new_rounded_size)
                            response = await self._request("POST", endpoint, data=data)
                            logger.info(
                                f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                                f"Retry successful! Full response: {response}"
                            )
                            return response
                        except Exception as e3:
                            logger.warning(
                                f"⚠️ [TP/SL RETRY PRECISION FAILED] {symbol} | {order_type} | "
                                f"precision={new_precision} error={e3}"
                            )
                    logger.error(
                        f"❌ [TP/SL RETRY FAILED] {symbol} | {order_type} | "
                        f"All precision candidates failed"
                    )
                    raise
                else:
                    logger.warning(
                        f"⚠️  [TP/SL FALLBACK] {symbol} | {order_type} | "
                        f"mark_price failed: {e} | Trying market_price..."
                    )
                    # Fallback to market_price if exchange rejects mark_price
                    data["triggerType"] = "market_price"
                    try:
                        logger.info(
                            f"🔄 [TP/SL TRY] {symbol} | {order_type} | triggerType: market_price"
                        )
                        response = await self._request("POST", endpoint, data=data)
                        logger.info(
                            f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                            f"Full response: {response}"
                        )
                        return response
                    except Exception as e2:
                        logger.error(
                            f"❌ [TP/SL FAILED] {symbol} | {order_type} | "
                            f"Both triggerType attempts failed: {e2}"
                        )
                        raise

        # Place STOP-LOSS order (separate order #1)
        # Place STOP-LOSS order with retry logic
        if stop_loss_price is not None:
            # 🎯 USE pos_loss FOR FULL POSITION STOP-LOSS (Gesamter TP/SL)!
            sl_data: dict[str, str] = {
                "symbol": symbol,
                "productType": product_type,  # "usdt-futures" (lowercase)
                "marginMode": "isolated",  # Match our trading mode
                "marginCoin": "USDT",
                "planType": "pos_loss",  # default; may be overridden below
                "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
                "triggerPrice": str(stop_loss_price),
                "triggerType": "mark_price",  # Trigger type for pos_loss
                # 🚨 NO size parameter for pos_loss = applies to ENTIRE position!
                # 🚨 NO executePrice for pos_loss = executes at market automatically!
            }
            # If caller requests a backup SL using loss_plan, include size
            if force_plan_type == "loss_plan":
                sl_data["planType"] = "loss_plan"
                sl_data["size"] = str(rounded_size)

            # Pre-send validation: ensure SL trigger is on correct side of current price
            try:
                cur_px = await _get_current_price()
                if cur_px:
                    trig_sl = float(sl_data["triggerPrice"])
                    tick = _tick_size()
                    if api_hold_side == "buy":
                        # LONG SL must be BELOW current price
                        if trig_sl >= cur_px:
                            trig_sl = cur_px - tick
                    else:
                        # SHORT SL must be ABOVE current price
                        if trig_sl <= cur_px:
                            trig_sl = cur_px + tick
                    trig_sl = _round_price(trig_sl) or trig_sl
                    sl_data["triggerPrice"] = str(trig_sl)
                    logger.info(
                        f"🔧 [SL VALIDATION ADJUST] {symbol} | planType={sl_data['planType']} | New SL trigger={trig_sl}"
                    )
            except Exception:
                pass
            logger.info(
                f"📋 [STOP-LOSS ORDER - GESAMTER TP/SL MODE!] {symbol} | "
                f"planType={sl_data['planType']} | "
                f"holdSide={api_hold_side}, triggerPrice={stop_loss_price}, "
                f"App will show 'Gesamter TP/SL' for SL!"
            )
            # Retry logic for SL placement
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    results["sl"] = await _post_plan(sl_data, "STOP-LOSS", size)
                    code = results["sl"].get("code") if results["sl"] else "NO_CODE"
                    msg = results["sl"].get("msg") if results["sl"] else "NO_MSG"
                    data = results["sl"].get("data") if results["sl"] else None
                    if code == "00000":
                        order_id = data.get('orderId', 'N/A') if data else 'N/A'
                        logger.info(
                            f"✅ [GESAMTER SL PLACED!] {symbol} @ ${stop_loss_price:.4f} | "
                            f"planType=pos_loss (FULL POSITION!) | "
                            f"holdSide: {api_hold_side} | "
                            f"Order ID: {order_id}"
                        )
                        logger.warning(
                            f"🔍 [DEBUG] CHECK BITGET APP: Is SL order ID {order_id} visible in TP/SL tab for {symbol}? "
                            f"If NOT visible = order was silently cancelled!"
                        )
                        break  # Success, exit retry loop
                    else:
                        # Check for "Insufficient position" error (43023) - needs longer wait
                        if code == "43023" or "Insufficient position" in msg:
                            logger.warning(
                                f"⚠️  [EXCHANGE SL ERROR 43023] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                                f"Insufficient position error - position may not be fully available yet. "
                                f"Waiting longer before retry..."
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(
                                    3.0
                                )  # Wait longer for position to become available
                            else:
                                logger.error(
                                    f"❌ [EXCHANGE SL FAILED] {symbol} | "
                                    f"Failed after {max_retries} attempts! Code: {code} | Msg: {msg} | "
                                    f"Position may not be fully available on exchange yet."
                                )
                        else:
                            logger.warning(
                                f"⚠️  [EXCHANGE SL ERROR] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                                f"API returned error code: {code} | Message: {msg} | Full response: {results['sl']}"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1.0)  # Wait before retry
                            else:
                                logger.error(
                                    f"❌ [EXCHANGE SL FAILED] {symbol} | "
                                    f"Failed after {max_retries} attempts! Code: {code} | Msg: {msg}"
                                )
                except Exception as e:
                    logger.warning(
                        f"⚠️  [EXCHANGE SL EXCEPTION] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                        f"Exception: {e} | Type: {type(e).__name__}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)  # Wait before retry
                    else:
                        logger.error(
                            f"❌ [EXCHANGE SL FAILED] {symbol} | "
                            f"Failed after {max_retries} attempts! Exception: {e}"
                        )
                        results["sl"] = {"code": "error", "msg": str(e)}

        # Place TAKE-PROFIT order with retry logic
        if take_profit_price is not None:
            # 🚨 CRITICAL FIX: We MUST send 'size' for TP orders!
            # For RECOVERED positions, Bitget API requires size parameter (error 40019 if missing)
            # Sending size = full position size makes it apply to entire position
            # Round TP price to correct price precision
            take_profit_price = _round_price(take_profit_price)
            tp_data: dict[str, str] = {
                "symbol": symbol,
                "productType": product_type,  # "usdt-futures" (lowercase)
                "marginMode": "isolated",
                "marginCoin": "USDT",
                "planType": "profit_plan",  # TAKE-PROFIT type
                "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
                "triggerPrice": str(take_profit_price),
                "triggerType": "mark_price",  # Trigger type
                "size": str(rounded_size),  # MUST include size for recovered positions!
                # 🚨 NO executePrice = executes at market automatically!
            }
            # Pre-send validation: ensure TP trigger is on correct side of current price
            try:
                cur_px = await _get_current_price()
                if cur_px:
                    trig_tp = float(tp_data["triggerPrice"])
                    tick = _tick_size()
                    if api_hold_side == "buy":
                        # LONG TP must be ABOVE current price
                        if trig_tp <= cur_px:
                            trig_tp = cur_px + tick
                    else:
                        # SHORT TP must be BELOW current price
                        if trig_tp >= cur_px:
                            trig_tp = cur_px - tick
                    trig_tp = _round_price(trig_tp) or trig_tp
                    tp_data["triggerPrice"] = str(trig_tp)
                    logger.info(
                        f"🔧 [TP VALIDATION ADJUST] {symbol} | planType=profit_plan | New TP trigger={trig_tp}"
                    )
            except Exception:
                pass
            logger.info(
                f"📋 [TAKE-PROFIT ORDER] {symbol} | "
                f"planType=profit_plan | size={rounded_size} | "
                f"holdSide={api_hold_side}, triggerPrice={take_profit_price}"
            )
            # Retry logic for TP placement
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    results["tp"] = await _post_plan(tp_data, "TAKE-PROFIT", size)
                    code = results["tp"].get("code") if results["tp"] else "NO_CODE"
                    msg = results["tp"].get("msg") if results["tp"] else "NO_MSG"
                    data = results["tp"].get("data") if results["tp"] else None
                    if code == "00000":
                        logger.info(
                            f"✅ [EXCHANGE TP] {symbol} @ ${take_profit_price:.4f} | "
                            f"Size: {size:.4f} | holdSide: {api_hold_side} | "
                            f"Code: {code} | Msg: {msg} | Data: {data}"
                        )
                        break  # Success, exit retry loop
                    else:
                        # Check for "Insufficient position" error (43023) - needs longer wait
                        if code == "43023" or "Insufficient position" in msg:
                            logger.warning(
                                f"⚠️  [EXCHANGE TP ERROR 43023] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                                f"Insufficient position error - position may not be fully available yet. "
                                f"Waiting longer before retry..."
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(
                                    3.0
                                )  # Wait longer for position to become available
                            else:
                                logger.error(
                                    f"❌ [EXCHANGE TP FAILED] {symbol} | "
                                    f"Failed after {max_retries} attempts! Code: {code} | Msg: {msg} | "
                                    f"Position may not be fully available on exchange yet."
                                )
                        else:
                            logger.warning(
                                f"⚠️  [EXCHANGE TP ERROR] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                                f"API returned error code: {code} | Message: {msg} | Full response: {results['tp']}"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1.0)  # Wait before retry
                            else:
                                logger.error(
                                    f"❌ [EXCHANGE TP FAILED] {symbol} | "
                                    f"Failed after {max_retries} attempts! Code: {code} | Msg: {msg}"
                                )
                except Exception as e:
                    logger.warning(
                        f"⚠️  [EXCHANGE TP EXCEPTION] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                        f"Exception: {e} | Type: {type(e).__name__}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)  # Wait before retry
                    else:
                        logger.error(
                            f"❌ [EXCHANGE TP FAILED] {symbol} | "
                            f"Failed after {max_retries} attempts! Exception: {e}"
                        )
                        results["tp"] = {"code": "error", "msg": str(e)}

        # 🚨 CRITICAL: Return results dict with SL and TP order results
        return results

    async def place_trailing_take_profit_order(
        self,
        symbol: str,
        hold_side: str,  # "long" or "short" - which position to protect (converted to "buy"/"sell")
        size: float,  # Position size in contracts
        range_rate: float,  # Trailing take profit range rate as decimal (e.g., 0.015 = 1.5%, will be converted to "1.50")
        trigger_price: float,  # Price at which trailing take profit becomes active
        product_type: str = "usdt-futures",  # FIXED: lowercase format required by API
        size_precision: int | None = None,  # Size precision (decimal places)
    ) -> dict[str, Any]:
        """
        Place exchange-side trailing take profit order using Bitget's moving_plan API.

        🚨 WARNING: This uses place-tpsl-order endpoint which may show as "Partial" in Bitget app!
        
        For TRUE "Gesamter TP/SL" (Full) mode, use place_trailing_stop_full_position() instead!
        
        This method uses:
        - Endpoint: /api/v2/mix/order/place-tpsl-order
        - planType: "moving_plan"
        - May display as "Teilweise TP/SL" (Partial) in app even with exact size
        
        The trailing take profit will automatically adjust as price moves in your favor!

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            hold_side: "long" or "short" - which position to protect (converted to "buy"/"sell" for API)
            size: Position size in contracts (must match position size!)
            range_rate: Trailing take profit range rate as decimal (e.g., 0.015 = 1.5%, will be converted to "1.50")
            trigger_price: Price at which trailing take profit becomes active
            product_type: Product type (default: "usdt-futures" - lowercase required!)
            size_precision: Size precision (decimal places) - if None, will infer from size

        Returns:
            Dict with order result
        """
        endpoint = "/api/v2/mix/order/place-tpsl-order"

        # Round size to correct precision
        # 🚨 CRITICAL: Must preserve all significant digits to avoid rounding to 0!
        if size_precision is None:
            # Convert to string and count decimal places
            size_str = f"{size:.10f}".rstrip('0').rstrip('.')
            if '.' in size_str:
                size_precision = len(size_str.split('.')[1])
            else:
                size_precision = 0
            # Ensure at least the precision needed to represent the number
            size_precision = max(size_precision, 0)
        rounded_size = round(size, size_precision)

        # Convert "long"/"short" to "buy"/"sell" for one-way mode
        api_hold_side = "buy" if hold_side == "long" else "sell"

        # 🚨 CRITICAL: Bitget API requires rangeRate as percentage with exactly 2 decimal places
        # Convert decimal to percentage: 0.015 → "1.50", 0.02 → "2.00", 0.001 → "0.10"
        formatted_range_rate = f"{range_rate * 100:.2f}"  # Convert to percentage and format to 2 decimal places

        # Pre-send validation: ensure trigger is valid vs current price and tick
        async def _get_current_price() -> float | None:
            try:
                t = await self.get_ticker(symbol, product_type="USDT-FUTURES")
                if t.get("code") == "00000":
                    data = t.get("data") or {}
                    for k in ("markPr", "markPrice", "lastPr", "last", "close", "bestAsk", "bestBid", "price"):
                        v = data.get(k)
                        if v is None:
                            continue
                        try:
                            return float(v)
                        except Exception:
                            try:
                                return float(str(v))
                            except Exception:
                                continue
            except Exception:
                return None
            return None

        # Try to fetch contract for tick/precision
        price_places = None
        price_end_step = None
        try:
            contract = await self.get_symbol_info(symbol, product_type="USDT-FUTURES")
            if contract:
                if contract.get("pricePlace") is not None:
                    try:
                        price_places = int(contract.get("pricePlace"))
                    except Exception:
                        price_places = None
                if contract.get("priceEndStep") is not None:
                    try:
                        price_end_step = float(contract.get("priceEndStep"))
                    except Exception:
                        price_end_step = None
        except Exception:
            pass

        def _round_price_local(val: float) -> float:
            try:
                places = int(price_places) if price_places is not None else 4
                return round(float(val), places)
            except Exception:
                return round(float(val), 4)

        def _tick_size() -> float:
            if price_end_step and price_end_step > 0:
                return float(price_end_step)
            places = int(price_places) if price_places is not None else 4
            return 10 ** (-places)

        try:
            cur_px = await _get_current_price()
            if cur_px:
                tick = _tick_size()
                # For trailing activation:
                # - LONG ('buy'): activation must be >= current price (nudge above)
                # - SHORT ('sell'): activation must be <= current price (nudge below)
                if api_hold_side == "buy":
                    if trigger_price <= cur_px:
                        trigger_price = cur_px + tick
                else:
                    if trigger_price >= cur_px:
                        trigger_price = cur_px - tick
                trigger_price = _round_price_local(trigger_price)
                logger.info(
                    f"🔧 [TRAILING TRIGGER ADJUST] {symbol} | side={api_hold_side} | activation={trigger_price} (cur={cur_px})"
                )
        except Exception:
            pass

        # 🚨 CRITICAL: Size parameter IS REQUIRED by Bitget API (error 40019 if omitted)!
        # "Gesamter TP/SL" vs "Teilweise TP/SL" display in app is determined by:
        # - size EXACTLY matches position → app shows it as "Gesamter TP/SL" ✅
        # - size != position → app shows it as "Teilweise TP/SL" ❌
        # 
        # The key is ensuring size precision is PERFECT to match the position exactly!
        data = {
            "symbol": symbol,
            "productType": product_type,  # "usdt-futures" (lowercase)
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "planType": "moving_plan",  # Trailing take profit order type
            "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
            "size": str(rounded_size),  # MUST match position size EXACTLY for "Gesamter TP/SL" mode!
            "rangeRate": formatted_range_rate,  # Trailing callback rate as percentage (e.g., "2.00" = 2%, "1.50" = 1.5%, must be 2 decimal places!)
            "triggerPrice": str(
                trigger_price
            ),  # Price at which trailing TP becomes active (Rückrufpreis)
            "triggerType": "mark_price",  # Use mark price for triggering
            # NOTE: reduceOnly is NOT supported for plan orders on Bitget - it's silently ignored
        }

        logger.info(
            f"🧵 [TRAILING TP ORDER] {symbol} | "
            f"planType=moving_plan | "
            f"size: {size} → rounded: {rounded_size} (MUST match position EXACTLY for 'Gesamter TP/SL'!) | "
            f"hold_side: {hold_side} → API holdSide: {api_hold_side} | "
            f"callback_rate: {range_rate*100:.2f}% (Rückrufquote) → API: {formatted_range_rate} | "
            f"trigger_price: {trigger_price} (activation price) | "
            f"product_type: {product_type}"
        )

        # Retry logic for trailing TP placement
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._request("POST", endpoint, data=data)
                code = response.get("code", "N/A")
                msg = response.get("msg", "N/A")
                data_resp = response.get("data", {})

                if code == "00000":
                    logger.info(
                        f"✅ [TRAILING TP PLACED] {symbol} | "
                        f"planType=moving_plan | "
                        f"size={rounded_size} (if matches position → 'Gesamter TP/SL' in app) | "
                        f"Callback Rate: {range_rate*100:.2f}% (Rückrufquote) | "
                        f"Trigger Price: {trigger_price} (activation) | "
                        f"Order ID: {data_resp.get('orderId', 'N/A')}"
                    )
                    return response
                else:
                    # Check for "Insufficient position" error - needs longer wait
                    if code == "43023" or "Insufficient position" in str(msg):
                        wait_time = 3.0 * (
                            attempt + 1
                        )  # Exponential backoff: 3s, 6s, 9s
                        logger.warning(
                            f"⚠️ [TRAILING TP ERROR 43023] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                            f"Insufficient position - waiting {wait_time:.1f}s before retry..."
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                    # Check for "rangeRate must 2 decimal places" error (43011)
                    elif code == "43011" or "rangeRate must 2 decimal places" in str(
                        msg
                    ):
                        logger.warning(
                            f"⚠️ [TRAILING TP ERROR 43011] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                            f"rangeRate format error - should be 2 decimal places. Current: {formatted_range_rate} | "
                            f"Original: {range_rate} | Reformatting..."
                        )
                        # Reformat range_rate as percentage to exactly 2 decimal places
                        formatted_range_rate = f"{range_rate * 100:.2f}"
                        data["rangeRate"] = formatted_range_rate
                        logger.info(
                            f"🔄 [TRAILING TP REFORMAT] {symbol} | New rangeRate: {formatted_range_rate}"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1.0)  # Short wait before retry
                            continue
                    # Check for "trigger price should be ≥ current market price" error (43035)
                    elif (
                        code == "43035" or "trigger price should be" in str(msg).lower()
                    ):
                        logger.warning(
                            f"⚠️ [TRAILING TP ERROR 43035] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                            f"Trigger price too low - caller should fetch fresh price and recalculate trigger price"
                        )
                        # Return error so caller can handle it (fetch fresh price and retry)
                        return response
                    else:
                        logger.error(
                            f"❌ [TRAILING TAKE PROFIT FAILED] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                            f"Code: {code} | Msg: {msg} | Full response: {response}"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2.0)  # Wait before retry
                            continue
                        else:
                            return response  # Return failed response after all retries
            except Exception as e:
                logger.warning(
                    f"⚠️ [TRAILING TAKE PROFIT EXCEPTION] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                    f"Exception: {e} | Type: {type(e).__name__}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)  # Wait before retry
                    continue
                else:
                    logger.error(
                        f"❌ [TRAILING TAKE PROFIT EXCEPTION] {symbol} | "
                        f"Failed after {max_retries} attempts! Exception: {e}"
                    )
                    return {"code": "error", "msg": str(e)}

        # Should never reach here, but return error if we do
        return {"code": "error", "msg": "Failed after all retries"}

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

    async def place_trailing_stop_full_position(
        self,
        symbol: str,
        hold_side: str,  # "long" or "short" - which position we're closing
        callback_ratio: float,  # Callback rate as decimal (e.g., 0.10 = 10%, MAX 0.10!)
        trigger_price: float,  # Activation price
        size: float,  # Position size in contracts
        size_precision: int | None = None,
        product_type: str = "USDT-FUTURES",  # UPPERCASE for place-plan-order!
    ) -> dict[str, Any]:
        """
        Place NORMAL TRAILING order using track_plan (shows in "Trailing" tab).
        
        🎯 DEFINITIVE ANSWER from Bitget API documentation:
        
        - Endpoint: /api/v2/mix/order/place-plan-order (NOT place-tpsl-order!)
        - planType: "track_plan" (Bitget's official "trailing stop order")
        - callbackRatio: Max 10% (0.10), sent as percentage string
        - Shows in: "Trailing" tab in Bitget app (NOT "Entire TP/SL")
        - Behavior: TRUE trailing that closes FULL position
        
        This is Bitget's "Normal Trailing TP" that you see in the app!
        
        Args:
            symbol: Trading pair
            hold_side: "long" or "short" - position to protect
            callback_ratio: Trailing callback (0.01-0.10 = 1-10%)
            trigger_price: Activation price
            size: Position size in contracts
            size_precision: Size precision
            product_type: "USDT-FUTURES" (uppercase for this endpoint!)
            
        Returns:
            API response
        """
        endpoint = "/api/v2/mix/order/place-plan-order"
        
        # Validate callback ratio (max 10% per Bitget docs)
        if callback_ratio <= 0 or callback_ratio > 0.10:
            raise ValueError(f"callbackRatio must be between 0 and 0.10 (0%-10%). Got: {callback_ratio}")
        
        # Format as percentage string
        callback_str = f"{callback_ratio * 100:.2f}"
        
        # Fetch contract to determine volume/price places
        volume_places = None
        price_places = None
        try:
            contract = await self.get_symbol_info(symbol, product_type=product_type)
            if contract:
                if contract.get("volumePlace") is not None:
                    try:
                        volume_places = int(contract.get("volumePlace"))
                    except Exception:
                        volume_places = None
                if contract.get("pricePlace") is not None:
                    try:
                        price_places = int(contract.get("pricePlace"))
                    except Exception:
                        price_places = None
        except Exception:
            pass

        # Round size to correct precision
        if size_precision is None:
            if volume_places is not None:
                size_precision = max(0, int(volume_places))
            else:
                size_str = f"{size:.10f}".rstrip('0').rstrip('.')
                size_precision = len(size_str.split('.')[1]) if '.' in size_str else 0
        rounded_size = round(size, size_precision)

        # Round trigger price to price precision
        if price_places is not None:
            try:
                trigger_price = round(float(trigger_price), int(price_places))
            except Exception:
                trigger_price = round(float(trigger_price), 4)
        
        # Side to CLOSE the position (opposite of held position)
        side = "sell" if hold_side == "long" else "buy"
        
        data = {
            "planType": "track_plan",  # 🚨 Bitget's official trailing stop order!
            "symbol": symbol,
            "productType": product_type.lower().replace("_", "-"),  # Use lowercase per API
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "size": str(rounded_size),
            "orderType": "market",  # REQUIRED for track_plan
            "price": "",  # MUST be empty for track_plan
            "callbackRatio": callback_str,  # e.g. "10.00" for 10%
            "triggerPrice": str(trigger_price),
            "triggerType": "market_price",  # Use market_price for plan orders
            "side": side,  # "buy" or "sell" to close
        }
        
        logger.info(
            f"🎯 [NORMAL TRAILING TP - track_plan!] {symbol} | "
            f"Endpoint: place-plan-order | "
            f"planType=track_plan (Official Bitget trailing!) | "
            f"side={side} (closes {hold_side} position) | "
            f"size={size} → rounded={rounded_size} | "
            f"callbackRatio={callback_str}% (TRAILS!) | "
            f"trigger={trigger_price} | "
            f"Shows in: 'Trailing' tab (NOT 'TP/SL' tab!)"
        )
        
        # 🚨 RETRY LOGIC: Try up to 3 times to ensure it places!
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._request("POST", endpoint, data=data)
                code = response.get("code", "N/A")
                msg = response.get("msg", "N/A")
                data_resp = response.get("data", {})
                
                if code == "00000":
                    order_id = data_resp.get('orderId', 'N/A')
                    logger.info(
                        f"✅ [NORMAL TRAILING TP PLACED!] {symbol} | "
                        f"planType=track_plan + callbackRatio={callback_str}% | "
                        f"size={rounded_size} (FULL position) | "
                        f"Trigger: {trigger_price} | "
                        f"Order ID: {order_id} | "
                        f"Attempt: {attempt + 1}/{max_retries}"
                    )
                    logger.warning(
                        f"✨ [CHECK APP] {symbol} trailing TP in 'Trailing' tab (NOT TP/SL tab!) "
                        f"with {callback_ratio*100:.1f}% callback!"
                    )
                    return response  # Success, return immediately
                else:
                    # Check for "Insufficient position" error - needs longer wait
                    if code == "43023" or "Insufficient position" in str(msg):
                        if attempt < max_retries - 1:
                            wait_time = 2.0 * (attempt + 1)  # 2s, 4s, 6s
                            logger.warning(
                                f"⚠️ [TP RETRY] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                                f"Insufficient position - waiting {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                            continue
                    
                    logger.error(
                        f"❌ [TRAILING TP FAILED] {symbol} | "
                        f"Attempt {attempt + 1}/{max_retries} | "
                        f"Code: {code} | Msg: {msg}"
                    )
                    
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 Retrying TP placement for {symbol}...")
                        await asyncio.sleep(1.0)
                        continue
                    else:
                        return response  # Final attempt failed, return error response
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ [TP EXCEPTION] {symbol} | Attempt {attempt + 1}/{max_retries} | "
                        f"Exception: {e} | Retrying..."
                    )
                    await asyncio.sleep(1.0)
                    continue
                else:
                    logger.error(
                        f"❌ [TP EXCEPTION] {symbol} | All {max_retries} attempts failed! | "
                        f"Exception: {e}"
                    )
                    raise
        
        # Should never reach here
        return {"code": "error", "msg": "All retries exhausted"}

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
            count=len(response.get("data", []))
            if response.get("code") == "00000"
            else 0,
        )

        return response
