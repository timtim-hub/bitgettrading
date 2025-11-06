"""Live trading engine with async CCXT integration."""

import asyncio
from datetime import datetime
from typing import Literal

import ccxt.pro as ccxtpro
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from bitget_trading.config import TradingConfig
from bitget_trading.features import create_sequences
from bitget_trading.logger import get_logger
from bitget_trading.model import CNN_LSTM_GRU

logger = get_logger()

PositionType = Literal["long", "short", "flat"]


class LiveTrader:
    """
    Live trading bot with async exchange integration.

    Args:
        config: Trading configuration
        model: Trained neural network model
    """

    def __init__(self, config: TradingConfig, model: CNN_LSTM_GRU) -> None:
        """Initialize live trader."""
        self.config = config
        self.model = model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        self.model.eval()

        # Initialize exchange
        self.exchange = ccxtpro.bitget(
            {
                "apiKey": config.bitget_api_key,
                "secret": config.bitget_api_secret,
                "password": config.bitget_passphrase,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            }
        )

        if config.sandbox:
            self.exchange.set_sandbox_mode(True)
            logger.info("exchange_initialized", mode="sandbox")
        else:
            logger.info("exchange_initialized", mode="live")

        # Trading state
        self.buffer: pd.DataFrame = pd.DataFrame()
        self.position: PositionType = "flat"
        self.entry_price: float = 0.0
        self.position_size: float = 0.0
        self.daily_pnl: float = 0.0
        self.last_day: int = datetime.now().day
        self.is_running: bool = False

    async def start(self) -> None:
        """Start the trading bot."""
        logger.info(
            "trader_starting",
            symbol=self.config.symbol,
            leverage=self.config.leverage,
            timeframe=self.config.timeframe,
        )

        # Validate credentials
        if not self.config.validate_credentials():
            logger.error("invalid_credentials")
            raise ValueError("API credentials not configured")

        # Set leverage on exchange
        try:
            await self.exchange.set_leverage(
                self.config.leverage, self.config.symbol
            )
            logger.info("leverage_set", leverage=self.config.leverage)
        except Exception as e:
            logger.warning("leverage_set_failed", error=str(e))

        self.is_running = True
        await self.watch_klines()

    async def stop(self) -> None:
        """Stop the trading bot gracefully."""
        logger.info("trader_stopping")
        self.is_running = False
        await self.exchange.close()
        logger.info("trader_stopped")

    async def watch_klines(self) -> None:
        """Watch real-time klines and execute trading logic."""
        while self.is_running:
            try:
                # Watch OHLCV data
                klines = await self.exchange.watch_ohlcv(
                    self.config.symbol, self.config.timeframe
                )

                # Process latest candle
                latest = klines[-1]
                candle = pd.DataFrame(
                    [
                        {
                            "timestamp": pd.to_datetime(latest[0], unit="ms"),
                            "open": latest[1],
                            "high": latest[2],
                            "low": latest[3],
                            "close": latest[4],
                            "volume": latest[5],
                        }
                    ]
                )

                # Update buffer
                self.buffer = pd.concat([self.buffer, candle], ignore_index=True)
                if len(self.buffer) > 500:
                    self.buffer = self.buffer.iloc[-500:].reset_index(drop=True)

                # Check if new candle closed (on minute boundary for 1m timeframe)
                if latest[0] % (60 * 1000) == 0 and len(self.buffer) >= self.config.seq_len + 100:
                    await self.execute_trading_logic()

            except Exception as e:
                logger.error("websocket_error", error=str(e))
                await asyncio.sleep(5)

    async def execute_trading_logic(self) -> None:
        """Execute trading logic based on model predictions."""
        try:
            # Reset daily PnL tracking
            if datetime.now().day != self.last_day:
                self.daily_pnl = 0.0
                self.last_day = datetime.now().day
                logger.info("daily_pnl_reset")

            # Check daily loss limit
            if self.daily_pnl <= -self.config.daily_loss_limit:
                logger.warning(
                    "daily_loss_limit_hit",
                    daily_pnl=self.daily_pnl,
                )
                return

            # Generate prediction
            signal = await self._predict_signal()

            if signal is None:
                return

            # Get current balance and position
            balance = await self._get_balance()
            current_position = await self._get_position()
            current_price = self.buffer.iloc[-1]["close"]

            # Calculate position size
            risk_amount = balance * self.config.risk_per_trade
            position_value = risk_amount * self.config.leverage
            qty = position_value / current_price

            # Execute trades based on signal
            if signal == 0 and current_position != "long":  # Go long
                await self._open_long(qty, current_price)

            elif signal == 1 and current_position != "short":  # Go short
                await self._open_short(qty, current_price)

            elif signal == 2 and current_position != "flat":  # Close position
                await self._close_position(current_price)

        except Exception as e:
            logger.error("trading_logic_error", error=str(e))

    async def _predict_signal(self) -> int | None:
        """Generate trading signal from model."""
        if len(self.buffer) < self.config.seq_len + 100:
            logger.debug("insufficient_data", buffer_size=len(self.buffer))
            return None

        # Create sequences
        sequences, _ = create_sequences(
            self.buffer.tail(400), self.config.seq_len
        )

        if len(sequences) == 0:
            return None

        # Get latest sequence
        latest_seq = sequences[-1:]
        dataset = TensorDataset(torch.tensor(latest_seq, dtype=torch.float32))
        loader = DataLoader(dataset, batch_size=1)

        # Predict
        with torch.no_grad():
            for batch in loader:
                batch_data = batch[0].to(self.device)
                outputs = self.model(batch_data)
                probs = torch.softmax(outputs, dim=1)
                signal = torch.argmax(probs, dim=1).item()

                logger.debug(
                    "signal_generated",
                    signal=signal,
                    probs=probs[0].cpu().numpy().tolist(),
                )

                return int(signal)

        return None

    async def _get_balance(self) -> float:
        """Get available USDT balance."""
        balance = await self.exchange.fetch_balance()
        usdt_free = balance["total"].get("USDT", 0.0)
        logger.debug("balance_fetched", usdt=usdt_free)
        return usdt_free

    async def _get_position(self) -> PositionType:
        """Get current position from exchange."""
        positions = await self.exchange.fetch_positions([self.config.symbol])

        if not positions or positions[0]["contracts"] == 0:
            return "flat"

        side = positions[0]["side"]
        if side == "long":
            return "long"
        elif side == "short":
            return "short"

        return "flat"

    async def _open_long(self, qty: float, price: float) -> None:
        """Open long position."""
        try:
            # Close short if exists
            if self.position == "short":
                await self._close_position(price)

            # Open long
            params = {"leverage": self.config.leverage, "reduceOnly": False}
            order = await self.exchange.create_order(
                self.config.symbol, "market", "buy", qty, None, params
            )

            self.position = "long"
            self.entry_price = price
            self.position_size = qty

            logger.info(
                "position_opened",
                side="long",
                price=price,
                size=qty,
                leverage=self.config.leverage,
                order_id=order.get("id"),
            )

        except Exception as e:
            logger.error("open_long_failed", error=str(e))

    async def _open_short(self, qty: float, price: float) -> None:
        """Open short position."""
        try:
            # Close long if exists
            if self.position == "long":
                await self._close_position(price)

            # Open short
            params = {"leverage": self.config.leverage, "reduceOnly": False}
            order = await self.exchange.create_order(
                self.config.symbol, "market", "sell", qty, None, params
            )

            self.position = "short"
            self.entry_price = price
            self.position_size = qty

            logger.info(
                "position_opened",
                side="short",
                price=price,
                size=qty,
                leverage=self.config.leverage,
                order_id=order.get("id"),
            )

        except Exception as e:
            logger.error("open_short_failed", error=str(e))

    async def _close_position(self, price: float) -> None:
        """Close current position."""
        if self.position == "flat":
            return

        try:
            side = "sell" if self.position == "long" else "buy"
            params = {"reduceOnly": True}

            order = await self.exchange.create_order(
                self.config.symbol,
                "market",
                side,
                self.position_size,
                None,
                params,
            )

            # Calculate PnL
            price_change = price - self.entry_price
            if self.position == "short":
                price_change = -price_change

            pnl = price_change * self.position_size * self.config.leverage
            pnl_pct = pnl / (self.position_size * price) if price > 0 else 0.0

            self.daily_pnl += pnl_pct

            logger.info(
                "position_closed",
                side=self.position,
                entry_price=self.entry_price,
                exit_price=price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                order_id=order.get("id"),
            )

            # Reset position
            self.position = "flat"
            self.entry_price = 0.0
            self.position_size = 0.0

        except Exception as e:
            logger.error("close_position_failed", error=str(e))

