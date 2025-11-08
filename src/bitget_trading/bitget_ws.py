"""Bitget WebSocket client for real-time market data."""

import asyncio
import time
from collections import deque
from typing import Any, Callable, Deque

import orjson
import websockets
from websockets.client import WebSocketClientProtocol

from src.bitget_trading.logger import get_logger

logger = get_logger()


class BitgetWebSocketClient:
    """
    Bitget WebSocket client for USDT-M futures market data.
    
    Subscribes to ticker and order book (depth) channels.
    """

    WS_URL = "wss://ws.bitget.com/v2/ws/public"
    PING_INTERVAL = 20  # seconds
    
    def __init__(
        self,
        symbol: str,
        product_type: str = "USDT-FUTURES",
        orderbook_levels: int = 5,
    ) -> None:
        """
        Initialize WebSocket client.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            product_type: Product type (default: "USDT-FUTURES")
            orderbook_levels: Number of order book levels (1, 5, or 15)
        """
        self.symbol = symbol
        self.product_type = product_type
        self.orderbook_levels = orderbook_levels
        
        # WebSocket connection
        self.ws: WebSocketClientProtocol | None = None
        self.is_connected: bool = False
        self.should_run: bool = False
        
        # Data storage
        self.ticker_data: dict[str, Any] = {}
        self.orderbook: dict[str, Any] = {
            "bids": [],
            "asks": [],
            "timestamp": 0,
        }
        
        # Message queue for processing
        self.message_queue: Deque[dict[str, Any]] = deque(maxlen=1000)
        
        # Callbacks
        self.on_ticker: Callable[[dict[str, Any]], None] | None = None
        self.on_orderbook: Callable[[dict[str, Any]], None] | None = None
        
        # Stats
        self.last_ping: float = 0
        self.last_pong: float = 0
        self.messages_received: int = 0

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        try:
            self.ws = await websockets.connect(
                self.WS_URL,
                ping_interval=None,  # We handle pings manually
                max_size=10 * 1024 * 1024,  # 10MB max message size
            )
            self.is_connected = True
            self.should_run = True
            
            logger.info(
                "websocket_connected",
                url=self.WS_URL,
                symbol=self.symbol,
            )
            
            # Subscribe to channels
            await self._subscribe()
            
        except Exception as e:
            logger.error("websocket_connection_failed", error=str(e))
            raise

    async def _subscribe(self) -> None:
        """Subscribe to ticker and order book channels."""
        if not self.ws:
            return
        
        # Subscribe to ticker
        ticker_sub = {
            "op": "subscribe",
            "args": [{
                "instType": self.product_type,
                "channel": "ticker",
                "instId": self.symbol,
            }]
        }
        
        # Subscribe to order book
        depth_channel = f"books{self.orderbook_levels}"
        orderbook_sub = {
            "op": "subscribe",
            "args": [{
                "instType": self.product_type,
                "channel": depth_channel,
                "instId": self.symbol,
            }]
        }
        
        await self.ws.send(orjson.dumps(ticker_sub).decode())
        await self.ws.send(orjson.dumps(orderbook_sub).decode())
        
        logger.info(
            "subscribed_to_channels",
            symbol=self.symbol,
            channels=["ticker", depth_channel],
        )

    async def _send_ping(self) -> None:
        """Send ping to keep connection alive."""
        if self.ws and self.is_connected:
            try:
                await self.ws.send("ping")
                self.last_ping = time.time()
                logger.debug("ping_sent")
            except Exception as e:
                logger.error("ping_failed", error=str(e))

    async def _handle_message(self, message: str) -> None:
        """
        Handle incoming WebSocket message.
        
        Args:
            message: Raw message string
        """
        if message == "pong":
            self.last_pong = time.time()
            logger.debug("pong_received")
            return
        
        try:
            data = orjson.loads(message)
            
            # Handle subscription confirmation
            if data.get("event") == "subscribe":
                logger.info("subscription_confirmed", data=data.get("arg"))
                return
            
            # Handle data messages
            if "data" in data and "arg" in data:
                channel = data["arg"].get("channel")
                payload = data["data"]
                
                if channel == "ticker":
                    await self._handle_ticker(payload)
                elif channel.startswith("books"):
                    await self._handle_orderbook(payload)
            
            self.messages_received += 1
            
        except Exception as e:
            logger.error("message_handling_error", error=str(e), message=message[:200])

    async def _handle_ticker(self, data: list[dict[str, Any]]) -> None:
        """
        Handle ticker data.
        
        Args:
            data: Ticker data array
        """
        if not data:
            return
        
        ticker = data[0]
        
        # Update ticker storage
        self.ticker_data = {
            "symbol": ticker.get("instId"),
            "last_price": float(ticker.get("lastPr", 0)),
            "bid_price": float(ticker.get("bidPr", 0)),
            "ask_price": float(ticker.get("askPr", 0)),
            "mark_price": float(ticker.get("markPrice", 0)),
            "index_price": float(ticker.get("indexPrice", 0)),
            "funding_rate": float(ticker.get("fundingRate", 0)),
            "next_funding_time": int(ticker.get("nextFundingTime", 0)),
            "volume_24h": float(ticker.get("baseVolume", 0)),
            "quote_volume_24h": float(ticker.get("quoteVolume", 0)),
            "open_interest": float(ticker.get("openInterest", 0)),
            "timestamp": int(ticker.get("ts", 0)),
        }
        
        # Call callback if set
        if self.on_ticker:
            self.on_ticker(self.ticker_data)
        
        logger.debug(
            "ticker_updated",
            last=self.ticker_data["last_price"],
            bid=self.ticker_data["bid_price"],
            ask=self.ticker_data["ask_price"],
        )

    async def _handle_orderbook(self, data: list[dict[str, Any]]) -> None:
        """
        Handle order book data.
        
        Args:
            data: Order book data array
        """
        if not data:
            return
        
        book = data[0]
        
        # Update orderbook storage
        self.orderbook = {
            "bids": [[float(p), float(s)] for p, s in book.get("bids", [])],
            "asks": [[float(p), float(s)] for p, s in book.get("asks", [])],
            "timestamp": int(book.get("ts", 0)),
            "checksum": book.get("checksum"),
        }
        
        # Call callback if set
        if self.on_orderbook:
            self.on_orderbook(self.orderbook)
        
        logger.debug(
            "orderbook_updated",
            best_bid=self.orderbook["bids"][0][0] if self.orderbook["bids"] else None,
            best_ask=self.orderbook["asks"][0][0] if self.orderbook["asks"] else None,
            levels=len(self.orderbook["bids"]),
        )

    async def run(self) -> None:
        """Main run loop for WebSocket client."""
        await self.connect()
        
        if not self.ws:
            return
        
        # Start ping task
        ping_task = asyncio.create_task(self._ping_loop())
        
        try:
            while self.should_run:
                try:
                    message = await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=30.0,
                    )
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    logger.warning("websocket_timeout")
                    break
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("websocket_connection_closed")
                    break
                    
        except Exception as e:
            logger.error("websocket_run_error", error=str(e))
        finally:
            ping_task.cancel()
            await self.close()

    async def _ping_loop(self) -> None:
        """Periodic ping loop."""
        while self.should_run:
            await asyncio.sleep(self.PING_INTERVAL)
            await self._send_ping()

    async def close(self) -> None:
        """Close WebSocket connection."""
        self.should_run = False
        self.is_connected = False
        
        if self.ws:
            await self.ws.close()
            logger.info("websocket_closed", messages_received=self.messages_received)

    def get_mid_price(self) -> float:
        """Get mid price from ticker or order book."""
        if self.ticker_data:
            bid = self.ticker_data.get("bid_price", 0)
            ask = self.ticker_data.get("ask_price", 0)
            if bid > 0 and ask > 0:
                return (bid + ask) / 2.0
        
        if self.orderbook["bids"] and self.orderbook["asks"]:
            return (self.orderbook["bids"][0][0] + self.orderbook["asks"][0][0]) / 2.0
        
        return 0.0

    def get_spread_bps(self) -> float:
        """Get spread in basis points."""
        if self.orderbook["bids"] and self.orderbook["asks"]:
            best_bid = self.orderbook["bids"][0][0]
            best_ask = self.orderbook["asks"][0][0]
            mid = (best_bid + best_ask) / 2.0
            if mid > 0:
                return ((best_ask - best_bid) / mid) * 10000.0
        return 0.0

