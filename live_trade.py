#!/usr/bin/env python3
"""
LIVE TRADING SYSTEM for Bitget USDT-M Futures.

🚨 SAFETY FEATURES:
- Paper trading mode by default
- Daily loss limits
- Position size limits
- Real-time risk monitoring
- Emergency kill switch
- Account balance validation

⚠️ USE AT YOUR OWN RISK - TRADING IS RISKY!
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.bitget_ws import BitgetWebSocket
from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.universe import UniverseManager

logger = setup_logging()


class LiveTrader:
    """Live trading system with safety features."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        initial_capital: float = 50.0,
        leverage: int = 50,
        position_size_pct: float = 0.10,
        max_positions: int = 10,
        daily_loss_limit: float = 0.15,
        paper_mode: bool = True,
    ):
        """Initialize live trader."""
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.daily_loss_limit = daily_loss_limit
        self.paper_mode = paper_mode

        # Components (sandbox=False for production API)
        self.rest_client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
        self.ws_client = BitgetWebSocket()
        self.universe_manager = UniverseManager()
        self.state_manager = MultiSymbolStateManager()
        self.ranker = CrossSectionalRanker()

        # State
        self.equity = initial_capital
        self.initial_equity = initial_capital
        self.positions: dict[str, dict[str, Any]] = {}
        self.trades: list[dict[str, Any]] = []
        self.running = True
        self.start_time = datetime.now()

    async def verify_api_credentials(self) -> bool:
        """Verify API credentials work."""
        try:
            logger.info("🔑 Verifying API credentials...")
            balance = await self.rest_client.get_account_balance()

            if not balance:
                logger.error("❌ Could not fetch account balance - invalid credentials?")
                return False

            logger.info("✅ API credentials verified!")
            logger.info(f"💰 Account balance: ${balance.get('available', 0):.2f} USDT")

            return True

        except Exception as e:
            logger.error(f"❌ API verification failed: {e}")
            return False

    async def check_account_balance(self) -> bool:
        """Check if account has sufficient balance."""
        try:
            balance = await self.rest_client.get_account_balance()
            available = float(balance.get("available", 0))

            logger.info(f"💰 Available balance: ${available:.2f} USDT")

            if available < self.initial_capital:
                logger.error(
                    f"❌ Insufficient balance! Need ${self.initial_capital:.2f}, have ${available:.2f}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Balance check failed: {e}")
            return False

    async def fetch_current_positions(self) -> None:
        """Fetch current positions from exchange."""
        try:
            positions = await self.rest_client.get_positions()

            for pos in positions:
                symbol = pos.get("symbol")
                if not symbol:
                    continue

                # Convert to our format
                self.positions[symbol] = {
                    "symbol": symbol,
                    "side": "long" if pos.get("holdSide") == "long" else "short",
                    "size": float(pos.get("total", 0)),
                    "entry_price": float(pos.get("averageOpenPrice", 0)),
                    "unrealized_pnl": float(pos.get("unrealizedPL", 0)),
                }

            logger.info(f"📊 Current positions: {len(self.positions)}")

        except Exception as e:
            logger.error(f"❌ Failed to fetch positions: {e}")

    async def place_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> bool:
        """Place order (paper or live)."""
        if self.paper_mode:
            # Paper trading
            logger.info(
                f"📝 [PAPER] {side.upper()} {symbol} | Size: {size:.4f} | Price: ${price:.4f}"
            )
            return True
        else:
            # Real trading
            try:
                order_side = "buy" if side == "long" else "sell"
                order = await self.rest_client.place_order(
                    symbol=symbol,
                    side=order_side,
                    order_type="market",
                    size=size,
                    leverage=self.leverage,
                )

                if order:
                    logger.info(
                        f"✅ [LIVE] {side.upper()} {symbol} | Size: {size:.4f} | Order: {order.get('orderId')}"
                    )
                    return True
                else:
                    logger.error(f"❌ Failed to place order for {symbol}")
                    return False

            except Exception as e:
                logger.error(f"❌ Order placement error: {e}")
                return False

    async def close_position(self, symbol: str) -> bool:
        """Close an existing position."""
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        side = "sell" if pos["side"] == "long" else "buy"

        if self.paper_mode:
            logger.info(f"📝 [PAPER] CLOSE {symbol} | Size: {pos['size']:.4f}")
            del self.positions[symbol]
            return True
        else:
            try:
                order = await self.rest_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="market",
                    size=pos["size"],
                    leverage=self.leverage,
                    reduce_only=True,
                )

                if order:
                    logger.info(f"✅ [LIVE] CLOSED {symbol}")
                    del self.positions[symbol]
                    return True

            except Exception as e:
                logger.error(f"❌ Failed to close {symbol}: {e}")
                return False

        return False

    async def manage_positions(self) -> None:
        """Manage existing positions (stop-loss, take-profit)."""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            # Get current price
            state = self.state_manager.get_symbol_state(symbol)
            if not state:
                continue

            current_price = state.get("last_price", 0)
            if current_price == 0:
                continue

            entry_price = pos["entry_price"]
            pnl_pct = 0.0

            if pos["side"] == "long":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - current_price) / entry_price) * 100

            # Stop-loss: -2% (accounting for leverage)
            if pnl_pct * self.leverage < -2.0:
                logger.warning(
                    f"🛑 STOP-LOSS triggered for {symbol} | PnL: {pnl_pct * self.leverage:.2f}%"
                )
                await self.close_position(symbol)
                continue

            # Take-profit: +5%
            if pnl_pct * self.leverage > 5.0:
                logger.info(
                    f"💰 TAKE-PROFIT triggered for {symbol} | PnL: {pnl_pct * self.leverage:.2f}%"
                )
                await self.close_position(symbol)
                continue

    async def execute_trades(self, allocations: list[dict[str, Any]]) -> None:
        """Execute trades based on allocations."""
        # Close positions not in new allocations
        allocated_symbols = {alloc["symbol"] for alloc in allocations}
        for symbol in list(self.positions.keys()):
            if symbol not in allocated_symbols:
                logger.info(f"🔄 Closing {symbol} (no longer in top allocations)")
                await self.close_position(symbol)

        # Open new positions
        for alloc in allocations:
            symbol = alloc["symbol"]
            signal_side = alloc["predicted_side"]

            # Skip if already have position
            if symbol in self.positions:
                continue

            # Skip if max positions reached
            if len(self.positions) >= self.max_positions:
                break

            # Calculate position size
            state = self.state_manager.get_symbol_state(symbol)
            if not state:
                continue

            price = state.get("last_price", 0)
            if price == 0:
                continue

            position_value = self.equity * self.position_size_pct
            size = (position_value * self.leverage) / price

            # Place order
            success = await self.place_order(symbol, signal_side, size, price)

            if success:
                self.positions[symbol] = {
                    "symbol": symbol,
                    "side": signal_side,
                    "size": size,
                    "entry_price": price,
                    "unrealized_pnl": 0.0,
                }

                self.trades.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "symbol": symbol,
                        "side": signal_side,
                        "size": size,
                        "price": price,
                    }
                )

    async def trading_loop(self) -> None:
        """Main trading loop."""
        iteration = 0

        while self.running:
            try:
                iteration += 1

                # Check daily loss limit
                daily_pnl_pct = ((self.equity - self.initial_equity) / self.initial_equity)
                if daily_pnl_pct < -self.daily_loss_limit:
                    logger.error(
                        f"🚨 DAILY LOSS LIMIT HIT: {daily_pnl_pct*100:.2f}% | STOPPING!"
                    )
                    self.running = False
                    break

                # Rank symbols
                allocations = self.ranker.rank_and_allocate(
                    self.state_manager, max_positions=self.max_positions
                )

                # Manage existing positions (stop-loss, take-profit)
                await self.manage_positions()

                # Execute trades
                if allocations:
                    await self.execute_trades(allocations)

                # Update equity
                total_unrealized_pnl = sum(
                    pos.get("unrealized_pnl", 0) for pos in self.positions.values()
                )
                self.equity = self.initial_equity + total_unrealized_pnl

                # Log status
                if iteration % 10 == 0:
                    pnl_pct = ((self.equity - self.initial_equity) / self.initial_equity) * 100
                    logger.info(
                        f"[{iteration}] Equity: ${self.equity:.2f} ({pnl_pct:+.2f}%) | "
                        f"Positions: {len(self.positions)} | Trades: {len(self.trades)}"
                    )

                # Wait before next iteration
                await asyncio.sleep(60)

            except KeyboardInterrupt:
                logger.info("⚠️  Keyboard interrupt - shutting down gracefully...")
                self.running = False
                break

            except Exception as e:
                logger.error(f"❌ Trading loop error: {e}")
                await asyncio.sleep(5)

    async def run(self) -> None:
        """Run the live trader."""
        logger.info("=" * 70)
        logger.info("🚀 BITGET LIVE TRADING SYSTEM")
        logger.info("=" * 70)
        logger.info(f"💰 Initial Capital: ${self.initial_capital:.2f}")
        logger.info(f"📊 Leverage: {self.leverage}x")
        logger.info(f"📈 Position Size: {self.position_size_pct*100:.1f}% per trade")
        logger.info(f"🎯 Max Positions: {self.max_positions}")
        logger.info(f"🛡️  Daily Loss Limit: {self.daily_loss_limit*100:.1f}%")
        logger.info(f"🎭 Mode: {'PAPER TRADING' if self.paper_mode else '🔴 LIVE TRADING'}")
        logger.info("=" * 70 + "\n")

        # Verify credentials
        if not await self.verify_api_credentials():
            logger.error("❌ Credential verification failed - cannot continue")
            return

        # Check balance
        if not self.paper_mode:
            if not await self.check_account_balance():
                logger.error("❌ Insufficient balance - cannot continue")
                return

        # Fetch current positions
        await self.fetch_current_positions()

        # Discover universe
        logger.info("🔍 Discovering tradable symbols...")
        symbols = await self.universe_manager.get_tradable_symbols(
            min_volume_24h=10000, top_n=100
        )
        logger.info(f"✅ Found {len(symbols)} tradable symbols")

        # Connect WebSocket
        logger.info("🔌 Connecting to Bitget WebSocket...")
        await self.ws_client.connect()

        # Subscribe to all symbols
        logger.info(f"📡 Subscribing to {len(symbols)} symbols...")
        for symbol in symbols:
            await self.ws_client.subscribe_ticker(symbol)
            await self.ws_client.subscribe_books(symbol, depth=5)

        # Start message handler
        asyncio.create_task(self.handle_ws_messages())

        # Wait for data to accumulate
        logger.info("⏳ Waiting 10 seconds for initial data...")
        await asyncio.sleep(10)

        logger.info("✅ Starting trading loop...\n")

        # Start trading
        await self.trading_loop()

        # Cleanup
        logger.info("\n🛑 Shutting down...")
        await self.ws_client.close()

        # Final report
        logger.info("\n" + "=" * 70)
        logger.info("FINAL REPORT")
        logger.info("=" * 70)
        logger.info(f"Initial Capital: ${self.initial_capital:.2f}")
        logger.info(f"Final Equity:    ${self.equity:.2f}")
        pnl = self.equity - self.initial_capital
        pnl_pct = (pnl / self.initial_capital) * 100
        logger.info(f"Total PnL:       ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        logger.info(f"Total Trades:    {len(self.trades)}")
        logger.info(f"Final Positions: {len(self.positions)}")
        logger.info("=" * 70)

    async def handle_ws_messages(self) -> None:
        """Handle WebSocket messages."""
        while self.running:
            try:
                msg = await self.ws_client.ws.recv()
                await self.ws_client.on_message(msg, self.state_manager)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(1)


async def main() -> None:
    """Main entry point."""
    # Load credentials from environment
    api_key = os.getenv("BITGET_API_KEY", "")
    secret_key = os.getenv("BITGET_SECRET_KEY", "")
    passphrase = os.getenv("BITGET_PASSPHRASE", "")

    if not api_key or not secret_key:
        logger.error("❌ Missing API credentials in .env file!")
        logger.error("Please set BITGET_API_KEY and BITGET_SECRET_KEY")
        sys.exit(1)

    # Ask for passphrase if not set
    if not passphrase:
        logger.warning("⚠️  BITGET_PASSPHRASE not set in .env")
        passphrase = input("Enter your Bitget API passphrase: ").strip()

        if not passphrase:
            logger.error("❌ Passphrase is required!")
            sys.exit(1)

    # Get trading mode
    trading_mode = os.getenv("TRADING_MODE", "paper").lower()
    paper_mode = trading_mode == "paper"

    if not paper_mode:
        logger.warning("=" * 70)
        logger.warning("⚠️  🔴 LIVE TRADING MODE ENABLED 🔴")
        logger.warning("=" * 70)
        logger.warning("This will place REAL orders with REAL money!")
        logger.warning("Are you sure you want to continue?")
        logger.warning("=" * 70)
        response = input("Type 'YES I AM SURE' to continue: ")

        if response != "YES I AM SURE":
            logger.info("❌ Live trading cancelled.")
            sys.exit(0)

    # Create trader
    trader = LiveTrader(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        initial_capital=float(os.getenv("INITIAL_CAPITAL", "50")),
        leverage=int(os.getenv("LEVERAGE", "50")),
        position_size_pct=float(os.getenv("POSITION_SIZE_PCT", "0.10")),
        max_positions=int(os.getenv("MAX_POSITIONS", "10")),
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "0.15")),
        paper_mode=paper_mode,
    )

    # Run trader
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())

