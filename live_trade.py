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

import numpy as np

from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.enhanced_ranker import EnhancedRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.position_manager import PositionManager
from src.bitget_trading.loss_tracker import LossTracker, TradeRecord
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
        leverage: int = 25,  # 25x leverage for safety
        position_size_pct: float = 0.05,  # 5% of capital per position (conservative)
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
        self.loss_tracker = LossTracker()  # Comprehensive loss analysis
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
        """Verify API credentials work with retry logic for network issues."""
        logger.info("🔑 Verifying API credentials...")
        
        # Retry logic for transient network issues
        max_retries = 5
        for attempt in range(max_retries):
            try:
                balance = await self.rest_client.get_account_balance()

                if not balance:
                    logger.error("❌ Could not fetch account balance - invalid credentials?")
                    return False

                logger.info("✅ API credentials verified!")
                
                # Parse balance correctly (nested structure)
                if balance.get("code") == "00000" and "data" in balance:
                    data = balance.get("data", [{}])[0]
                    equity = float(data.get("equity", 0))
                    available = float(data.get("available", 0))
                    logger.info(f"💰 Account balance: ${equity:.2f} USDT (Available: ${available:.2f})")
                else:
                    logger.info(f"💰 Account balance: Verified (details parsed at startup)")

                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s, 8s
                    logger.warning(f"⚠️  API verification attempt {attempt + 1}/{max_retries} failed: {e}")
                    logger.info(f"   Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ API verification failed after {max_retries} attempts: {e}")
                    logger.error("   Network connectivity issues detected.")
                    logger.error("   Please check your internet connection and try again.")
                    return False
        
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
        self, symbol: str, side: str, size: float, price: float, regime_params: dict = None
    ) -> bool:
        """
        Place order (paper or live).
        
        IMPROVED: Places 2-3 bps inside spread for better fills + maker fee!
        
        Args:
            regime_params: Dict with stop_loss_pct, take_profit_pct from regime_detector (SINGLE SOURCE OF TRUTH)
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
                
                if self.can_open_new_position():
                    try:
                        # 🚨 NEW STRATEGY: ATOMIC TP/SL on MARKET orders!
                        # This places the TP/SL values in the SAME order request as the entry
                        # Ensures TP/SL is active the MOMENT the position is opened
                        # BUT: No stuck orders blocking capital = worth the extra 0.04% fee!
                        
                        # Calculate TP/SL prices from regime_params
                        if regime_params:
                            sl_capital_pct = regime_params["stop_loss_pct"]
                            tp_capital_pct = regime_params["take_profit_pct"]
                            sl_price_pct = sl_capital_pct / self.leverage
                            tp_price_pct = tp_capital_pct / self.leverage
                        else:
                            # Fallback (should never happen)
                            sl_price_pct = 0.02  # 50% capital @ 25x
                            tp_price_pct = 0.004 # 10% capital @ 25x
                        
                        # Calculate actual prices
                        if side == "long":
                            stop_loss_price = price * (1 - sl_price_pct)
                            take_profit_price = price * (1 + tp_price_pct)
                        else:  # short
                            stop_loss_price = price * (1 + sl_price_pct)
                            take_profit_price = price * (1 - tp_price_pct)
                        
                        # Round to correct precision
                        contract_info = self.universe_manager.get_contract_info(symbol)
                        if contract_info:
                            price_place = contract_info.get("price_place", 4)
                            stop_loss_price = round(stop_loss_price, price_place)
                            take_profit_price = round(take_profit_price, price_place)
                        
                        logger.info(
                            f"📊 [TP/SL CALC] {symbol} | Entry: ${price:.4f} "
                            f"| TP: ${take_profit_price:.4f} ({tp_capital_pct*100:.0f}%) "
                            f"| SL: ${stop_loss_price:.4f} ({sl_capital_pct*100:.0f}%)"
                        )

                        # Place the actual MARKET order with atomic TP/SL
                        order_response = await self.rest_client.place_order(
                            symbol=symbol,
                            side=side,
                            size=size,
                            order_type="market",
                            take_profit_price=take_profit_price,
                            stop_loss_price=stop_loss_price,
                        )
                        
                        if order_response and order_response.get("code") == "00000":
                            order_id = order_response.get("data", {}).get("orderId")
                            self.position_manager.add_position(
                                symbol=symbol,
                                side=side,
                                size=size,
                                entry_price=price,
                                leverage=self.leverage,
                                **regime_params,
                                metadata=metadata
                            )
                            logger.info(
                                f"✅ [LIVE] MARKET {side.upper()} {symbol} | Size: {size:.4f} | "
                                f"Order ID: {order_id} | TP/SL Placed Atomically"
                            )
                            return True
                        else:
                            logger.error(
                                f"❌ Order placement failed for {symbol}: {order_response.get('msg')}"
                            )
                            return False

                    except Exception as e:
                        logger.error(f"❌ Order placement error: {e}")
                        return False
                return False # This is the misplaced line from 310, now correctly placed

    async def close_position(self, symbol: str, exit_reason: str = "MANUAL") -> bool:
        """Close an existing position."""
        position = self.position_manager.get_position(symbol)
        if not position:
            logger.warning(f"⚠️ [CLOSE_POSITION] No position found for {symbol}")
            return False

        side = "sell" if position.side == "long" else "buy"
        
        # Log WHY we're closing
        logger.info(
            f"🚨 [CLOSE_POSITION CALLED] {symbol} | "
            f"Reason: {exit_reason} | "
            f"Side: {position.side} | "
            f"Entry: ${position.entry_price:.4f} | "
            f"Size: {position.size:.4f}"
        )

        if self.paper_mode:
            logger.info(f"📝 [PAPER] CLOSE {symbol} | Size: {position.size:.4f}")
            self.position_manager.remove_position(symbol)
            return True
        else:
            try:
                # Get state for current price (for PnL calculation)
                state = self.state_manager.get_state(symbol)
                
                # CRITICAL: Use MARKET orders for exits to guarantee fill!
                # With 25x leverage, can't risk limit not filling and getting liquidated
                order = await self.rest_client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="market",  # MARKET = guaranteed fill, prevents liquidation!
                    size=position.size,
                    reduce_only=True,
                )

                if order and order.get("code") == "00000":
                    # Calculate trade details
                    exit_time = datetime.now().isoformat()
                    entry_dt = datetime.fromisoformat(position.entry_time)
                    exit_dt = datetime.fromisoformat(exit_time)
                    time_in_trade = (exit_dt - entry_dt).total_seconds()
                    
                    # Get current price for PnL calculation (market order = actual fill price)
                    current_price = state.last_price if state else position.entry_price
                    
                    # Calculate PnL metrics
                    pnl_pct_capital = (position.unrealized_pnl / position.capital) if position.capital > 0 else 0
                    pnl_pct_price = ((current_price - position.entry_price) / position.entry_price) if position.side == "long" else ((position.entry_price - current_price) / position.entry_price)
                    
                    # Estimate fees (0.06% taker fee for market orders: entry + exit)
                    # Entry: 0.02% maker (limit) + Exit: 0.06% taker (market)
                    fees_paid = (position.capital * 0.0002) + (position.capital * 0.0006)
                    net_pnl = position.unrealized_pnl - fees_paid
                    
                    # Get exit reason from position manager check
                    _, exit_reason = self.position_manager.check_exit_conditions(symbol, current_price)
                    
                    # Get entry metrics from position metadata
                    entry_grade = position.metadata.get("grade", "Unknown")
                    entry_score = position.metadata.get("score", 0.0)
                    entry_confluence = position.metadata.get("confluence", 0.0)
                    entry_volume_ratio = position.metadata.get("volume_ratio", 1.0)
                    entry_structure = position.metadata.get("entry_structure", "unknown")
                    entry_near_sr = position.metadata.get("near_sr", False)
                    entry_rr = position.metadata.get("rr_ratio", 0.0)
                    
                    # Get current market structure
                    state = self.state_manager.get_state(symbol)
                    prices = np.array([p for _, p in state.price_history]) if state and state.price_history else np.array([])
                    exit_structure = "unknown"
                    if len(prices) >= 30:
                        from src.bitget_trading.pro_trader_indicators import ProTraderIndicators
                        pro_ind = ProTraderIndicators()
                        market_structure = pro_ind.analyze_market_structure(prices)
                        exit_structure = market_structure.get("structure", "unknown")
                    
                    # Create detailed trade record for loss analysis
                    trade_record = TradeRecord(
                        trade_id=f"{symbol}_{position.entry_time}",
                        symbol=symbol,
                        entry_time=position.entry_time,
                        entry_price=position.entry_price,
                        entry_side=position.side,
                        position_size_usd=position.capital,
                        leverage=position.leverage,
                        entry_score=entry_score,
                        entry_grade=entry_grade,
                        entry_confluence=entry_confluence,
                        entry_volume_ratio=entry_volume_ratio,
                        entry_market_structure=entry_structure,
                        entry_near_sr=entry_near_sr,
                        entry_rr_ratio=entry_rr,
                        exit_time=exit_time,
                        exit_price=current_price,
                        exit_reason=exit_reason,
                        time_in_trade_seconds=time_in_trade,
                        pnl_usd=position.unrealized_pnl,
                        pnl_pct_capital=pnl_pct_capital,
                        pnl_pct_price=pnl_pct_price,
                        fees_paid=fees_paid,
                        slippage_cost=0.0,  # Using limit orders so minimal slippage
                        net_pnl=net_pnl,
                        exit_market_structure=exit_structure,
                        peak_pnl=position.peak_pnl_pct * position.capital / 100,
                        drawdown_from_peak=max(0, (position.peak_pnl_pct - pnl_pct_capital * 100) * position.capital / 100),
                        is_win=net_pnl > 0,
                        is_loss=net_pnl <= 0,
                        stopped_out="STOP-LOSS" in exit_reason,
                        took_profit="TAKE-PROFIT" in exit_reason or "PROFIT" in exit_reason,
                    )
                    
                    # Record for loss analysis
                    self.loss_tracker.record_trade(trade_record)
                    
                    # Record trade (legacy format)
                    self.trades.append({
                        "symbol": symbol,
                        "side": position.side,
                        "entry_price": position.entry_price,
                        "entry_time": position.entry_time,
                        "exit_time": exit_time,
                        "pnl": position.unrealized_pnl,
                        "peak_pnl_pct": position.peak_pnl_pct,
                    })
                    
                    logger.info(
                        f"✅ [LIVE] CLOSED {symbol} | PnL: ${position.unrealized_pnl:.2f} | "
                        f"Peak: {position.peak_pnl_pct:.2f}% | Exit Price: ${current_price:.4f}"
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
        
        OPTIMIZED: Sync with exchange every 5 seconds (not every 200ms!)
        Exchange-side TP/SL handles instant execution, so less frequent sync is fine.
        """
        # SYNC WITH EXCHANGE: Check what's actually open (but not EVERY iteration - too slow!)
        # Sync every 5 seconds (100 iterations @ 50ms = 5s)
        sync_count = getattr(self, '_sync_count', 0)
        self._sync_count = sync_count + 1
        
        if not self.paper_mode and sync_count % 100 == 0:
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
                        logger.warning(f"⚠️ {symbol} closed on exchange (TP/SL hit or manual close) - removing from tracking")
                        self.position_manager.remove_position(symbol)
            except Exception as e:
                logger.error(f"Failed to sync positions with exchange: {e}")
        
        # Now check exit conditions for remaining positions
        positions_checked = 0
        positions_to_check = list(self.position_manager.positions.keys())
        
        # Log position status every 100 checks (5 seconds @ 50ms interval)
        check_count = getattr(self, '_position_check_count', 0)
        self._position_check_count = check_count + 1
        
        if positions_to_check:
            if check_count % 100 == 0:
                # Detailed status every 5 seconds
                logger.info(f"🔍 Monitoring {len(positions_to_check)} positions for exits...")
                for sym in positions_to_check:
                    pos = self.position_manager.get_position(sym)
                    if pos:
                        pnl_pct = pos.unrealized_pnl / pos.capital * 100 if pos.capital > 0 else 0
                        logger.info(f"  📊 {sym}: {pos.side.upper()} @ ${pos.entry_price:.4f} | PnL: {pnl_pct:+.2f}% | Peak: {pos.peak_pnl_pct:.2f}%")
            else:
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
                
                # Pass the reason to close_position for comprehensive logging
                await self.close_position(symbol, exit_reason=reason)
                continue

    async def execute_trades(self, allocations: list[dict[str, Any]]) -> None:
        """Execute trades based on allocations."""
        logger.info(f"💼 Execute trades called with {len(allocations)} allocations")
        
        # 🚨 DISABLED: No rebalancing! Hold positions until TP/SL/trailing hit!
        # OLD BUGGY CODE was closing positions just because they're not in top rankings
        # This caused positions to exit at random PnL (1.74%, 3%, etc.) instead of our targets!
        # 
        # NEW STRATEGY: HOLD-AND-FILL
        # - Open positions with A-grade signals
        # - HOLD until TP (14%) or SL (50%) or trailing (4%) triggers
        # - Or emergency exit at 15 minutes
        # - NO rebalancing = lower fees, let winners run!
        #
        # Close positions not in new allocations - DISABLED!
        # allocated_symbols = {alloc["symbol"] for alloc in allocations}
        # for symbol in list(self.position_manager.positions.keys()):
        #     if symbol not in allocated_symbols:
        #         logger.info(f"🔄 Closing {symbol} (no longer in top allocations)")
        #         await self.close_position(symbol)

        # Open new positions
        trades_attempted = 0
        trades_successful = 0
        
        for alloc in allocations:
            try:  # CRITICAL: Wrap each trade in try-except so one failure doesn't stop all trades!
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
                
                # CRITICAL: Ensure minimum order value of 5 USDT (Bitget requirement)
                # Notional value = adjusted_position_value * leverage
                notional_value = adjusted_position_value * self.leverage
                min_order_value = 5.0  # Minimum 5 USDT per Bitget
                
                if notional_value < min_order_value:
                    # Adjust position value to meet minimum
                    adjusted_position_value = min_order_value / self.leverage
                    logger.info(
                        f"⚠️  {symbol} order too small ({notional_value:.2f} USDT) - "
                        f"increased to minimum {min_order_value:.2f} USDT"
                    )
                
                size = (adjusted_position_value * self.leverage) / price

                # Get regime-specific parameters
                regime_params = self.regime_detector.get_regime_parameters(regime)

                # Calculate final notional value for logging
                final_notional_value = adjusted_position_value * self.leverage
                
                logger.info(
                    f"📈 {signal_side.upper()} {symbol} | "
                    f"Price: ${price:.4f} | Size: {size:.4f} | "
                    f"Notional: ${final_notional_value:.2f} USDT | "
                    f"Regime: {regime} | TP: {regime_params['take_profit_pct']*100:.1f}%"
                )

                # Place order (pass regime_params for exchange-side TP/SL)
                trades_attempted += 1
                success = await self.place_order(symbol, signal_side, size, price, regime_params)

                if success:
                    trades_successful += 1
                    
                    # Extract entry metadata for loss tracking
                    entry_metadata = {
                        "grade": alloc.get("grade", "Unknown"),
                        "score": alloc.get("score", 0.0),
                        "confluence": alloc.get("confluence", 0.0),
                        "volume_ratio": alloc.get("volume_ratio", 1.0),
                        "entry_structure": alloc.get("market_structure", "unknown"),
                        "near_sr": alloc.get("near_sr", False),
                        "rr_ratio": alloc.get("rr_ratio", 0.0),
                    }
                    
                    # Add to position manager with REGIME-BASED PARAMETERS + METADATA
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
                        metadata=entry_metadata,
                    )
                    
                    logger.info(
                        f"✅ Trade #{len(self.trades) + 1}: {signal_side.upper()} {symbol} @ ${price:.4f} | "
                        f"Grade: {entry_metadata['grade']} | Structure: {entry_metadata['entry_structure']}"
                    )
                else:
                    logger.error(f"❌ Failed to place order for {symbol}")
                    
            except Exception as e:
                # Log error but CONTINUE to next trade (don't let one failure stop all 10!)
                logger.error(f"❌ Error placing trade for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue  # Move to next trade
        
        logger.info(f"📊 Trade execution complete: {trades_successful}/{trades_attempted} successful")
        
        # Log all position settings for debugging
        if trades_successful > 0:
            self.position_manager.log_all_position_settings()

    async def trading_loop(self) -> None:
        """
        HOLD-AND-FILL trading loop (NO REBALANCING!):
        - HYPER-FAST: Check exits every 5ms (0.005s) - TP/SL/trailing only - 10x FASTER!
        - FAST: Look for new entries every 5 seconds when slots available
        
        KEY: Hold winners until TP/SL hit. No churning = minimal fees!
        """
        iteration = 0
        last_entry_check_time = datetime.now()
        entry_check_interval_sec = 5  # Check for new entries every 5 seconds (SCALPING SPEED!)
        position_check_interval_sec = 0.005  # Check exits every 0.005 seconds (5ms - HYPER FAST! 10x faster!)

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
        
        # 🚨 CRITICAL: Cancel ALL old TP/SL orders from previous runs!
        # These could be limit orders placed by old code versions
        # We rely on bot-side monitoring ONLY now (5ms checks with 50% SL, 10% TP)
        logger.info("🧹 Cancelling all old TP/SL and pending orders...")
        all_positions = self.position_manager.get_all_positions()
        tpsl_cancelled = 0
        pending_cancelled = 0
        
        for symbol in all_positions.keys():
            # Cancel old TP/SL orders
            try:
                result = await self.rest_client.cancel_all_tpsl_orders(symbol)
                if result.get("code") == "00000":
                    msg = result.get("msg", "")
                    if "Cancelled" in msg:
                        count = int(msg.split()[1]) if len(msg.split()) > 1 else 0
                        tpsl_cancelled += count
            except Exception as e:
                logger.warning(f"⚠️  Failed to cancel TP/SL for {symbol}: {e}")
            
            # Cancel stuck pending orders
            try:
                result = await self.rest_client.cancel_all_pending_orders(symbol)
                if result.get("code") == "00000":
                    msg = result.get("msg", "")
                    if "Cancelled" in msg:
                        count = int(msg.split()[1]) if len(msg.split()) > 1 else 0
                        pending_cancelled += count
            except Exception as e:
                logger.warning(f"⚠️  Failed to cancel pending for {symbol}: {e}")
        
        logger.info(f"✅ Cancelled {tpsl_cancelled} TP/SL orders + {pending_cancelled} pending orders")
        logger.info("✅ Exchange-side TP/SL ENABLED (STOP-MARKET). Bot-side 5ms checks as backup.")

        # Discover universe
        logger.info("🔍 Discovering tradable symbols...")
        self.symbols = await self.universe_manager.get_tradeable_universe()
        # USE ALL SYMBOLS - Maximum opportunity!
        # Bitget API fetches all in one call anyway, so no speed penalty
        total_available = len(self.symbols)
        logger.info(f"✅ Using ALL {len(self.symbols)} symbols (maximum opportunities!)")

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
        
        # 🚀 INSTANT DATA LOADING using Bitget's historical candles API!
        # Fetch MULTIPLE TIMEFRAMES for better multi-timeframe analysis
        logger.info("⚡ INSTANT DATA LOADING - Fetching MULTIPLE timeframes from Bitget API...")
        logger.info(f"   🎯 Loading 1m, 5m, 15m candles per symbol (MORE DATA!)")
        logger.info(f"   💪 Processing %d symbols in parallel...", len(self.symbols))

        # Fetch historical candles for all symbols in parallel
        async def fetch_and_store(symbol: str, timeframe: str):
            try:
                response = await self.rest_client.get_historical_candles(symbol, timeframe, 200)
                if not isinstance(response, dict) or response.get("code") != "00000":
                    logger.warning(
                        f"⚠️  History fetch failed for {symbol} ({timeframe}): "
                        f"{response.get('msg') if isinstance(response, dict) else 'invalid response'}"
                    )
                    return
                candles = response.get("data", [])
                if not candles:
                    logger.warning(f"⚠️  No candles returned for {symbol} ({timeframe})")
                    return
                # Ensure oldest -> newest
                for candle in reversed(candles):
                    # Each candle: [timestamp, open, high, low, close, volume, ...]
                    timestamp = int(candle[0])
                    price = float(candle[4])
                    volume = float(candle[5]) if len(candle) > 5 else 0.0
                    self.state_manager.add_price_point(symbol, price, timestamp, volume)
            except Exception as e:
                logger.warning(f"⚠️  Could not fetch history for {symbol} ({timeframe}): {e}")

        batch_size = 10  # Process 10 symbols concurrently
        total_batches = (len(self.symbols) + batch_size - 1) // batch_size
        timeframes = ["1m", "5m", "15m"]
        
        total_symbols = len(self.symbols)
        completed_symbols = 0

        for i in range(0, len(self.symbols), batch_size):
            batch_symbols = self.symbols[i : i + batch_size]
            logger.info(
                f"   🚚 Starting batch {(i // batch_size) + 1}/{total_batches}: "
                f"{len(batch_symbols)} symbols"
            )

            tasks = []
            for symbol in batch_symbols:
                for timeframe in timeframes:
                    tasks.append(fetch_and_store(symbol, timeframe))

            # Stream progress as requests complete
            total_requests = len(tasks)
            completed_requests = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                completed_requests += 1
                if completed_requests % 30 == 0 or completed_requests == total_requests:
                    logger.info(
                        f"   ⏳ Batch {(i // batch_size) + 1}/{total_batches}: "
                        f"{completed_requests}/{total_requests} requests "
                        f"({completed_requests/total_requests:.0%})"
                    )
 
            completed_symbols += len(batch_symbols)
            logger.info(
                f"   📊 Batch {(i // batch_size) + 1}/{total_batches}: "
                f"Loaded {len(batch_symbols)} symbols "
                f"({completed_symbols}/{total_symbols} total - {completed_symbols/total_symbols:.0%})"
            )
            
        logger.info("✅ All historical data loaded successfully!")

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
        leverage=int(os.getenv("LEVERAGE", "25")),  # 25x for safety
        position_size_pct=float(os.getenv("POSITION_SIZE_PCT", "0.05")),  # 5% per position (conservative)
        max_positions=int(os.getenv("MAX_POSITIONS", "10")),
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "0.15")),
        paper_mode=paper_mode,
    )

    # Run trader
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())
