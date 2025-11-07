"""Bitget REST API client with HMAC authentication."""

import asyncio
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
        except TimeoutError:
            logger.error(f"❌ API request timeout: {method} {url}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"❌ API client error: {method} {url} - {e}")
            raise

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

    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: float,
        order_type: str = "market",
        price: float | None = None,
        reduce_only: bool = False,
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

        # 🚨 CRITICAL FIX: Round size to correct precision (Bitget API requires specific decimal places)
        # Different contracts have different checkScale values:
        # - checkScale=0: whole numbers (no decimals) - e.g., THETAUSDT, SUSHIUSDT
        # - checkScale=1: 1 decimal place - e.g., LTCUSDT, BNBUSDT
        # If not specified, try to infer from size value or default to 1
        if size_precision is None:
            # Try to infer: if size is already a whole number or very close, use 0
            # Otherwise default to 1
            if abs(size - round(size)) < 0.01:  # Very close to whole number
                size_precision = 0
            else:
                size_precision = 1  # Default to 1 decimal place
        rounded_size = round(size, size_precision)

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
                # Check if it's a checkScale error - try different precision
                if "checkBDScale" in error_msg or "checkScale" in error_msg:
                    logger.warning(
                        f"⚠️  [TP/SL PRECISION ERROR] {symbol} | {order_type} | "
                        f"checkScale error: {error_msg} | Trying different precision..."
                    )
                    # Try opposite precision (0 vs 1)
                    if size_precision == 0:
                        new_precision = 1
                        new_rounded_size = round(original_size, 1)
                    else:
                        new_precision = 0
                        new_rounded_size = round(original_size, 0)

                    logger.info(
                        f"🔄 [TP/SL RETRY] {symbol} | {order_type} | "
                        f"Trying precision {new_precision} (rounded size: {new_rounded_size})"
                    )
                    data["size"] = str(new_rounded_size)
                    try:
                        response = await self._request("POST", endpoint, data=data)
                        logger.info(
                            f"✅ [TP/SL RESPONSE] {symbol} | {order_type} | "
                            f"Retry successful! Full response: {response}"
                        )
                        return response
                    except Exception as e3:
                        logger.error(
                            f"❌ [TP/SL RETRY FAILED] {symbol} | {order_type} | "
                            f"Both precisions failed: {e3}"
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
            sl_data = {
                "symbol": symbol,
                "productType": product_type,  # "usdt-futures" (lowercase)
                "marginMode": "isolated",  # Match our trading mode
                "marginCoin": "USDT",
                "planType": "loss_plan",  # STOP-LOSS type
                "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
                "triggerPrice": str(stop_loss_price),
                "executePrice": "0",  # MARKET on trigger
                "size": str(rounded_size),  # Size in contracts (will close this amount)
                "reduceOnly": "YES",  # 🚨 CRITICAL: Only close position, never open new one!
            }
            logger.info(
                f"📋 [STOP-LOSS ORDER] {symbol} | "
                f"symbol={symbol}, productType={product_type}, "
                f"marginMode=isolated, planType=loss_plan, "
                f"holdSide={api_hold_side}, triggerPrice={stop_loss_price}, "
                f"executePrice=0 (market), size={rounded_size}, "
                f"reduceOnly=YES (closes position only)"
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
                        logger.info(
                            f"✅ [EXCHANGE SL] {symbol} @ ${stop_loss_price:.4f} | "
                            f"Size: {size:.4f} | holdSide: {api_hold_side} | "
                            f"Code: {code} | Msg: {msg} | Data: {data}"
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
            tp_data = {
                "symbol": symbol,
                "productType": product_type,  # "usdt-futures" (lowercase)
                "marginMode": "isolated",
                "marginCoin": "USDT",
                "planType": "profit_plan",  # TAKE-PROFIT type
                "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
                "triggerPrice": str(take_profit_price),
                "executePrice": "0",  # MARKET on trigger
                "size": str(
                    rounded_size
                ),  # REQUIRED! Must be rounded to correct precision
            }
            logger.info(
                f"📋 [TP/SL TP DATA] {symbol} | "
                f"Building TP order: symbol={symbol}, productType={product_type}, "
                f"marginMode=isolated, marginCoin=USDT, planType=profit_plan, "
                f"holdSide={api_hold_side}, triggerPrice={take_profit_price}, "
                f"executePrice=0, size={size}"
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

        🚨 CRITICAL: This uses the place-tpsl-order endpoint with planType="moving_plan"
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
        if size_precision is None:
            if abs(size - round(size)) < 0.01:
                size_precision = 0
            else:
                size_precision = 1
        rounded_size = round(size, size_precision)

        # Convert "long"/"short" to "buy"/"sell" for one-way mode
        api_hold_side = "buy" if hold_side == "long" else "sell"

        # 🚨 CRITICAL: Bitget API requires rangeRate as percentage with exactly 2 decimal places
        # Convert decimal to percentage: 0.015 → "1.50", 0.02 → "2.00", 0.001 → "0.10"
        formatted_range_rate = f"{range_rate * 100:.2f}"  # Convert to percentage and format to 2 decimal places

        data = {
            "symbol": symbol,
            "productType": product_type,  # "usdt-futures" (lowercase)
            "marginMode": "isolated",
            "marginCoin": "USDT",
            "planType": "moving_plan",  # Trailing take profit order type (normal trailing mode)
            "holdSide": api_hold_side,  # "buy" or "sell" (NOT "long"/"short")
            "size": str(rounded_size),  # Size in contracts (will close this amount)
            "rangeRate": formatted_range_rate,  # Trailing callback rate as percentage (e.g., "2.00" = 2%, "1.50" = 1.5%, must be 2 decimal places!)
            "triggerPrice": str(
                trigger_price
            ),  # Price at which trailing TP becomes active (Rückrufpreis)
            "triggerType": "mark_price",  # Use mark price for triggering
            "reduceOnly": "YES",  # 🚨 CRITICAL: Only close position, never open new one!
        }

        logger.info(
            f"🧵 [TRAILING TP ORDER - NORMAL MODE] {symbol} | "
            f"hold_side: {hold_side} → API holdSide: {api_hold_side} | "
            f"size: {size} → rounded: {rounded_size} | "
            f"callback_rate: {range_rate*100:.2f}% (Rückrufquote) → API: {formatted_range_rate} | "
            f"trigger_price: {trigger_price} (activation price) | "
            f"reduceOnly: YES (closes position only) | "
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
                        f"✅ [TRAILING TP PLACED - NORMAL MODE] {symbol} | "
                        f"Callback Rate: {range_rate*100:.2f}% (Rückrufquote) | "
                        f"Trigger Price: {trigger_price} (activation) | "
                        f"Size: {rounded_size} contracts | "
                        f"reduceOnly: YES | "
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
