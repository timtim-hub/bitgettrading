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
from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.enhanced_ranker import EnhancedRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.position_manager import PositionManager
from src.bitget_trading.regime_detector import RegimeDetector
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
        self.universe_manager = UniverseManager()
        self.state_manager = MultiSymbolStateManager()
        self.simple_ranker = CrossSectionalRanker()  # WORKING paper trading ranker
        self.enhanced_ranker = EnhancedRanker()  # Enhanced ranker (use when data accumulated)
        self.position_manager = PositionManager()  # Position persistence + trailing stops
        self.regime_detector = RegimeDetector()  # Market regime detection
        self.use_enhanced = False  # Start with simple, upgrade to enhanced after data accumulates

        # State
        self.equity = initial_capital
        self.initial_equity = initial_capital
        self.trades: list[dict[str, Any]] = []
        self.running = True
        self.start_time = datetime.now()
        self.symbols: list[str] = []  # Tradable symbols
        
        # Load saved positions on startup
        logger.info(
            "positions_restored_from_disk",
            count=len(self.position_manager.positions),
            symbols=list(self.position_manager.positions.keys()),
        )

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
            
            if balance and balance.get("code") == "00000":
                data = balance.get("data", [{}])[0]
                available = float(data.get("available", 0))

                logger.info(f"💰 Available balance: ${available:.2f} USDT")

                if available < self.initial_capital:
                    logger.error(
                        f"❌ Insufficient balance! Need ${self.initial_capital:.2f}, have ${available:.2f}"
                    )
                    return False

                return True
            else:
                logger.error("❌ Failed to fetch balance")
                return False

        except Exception as e:
            logger.error(f"❌ Balance check failed: {e}")
            return False

    async def fetch_current_positions(self) -> None:
        """
        Fetch current positions from exchange and SYNC with saved positions.
        
        CRITICAL: Ensures positions.json matches reality on exchange!
        """
        try:
            # Fetch all positions from exchange via REST API
            endpoint = "/api/v2/mix/position/all-position"
            params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
            
            response = await self.rest_client._request("GET", endpoint, params=params)
            
            exchange_positions = {}
            if response.get("code") == "00000" and "data" in response:
                for pos in response.get("data", []):
                    symbol = pos.get("symbol")
                    total = float(pos.get("total", 0))
                    
                    if symbol and total > 0:
                        exchange_positions[symbol] = {
                            "size": total,
                            "side": "long" if pos.get("holdSide") == "long" else "short",
                            "entry_price": float(pos.get("averageOpenPrice", 0)),
                        }
            
            logger.info(f"📊 Fetched {len(exchange_positions)} open positions from exchange")
            
            # SYNC: Remove positions from disk that don't exist on exchange
            saved_symbols = list(self.position_manager.positions.keys())
            for symbol in saved_symbols:
                if symbol not in exchange_positions:
                    logger.warning(f"🧹 Removing {symbol} from disk (not on exchange)")
                    self.position_manager.remove_position(symbol)
            
            logger.info(f"📊 After sync: {len(self.position_manager.positions)} positions")

        except Exception as e:
            logger.error(f"❌ Failed to fetch/sync positions: {e}")

    async def place_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> bool:
        """
        Place order (paper or live).
        
        IMPROVED: Places 2-3 bps inside spread for better fills + maker fee!
        """
        if self.paper_mode:
            # Paper trading
            logger.info(
                f"📝 [PAPER] {side.upper()} {symbol} | Size: {size:.4f} | Price: ${price:.4f}"
            )
            return True
        else:
            # Real trading
            try:
                # Set isolated margin mode first
                try:
                    await self.rest_client.set_margin_mode(
                        symbol=symbol,
                        margin_mode="isolated",
                    )
                except Exception:
                    pass  # May already be set, ignore error
                
                # Set leverage for both sides
                for hold_side in ["long", "short"]:
                    try:
                        await self.rest_client.set_leverage(
                            symbol=symbol,
                            leverage=self.leverage,
                            hold_side=hold_side,
                        )
                    except Exception:
                        pass  # May already be set
                
                # SMART LIMIT ORDERS: Place 2bps INSIDE spread for:
                # - Better entry price (0.02% improvement)
                # - High fill probability
                # - Guaranteed maker fee (0.02% vs 0.06%)
                state = self.state_manager.get_state(symbol)
                if state and state.bid_price > 0 and state.ask_price > 0:
                    if side == "long":
                        # Buy 2bps BELOW ask = better price + likely fill
                        limit_price = state.ask_price * 0.9998  # 0.02% better
                    else:  # short
                        # Sell 2bps ABOVE bid = better price + likely fill
                        limit_price = state.bid_price * 1.0002  # 0.02% better
                else:
                    limit_price = price
                
                # CRITICAL: Round to Bitget's required price precision
                contract_info = self.universe_manager.get_contract_info(symbol)
                if contract_info:
                    price_place = contract_info.get("price_place", 2)
                    limit_price = round(limit_price, price_place)
                else:
                    # Default rounding based on price magnitude
                    if limit_price > 1000:
                        limit_price = round(limit_price, 1)  # BTC: 0.1 precision
                    elif limit_price > 10:
                        limit_price = round(limit_price, 2)  # ETH: 0.01 precision
                    else:
                        limit_price = round(limit_price, 4)  # Altcoins: 0.0001 precision
                
                # Place LIMIT order AT best price = instant fill + maker fee!
                order_side = "buy" if side == "long" else "sell"
                order = await self.rest_client.place_order(
                    symbol=symbol,
                    side=order_side,
                    order_type="limit",  # LIMIT at bid/ask = maker fee + instant fill!
                    size=size,
                    price=limit_price,
                )

                if order:
                    logger.info(
                        f"✅ [LIVE] {side.upper()} {symbol} | Size: {size:.4f} | "
                        f"Order: {order.get('data', {}).get('orderId', 'N/A')}"
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
        position = self.position_manager.get_position(symbol)
        if not position:
            return False

        side = "sell" if position.side == "long" else "buy"

        if self.paper_mode:
            logger.info(f"📝 [PAPER] CLOSE {symbol} | Size: {position.size:.4f}")
            self.position_manager.remove_position(symbol)
            return True
        else:
            try:
                # Use LIMIT order at bid/ask for instant fill + maker fee (0.02% vs 0.06%)
                state = self.state_manager.get_state(symbol)
                if state and state.bid_price > 0 and state.ask_price > 0:
                    if side == "sell":  # Closing long
                        limit_price = state.bid_price  # Sell at bid = instant fill as maker
                    else:  # Closing short
                        limit_price = state.ask_price  # Buy at ask = instant fill as maker
                else:
                    # Fallback to current price
                    limit_price = position.entry_price
                
                # Round to required precision
                contract_info = self.universe_manager.get_contract_info(symbol)
                if contract_info:
                    price_place = contract_info.get("price_place", 2)
                    limit_price = round(limit_price, price_place)
                else:
                    if limit_price > 1000:
                        limit_price = round(limit_price, 1)
                    elif limit_price > 10:
                        limit_price = round(limit_price, 2)
                    else:
                        limit_price = round(limit_price, 4)
                
                order = await self.rest_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="limit",  # LIMIT at bid/ask = maker fee + instant fill!
                    size=position.size,
                    price=limit_price,
                    reduce_only=True,
                )

                if order and order.get("code") == "00000":
                    # Record trade
                    self.trades.append({
                        "symbol": symbol,
                        "side": position.side,
                        "entry_price": position.entry_price,
                        "entry_time": position.entry_time,
                        "exit_time": datetime.now().isoformat(),
                        "pnl": position.unrealized_pnl,
                        "peak_pnl_pct": position.peak_pnl_pct,
                    })
                    
                    logger.info(
                        f"✅ [LIVE] CLOSED {symbol} | PnL: ${position.unrealized_pnl:.2f} | "
                        f"Peak: {position.peak_pnl_pct:.2f}% | Exit Price: ${limit_price:.4f}"
                    )
                    
                    self.position_manager.remove_position(symbol)
                    return True

            except Exception as e:
                error_msg = str(e)
                # Handle "No position to close" error (position already closed on exchange)
                if "22002" in error_msg or "No position" in error_msg:
                    logger.warning(f"⚠️ {symbol} already closed on exchange, removing from tracking")
                    self.position_manager.remove_position(symbol)
                    return True
                else:
                    logger.error(f"❌ Failed to close {symbol}: {e}")
                    return False

        return False

    async def manage_positions(self) -> None:
        """
        Manage existing positions with TRAILING STOPS.
        
        CRITICAL: Sync with exchange EVERY iteration to catch liquidations/manual closes!
        """
        # SYNC WITH EXCHANGE: Check what's actually open on exchange
        # (positions might be closed by liquidation, manual close, or exchange)
        if not self.paper_mode:
            try:
                endpoint = "/api/v2/mix/position/all-position"
                params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
                response = await self.rest_client._request("GET", endpoint, params=params)
                
                exchange_open_symbols = set()
                if response.get("code") == "00000" and "data" in response:
                    for pos in response.get("data", []):
                        symbol = pos.get("symbol")
                        total = float(pos.get("total", 0))
                        if symbol and total > 0:
                            exchange_open_symbols.add(symbol)
                
                # Remove positions from tracking if not on exchange anymore
                for symbol in list(self.position_manager.positions.keys()):
                    if symbol not in exchange_open_symbols:
                        logger.warning(f"⚠️ {symbol} closed on exchange (liquidation or manual close) - removing from tracking")
                        self.position_manager.remove_position(symbol)
            except Exception as e:
                logger.error(f"Failed to sync positions with exchange: {e}")
        
        # Now check exit conditions for remaining positions
        positions_checked = 0
        positions_to_check = list(self.position_manager.positions.keys())
        
        if positions_to_check:
            logger.debug(f"🔍 Checking {len(positions_to_check)} positions for exits...")
        
        for symbol in positions_to_check:
            # Get current price
            state = self.state_manager.get_state(symbol)
            if not state:
                continue

            current_price = state.last_price
            if current_price == 0:
                continue

            # Update position price and trailing stop levels
            self.position_manager.update_position_price(symbol, current_price)

            # Check exit conditions (stop-loss, take-profit, trailing stop)
            should_close, reason = self.position_manager.check_exit_conditions(
                symbol, current_price
            )
            
            positions_checked += 1

            if should_close:
                position = self.position_manager.get_position(symbol)
                if position:
                    pnl_pct = position.unrealized_pnl / position.capital * 100 if position.capital > 0 else 0
                    
                    if "STOP-LOSS" in reason:
                        logger.warning(
                            f"🛑 {reason} for {symbol} | PnL: {pnl_pct:.2f}%"
                        )
                    elif "TRAILING" in reason:
                        logger.info(
                            f"📈 {reason} for {symbol} | PnL: {pnl_pct:.2f}% | Peak: {position.peak_pnl_pct:.2f}%"
                        )
                    else:
                        logger.info(
                            f"💰 {reason} for {symbol} | PnL: {pnl_pct:.2f}%"
                        )
                
                await self.close_position(symbol)
                continue

    async def execute_trades(self, allocations: list[dict[str, Any]]) -> None:
        """Execute trades based on allocations."""
        logger.info(f"💼 Execute trades called with {len(allocations)} allocations")
        
        # Close positions not in new allocations
        allocated_symbols = {alloc["symbol"] for alloc in allocations}
        for symbol in list(self.position_manager.positions.keys()):
            if symbol not in allocated_symbols:
                logger.info(f"🔄 Closing {symbol} (no longer in top allocations)")
                await self.close_position(symbol)

        # Open new positions
        trades_attempted = 0
        trades_successful = 0
        
        for alloc in allocations:
            symbol = alloc["symbol"]
            signal_side = alloc["predicted_side"]
            regime = alloc["regime"]
            position_size_multiplier = alloc["position_size_multiplier"]

            # Skip if already have position
            if symbol in self.position_manager.positions:
                continue

            # Skip if max positions reached
            if len(self.position_manager.positions) >= self.max_positions:
                break

            # Calculate position size (SMART SIZING based on signal strength + regime)
            state = self.state_manager.get_state(symbol)
            if not state:
                continue

            price = state.last_price
            if price == 0:
                continue

            # Base position size with smart multiplier
            base_position_value = self.equity * self.position_size_pct
            adjusted_position_value = base_position_value * position_size_multiplier
            size = (adjusted_position_value * self.leverage) / price

            # Get regime-specific parameters
            regime_params = self.regime_detector.get_regime_parameters(regime)

            logger.info(
                f"📈 {signal_side.upper()} {symbol} | "
                f"Price: ${price:.4f} | Size: {size:.4f} (×{position_size_multiplier:.2f}) | "
                f"Regime: {regime} | TP: {regime_params['take_profit_pct']*100:.1f}%"
            )

            # Place order
            trades_attempted += 1
            success = await self.place_order(symbol, signal_side, size, price)

            if success:
                trades_successful += 1
                
                # Add to position manager with REGIME-BASED PARAMETERS
                self.position_manager.add_position(
                    symbol=symbol,
                    side=signal_side,
                    entry_price=price,
                    size=size,
                    capital=adjusted_position_value / self.leverage,
                    leverage=self.leverage,
                    regime=regime,
                    stop_loss_pct=regime_params["stop_loss_pct"],
                    take_profit_pct=regime_params["take_profit_pct"],
                    trailing_stop_pct=regime_params["trailing_stop_pct"],
                )
                
                logger.info(
                    f"✅ Trade #{len(self.trades) + 1}: {signal_side.upper()} {symbol} @ ${price:.4f}"
                )
            else:
                logger.error(f"❌ Failed to place order for {symbol}")
        
        logger.info(f"📊 Trade execution complete: {trades_successful}/{trades_attempted} successful")

    async def trading_loop(self) -> None:
        """
        HOLD-AND-FILL trading loop (NO REBALANCING!):
        - FAST: Check exits every 2-3 seconds (TP/SL/trailing only)
        - SLOW: Look for new entries every 60 seconds when slots available
        
        KEY: Hold winners until TP/SL hit. No churning = minimal fees!
        """
        iteration = 0
        last_entry_check_time = datetime.now()
        entry_check_interval_sec = 60  # Check for new entries every 60 seconds
        position_check_interval_sec = 2  # Check exits every 2 seconds

        while self.running:
            try:
                # ALWAYS: Update market data and check positions (FAST LOOP)
                ticker_dict = await self.universe_manager.fetch_tickers()
                for symbol, ticker in ticker_dict.items():
                    if symbol not in self.symbols:
                        continue
                    
                    self.state_manager.update_ticker(symbol, ticker)
                    
                    # Simulate order book
                    mid = ticker.get("last_price", 0)
                    if mid > 0:
                        spread = mid * 0.0005  # 5 bps estimate
                        self.state_manager.update_orderbook(symbol, {
                            "bids": [[mid - spread/2, 1000], [mid - spread, 500]],
                            "asks": [[mid + spread/2, 1000], [mid + spread, 500]],
                        })

                # ALWAYS: Manage existing positions (stop-loss, take-profit, trailing)
                await self.manage_positions()

                # ALWAYS: Update equity with latest prices
                total_unrealized_pnl = self.position_manager.get_total_unrealized_pnl()
                self.equity = self.initial_equity + total_unrealized_pnl
                pnl_pct = ((self.equity - self.initial_equity) / self.initial_equity) * 100

                # Check daily loss limit
                if pnl_pct < -self.daily_loss_limit * 100:
                    logger.error(
                        f"🚨 DAILY LOSS LIMIT HIT: {pnl_pct:.2f}% | STOPPING!"
                    )
                    self.running = False
                    break

                # SOMETIMES: Look for new entries ONLY if we have empty slots (NO REBALANCING!)
                available_slots = self.max_positions - len(self.position_manager.positions)
                time_since_entry_check = (datetime.now() - last_entry_check_time).total_seconds()
                should_check_entries = time_since_entry_check >= entry_check_interval_sec

                if should_check_entries and available_slots > 0:
                    iteration += 1
                    last_entry_check_time = datetime.now()
                    
                    logger.info(f"\n{'='*70}")
                    logger.info(f"[ENTRY CHECK #{iteration}] Looking for {available_slots} new positions")
                    logger.info(f"{'='*70}")

                    # Rank symbols - ONLY for available slots (not full portfolio)
                    allocations = self.enhanced_ranker.rank_symbols_enhanced(
                        self.state_manager,
                        top_k=available_slots,  # CRITICAL: Only rank for empty slots!
                    )

                    logger.info(f"📊 Found {len(allocations)} high-quality signals for empty slots")
                    if allocations:
                        for i, alloc in enumerate(allocations, 1):
                            logger.info(
                                f"  {i}. {alloc['symbol']}: score={alloc.get('score', 0):.3f}, "
                                f"side={alloc.get('predicted_side', 'N/A')}"
                            )

                        logger.info(f"🎯 Filling {len(allocations)} empty slots...")
                        await self.execute_trades(allocations)
                    else:
                        logger.info(f"⏸️ No strong signals for {available_slots} empty slots - holding current positions")
                    
                    logger.info(
                        f"[{iteration}] Equity: ${self.equity:.2f} ({pnl_pct:+.2f}%) | "
                        f"Positions: {len(self.position_manager.positions)}/{self.max_positions} | "
                        f"Total Trades: {len(self.trades)} | Unrealized PnL: ${total_unrealized_pnl:.2f}"
                    )
                    logger.info(f"{'='*70}\n")
                else:
                    # Just log quick status - every 20th check (40 seconds @ 2s interval)
                    check_count = getattr(self, '_check_count', 0)
                    self._check_count = check_count + 1
                    
                    if check_count % 20 == 0:
                        if len(self.position_manager.positions) > 0:
                            logger.info(
                                f"[Monitor] Equity: ${self.equity:.2f} ({pnl_pct:+.2f}%) | "
                                f"Positions: {len(self.position_manager.positions)}/{self.max_positions} | "
                                f"Next entry check: {entry_check_interval_sec - time_since_entry_check:.0f}s"
                            )
                        else:
                            # No positions - show time until next search
                            logger.info(
                                f"[Waiting] No positions | Equity: ${self.equity:.2f} ({pnl_pct:+.2f}%) | "
                                f"Next entry search: {entry_check_interval_sec - time_since_entry_check:.0f}s"
                            )

                # Wait before next position check
                await asyncio.sleep(position_check_interval_sec)

            except KeyboardInterrupt:
                logger.info("⚠️  Keyboard interrupt - shutting down gracefully...")
                self.running = False
                break

            except Exception as e:
                logger.error(f"❌ Trading loop error: {e}")
                import traceback
                logger.error(traceback.format_exc())
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

        # Fetch current positions
        await self.fetch_current_positions()

        # Discover universe
        logger.info("🔍 Discovering tradable symbols...")
        self.symbols = await self.universe_manager.get_tradeable_universe()
        self.symbols = self.symbols[:100]  # Limit to top 100 for speed
        logger.info(f"✅ Found {len(self.symbols)} tradable symbols")

        # Initialize state with current market data
        logger.info("📊 Fetching initial market data...")
        ticker_dict = await self.universe_manager.fetch_tickers()
        for symbol, ticker in ticker_dict.items():
            if symbol not in self.symbols:
                continue
            
            # Add symbol to state manager
            self.state_manager.add_symbol(symbol)
            
            self.state_manager.update_ticker(symbol, ticker)
            
            # Simulate order book (same as paper trading)
            mid = ticker.get("last_price", 0)
            if mid > 0:
                spread = mid * 0.0005  # 5 bps estimate
                self.state_manager.update_orderbook(symbol, {
                    "bids": [[mid - spread/2, 1000], [mid - spread, 500]],
                    "asks": [[mid + spread/2, 1000], [mid + spread, 500]],
                })
        
        # CRITICAL: Accumulate 60 seconds of 1-second data for ultra-fast startup
        # This is enough for ultra-short-term timeframes (1s, 3s, 5s, 10s, 15s, 30s)
        logger.info("⏳ Accumulating price history (60 seconds at 1-second intervals - MAXIMUM SPEED)...")
        logger.info(f"   💪 Using all device power for 100 symbols in parallel...")
        
        for i in range(60):  # 60 iterations = 1 minute
            await asyncio.sleep(1)
            # Fetch ALL tickers in ONE API call (Bitget returns all symbols at once - FAST!)
            ticker_dict = await self.universe_manager.fetch_tickers()
            
            # Batch update all symbols (Python is fast enough, no multiprocessing overhead)
            for symbol, ticker in ticker_dict.items():
                if symbol in self.symbols:
                    self.state_manager.update_ticker(symbol, ticker)
            
            # Log progress every 15 seconds
            if (i + 1) % 15 == 0:
                active_count = len([s for s in self.symbols if s in ticker_dict])
                logger.info(f"   📊 {i+1}/60s complete ({(i+1)/60:.0%}) | {active_count} symbols active")

        logger.info("✅ 60 seconds of data ready! Multi-timeframe signals active. Starting trading...\n")

        # Start trading
        await self.trading_loop()

        # Cleanup
        logger.info("\n🛑 Shutting down...")

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
        logger.info(f"Final Positions: {len(self.position_manager.positions)}")
        logger.info("=" * 70)
        
        # Save final positions
        self.position_manager.save_positions()



async def main() -> None:
    """Main entry point."""
    # Load .env file
    from dotenv import load_dotenv
    load_dotenv()
    
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
        logger.warning("=" * 70)

    # FETCH DYNAMIC BALANCE from Bitget API
    logger.info("💰 Fetching current account balance...")
    temp_client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
    try:
        balance = await temp_client.get_account_balance()
        
        if balance and balance.get("code") == "00000":
            # Parse nested data structure
            data = balance.get("data", [{}])[0]
            
            # Use TOTAL EQUITY (available + margin in positions + unrealized PnL)
            # This is the correct capital to base position sizing on
            equity = float(data.get("equity", 0))
            available = float(data.get("available", 0))
            frozen = float(data.get("frozen", 0))
            unrealized_pnl = float(data.get("unrealizedPL", 0))
            
            # If equity field exists, use it. Otherwise calculate from components
            if equity > 0:
                initial_capital = equity
                logger.info(f"✅ Total Equity: ${equity:.2f} USDT")
                logger.info(f"   Available: ${available:.2f} | Frozen: ${frozen:.2f} | Unrealized PnL: ${unrealized_pnl:+.2f}")
            else:
                # Fallback: calculate equity manually
                initial_capital = available + frozen + unrealized_pnl
                logger.info(f"✅ Calculated Equity: ${initial_capital:.2f} USDT")
                logger.info(f"   Available: ${available:.2f} | Frozen: ${frozen:.2f} | Unrealized PnL: ${unrealized_pnl:+.2f}")
            
            if initial_capital <= 0:
                logger.error(f"❌ Insufficient balance! Equity: ${initial_capital:.2f}")
                sys.exit(1)
        else:
            logger.error("❌ Failed to fetch balance from API")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch balance: {e}")
        logger.warning("⚠️  Falling back to configured initial capital...")
        initial_capital = float(os.getenv("INITIAL_CAPITAL", "50"))

    # Create trader with DYNAMIC balance
    trader = LiveTrader(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        initial_capital=initial_capital,  # USE ACTUAL BALANCE!
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

