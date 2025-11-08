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

from src.bitget_trading.backtest_service import BacktestService
from src.bitget_trading.bitget_rest import BitgetRestClient
from src.bitget_trading.config import get_config
from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.dynamic_params import DynamicParams
from src.bitget_trading.enhanced_ranker import EnhancedRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.position_manager import PositionManager
from src.bitget_trading.loss_tracker import LossTracker, TradeRecord
from src.bitget_trading.regime_detector import RegimeDetector
from src.bitget_trading.symbol_filter import SymbolFilter
from src.bitget_trading.universe import UniverseManager
from src.bitget_trading.leverage_cache import LeverageCache

logger = setup_logging()


class LiveTrader:
    """Live trading system with safety features."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        initial_capital: float = 50.0,
        leverage: int = 25,  # 25x leverage (fixed in code)
        position_size_pct: float = 0.10,  # 10% of capital per position
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
        self.leverage_cache = LeverageCache()  # Cache to avoid redundant leverage API calls
        self.use_enhanced = False  # Start with simple, upgrade to enhanced after data accumulates
        
        # 🚀 NEW: Backtesting and performance tracking
        self.config = get_config()
        self.backtest_service: BacktestService | None = None
        self.symbol_filter: SymbolFilter | None = None
        self.dynamic_params: DynamicParams | None = None
        
        if self.config.backtest_enabled:
            # Initialize backtesting service
            self.backtest_service = BacktestService(
                config=self.config,
                rest_client=self.rest_client,
                enhanced_ranker=self.enhanced_ranker,
                state_manager=self.state_manager,
                symbols=[],  # Will be set after symbols are loaded
                enabled=self.config.backtest_enabled,
                interval_hours=self.config.backtest_interval_hours,
                lookback_days=self.config.backtest_lookback_days,
                min_trades=self.config.backtest_min_trades,
                parallel_tokens=self.config.backtest_parallel_tokens,
            )
            
            # Initialize symbol filter
            performance_tracker = self.backtest_service.get_performance_tracker()
            self.symbol_filter = SymbolFilter(
                performance_tracker=performance_tracker,
                enabled=self.config.filter_losing_tokens,
                min_win_rate=self.config.filter_min_win_rate,
                min_roi=self.config.filter_min_roi,
                min_sharpe=self.config.filter_min_sharpe,
                min_profit_factor=self.config.filter_min_profit_factor,
            )
            
            # Initialize dynamic params
            self.dynamic_params = DynamicParams(
                performance_tracker=performance_tracker,
                enabled=self.config.dynamic_params_enabled,
            )
            
            logger.info("✅ [BACKTEST] Backtesting service initialized")

        # State
        self.equity = initial_capital
        self.initial_equity = initial_capital
        self.trades: list[dict[str, Any]] = []
        self.running = True
        self.start_time = datetime.now()
        self.symbols: list[str] = []  # Tradable symbols
        
        # 🚀 PHASE 3.2: Real-time performance filtering
        # Track recent performance per symbol (last 10 trades)
        self.symbol_recent_trades: dict[str, list[dict[str, Any]]] = {}  # symbol -> list of recent trades
        self.symbol_filter_reset_time: dict[str, datetime] = {}  # symbol -> reset time (24 hours)
        
        # Load saved positions on startup
        logger.info(
            "positions_restored_from_disk",
            count=len(self.position_manager.positions),
            symbols=list(self.position_manager.positions.keys()),
        )

    def can_open_new_position(self) -> bool:
        """Return True if opening a new position is allowed.

        Criteria:
        - Total open positions < self.max_positions
        - Daily loss limit DISABLED (user requested removal for maximum profit!)
        """
        # Max positions check
        if len(self.position_manager.positions) >= self.max_positions:
            logger.debug(
                "max_positions_reached",
                current=len(self.position_manager.positions),
                max=self.max_positions,
            )
            return False

        # 🚨 DAILY LOSS LIMIT DISABLED BY USER REQUEST!
        # User priority: MAXIMUM PROFIT > risk limits
        # We rely on exchange-side stop-loss for protection
        
        return True

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
                    
                    # 🚨 Log account margin mode for hedge mode debugging
                    margin_mode = data.get("marginMode", "unknown").lower()
                    if margin_mode == "cross":
                        logger.warning(f"⚠️  Account is in CROSS margin mode! Consider ISOLATED for better risk control.")
                    elif margin_mode == "isolated":
                        logger.info(f"✅ Account is in ISOLATED margin mode.")
                    elif margin_mode == "hedge_mode":
                        logger.warning(f"⚠️  Account is in HEDGE margin mode! This might affect TP/SL visibility.")
                    else:
                        logger.info(f"ℹ️  Account margin mode: {margin_mode}")
                        
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
                
                # 🚨 CRITICAL: Set leverage to 25x for both sides (MUST BE SET!)
                # 🚀 OPTIMIZATION: Check cache first to avoid retrying failed tokens!
                leverage_set_success = False
                for hold_side in ["long", "short"]:
                    try:
                        # Check cache first - if already set or failed, skip API call!
                        if self.leverage_cache.is_set(symbol, self.leverage, hold_side):
                            # Check if it was a failure (cached as failed)
                            cache_key = f"{symbol}_{hold_side}"
                            entry = self.leverage_cache.cache.get(cache_key, {})
                            if entry.get("failed", False):
                                logger.debug(
                                    f"🚫 [LEVERAGE CACHE] {symbol} {hold_side}: Cached as failed (not supported) - skipping"
                                )
                                leverage_set_success = True  # Consider it "success" (we won't retry)
                            else:
                                logger.debug(
                                    f"💾 [LEVERAGE CACHE] {symbol} {hold_side}: Already set in cache - skipping"
                                )
                                leverage_set_success = True
                            continue
                        
                        # Not in cache - try to set via API
                        response = await self.rest_client.set_leverage(
                            symbol=symbol,
                            leverage=self.leverage,
                            hold_side=hold_side,
                        )
                        if response.get("code") == "00000":
                            logger.info(
                                f"✅ [LEVERAGE SET] {symbol} {hold_side}: {self.leverage}x | "
                                f"Response: {response.get('msg', 'OK')}"
                            )
                            # Cache success
                            self.leverage_cache.mark_set(symbol, self.leverage, hold_side)
                            leverage_set_success = True
                        else:
                            error_code = response.get('code', 'unknown')
                            error_msg = response.get('msg', 'Unknown error')
                            
                            # 🚨 CRITICAL: Mark as failed in cache if it's a "not supported" error
                            if error_code in ["40797", "40798"] or "maximum settable leverage" in error_msg.lower() or "not supported" in error_msg.lower():
                                self.leverage_cache.mark_failed(symbol, self.leverage, hold_side, error_code)
                                logger.warning(
                                    f"🚫 [LEVERAGE SET FAILED] {symbol} {hold_side}: Leverage {self.leverage}x not supported | "
                                    f"Code: {error_code} | Cached to skip future attempts"
                                )
                                leverage_set_success = True  # Consider it "success" (we won't retry)
                            else:
                                logger.error(
                                    f"❌ [LEVERAGE SET FAILED] {symbol} {hold_side}: {self.leverage}x | "
                                    f"Code: {error_code} | Msg: {error_msg}"
                                )
                    except Exception as e:
                        error_str = str(e)
                        error_repr = repr(e)
                        # 🚨 CRITICAL: Check if it's a "not supported" error in the exception message
                        # Check both str(e) and repr(e) to catch all formats
                        is_not_supported = (
                            "40797" in error_str or "40798" in error_str or
                            "40797" in error_repr or "40798" in error_repr or
                            "maximum settable leverage" in error_str.lower() or
                            "exceeded the maximum" in error_str.lower() or
                            "maximum settable leverage" in error_repr.lower() or
                            "exceeded the maximum" in error_repr.lower()
                        )
                        
                        if is_not_supported:
                            # Cache as failed to prevent retrying
                            self.leverage_cache.mark_failed(symbol, self.leverage, hold_side, "40797")
                            logger.warning(
                                f"🚫 [LEVERAGE SET ERROR] {symbol} {hold_side}: Leverage {self.leverage}x not supported (from exception) | "
                                f"Cached to skip future attempts | Error: {error_str[:100]}"
                            )
                            leverage_set_success = True  # Consider it "success" (we won't retry)
                        else:
                            # For other exceptions, check if we should cache as failed based on error type
                            # Network errors shouldn't be cached, but API errors should
                            if "API error" in error_str or "400" in error_str or "403" in error_str:
                                # Likely an API error - might be a permanent failure
                                # But don't cache unless we're sure it's a "not supported" error
                                logger.error(
                                    f"❌ [LEVERAGE SET ERROR] {symbol} {hold_side}: {self.leverage}x | "
                                    f"Error: {error_str[:200]}"
                                )
                            else:
                                # Network/timeout errors - don't cache
                                logger.error(
                                    f"❌ [LEVERAGE SET ERROR] {symbol} {hold_side}: {self.leverage}x | "
                                    f"Error: {error_str[:200]} (network/timeout - not caching)"
                                )
                        # Don't pass silently - log the error!
                
                # 🚨 CRITICAL: Wait 1 second after setting leverage to ensure it's applied
                if leverage_set_success:
                    await asyncio.sleep(1.0)
                    logger.info(f"⏳ [LEVERAGE WAIT] {symbol}: Waited 1s after setting leverage to ensure it's applied")
                
                if self.can_open_new_position():
                    try:
                        # 🚨 NEW STRATEGY: ATOMIC TP/SL on MARKET orders!
                        # This places the TP/SL values in the SAME order request as the entry
                        # Ensures TP/SL is active the MOMENT the position is opened
                        # BUT: No stuck orders blocking capital = worth the extra 0.04% fee!
                        
                        # Calculate TP/SL prices from regime_params
                        if regime_params:
                            # 🚨 CRITICAL FIX: regime_params["stop_loss_pct"] is in CAPITAL %, not price %!
                            # Must divide by leverage to convert to price %, same as TP!
                            sl_capital_pct = regime_params["stop_loss_pct"]  # Capital % (e.g., 0.50 = 50%)
                            tp_capital_pct = regime_params["take_profit_pct"]  # Capital % (e.g., 0.16 = 16%)
                            
                            # Convert both from capital % to price % by dividing by leverage
                            sl_price_pct = sl_capital_pct / self.leverage  # 50% capital @ 25x = 2% price
                            tp_price_pct = tp_capital_pct / self.leverage  # 16% capital @ 25x = 0.64% price
                            
                            # 🚨 DEBUG: Log the actual values being used
                            logger.info(
                                f"🔍 [TP/SL DEBUG] {symbol} | SL: {sl_capital_pct*100:.0f}% capital → {sl_price_pct*100:.2f}% price | "
                                f"TP: {tp_capital_pct*100:.0f}% capital → {tp_price_pct*100:.2f}% price | Leverage: {self.leverage}x"
                            )
                        else:
                            # Fallback (should never happen) - Use correct values: 50% SL, 8% TP
                            sl_price_pct = 0.02  # 50% capital @ 25x = 2% price
                            tp_price_pct = 0.0032  # 8% capital @ 25x = 0.32% price
                            sl_capital_pct = 0.50  # For logging
                            tp_capital_pct = 0.08  # For logging
                            logger.warning(
                                f"⚠️ [TP/SL FALLBACK] {symbol} | regime_params is None! Using fallback: "
                                f"SL={sl_capital_pct*100:.0f}%, TP={tp_capital_pct*100:.0f}%"
                            )
                        
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
                        
                        # 🚨 VERIFY: Calculate actual price move and verify it matches expected capital %
                        if side == "long":
                            actual_price_move_pct = (price - stop_loss_price) / price
                        else:
                            actual_price_move_pct = (stop_loss_price - price) / price
                        actual_capital_pct = actual_price_move_pct * self.leverage
                        
                        logger.info(
                            f"📊 [TP/SL CALC] {symbol} | Entry: ${price:.4f} "
                            f"| TP: ${take_profit_price:.4f} ({tp_capital_pct*100:.0f}%) "
                            f"| SL: ${stop_loss_price:.4f} ({sl_capital_pct*100:.0f}%) | "
                            f"VERIFIED: Actual SL = {actual_capital_pct*100:.2f}% capital "
                            f"({actual_price_move_pct*100:.4f}% price @ {self.leverage}x)"
                        )
                        
                        # 🚨 ALERT if stop loss doesn't match expected value
                        if abs(actual_capital_pct - sl_capital_pct) > 0.01:  # More than 1% difference
                            logger.error(
                                f"❌ [TP/SL MISMATCH] {symbol} | Expected SL: {sl_capital_pct*100:.0f}% capital, "
                                f"but calculated SL: {actual_capital_pct*100:.2f}% capital! "
                                f"Price move: {actual_price_move_pct*100:.4f}% | Leverage: {self.leverage}x"
                            )

                        # Convert logical side to API side
                        order_side = "buy" if side == "long" else "sell"

                        # 🚀 NEW: Use limit orders with better prices (0.05% inside spread) for better fills
                        # This reduces slippage and ensures we enter at better prices
                        # For long: enter 0.05% below current price (better fill)
                        # For short: enter 0.05% above current price (better fill)
                        spread_adjustment = 0.0005  # 0.05% inside spread
                        if order_side == "buy":
                            limit_price = price * (1 - spread_adjustment)  # 0.05% below for long
                        else:  # sell
                            limit_price = price * (1 + spread_adjustment)  # 0.05% above for short
                        
                        # Round to correct precision
                        contract_info = self.universe_manager.get_contract_info(symbol)
                        if contract_info:
                            price_place = contract_info.get("price_place", 4)
                            limit_price = round(limit_price, price_place)
                        
                        logger.info(
                            f"🎯 [LIMIT ORDER] {symbol} | Side: {order_side} | "
                            f"Market price: ${price:.4f} | Limit price: ${limit_price:.4f} | "
                            f"Spread adjustment: {spread_adjustment*100:.2f}%"
                        )
                        
                        # Try limit order first (better price, maker fee)
                        order_response = await self.rest_client.place_order(
                            symbol=symbol,
                            side=order_side,
                            size=size,
                            order_type="limit",
                            price=limit_price,
                        )
                        
                        # If limit order fails or doesn't fill quickly, use market order
                        if not order_response or order_response.get("code") != "00000":
                            logger.warning(
                                f"⚠️ [LIMIT ORDER FAILED] {symbol} | Code: {order_response.get('code', 'N/A') if order_response else 'None'} | "
                                f"Falling back to market order"
                            )
                            # Fallback to market order
                            order_response = await self.rest_client.place_order(
                                symbol=symbol,
                                side=order_side,
                                size=size,
                                order_type="market",
                            )
                        
                        if order_response and order_response.get("code") == "00000":
                            order_id = order_response.get("data", {}).get("orderId")
                            logger.info(
                                f"✅ [LIVE] MARKET {side.upper()} {symbol} | Size: {size:.4f} | "
                                f"Order ID: {order_id}"
                            )
                            
                            # 🚨 CRITICAL: Wait for order to fill, then get ACTUAL position size from exchange
                            # The calculated size might not match the actual filled size
                            # This prevents "Insufficient position" errors (code 43023)
                            # Market orders should fill instantly, but position query might lag
                            # Increased wait time to ensure position is fully available on exchange
                            await asyncio.sleep(3.0)  # Wait 3 seconds for market order to fill and position to update
                            
                            # Query actual position from exchange with retry
                            # Sometimes the position query returns 0 or wrong size immediately after fill
                            actual_position_size = size  # Fallback to calculated size
                            max_retries = 3
                            retry_delay = 1.0
                            for attempt in range(max_retries):
                                try:
                                    positions = await self.rest_client.get_positions(symbol)
                                    if positions:
                                        pos = positions[0]
                                        # 🚨 CRITICAL: Log FULL position response to debug "partial SL" issue
                                        logger.info(
                                            f"🔍 [POSITION FULL RESPONSE] {symbol} | "
                                            f"Full position data: {pos}"
                                        )
                                        # Try multiple fields: total, available, size
                                        # Bitget API might use different field names
                                        total_size = pos.get("total") or pos.get("size") or pos.get("available")
                                        if total_size is None:
                                            # Fallback: try to find any numeric field that looks like size
                                            for key, value in pos.items():
                                                if "size" in key.lower() or "total" in key.lower() or "available" in key.lower():
                                                    if isinstance(value, (int, float)) and value > 0:
                                                        total_size = value
                                                        logger.info(
                                                            f"🔍 [POSITION FIELD FOUND] {symbol} | "
                                                            f"Using field '{key}' = {value}"
                                                        )
                                                        break
                                        
                                        if total_size is not None:
                                            actual_position_size = float(total_size)
                                        else:
                                            logger.warning(
                                                f"⚠️  [POSITION FIELD MISSING] {symbol} | "
                                                f"Could not find size field in position response! "
                                                f"Available fields: {list(pos.keys())} | "
                                                f"Using calculated size: {size}"
                                            )
                                            actual_position_size = size
                                        
                                        actual_side = pos.get("holdSide", "long")
                                        # 🚨 CRITICAL: Get ACTUAL leverage from position (some tokens can't be set to 25x!)
                                        # Position response has leverage as string, convert to int
                                        # Store in position_actual_leverage for use throughout this scope (including TP/SL placement)
                                        position_actual_leverage = int(pos.get("leverage", self.leverage)) if pos.get("leverage") else self.leverage
                                        logger.info(
                                            f"📊 [POSITION QUERY] {symbol} | "
                                            f"Actual size from exchange: {actual_position_size} | "
                                            f"Calculated size: {size} | "
                                            f"Difference: {abs(actual_position_size - size):.4f} | "
                                            f"Side: {actual_side} | "
                                            f"Actual leverage: {position_actual_leverage}x (requested: {self.leverage}x)"
                                        )
                                        
                                        # 🚨 CRITICAL FIX: ALWAYS recalculate TP/SL prices using ACTUAL entry price and leverage!
                                        # The initial calculation uses the order price and requested leverage, but:
                                        # 1. Actual entry price may differ due to slippage/partial fills
                                        # 2. Actual leverage may differ if token doesn't support requested leverage
                                        # 3. We MUST ALWAYS use actual values from exchange to ensure 100% correct TP/SL prices!
                                        if regime_params:
                                            # Get actual entry price from position (this is the REAL filled price!)
                                            entry_price_actual = float(pos.get("openPriceAvg", price))
                                            
                                            # Check for mismatches (for logging)
                                            entry_price_diff = abs(entry_price_actual - price) / price if price > 0 else 0
                                            leverage_mismatch = position_actual_leverage != self.leverage
                                            entry_price_mismatch = entry_price_diff > 0.001  # More than 0.1% difference
                                            
                                            # Log mismatches if any
                                            if leverage_mismatch:
                                                logger.warning(
                                                    f"⚠️ [LEVERAGE MISMATCH] {symbol} | "
                                                    f"Actual leverage ({position_actual_leverage}x) != requested ({self.leverage}x)! | "
                                                    f"Recalculating TP/SL prices using actual leverage..."
                                                )
                                            if entry_price_mismatch:
                                                logger.warning(
                                                    f"⚠️ [ENTRY PRICE MISMATCH] {symbol} | "
                                                    f"Actual entry price (${entry_price_actual:.4f}) != order price (${price:.4f})! | "
                                                    f"Difference: {entry_price_diff*100:.2f}% | "
                                                    f"Recalculating TP/SL prices using actual entry price..."
                                                )
                                            
                                            # 🚨 ALWAYS recalculate using ACTUAL values (even if no mismatch, to ensure correctness)
                                            # Store original prices for logging
                                            original_sl_price = stop_loss_price
                                            original_tp_price = take_profit_price
                                            
                                            # Recalculate TP/SL prices using ACTUAL leverage and ACTUAL entry price
                                            # 🚨 CRITICAL: Both SL and TP are capital-based, must divide by ACTUAL leverage!
                                            sl_capital_pct = regime_params["stop_loss_pct"]  # Capital % (e.g., 0.50 = 50%)
                                            tp_capital_pct = regime_params["take_profit_pct"]  # Capital % (e.g., 0.16 = 16%)
                                            
                                            # Convert both to price % using ACTUAL leverage from exchange
                                            sl_price_pct = sl_capital_pct / position_actual_leverage  # 50% ÷ actual_leverage
                                            tp_price_pct = tp_capital_pct / position_actual_leverage  # 16% ÷ actual_leverage
                                            
                                            # Recalculate stop-loss price using actual entry price and leverage
                                            if side == "long":
                                                stop_loss_price = entry_price_actual * (1 - sl_price_pct)
                                                take_profit_price = entry_price_actual * (1 + tp_price_pct)
                                            else:  # short
                                                stop_loss_price = entry_price_actual * (1 + sl_price_pct)
                                                take_profit_price = entry_price_actual * (1 - tp_price_pct)
                                            
                                            # Round to correct precision
                                            contract_info = self.universe_manager.get_contract_info(symbol)
                                            if contract_info:
                                                price_place = contract_info.get("price_place", 4)
                                                stop_loss_price = round(stop_loss_price, price_place)
                                                take_profit_price = round(take_profit_price, price_place)
                                            
                                            # Verify the recalculation
                                            if side == "long":
                                                actual_sl_price_move = (entry_price_actual - stop_loss_price) / entry_price_actual
                                                actual_tp_price_move = (take_profit_price - entry_price_actual) / entry_price_actual
                                            else:
                                                actual_sl_price_move = (stop_loss_price - entry_price_actual) / entry_price_actual
                                                actual_tp_price_move = (entry_price_actual - take_profit_price) / entry_price_actual
                                            
                                            actual_sl_capital_pct = actual_sl_price_move * position_actual_leverage
                                            actual_tp_capital_pct = actual_tp_price_move * position_actual_leverage
                                            
                                            # Log recalculation (warning if mismatch, info if no mismatch)
                                            if leverage_mismatch or entry_price_mismatch:
                                                logger.warning(
                                                    f"🔧 [TP/SL RECALC] {symbol} | "
                                                    f"Original SL: ${original_sl_price:.4f} → New SL: ${stop_loss_price:.4f} | "
                                                    f"Original TP: ${original_tp_price:.4f} → New TP: ${take_profit_price:.4f} | "
                                                    f"Entry: ${entry_price_actual:.4f} (was ${price:.4f}) | "
                                                    f"Leverage: {position_actual_leverage}x (was {self.leverage}x) | "
                                                    f"VERIFIED: SL = {actual_sl_capital_pct*100:.2f}% capital ({actual_sl_price_move*100:.4f}% price) | "
                                                    f"TP = {actual_tp_capital_pct*100:.2f}% capital ({actual_tp_price_move*100:.4f}% price)"
                                                )
                                            else:
                                                logger.info(
                                                    f"✅ [TP/SL VERIFY] {symbol} | "
                                                    f"Recalculated using actual values: Entry: ${entry_price_actual:.4f}, Leverage: {position_actual_leverage}x | "
                                                    f"SL: ${stop_loss_price:.4f} ({actual_sl_capital_pct*100:.2f}% capital) | "
                                                    f"TP: ${take_profit_price:.4f} ({actual_tp_capital_pct*100:.2f}% capital)"
                                                )
                                        
                                        # Store actual leverage for use in TP/SL placement (accessible to retry logic)
                                        # This ensures callback ratio uses correct leverage even if token can't be set to 25x
                                        
                                        # 🚨 CRITICAL: Check if actual size is significantly less than calculated
                                        # This could indicate partial fill or margin issue
                                        if actual_position_size < size * 0.9:  # More than 10% difference
                                            logger.warning(
                                                f"⚠️  [POSITION SIZE MISMATCH] {symbol} | "
                                                f"Actual size ({actual_position_size}) is significantly less than "
                                                f"calculated size ({size})! This could cause 'partial SL' issue. "
                                                f"Possible reasons: partial fill, margin issue, or frozen position."
                                            )
                                        
                                        if actual_position_size <= 0:
                                            if attempt < max_retries - 1:
                                                logger.warning(
                                                    f"⚠️  [POSITION RETRY] {symbol} | "
                                                    f"Position size is 0 or negative (attempt {attempt + 1}/{max_retries})! "
                                                    f"Retrying in {retry_delay}s..."
                                                )
                                                await asyncio.sleep(retry_delay)
                                                continue
                                            else:
                                                logger.warning(
                                                    f"⚠️  [POSITION WARNING] {symbol} | "
                                                    f"Position size is still 0 or negative after {max_retries} attempts! "
                                                    f"Order might not have filled yet. Skipping TP/SL."
                                                )
                                                return True  # Order placed, but position not filled yet
                                        else:
                                            # Got valid position size, break out of retry loop
                                            break
                                    else:
                                        if attempt < max_retries - 1:
                                            logger.warning(
                                                f"⚠️  [POSITION RETRY] {symbol} | "
                                                f"No position found on exchange (attempt {attempt + 1}/{max_retries})! "
                                                f"Retrying in {retry_delay}s..."
                                            )
                                            await asyncio.sleep(retry_delay)
                                            continue
                                        else:
                                            logger.warning(
                                                f"⚠️  [POSITION WARNING] {symbol} | "
                                                f"No position found on exchange after {max_retries} attempts! "
                                                f"Order might not have filled yet. Will retry TP/SL placement later."
                                            )
                                            # 🚨 CRITICAL: Don't skip TP/SL! Use calculated size and continue
                                            # The position might be available but query is slow
                                            actual_position_size = size  # Use calculated size
                                            logger.info(
                                                f"🔄 [TP/SL CONTINUE] {symbol} | "
                                                f"Using calculated size {actual_position_size} to place TP/SL"
                                            )
                                            break  # Continue to TP/SL placement with calculated size
                                except Exception as e:
                                    if attempt < max_retries - 1:
                                        logger.warning(
                                            f"⚠️  [POSITION RETRY] {symbol} | "
                                            f"Failed to query position (attempt {attempt + 1}/{max_retries}): {e} | "
                                            f"Retrying in {retry_delay}s..."
                                        )
                                        await asyncio.sleep(retry_delay)
                                        continue
                                    else:
                                        logger.warning(
                                            f"⚠️  [POSITION QUERY ERROR] {symbol} | "
                                            f"Failed to query position after {max_retries} attempts: {e} | "
                                            f"Using calculated size: {size}"
                                        )
                                        actual_position_size = size  # Use calculated size as fallback
                                        break
                            
                            # 🚨 CRITICAL: Place TP/SL as separate plan orders (visible in app)
                            # Cancel any old TP/SL orders first (AGGRESSIVE CANCELLATION!)
                            try:
                                cancel_result = await self.rest_client.cancel_all_tpsl_orders(symbol)
                                logger.info(
                                    f"🗑️ [CANCEL OLD ORDERS] {symbol} | "
                                    f"Result: {cancel_result.get('msg', 'N/A')} | "
                                    f"This ensures OLD orders don't interfere!"
                                )
                                # Wait for cancellation to propagate
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.warning(f"⚠️ Cancel failed for {symbol}: {e}")
                            
                            # 🚨 CRITICAL: Additional wait after position query to ensure position is fully available
                            # Sometimes position query returns size but position isn't fully available for TP/SL yet
                            # This helps prevent "Insufficient position" errors (code 43023)
                            await asyncio.sleep(1.0)  # Additional wait before placing TP/SL
                            
                            # Place TP/SL plan orders with market execution
                            # Get contract info to determine size precision
                            # Different contracts have different checkScale values:
                            # - checkScale=0: whole numbers (no decimals) - e.g., THETAUSDT, SUSHIUSDT
                            # - checkScale=1: 1 decimal place - e.g., LTCUSDT, BNBUSDT
                            contract_info = self.universe_manager.get_contract_info(symbol)
                            size_precision = None  # Let place_tpsl_order infer from size
                            
                            # 🚨 CRITICAL FIX: Better size precision detection to prevent size <= 0 errors!
                            # Try to get size precision from contract info if available
                            # Note: Bitget API doesn't expose checkScale directly, so we infer it
                            # Based on errors: some contracts need 0 decimals, some need 1
                            if contract_info:
                                # Check if size is close to whole number
                                if abs(actual_position_size - round(actual_position_size)) < 0.01:
                                    size_precision = 0  # Whole number
                                else:
                                    size_precision = 1  # 1 decimal place
                            else:
                                # No contract info, infer from size
                                if abs(actual_position_size - round(actual_position_size)) < 0.01:
                                    size_precision = 0
                                else:
                                    size_precision = 1
                            
                            # 🚨 CRITICAL: Ensure rounded size is never 0!
                            # For small positions (e.g., BTCUSDT with 0.0004), rounding to 0 decimals = 0.0
                            # This causes API error 43011: "size <= 0"
                            rounded_size = round(actual_position_size, size_precision)
                            if rounded_size <= 0:
                                # Size rounded to 0 - use higher precision or minimum size
                                if size_precision == 0:
                                    # Try 1 decimal place instead
                                    size_precision = 1
                                    rounded_size = round(actual_position_size, 1)
                                    logger.warning(
                                        f"⚠️ [SIZE PRECISION FIX] {symbol} | "
                                        f"Size rounded to 0 with precision 0, using precision 1: {rounded_size}"
                                    )
                                
                                # If still 0, use minimum size (0.0001) or original size
                                if rounded_size <= 0:
                                    # Use minimum size or original size (whichever is larger)
                                    min_size = 0.0001
                                    rounded_size = max(min_size, actual_position_size)
                                    # Adjust precision to match
                                    if rounded_size < 0.01:
                                        size_precision = 4  # 4 decimal places for very small sizes
                                    elif rounded_size < 0.1:
                                        size_precision = 3  # 3 decimal places
                                    elif rounded_size < 1.0:
                                        size_precision = 2  # 2 decimal places
                                    else:
                                        size_precision = 1  # 1 decimal place
                                    rounded_size = round(rounded_size, size_precision)
                                    logger.warning(
                                        f"⚠️ [SIZE MINIMUM FIX] {symbol} | "
                                        f"Size still <= 0, using minimum: {rounded_size} (precision: {size_precision})"
                                    )
                            
                            # Update actual_position_size to use rounded size
                            actual_position_size = rounded_size
                            
                            logger.info(
                                f"🚀 [TP/SL CALL] {symbol} | "
                                f"About to call place_tpsl_order with: "
                                f"side={side}, actual_size={actual_position_size} (precision: {size_precision}), "
                                f"SL_price={stop_loss_price}, TP_price={take_profit_price}"
                            )
                            try:
                                # 🚨 NEW: Place static SL + trailing TP (not static TP!)
                                # Static SL is OK, but TP should be trailing for better profit capture
                                
                                # 1. Place static SL order
                                sl_results = await self.rest_client.place_tpsl_order(
                                    symbol=symbol,
                                    hold_side=side,
                                    size=actual_position_size,
                                    stop_loss_price=stop_loss_price,
                                    take_profit_price=None,  # No static TP - we'll use trailing TP
                                    size_precision=size_precision,
                                )
                                
                                # 2. Place trailing take profit order (track_plan)
                                # 🚀 NEW: Get dynamic trailing TP callback (if enabled)
                                trailing_stop_pct = regime_params.get("trailing_stop_pct", 0.04)  # Default 4%
                                if self.dynamic_params:
                                    dynamic_callback = self.dynamic_params.get_trailing_tp_callback(symbol, trailing_stop_pct)
                                    trailing_stop_pct = dynamic_callback
                                    logger.info(
                                        f"📊 [DYNAMIC PARAMS] {symbol} | Trailing TP callback: {dynamic_callback:.2%} "
                                        f"(was {regime_params.get('trailing_stop_pct', 0.04):.2%})"
                                    )
                                
                                # Calculate trailing TP parameters
                                # 🚨 CRITICAL: Bitget's callbackRatio is PRICE-BASED, not capital-based!
                                # We need to convert capital-based trailing_stop_pct to price-based
                                # 🚨 CRITICAL: Use ACTUAL leverage from position (some tokens can't be set to 25x!)
                                # Example: 4% capital @ 25x leverage = 4% / 25 = 0.16% price callback
                                # Example: 4% capital @ 10x leverage = 4% / 10 = 0.4% price callback
                                trailing_stop_pct_capital = trailing_stop_pct  # Use dynamic value if enabled
                                # Use actual leverage from position (fetched from exchange above) - stored in position_actual_leverage
                                trailing_range_rate = trailing_stop_pct_capital / position_actual_leverage  # Convert to price-based using ACTUAL leverage
                                
                                # 🚨 CRITICAL: Get FRESH current market price RIGHT BEFORE placing order
                                # Bitget API requires: trigger price ≥ current market price (for longs)
                                # Price can change between entry and TP placement, so fetch fresh price
                                try:
                                    # Fetch fresh ticker data from exchange to get current market price
                                    ticker_data = await self.rest_client.get_ticker(symbol)
                                    if ticker_data and ticker_data.get("code") == "00000":
                                        ticker_list = ticker_data.get("data", [])
                                        if ticker_list and len(ticker_list) > 0:
                                            current_market_price = float(ticker_list[0].get("lastPr", price))
                                        else:
                                            # Fallback to state manager
                                            state = self.state_manager.get_state(symbol)
                                            current_market_price = state.last_price if state and state.last_price > 0 else price
                                    else:
                                        # Fallback to state manager
                                        state = self.state_manager.get_state(symbol)
                                        current_market_price = state.last_price if state and state.last_price > 0 else price
                                except Exception as e:
                                    logger.warning(f"⚠️ [PRICE FETCH ERROR] {symbol} | Error: {e} | Using fallback price")
                                    # Fallback to state manager
                                    state = self.state_manager.get_state(symbol)
                                    current_market_price = state.last_price if state and state.last_price > 0 else price
                                
                                # 🚨 CRITICAL FIX: Trigger price must be ≥ current market price (error 43035)
                                # For LONG: trigger price must be ≥ current price (activates when price goes up)
                                # For SHORT: trigger price must be ≤ current price (activates when price goes down)
                                # 
                                # 🚨 IMPORTANT: Trailing TP should activate at TP threshold, NOT at current price!
                                # If current price is already above TP threshold, we still set trigger at TP threshold
                                # (Bitget will activate it when price reaches that level)
                                # Only if current price is BELOW TP threshold, we need to set trigger ≥ current price
                                if side == "long":
                                    # For long positions, trigger price must be ≥ current market price
                                    # 🚨 CRITICAL FIX: If price is already above TP threshold, set trigger ABOVE current price
                                    # This prevents immediate activation and early exits!
                                    # Solution: Set trigger slightly above current price (0.2% buffer) so trailing waits
                                    # Once price goes up and hits trigger, trailing activates and trails from that point
                                    if current_market_price < take_profit_price:
                                        # Price hasn't reached TP threshold yet - set trigger at TP threshold or slightly above current
                                        trailing_trigger_price = max(take_profit_price, current_market_price * 1.001)  # 0.1% above current to ensure it activates
                                    else:
                                        # 🚨 FIX: Price already at/above TP threshold!
                                        # Bitget requires trigger ≥ current price, but we don't want immediate activation
                                        # Solution: Set trigger 0.2% ABOVE current price so trailing waits for price to go up
                                        # This prevents early exits from immediate activation!
                                        trailing_trigger_price = current_market_price * 1.002  # 0.2% above current - trailing waits!
                                        logger.info(
                                            f"✅ [TRAILING TP FIX] {symbol} | "
                                            f"Current price (${current_market_price:.4f}) is already ABOVE TP threshold (${take_profit_price:.4f})! | "
                                            f"Setting trigger 0.2% ABOVE current (${trailing_trigger_price:.4f}) to prevent immediate activation | "
                                            f"Trailing will wait for price to reach trigger, then activate and trail from that point!"
                                        )
                                else:  # short
                                    # For short positions: trigger activates when price goes DOWN (profit)
                                    # Trigger should be set at the take-profit threshold or slightly below
                                    # 🚀 SIMPLIFIED: Just use the TP price as trigger, let trailing handle the rest!
                                    trailing_trigger_price = take_profit_price
                                    logger.info(
                                        f"✅ [SHORT TRAILING TP] {symbol} | "
                                        f"Trigger set at TP threshold: ${trailing_trigger_price:.4f} | "
                                        f"Current price: ${current_market_price:.4f} | "
                                        f"Callback: {trailing_range_rate*100:.2f}% | "
                                        f"When price drops to ${trailing_trigger_price:.4f}, trailing activates!"
                                    )
                                
                                # 🚨 CRITICAL: Round trigger price to correct decimal places (error 40808: checkBDScale)
                                # Bitget API requires trigger price to have exact precision based on contract's pricePlace
                                # Get price precision from contract info
                                price_precision = contract_info.get("price_place", 4) if contract_info else 4  # Default to 4 if not available
                                trailing_trigger_price = round(trailing_trigger_price, price_precision)
                                logger.info(
                                    f"🔧 [TRIGGER PRICE PRECISION] {symbol} | "
                                    f"Original: {max(take_profit_price, current_market_price * 1.001) if side == 'long' else min(take_profit_price, current_market_price * 0.999)} | "
                                    f"Rounded: {trailing_trigger_price} | "
                                    f"Precision: {price_precision} decimal places"
                                )
                                
                                # "Rückrufpreis" (callback price) = trigger_price - this is when trailing activates
                                logger.info(
                                    f"🧵 [TRAILING TP SETUP] {symbol} | "
                                    f"Side: {side.upper()} | Current Price: ${current_market_price:.4f} | "
                                    f"Trigger Price (Rückrufpreis): ${trailing_trigger_price:.4f} | "
                                    f"Callback Rate: {trailing_stop_pct_capital*100:.1f}% capital ({trailing_range_rate*100:.3f}% price @ {position_actual_leverage}x) | "
                                    f"TP Threshold: ${take_profit_price:.4f}"
                                )
                                
                                # 🚨 CRITICAL: Validate position size before placing trailing TP!
                                # Ensure actual_position_size is valid (> 0) before attempting to place trailing TP
                                if actual_position_size <= 0:
                                    logger.error(
                                        f"🚨 [TRAILING TP SIZE ERROR] {symbol} | "
                                        f"Invalid position size: {actual_position_size} | "
                                        f"Attempting to query position again..."
                                    )
                                    # Try to query position one more time
                                    try:
                                        positions = await self.rest_client.get_positions(symbol)
                                        if positions:
                                            pos = positions[0]
                                            total_size = pos.get("total") or pos.get("size") or pos.get("available")
                                            if total_size is not None:
                                                actual_position_size = float(total_size)
                                                logger.info(
                                                    f"✅ [TRAILING TP SIZE FIXED] {symbol} | "
                                                    f"Queried position size: {actual_position_size}"
                                                )
                                            else:
                                                # Still can't get size - use calculated size
                                                actual_position_size = size
                                                logger.warning(
                                                    f"⚠️ [TRAILING TP SIZE FALLBACK] {symbol} | "
                                                    f"Using calculated size: {actual_position_size}"
                                                )
                                        else:
                                            # No position found - use calculated size
                                            actual_position_size = size
                                            logger.warning(
                                                f"⚠️ [TRAILING TP SIZE FALLBACK] {symbol} | "
                                                f"No position found, using calculated size: {actual_position_size}"
                                            )
                                    except Exception as e:
                                        # Query failed - use calculated size
                                        actual_position_size = size
                                        logger.warning(
                                            f"⚠️ [TRAILING TP SIZE FALLBACK] {symbol} | "
                                            f"Position query failed: {e} | Using calculated size: {actual_position_size}"
                                        )
                                
                                # Final validation - if still invalid, skip trailing TP
                                if actual_position_size <= 0:
                                    logger.error(
                                        f"🚨 [TRAILING TP CRITICAL] {symbol} | "
                                        f"Cannot place trailing TP - position size is invalid: {actual_position_size} | "
                                        f"Skipping trailing TP placement!"
                                    )
                                    trailing_tp_placed = False
                                    tp_results = {"code": "error", "msg": "Invalid position size"}
                                else:
                                    # 🚨 CRITICAL: Place trailing TP with robust retry logic
                                    # Keep retrying until it succeeds or we exhaust all attempts
                                    trailing_tp_placed = False
                                    max_trailing_tp_retries = 10  # Increased retries for trailing TP
                                    trailing_tp_retry_delay = 1.0  # Wait between retries
                                    
                                    for trailing_attempt in range(max_trailing_tp_retries):
                                        # 🚨 CRITICAL: ALWAYS fetch fresh price RIGHT BEFORE placing order!
                                        # Price can move between calculation and placement, causing error 43035
                                        try:
                                            fresh_ticker = await self.rest_client.get_ticker(symbol)
                                            if fresh_ticker and fresh_ticker.get("code") == "00000":
                                                fresh_ticker_list = fresh_ticker.get("data", [])
                                                if fresh_ticker_list and len(fresh_ticker_list) > 0:
                                                    fresh_current_price = float(fresh_ticker_list[0].get("lastPr", current_market_price))
                                                    # Recalculate trigger price with fresh price to ensure it's valid
                                                    if side == "long":
                                                        # For long: trigger must be ≥ current price
                                                        if fresh_current_price < take_profit_price:
                                                            # Price hasn't reached TP yet - set trigger at TP or slightly above current
                                                            trailing_trigger_price = max(take_profit_price, fresh_current_price * 1.001)
                                                        else:
                                                            # Price already at/above TP - set trigger 0.2% above current
                                                            trailing_trigger_price = fresh_current_price * 1.002
                                                    else:  # short
                                                        # For short: trigger must be ≤ current price
                                                        if fresh_current_price > take_profit_price:
                                                            # Price hasn't reached TP yet - set trigger at TP or slightly below current
                                                            trailing_trigger_price = min(take_profit_price, fresh_current_price * 0.999)
                                                        else:
                                                            # Price already at/below TP - set trigger 0.2% below current
                                                            trailing_trigger_price = fresh_current_price * 0.998
                                                    
                                                    # Round to correct precision
                                                    trailing_trigger_price = round(trailing_trigger_price, price_precision)
                                                    current_market_price = fresh_current_price  # Update for logging
                                                else:
                                                    logger.warning(f"⚠️ [TRAILING TP] {symbol} | Could not get fresh price, using calculated trigger")
                                            else:
                                                logger.warning(f"⚠️ [TRAILING TP] {symbol} | Could not get fresh price, using calculated trigger")
                                        except Exception as e:
                                            logger.warning(f"⚠️ [TRAILING TP] {symbol} | Error fetching fresh price: {e} | Using calculated trigger")
                                        
                                        # 🎯 USE NORMAL TRAILING MODE (track_plan)!
                                        tp_results = await self.rest_client.place_trailing_stop_full_position(
                                            symbol=symbol,
                                            hold_side=side,  # "long" or "short"
                                            callback_ratio=trailing_range_rate,  # Trailing callback rate
                                            trigger_price=trailing_trigger_price,  # Freshly calculated trigger price
                                            size=actual_position_size,  # EXACT size for full position
                                            size_precision=size_precision,
                                        )
                                        
                                        # Verify trailing TP was placed successfully
                                        if tp_results and tp_results.get("code") == "00000":
                                            logger.info(
                                                f"✅ [TRAILING TP PLACED] {symbol} | "
                                                f"Order ID: {tp_results.get('data', {}).get('orderId', 'N/A')} | "
                                                f"Attempt: {trailing_attempt + 1}/{max_trailing_tp_retries} | "
                                                f"Trigger: ${trailing_trigger_price:.4f} | Current: ${current_market_price:.4f}"
                                            )
                                            trailing_tp_placed = True
                                            break  # Success! Exit retry loop
                                        else:
                                            code = tp_results.get('code', 'N/A') if tp_results else 'N/A'
                                            msg = tp_results.get('msg', 'N/A') if tp_results else 'N/A'
                                            
                                            # Check for "Insufficient position" error - needs longer wait
                                            if code == "43023" or "Insufficient position" in str(msg):
                                                wait_time = trailing_tp_retry_delay * (trailing_attempt + 1)  # Exponential backoff
                                                logger.warning(
                                                    f"⚠️ [TRAILING TP ERROR 43023] {symbol} | "
                                                    f"Attempt {trailing_attempt + 1}/{max_trailing_tp_retries} | "
                                                    f"Insufficient position - waiting {wait_time:.1f}s before retry..."
                                                )
                                                if trailing_attempt < max_trailing_tp_retries - 1:
                                                    await asyncio.sleep(wait_time)
                                                    continue
                                            # Check for "trigger price should be ≥ current market price" error (43035)
                                            elif code == "43035" or "trigger price should be" in str(msg).lower():
                                                # 🚨 CRITICAL: Price moved! Wait a bit and retry with fresh price
                                                logger.warning(
                                                    f"⚠️ [TRAILING TP ERROR 43035] {symbol} | "
                                                    f"Attempt {trailing_attempt + 1}/{max_trailing_tp_retries} | "
                                                    f"Trigger price (${trailing_trigger_price:.4f}) invalid - price moved! | "
                                                    f"Will fetch fresh price and retry..."
                                                )
                                                if trailing_attempt < max_trailing_tp_retries - 1:
                                                    await asyncio.sleep(0.5)  # Short wait for price to stabilize
                                                    continue  # Retry with fresh price (fetched at start of loop)
                                            else:
                                                logger.error(
                                                    f"❌ [TRAILING TP FAILED] {symbol} | "
                                                    f"Attempt {trailing_attempt + 1}/{max_trailing_tp_retries} | "
                                                    f"Code: {code} | Msg: {msg}"
                                                )
                                                if trailing_attempt < max_trailing_tp_retries - 1:
                                                    await asyncio.sleep(trailing_tp_retry_delay)
                                                    continue
                                    
                                    # 🚨 CRITICAL: If trailing TP still not placed after all retries, log error
                                    if not trailing_tp_placed:
                                        logger.error(
                                            f"🚨 [TRAILING TP CRITICAL FAILURE] {symbol} | "
                                            f"Failed to place trailing TP after {max_trailing_tp_retries} attempts! | "
                                            f"This is a CRITICAL issue - position will not have trailing TP protection!"
                                        )
                                        # Set tp_results to empty dict to prevent errors downstream
                                        tp_results = {"code": "error", "msg": "Failed after all retries"}
                                
                                # Handle results safely (check for None)
                                # 🚨 CRITICAL FIX: place_tpsl_order returns {"sl": {...}, "tp": {...}} dict
                                # Check results correctly!
                                if sl_results is None:
                                    sl_results = {}
                                if tp_results is None:
                                    tp_results = {}
                                
                                # sl_results is the return value from place_tpsl_order, which is {"sl": {...}, "tp": {...}}
                                sl_code = sl_results.get('sl', {}).get('code', 'N/A') if sl_results and sl_results.get('sl') else 'N/A'
                                tp_code = tp_results.get('code', 'N/A') if tp_results else 'N/A'
                                sl_msg = sl_results.get('sl', {}).get('msg', 'N/A') if sl_results and sl_results.get('sl') else 'N/A'
                                tp_msg = tp_results.get('msg', 'N/A') if tp_results else 'N/A'
                                
                                # 🚨 CRITICAL: Store stop-loss order ID for verification!
                                # This fixes the root cause of SAPIENUSDT (-42% loss) - we need to verify orders are active!
                                sl_order_id = None
                                if sl_code == "00000" and sl_results and sl_results.get('sl'):
                                    sl_data = sl_results.get('sl', {}).get('data', {})
                                    sl_order_id = sl_data.get('orderId') if sl_data else None
                                
                                logger.info(
                                    f"✅ [TP/SL PLACED] {symbol} | "
                                    f"SL (static): code={sl_code}, msg={sl_msg}, order_id={sl_order_id or 'N/A'} | "
                                    f"TP (trailing): code={tp_code}, msg={tp_msg} | "
                                    f"Trailing callback: {trailing_stop_pct_capital*100:.1f}% capital ({trailing_range_rate*100:.3f}% price @ {actual_leverage}x) | "
                                    f"Trigger price: ${trailing_trigger_price:.4f}"
                                )
                                
                                # Verify both orders were placed successfully
                                sl_success = sl_code == "00000"
                                tp_success = tp_code == "00000"
                                
                                # 🚨 CRITICAL: Verify stop-loss order is actually active on exchange!
                                # This fixes the root cause - stop-loss orders can be silently cancelled!
                                if sl_success and sl_order_id:
                                    try:
                                        # Wait a moment for order to propagate
                                        await asyncio.sleep(0.5)
                                        
                                        # Verify stop-loss order is active
                                        verification = await self.rest_client.verify_stop_loss_order(
                                            symbol=symbol,
                                            expected_order_id=sl_order_id,
                                        )
                                        
                                        if verification.get("exists"):
                                            logger.info(
                                                f"✅ [STOP-LOSS VERIFIED] {symbol} | "
                                                f"Order ID {sl_order_id} is active on exchange | "
                                                f"Trigger price: ${verification.get('trigger_price', 0):.4f}"
                                            )
                                        else:
                                            # Check if it's a timing issue (known Bitget API quirk)
                                            if verification.get("timing_issue"):
                                                logger.warning(
                                                    f"⚠️ [STOP-LOSS VERIFICATION] {symbol} | "
                                                    f"Timing issue (API error 40812) - order might not be registered yet. "
                                                    f"Will retry verification in 2 seconds..."
                                                )
                                                # Wait 2 seconds and retry verification (don't re-place immediately)
                                                await asyncio.sleep(2.0)
                                                retry_verification = await self.rest_client.verify_stop_loss_order(
                                                    symbol=symbol,
                                                    expected_order_id=sl_order_id,
                                                )
                                                if retry_verification.get("exists"):
                                                    logger.info(
                                                        f"✅ [STOP-LOSS VERIFIED (RETRY)] {symbol} | "
                                                        f"Order ID {sl_order_id} is now active on exchange"
                                                    )
                                                else:
                                                    # Still not verified after retry - re-place it
                                                    logger.error(
                                                        f"🚨 [STOP-LOSS NOT VERIFIED!] {symbol} | "
                                                        f"Order ID {sl_order_id} is NOT active on exchange after retry! | "
                                                        f"Re-placing stop-loss immediately..."
                                                    )
                                                    retry_sl = await self.rest_client.place_tpsl_order(
                                                        symbol=symbol,
                                                        hold_side=side,
                                                        size=actual_position_size,
                                                        stop_loss_price=stop_loss_price,
                                                        take_profit_price=None,
                                                        size_precision=size_precision,
                                                    )
                                                    retry_sl_code = retry_sl.get('sl', {}).get('code', 'N/A') if retry_sl and retry_sl.get('sl') else 'N/A'
                                                    if retry_sl_code == "00000":
                                                        retry_sl_data = retry_sl.get('sl', {}).get('data', {}) if retry_sl and retry_sl.get('sl') else {}
                                                        sl_order_id = retry_sl_data.get('orderId') if retry_sl_data else sl_order_id
                                                        logger.info(f"✅ [STOP-LOSS RE-PLACED] {symbol} | New order ID: {sl_order_id}")
                                            else:
                                                # Not a timing issue - this is a real problem
                                                logger.error(
                                                    f"🚨 [STOP-LOSS NOT VERIFIED!] {symbol} | "
                                                    f"Order ID {sl_order_id} is NOT active on exchange! | "
                                                    f"This is the root cause of SAPIENUSDT (-42% loss)! | "
                                                    f"Re-placing stop-loss immediately..."
                                                )
                                                # Re-place stop-loss immediately
                                                retry_sl = await self.rest_client.place_tpsl_order(
                                                    symbol=symbol,
                                                    hold_side=side,
                                                    size=actual_position_size,
                                                    stop_loss_price=stop_loss_price,
                                                    take_profit_price=None,
                                                    size_precision=size_precision,
                                                )
                                                retry_sl_code = retry_sl.get('sl', {}).get('code', 'N/A') if retry_sl and retry_sl.get('sl') else 'N/A'
                                                if retry_sl_code == "00000":
                                                    retry_sl_data = retry_sl.get('sl', {}).get('data', {}) if retry_sl and retry_sl.get('sl') else {}
                                                    sl_order_id = retry_sl_data.get('orderId') if retry_sl_data else sl_order_id
                                                    logger.info(f"✅ [STOP-LOSS RE-PLACED] {symbol} | New order ID: {sl_order_id}")
                                    except Exception as e:
                                        logger.warning(f"⚠️ Failed to verify stop-loss for {symbol}: {e}")
                                
                                if not sl_success or not tp_success:
                                    logger.warning(
                                        f"⚠️  [TP/SL WARNING] {symbol} | "
                                        f"SL: {'✅' if sl_success else '❌'} (code={sl_code}) | "
                                        f"TP: {'✅' if tp_success else '❌'} (code={tp_code}) | "
                                        f"One or both orders may have failed! Retrying..."
                                    )
                                    # Retry failed orders
                                    if not sl_success and stop_loss_price is not None:
                                        logger.info(f"🔄 [TP/SL RETRY] {symbol} | Retrying SL order...")
                                        try:
                                            retry_sl = await self.rest_client.place_tpsl_order(
                                                symbol=symbol,
                                                hold_side=side,
                                                size=actual_position_size,
                                                stop_loss_price=stop_loss_price,
                                                take_profit_price=None,  # Only retry SL
                                                size_precision=size_precision,
                                            )
                                            retry_sl_code = retry_sl.get('sl', {}).get('code', 'N/A') if retry_sl and retry_sl.get('sl') else 'N/A'
                                            if retry_sl_code == "00000":
                                                logger.info(f"✅ [TP/SL RETRY SUCCESS] {symbol} | SL order placed successfully!")
                                            else:
                                                logger.error(f"❌ [TP/SL RETRY FAILED] {symbol} | SL retry failed: {retry_sl_code}")
                                        except Exception as e2:
                                            logger.error(f"❌ [TP/SL RETRY EXCEPTION] {symbol} | SL retry exception: {e2}")
                                    
                                    if not tp_success and take_profit_price is not None:
                                        logger.info(f"🔄 [TP/SL RETRY] {symbol} | Retrying trailing TP order...")
                                        try:
                                            # Convert capital-based to price-based callback ratio using ACTUAL leverage
                                            trailing_stop_pct_capital = regime_params.get("trailing_stop_pct", 0.04) if regime_params else 0.04
                                            trailing_range_rate = trailing_stop_pct_capital / actual_leverage  # Use actual leverage (may be 10x, not 25x!)
                                            retry_tp = await self.rest_client.place_trailing_stop_full_position(
                                                symbol=symbol,
                                                hold_side=side,
                                                callback_ratio=trailing_range_rate,
                                                trigger_price=take_profit_price,
                                                size=actual_position_size,
                                                size_precision=size_precision,
                                            )
                                            retry_tp_code = retry_tp.get('code', 'N/A') if retry_tp else 'N/A'
                                            if retry_tp_code == "00000":
                                                logger.info(f"✅ [TP/SL RETRY SUCCESS] {symbol} | Trailing TP order placed successfully!")
                                            else:
                                                logger.error(f"❌ [TP/SL RETRY FAILED] {symbol} | Trailing TP retry failed: {retry_tp_code}")
                                        except Exception as e2:
                                            logger.error(f"❌ [TP/SL RETRY EXCEPTION] {symbol} | Trailing TP retry exception: {e2}")
                                else:
                                    logger.info(
                                        f"✅ [TP/SL VERIFIED] {symbol} | "
                                        f"Both SL (static) and TP (trailing) orders placed successfully! "
                                        f"SL: ${stop_loss_price:.4f} | TP (trailing): {trailing_stop_pct_capital*100:.1f}% capital ({trailing_range_rate*100:.3f}% price @ {actual_leverage}x) trailing from ${trailing_trigger_price:.4f}"
                                    )
                                
                                # 🚨 CRITICAL: Store stop-loss order ID in position metadata for verification!
                                # This fixes the root cause of SAPIENUSDT (-42% loss) - we need to verify orders are active!
                                if sl_order_id and sl_success:
                                    # Update position metadata with stop-loss order ID
                                    position = self.position_manager.get_position(symbol)
                                    if position:
                                        position.metadata["stop_loss_order_id"] = sl_order_id
                                        position.metadata["stop_loss_price"] = stop_loss_price
                                        self.position_manager.save_positions()
                                        logger.info(
                                            f"💾 [STOP-LOSS STORED] {symbol} | "
                                            f"Order ID {sl_order_id} stored in position metadata for verification"
                                        )
                            except Exception as e:
                                import traceback
                                logger.error(
                                    f"❌ [TP/SL FAILED] {symbol} | "
                                    f"Exception: {e} | Type: {type(e).__name__} | "
                                    f"Traceback: {traceback.format_exc()}"
                                )
                                # 🚨 CRITICAL: Log this to ensure we see it!
                                logger.error(
                                    f"🚨 [CRITICAL] {symbol} | "
                                    f"TP/SL placement failed with exception! Position may not have trailing TP protection!"
                                )
                                # Retry entire TP/SL placement
                                logger.info(f"🔄 [TP/SL RETRY] {symbol} | Retrying entire TP/SL placement...")
                                try:
                                    await asyncio.sleep(2.0)  # Wait before retry
                                    
                                    # Retry static SL
                                    retry_sl_results = await self.rest_client.place_tpsl_order(
                                        symbol=symbol,
                                        hold_side=side,
                                        size=actual_position_size,
                                        stop_loss_price=stop_loss_price,
                                        take_profit_price=None,
                                        size_precision=size_precision,
                                    )
                                    retry_sl_code = retry_sl_results.get('sl', {}).get('code', 'N/A') if retry_sl_results and retry_sl_results.get('sl') else 'N/A'
                                    
                                    # Retry trailing TP using track_plan (Normal Trailing mode)
                                    # Convert capital-based to price-based callback ratio using ACTUAL leverage
                                    # Note: actual_leverage may not be accessible here, so re-fetch position or use fallback
                                    # Try to get actual leverage from position if available, otherwise use self.leverage
                                    try:
                                        retry_positions = await self.rest_client.get_positions(symbol)
                                        retry_actual_leverage = int(retry_positions[0].get("leverage", self.leverage)) if retry_positions and retry_positions[0].get("leverage") else self.leverage
                                    except Exception:
                                        retry_actual_leverage = self.leverage  # Fallback to requested leverage
                                    trailing_stop_pct_capital = regime_params.get("trailing_stop_pct", 0.04) if regime_params else 0.04
                                    trailing_range_rate = trailing_stop_pct_capital / retry_actual_leverage  # Use actual leverage (may be 10x, not 25x!)
                                    retry_tp_results = await self.rest_client.place_trailing_stop_full_position(
                                        symbol=symbol,
                                        hold_side=side,
                                        callback_ratio=trailing_range_rate,
                                        trigger_price=take_profit_price,
                                        size=actual_position_size,
                                        size_precision=size_precision,
                                    )
                                    retry_tp_code = retry_tp_results.get('code', 'N/A') if retry_tp_results else 'N/A'
                                    
                                    if retry_sl_code == "00000" and retry_tp_code == "00000":
                                        logger.info(f"✅ [TP/SL RETRY SUCCESS] {symbol} | Both orders placed successfully on retry!")
                                    else:
                                        logger.error(f"❌ [TP/SL RETRY FAILED] {symbol} | SL: {retry_sl_code}, TP: {retry_tp_code}")
                                except Exception as e2:
                                    logger.error(f"❌ [TP/SL RETRY EXCEPTION] {symbol} | Retry also failed: {e2}")
                                # Continue anyway - bot-side monitoring will handle it

                            return True
                        else:
                            logger.error(
                                f"❌ Order placement failed for {symbol}: {order_response.get('msg')}"
                            )
                            return False

                    except Exception as e:
                        logger.error(f"❌ Order placement error: {e}")
                        return False

                return False # Final fallback if can_open_new_position() is False or all attempts fail
            except Exception as e:
                logger.error(f"❌ Trading setup error: {e}")
                return False

    async def close_position(self, symbol: str, exit_reason: str = "MANUAL") -> bool:
        """Close an existing position."""
        position = self.position_manager.get_position(symbol)
        if not position:
            logger.warning(f"⚠️ [CLOSE_POSITION] No position found for {symbol}")
            return False

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
                
                # Calculate final PnL for logging
                current_price = state.last_price if state else position.entry_price # Fallback
                
                if position.side == "long":
                    price_change_pct = ((current_price - position.entry_price) / position.entry_price)
                else:
                    price_change_pct = ((position.entry_price - current_price) / position.entry_price)
                    
                return_on_capital_pct = price_change_pct * position.leverage
                
                logger.info(
                    f"✅ [CLOSING {symbol}] Reason: {exit_reason} | "
                    f"Entry: ${position.entry_price:.4f} | Exit: ${current_price:.4f} | "
                    f"Capital PnL: {return_on_capital_pct*100:.2f}% | "
                    f"Time Held: {(datetime.now() - datetime.fromisoformat(position.entry_time)).total_seconds()/60:.1f}min"
                )
                
                # Cancel any pending exchange-side TP/SL orders for this symbol
                try:
                    await self.rest_client.cancel_all_tpsl_orders(symbol)
                    logger.info(f"🗑️ Cancelled existing TP/SL orders for {symbol}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to cancel existing TP/SL for {symbol}: {e}")

                # Use MARKET order for guaranteed exit!
                side = "sell" if position.side == "long" else "buy"
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
                    
                    # 🚨 REMOVED: check_exit_conditions call - we use EXCHANGE-SIDE TP/SL!
                    # The exchange handles all exits automatically via TP/SL orders.
                    # We only call close_position when manually closing or when exchange already closed it.
                    # exit_reason is already passed as parameter to this function.
                    
                    # Get entry metrics from position metadata
                    entry_grade = position.metadata.get("grade", "Unknown")
                    entry_score = position.metadata.get("score", 0.0)
                    entry_confluence = position.metadata.get("confluence", 0.0)
                    entry_volume_ratio = position.metadata.get("volume_ratio", 1.0)
                    entry_structure = position.metadata.get("entry_structure", "unknown")
                    entry_near_sr = position.metadata.get("near_sr", False)
                    entry_rr = position.metadata.get("rr_ratio", 0.0)
                    
                    # Get all indicators from metadata
                    indicators = position.metadata.get("indicators", {})
                    entry_rsi = indicators.get("rsi", 50.0)
                    entry_macd_line = indicators.get("macd_line", 0.0)
                    entry_macd_signal = indicators.get("macd_signal", 0.0)
                    entry_macd_histogram = indicators.get("macd_histogram", 0.0)
                    entry_bb_upper = indicators.get("bb_upper", 0.0)
                    entry_bb_middle = indicators.get("bb_middle", 0.0)
                    entry_bb_lower = indicators.get("bb_lower", 0.0)
                    entry_bb_position = indicators.get("bb_position", 0.0)
                    entry_ema_bullish = indicators.get("ema_bullish", 0)
                    entry_ema_bearish = indicators.get("ema_bearish", 0)
                    entry_vwap = indicators.get("vwap", 0.0)
                    entry_vwap_deviation = indicators.get("vwap_deviation", 0.0)
                    entry_momentum_5s = position.metadata.get("momentum_5s", 0.0)
                    entry_momentum_15s = position.metadata.get("momentum_15s", 0.0)
                    entry_volatility_30s = position.metadata.get("volatility_30s", 0.0)
                    entry_volatility_60s = position.metadata.get("volatility_60s", 0.0)
                    entry_spread_bps = position.metadata.get("spread_bps", 0.0)
                    entry_ob_imbalance = position.metadata.get("ob_imbalance", 0.0)
                    entry_funding_rate = position.metadata.get("funding_rate", 0.0)
                    
                    # Get current market structure
                    state = self.state_manager.get_state(symbol)
                    prices = np.array([p for _, p in state.price_history]) if state and state.price_history else np.array([])
                    exit_structure = "unknown"
                    if len(prices) >= 30:
                        from src.bitget_trading.pro_trader_indicators import ProTraderIndicators
                        pro_ind = ProTraderIndicators()
                        market_structure = pro_ind.analyze_market_structure(prices)
                        exit_structure = market_structure.get("structure", "unknown")
                    
                    # Create detailed trade record for loss analysis (with all indicators)
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
                        # All technical indicators at entry
                        entry_rsi=entry_rsi,
                        entry_macd_line=entry_macd_line,
                        entry_macd_signal=entry_macd_signal,
                        entry_macd_histogram=entry_macd_histogram,
                        entry_bb_upper=entry_bb_upper,
                        entry_bb_middle=entry_bb_middle,
                        entry_bb_lower=entry_bb_lower,
                        entry_bb_position=entry_bb_position,
                        entry_ema_bullish=entry_ema_bullish,
                        entry_ema_bearish=entry_ema_bearish,
                        entry_vwap=entry_vwap,
                        entry_vwap_deviation=entry_vwap_deviation,
                        entry_momentum_5s=entry_momentum_5s,
                        entry_momentum_15s=entry_momentum_15s,
                        entry_volatility_30s=entry_volatility_30s,
                        entry_volatility_60s=entry_volatility_60s,
                        entry_spread_bps=entry_spread_bps,
                        entry_ob_imbalance=entry_ob_imbalance,
                        entry_funding_rate=entry_funding_rate,
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
                    
                    # 🚀 PHASE 3.2: Track recent performance for real-time filtering
                    if symbol not in self.symbol_recent_trades:
                        self.symbol_recent_trades[symbol] = []
                    self.symbol_recent_trades[symbol].append({
                        "is_win": trade_record.is_win,
                        "pnl_pct": pnl_pct_capital,
                        "exit_time": exit_time,
                    })
                    # Keep only last 10 trades
                    if len(self.symbol_recent_trades[symbol]) > 10:
                        self.symbol_recent_trades[symbol] = self.symbol_recent_trades[symbol][-10:]
                    
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
                    
                    # 🚀 NEW: Update live results in performance tracker (if enabled)
                    if self.backtest_service:
                        performance_tracker = self.backtest_service.get_performance_tracker()
                        # Calculate win rate and total PnL for this symbol
                        # Get all trades for this symbol
                        symbol_trades = [t for t in self.trades if t.get("symbol") == symbol]
                        if symbol_trades:
                            winning_trades = [t for t in symbol_trades if t.get("pnl", 0) > 0]
                            win_rate = len(winning_trades) / len(symbol_trades) if symbol_trades else 0.0
                            total_pnl = sum(t.get("pnl", 0) for t in symbol_trades)
                            performance_tracker.update_live_result(
                                symbol=symbol,
                                win_rate=win_rate,
                                total_trades=len(symbol_trades),
                                total_pnl=total_pnl,
                            )
                            logger.debug(
                                f"📊 [LIVE RESULTS] {symbol} | Win Rate: {win_rate:.1%} | "
                                f"Trades: {len(symbol_trades)} | Total PnL: ${total_pnl:.2f}"
                            )
                    
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
                        position = self.position_manager.get_position(symbol)
                        if position:
                            # Calculate PnL at closure
                            from datetime import datetime
                            pnl_pct = (position.unrealized_pnl / position.capital) * 100 if position.capital > 0 else 0
                            entry_time = datetime.fromisoformat(position.entry_time.replace('Z', '+00:00'))
                            time_held_min = (datetime.now(entry_time.tzinfo) - entry_time).total_seconds() / 60
                            
                            # 🚀 FIX: Determine exit reason based on PnL
                            if pnl_pct >= 16.0:
                                exit_reason = f"TAKE-PROFIT (Capital: {pnl_pct:.2f}%, Exchange TP/SL hit)"
                            elif pnl_pct <= -50.0:
                                exit_reason = f"STOP-LOSS (Capital: {pnl_pct:.2f}%, Exchange TP/SL hit)"
                            elif pnl_pct < 0:
                                exit_reason = f"LOSS (Capital: {pnl_pct:.2f}%, Exchange closed position)"
                            else:
                                exit_reason = f"PROFIT (Capital: {pnl_pct:.2f}%, Exchange closed position)"
                            
                            logger.warning(
                                f"⚠️ [POSITION CLOSED] {symbol} closed on exchange | "
                                f"PnL: {pnl_pct:.2f}% | "
                                f"Reason: {exit_reason} | "
                                f"Entry: ${position.entry_price:.4f} | "
                                f"Time held: {time_held_min:.1f}min"
                            )
                            
                            # 🚨 INVESTIGATION: Log if closure was premature (<1% profit/loss)
                            if abs(pnl_pct) < 1.0:
                                logger.error(
                                    f"🚨 [PREMATURE CLOSURE] {symbol} closed with {pnl_pct:.2f}% PnL! | "
                                    f"This should NOT happen with TP/SL set! | "
                                    f"Possible causes: Exchange auto-liquidation, margin call, or TP/SL order issue"
                                )
                            
                            # 🚀 FIX: Call close_position with proper exit_reason to record the trade
                            await self.close_position(symbol, exit_reason=exit_reason)
                            
                            # 🚨 CRITICAL: Cancel any remaining TP/SL and trailing orders when position closes!
                            # Exchange should auto-cancel them, but we ensure cleanup to prevent orphaned orders
                            try:
                                # Cancel TP/SL orders (profit_loss plan type)
                                cancel_result = await self.rest_client.cancel_all_tpsl_orders(symbol)
                                logger.info(
                                    f"🗑️ [CLEANUP] {symbol} | Cancelled TP/SL orders after position closed | "
                                    f"Result: {cancel_result.get('msg', 'N/A')}"
                                )
                                
                                # Also cancel trailing orders (track_plan) if they exist
                                # Note: cancel_all_tpsl_orders only cancels profit_loss, so we need to cancel track_plan separately
                                try:
                                    query_endpoint = "/api/v2/mix/order/orders-plan-pending"
                                    params = {
                                        "symbol": symbol,
                                        "productType": "usdt-futures",
                                        "planType": "track_plan",  # Trailing orders
                                    }
                                    trailing_orders = await self.rest_client._request("GET", query_endpoint, params=params)
                                    trailing_list = trailing_orders.get("data", {}).get("entrustedList", [])
                                    
                                    if trailing_list:
                                        cancel_endpoint = "/api/v2/mix/order/cancel-plan-order"
                                        for order in trailing_list:
                                            order_id = order.get("orderId")
                                            if order_id:
                                                try:
                                                    data = {
                                                        "symbol": symbol,
                                                        "productType": "usdt-futures",
                                                        "marginCoin": "USDT",
                                                        "orderId": order_id,
                                                        "planType": "track_plan",
                                                    }
                                                    await self.rest_client._request("POST", cancel_endpoint, data=data)
                                                    logger.info(f"🗑️ [CLEANUP] {symbol} | Cancelled trailing order {order_id}")
                                                except Exception as e:
                                                    logger.warning(f"⚠️ Failed to cancel trailing order {order_id} for {symbol}: {e}")
                                    else:
                                        logger.debug(f"✅ [CLEANUP] {symbol} | No trailing orders to cancel")
                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to query/cancel trailing orders for {symbol}: {e}")
                                    
                            except Exception as e:
                                logger.warning(f"⚠️ Failed to cancel TP/SL orders for {symbol} after position closed: {e}")
                        
                        # 🚀 FIX: Position already removed by close_position() at line 1402/1410, so no need to remove again
            except Exception as e:
                logger.error(f"Failed to sync positions with exchange: {e}")
        
        # 🚨 ROOT CAUSE FIX: Verify stop-loss orders are active and re-place if missing!
        # This fixes the SAPIENUSDT issue (-42% loss) - stop-loss orders can be silently cancelled!
        # Check every 20 iterations (1 second @ 50ms interval) to verify stop-loss orders
        from datetime import datetime
        current_time = datetime.now()
        
        verification_count = getattr(self, '_sl_verification_count', 0)
        self._sl_verification_count = verification_count + 1
        
        # Verify stop-loss orders every 20 iterations (1 second)
        if verification_count % 20 == 0:
            for symbol, position in list(self.position_manager.positions.items()):
                try:
                    # Get stored stop-loss order ID from position metadata
                    sl_order_id = position.metadata.get("stop_loss_order_id")
                    sl_price = position.metadata.get("stop_loss_price")
                    
                    if not sl_order_id or not sl_price:
                        continue  # No stop-loss order ID stored, skip verification
                    
                    # Verify stop-loss order is still active on exchange
                    verification = await self.rest_client.verify_stop_loss_order(
                        symbol=symbol,
                        expected_order_id=sl_order_id,
                    )
                    
                    if not verification.get("exists"):
                        # Stop-loss order is missing! This is the root cause of SAPIENUSDT!
                        logger.error(
                            f"🚨 [STOP-LOSS MISSING!] {symbol} | "
                            f"Stop-loss order {sl_order_id} is NOT active on exchange! | "
                            f"This is why SAPIENUSDT closed at -42% instead of -50%! | "
                            f"Re-placing stop-loss immediately..."
                        )
                        
                        # Re-place stop-loss order immediately
                        try:
                            # Get current position size from exchange
                            endpoint = "/api/v2/mix/position/all-position"
                            params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
                            response = await self.rest_client._request("GET", endpoint, params=params)
                            
                            actual_size = 0.0
                            if response.get("code") == "00000" and "data" in response:
                                for pos in response.get("data", []):
                                    if pos.get("symbol") == symbol:
                                        actual_size = float(pos.get("total", 0))
                                        break
                            
                            if actual_size > 0:
                                # Re-place stop-loss order
                                regime_params = self.regime_detector.get_regime_parameters(position.regime)
                                sl_pct = regime_params.get("stop_loss_pct", 0.50)
                                
                                # Calculate stop-loss price
                                if position.side == "long":
                                    sl_price_new = position.entry_price * (1 - sl_pct / position.leverage)
                                else:
                                    sl_price_new = position.entry_price * (1 + sl_pct / position.leverage)
                                
                                # Round to correct precision
                                contract_info = self.universe_manager.get_contract_info(symbol)
                                if contract_info:
                                    price_place = contract_info.get("price_place", 4)
                                    sl_price_new = round(sl_price_new, price_place)
                                
                                # Re-place stop-loss
                                sl_result = await self.rest_client.place_tpsl_order(
                                    symbol=symbol,
                                    hold_side=position.side,
                                    size=actual_size,
                                    stop_loss_price=sl_price_new,
                                    take_profit_price=None,
                                    size_precision=None,
                                )
                                
                                sl_code = sl_result.get('sl', {}).get('code', 'N/A') if sl_result and sl_result.get('sl') else 'N/A'
                                if sl_code == "00000":
                                    sl_order_id_new = sl_result.get('sl', {}).get('data', {}).get('orderId', 'N/A') if sl_result and sl_result.get('sl') and sl_result.get('sl').get('data') else 'N/A'
                                    # Update position metadata with new order ID
                                    position.metadata["stop_loss_order_id"] = sl_order_id_new
                                    position.metadata["stop_loss_price"] = sl_price_new
                                    self.position_manager.save_positions()
                                    logger.info(
                                        f"✅ [STOP-LOSS RE-PLACED] {symbol} | "
                                        f"New order ID: {sl_order_id_new} | "
                                        f"Price: ${sl_price_new:.4f}"
                                    )
                                else:
                                    logger.error(
                                        f"❌ [STOP-LOSS RE-PLACE FAILED] {symbol} | "
                                        f"Failed to re-place stop-loss! Code: {sl_code} | "
                                        f"Position is UNPROTECTED!"
                                    )
                            else:
                                logger.warning(f"⚠️ [STOP-LOSS RE-PLACE SKIPPED] {symbol} | Position size is 0, may be closing")
                        except Exception as e:
                            logger.error(f"❌ [STOP-LOSS RE-PLACE EXCEPTION] {symbol} | Exception: {e}")
                    
                    # 🚨 CRITICAL: Monitor liquidation price and close positions BEFORE liquidation!
                    # Get position data from exchange to check liquidation price
                    try:
                        endpoint = "/api/v2/mix/position/all-position"
                        params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
                        response = await self.rest_client._request("GET", endpoint, params=params)
                        
                        if response.get("code") == "00000" and "data" in response:
                            for pos_data in response.get("data", []):
                                if pos_data.get("symbol") == symbol:
                                    liquidation_price = float(pos_data.get("liquidationPrice", 0))
                                    margin_ratio = float(pos_data.get("marginRatio", 0))
                                    mark_price = float(pos_data.get("markPrice", 0))
                                    
                                    if liquidation_price > 0 and mark_price > 0:
                                        # Calculate distance to liquidation
                                        if position.side == "long":
                                            # For long: liquidation happens when price drops to liquidation_price
                                            distance_to_liquidation_pct = ((mark_price - liquidation_price) / mark_price) * 100
                                            # 🚀 FIX: Only trigger emergency closure if stop-loss has failed AND we're very close
                                            # Check if we're already past stop-loss level (should have triggered at -50%)
                                            price_change_pct = ((mark_price - position.entry_price) / position.entry_price)
                                            return_on_capital_pct = price_change_pct * position.leverage
                                            pnl_pct = return_on_capital_pct * 100
                                            
                                            # Emergency: close if within 0.5% of liquidation OR margin ratio > 85% OR loss > -45% (stop-loss failed)
                                            # Only trigger if stop-loss should have already triggered but didn't
                                            if (distance_to_liquidation_pct < 0.5 or margin_ratio > 0.85) or (pnl_pct < -45.0):
                                                logger.error(
                                                    f"🚨 [LIQUIDATION RISK!] {symbol} | "
                                                    f"Price ${mark_price:.4f} is {distance_to_liquidation_pct:.2f}% from liquidation (${liquidation_price:.4f}) | "
                                                    f"Margin ratio: {margin_ratio*100:.2f}% | PnL: {pnl_pct:.2f}% | "
                                                    f"EMERGENCY CLOSURE to prevent liquidation! (Stop-loss should have triggered at -50%)"
                                                )
                                                await self.close_position(symbol, exit_reason=f"EMERGENCY: Too close to liquidation (${liquidation_price:.4f}, margin: {margin_ratio*100:.1f}%, PnL: {pnl_pct:.2f}%)")
                                                continue
                                        else:  # short
                                            # For short: liquidation happens when price rises to liquidation_price
                                            distance_to_liquidation_pct = ((liquidation_price - mark_price) / mark_price) * 100
                                            # 🚀 FIX: Only trigger emergency closure if stop-loss has failed AND we're very close
                                            # Check if we're already past stop-loss level (should have triggered at -50%)
                                            price_change_pct = ((position.entry_price - mark_price) / position.entry_price)
                                            return_on_capital_pct = price_change_pct * position.leverage
                                            pnl_pct = return_on_capital_pct * 100
                                            
                                            # Emergency: close if within 0.5% of liquidation OR margin ratio > 85% OR loss > -45% (stop-loss failed)
                                            # Only trigger if stop-loss should have already triggered but didn't
                                            if (distance_to_liquidation_pct < 0.5 or margin_ratio > 0.85) or (pnl_pct < -45.0):
                                                logger.error(
                                                    f"🚨 [LIQUIDATION RISK!] {symbol} | "
                                                    f"Price ${mark_price:.4f} is {distance_to_liquidation_pct:.2f}% from liquidation (${liquidation_price:.4f}) | "
                                                    f"Margin ratio: {margin_ratio*100:.2f}% | PnL: {pnl_pct:.2f}% | "
                                                    f"EMERGENCY CLOSURE to prevent liquidation! (Stop-loss should have triggered at -50%)"
                                                )
                                                await self.close_position(symbol, exit_reason=f"EMERGENCY: Too close to liquidation (${liquidation_price:.4f}, margin: {margin_ratio*100:.1f}%, PnL: {pnl_pct:.2f}%)")
                                                continue
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to check liquidation price for {symbol}: {e}")
                    
                    # Also check if price has hit stop-loss level (bot-side backup)
                    state = self.state_manager.get_state(symbol)
                    if state and state.last_price > 0:
                        current_price = state.last_price
                        
                        # Calculate if price has hit stop-loss level
                        if position.side == "long":
                            price_change_pct = ((current_price - position.entry_price) / position.entry_price)
                            hit_sl = current_price <= sl_price
                        else:
                            price_change_pct = ((position.entry_price - current_price) / position.entry_price)
                            hit_sl = current_price >= sl_price
                        
                        return_on_capital_pct = price_change_pct * position.leverage
                        pnl_pct = return_on_capital_pct * 100
                        
                        # 🚨 CRITICAL: Close positions earlier to prevent liquidations!
                        # If price has hit stop-loss level OR loss exceeds -35%, close immediately
                        # Trigger earlier to catch stop-loss failures before they become big losses
                        if hit_sl or pnl_pct < -35.0:  # Trigger at -35% to prevent liquidations (was -40%)
                            logger.error(
                                f"🚨 [BOT-SIDE STOP-LOSS] {symbol} | "
                                f"Price hit stop-loss level (${sl_price:.4f}) or loss exceeded -35%! | "
                                f"Current price: ${current_price:.4f} | PnL: {pnl_pct:.2f}% | "
                                f"Closing manually as backup (exchange stop-loss may have failed!)"
                            )
                            await self.close_position(symbol, exit_reason=f"BOT-SIDE-STOP-LOSS (price hit ${sl_price:.4f}, PnL: {pnl_pct:.2f}%)")
                            continue
                
                except Exception as e:
                    logger.warning(f"⚠️ Failed to verify stop-loss for {symbol}: {e}")
        
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

            # 🚨 CRITICAL: Check liquidation risk on EVERY position check!
            # This prevents liquidations by closing positions before they get liquidated
            position = self.position_manager.get_position(symbol)
            if position:
                try:
                    # Get position data from exchange to check liquidation price
                    endpoint = "/api/v2/mix/position/all-position"
                    params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
                    response = await self.rest_client._request("GET", endpoint, params=params)
                    
                    if response.get("code") == "00000" and "data" in response:
                        for pos_data in response.get("data", []):
                            if pos_data.get("symbol") == symbol:
                                liquidation_price = float(pos_data.get("liquidationPrice", 0))
                                margin_ratio = float(pos_data.get("marginRatio", 0))
                                mark_price = float(pos_data.get("markPrice", 0))
                                
                                if liquidation_price > 0 and mark_price > 0:
                                    # Calculate distance to liquidation
                                    if position.side == "long":
                                        # For long: liquidation happens when price drops to liquidation_price
                                        distance_to_liquidation_pct = ((mark_price - liquidation_price) / mark_price) * 100
                                        # 🚀 FIX: Only trigger emergency closure if stop-loss has failed AND we're very close
                                        # Check if we're already past stop-loss level (should have triggered at -50%)
                                        price_change_pct = ((mark_price - position.entry_price) / position.entry_price)
                                        return_on_capital_pct = price_change_pct * position.leverage
                                        pnl_pct = return_on_capital_pct * 100
                                        
                                        # Emergency: close if within 0.5% of liquidation OR margin ratio > 85% OR loss > -45% (stop-loss failed)
                                        # Only trigger if stop-loss should have already triggered but didn't
                                        if (distance_to_liquidation_pct < 0.5 or margin_ratio > 0.85) or (pnl_pct < -45.0):
                                            logger.error(
                                                f"🚨 [LIQUIDATION RISK!] {symbol} | "
                                                f"Price ${mark_price:.4f} is {distance_to_liquidation_pct:.2f}% from liquidation (${liquidation_price:.4f}) | "
                                                f"Margin ratio: {margin_ratio*100:.2f}% | PnL: {pnl_pct:.2f}% | "
                                                f"EMERGENCY CLOSURE to prevent liquidation! (Stop-loss should have triggered at -50%)"
                                            )
                                            await self.close_position(symbol, exit_reason=f"EMERGENCY: Too close to liquidation (${liquidation_price:.4f}, margin: {margin_ratio*100:.1f}%, PnL: {pnl_pct:.2f}%)")
                                            continue
                                    else:  # short
                                        # For short: liquidation happens when price rises to liquidation_price
                                        distance_to_liquidation_pct = ((liquidation_price - mark_price) / mark_price) * 100
                                        # 🚀 FIX: Only trigger emergency closure if stop-loss has failed AND we're very close
                                        # Check if we're already past stop-loss level (should have triggered at -50%)
                                        price_change_pct = ((position.entry_price - mark_price) / position.entry_price)
                                        return_on_capital_pct = price_change_pct * position.leverage
                                        pnl_pct = return_on_capital_pct * 100
                                        
                                        # Emergency: close if within 0.5% of liquidation OR margin ratio > 85% OR loss > -45% (stop-loss failed)
                                        # Only trigger if stop-loss should have already triggered but didn't
                                        if (distance_to_liquidation_pct < 0.5 or margin_ratio > 0.85) or (pnl_pct < -45.0):
                                            logger.error(
                                                f"🚨 [LIQUIDATION RISK!] {symbol} | "
                                                f"Price ${mark_price:.4f} is {distance_to_liquidation_pct:.2f}% from liquidation (${liquidation_price:.4f}) | "
                                                f"Margin ratio: {margin_ratio*100:.2f}% | PnL: {pnl_pct:.2f}% | "
                                                f"EMERGENCY CLOSURE to prevent liquidation! (Stop-loss should have triggered at -50%)"
                                            )
                                            await self.close_position(symbol, exit_reason=f"EMERGENCY: Too close to liquidation (${liquidation_price:.4f}, margin: {margin_ratio*100:.1f}%, PnL: {pnl_pct:.2f}%)")
                                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check liquidation price for {symbol} in main loop: {e}")

            # 🚀 PHASE 4.1: Quick Profit Taking
            # If position reaches +5% capital profit within 2 minutes, take 50% profit
            # If position reaches +8% capital profit within 3 minutes, take 100% profit
            # This locks in quick wins before reversals
            if position:
                try:
                    entry_time = datetime.fromisoformat(position.entry_time.replace('Z', '+00:00'))
                    time_in_position_min = (datetime.now(entry_time.tzinfo) - entry_time).total_seconds() / 60
                    
                    # Calculate current PnL
                    if position.side == "long":
                        price_change_pct = ((current_price - position.entry_price) / position.entry_price)
                    else:  # short
                        price_change_pct = ((position.entry_price - current_price) / position.entry_price)
                    
                    return_on_capital_pct = price_change_pct * position.leverage
                    pnl_pct = return_on_capital_pct * 100
                    
                    # Quick profit taking rules
                    if time_in_position_min >= 2 and pnl_pct >= 5.0:
                        # Take 50% profit if +5% in 2 minutes
                        logger.info(
                            f"💰 [QUICK PROFIT] {symbol} | +{pnl_pct:.2f}% profit in {time_in_position_min:.1f}min | "
                            f"Taking 50% profit to lock in gains"
                        )
                        # Note: For now, we'll close the full position as partial closes are complex
                        # In future, we can implement partial position closing
                        await self.close_position(symbol, exit_reason=f"QUICK PROFIT: +{pnl_pct:.2f}% in {time_in_position_min:.1f}min (50% profit target)")
                        continue
                    elif time_in_position_min >= 3 and pnl_pct >= 8.0:
                        # Take 100% profit if +8% in 3 minutes
                        logger.info(
                            f"💰 [QUICK PROFIT] {symbol} | +{pnl_pct:.2f}% profit in {time_in_position_min:.1f}min | "
                            f"Taking 100% profit to lock in gains"
                        )
                        await self.close_position(symbol, exit_reason=f"QUICK PROFIT: +{pnl_pct:.2f}% in {time_in_position_min:.1f}min (100% profit target)")
                        continue
                    
                    # 🚨 TIME-BASED LOSS EXIT: Exit positions open >2 hours and still in loss
                    elif time_in_position_min >= 120 and pnl_pct < 0:
                        # Position has been open for 2+ hours and is still losing money - cut losses!
                        logger.warning(
                            f"⏰ [TIME-BASED LOSS EXIT] {symbol} | Position open for {time_in_position_min:.1f}min (>2h) and still in loss ({pnl_pct:.2f}%) | "
                            f"Closing to free capital and avoid further losses"
                        )
                        await self.close_position(symbol, exit_reason=f"TIME-BASED LOSS EXIT: {pnl_pct:.2f}% loss after {time_in_position_min:.1f}min (>2h)")
                        continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check quick profit/time-based exit for {symbol}: {e}")

            # 🚀 NEW FEATURE: Momentum Reversal Exit
            # If momentum gives a strong opposite signal, exit immediately regardless of profit/loss
            if position and self.config.momentum_reversal_enabled:
                try:
                    # Get current signal for this symbol
                    features = self.state_manager.get_features(symbol)
                    if features:
                        # Get BTC return for correlation check
                        btc_features = self.state_manager.get_features("BTCUSDT")
                        btc_return = btc_features.get("return_5min", 0.0) if btc_features else 0.0
                        
                        # Compute current signal score and direction
                        signal_score, signal_direction, signal_metadata = self.enhanced_ranker.compute_enhanced_score(
                            state, features, btc_return
                        )
                        
                        # Check if signal is opposite to position side AND score is strong
                        is_opposite = (
                            (position.side == "long" and signal_direction == "short") or
                            (position.side == "short" and signal_direction == "long")
                        )
                        
                        if is_opposite and signal_score >= self.config.momentum_reversal_threshold:
                            # Calculate current PnL for logging
                            if position.side == "long":
                                price_change_pct = ((current_price - position.entry_price) / position.entry_price)
                            else:
                                price_change_pct = ((position.entry_price - current_price) / position.entry_price)
                            return_on_capital_pct = price_change_pct * position.leverage
                            pnl_pct = return_on_capital_pct * 100
                            
                            logger.warning(
                                f"🔄 [MOMENTUM REVERSAL] {symbol} | "
                                f"Position: {position.side.upper()} | Current Signal: {signal_direction.upper()} (score: {signal_score:.2f}) | "
                                f"Strong opposite signal detected! | "
                                f"Current PnL: {pnl_pct:.2f}% | "
                                f"Exiting immediately regardless of profit/loss"
                            )
                            
                            await self.close_position(
                                symbol,
                                exit_reason=f"MOMENTUM REVERSAL: Strong {signal_direction.upper()} signal (score: {signal_score:.2f}) detected while holding {position.side.upper()} position | PnL: {pnl_pct:.2f}%"
                            )
                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check momentum reversal for {symbol}: {e}")
            
            # 🚀 CRITICAL BACKUP: Bot-side TP monitoring (in case exchange-side TP fails!)
            # This fixes the issue where positions reach +25% profit but TP never triggers
            # Exchange-side TP can fail if:
            # 1. Trailing TP order was never placed (size rounding issue)
            # 2. Trailing TP order was cancelled
            # 3. Exchange-side TP has bugs or delays
            # 
            # Bot-side TP acts as a backup to ensure profits are locked in!
            if position:
                try:
                    # Calculate current PnL
                    if position.side == "long":
                        price_change_pct = ((current_price - position.entry_price) / position.entry_price)
                    else:
                        price_change_pct = ((position.entry_price - current_price) / position.entry_price)
                    
                    return_on_capital_pct = price_change_pct * position.leverage
                    pnl_pct = return_on_capital_pct * 100
                    
                    # Get TP threshold from position metadata or use default
                    tp_threshold_pct = position.metadata.get("take_profit_pct", position.take_profit_pct) * 100
                    trailing_callback_pct = position.metadata.get("trailing_stop_pct", position.trailing_stop_pct) * 100
                    
                    # Check if position has reached TP threshold (e.g., 16% capital)
                    if pnl_pct >= tp_threshold_pct:
                        # Position has reached TP threshold - check if trailing TP should trigger
                        # Trailing TP activates at TP threshold, then trails from peak
                        peak_pnl_pct = position.peak_pnl_pct
                        
                        # If we've reached TP threshold, trailing TP should be active
                        # Check if price has dropped from peak by trailing callback amount
                        if peak_pnl_pct >= tp_threshold_pct:
                            # Calculate trailing stop price from peak
                            if position.side == "long":
                                # Peak price = entry * (1 + peak_pnl_price_pct)
                                peak_pnl_price_pct = peak_pnl_pct / (100 * position.leverage)
                                peak_price = position.entry_price * (1 + peak_pnl_price_pct)
                                
                                # Trailing stop = peak * (1 - trailing_callback_price_pct)
                                trailing_callback_price_pct = trailing_callback_pct / (100 * position.leverage)
                                trailing_stop_price = peak_price * (1 - trailing_callback_price_pct)
                                
                                # Check if current price has dropped below trailing stop
                                if current_price < trailing_stop_price:
                                    logger.warning(
                                        f"🎯 [BOT-SIDE TRAILING TP] {symbol} | "
                                        f"Position reached TP threshold ({tp_threshold_pct:.0f}%) and trailing TP should trigger! | "
                                        f"Peak: {peak_pnl_pct:.2f}% | Current: {pnl_pct:.2f}% | "
                                        f"Peak price: ${peak_price:.4f} | Trailing stop: ${trailing_stop_price:.4f} | "
                                        f"Current price: ${current_price:.4f} | "
                                        f"Closing manually as backup (exchange trailing TP may have failed!)"
                                    )
                                    await self.close_position(
                                        symbol,
                                        exit_reason=f"BOT-SIDE TRAILING TP: Price dropped below trailing stop (peak: {peak_pnl_pct:.2f}%, current: {pnl_pct:.2f}%)"
                                    )
                                    continue
                            else:  # short
                                # Peak price = entry * (1 - peak_pnl_price_pct)
                                peak_pnl_price_pct = peak_pnl_pct / (100 * position.leverage)
                                peak_price = position.entry_price * (1 - peak_pnl_price_pct)
                                
                                # Trailing stop = peak * (1 + trailing_callback_price_pct)
                                trailing_callback_price_pct = trailing_callback_pct / (100 * position.leverage)
                                trailing_stop_price = peak_price * (1 + trailing_callback_price_pct)
                                
                                # Check if current price has risen above trailing stop
                                if current_price > trailing_stop_price:
                                    logger.warning(
                                        f"🎯 [BOT-SIDE TRAILING TP] {symbol} | "
                                        f"Position reached TP threshold ({tp_threshold_pct:.0f}%) and trailing TP should trigger! | "
                                        f"Peak: {peak_pnl_pct:.2f}% | Current: {pnl_pct:.2f}% | "
                                        f"Peak price: ${peak_price:.4f} | Trailing stop: ${trailing_stop_price:.4f} | "
                                        f"Current price: ${current_price:.4f} | "
                                        f"Closing manually as backup (exchange trailing TP may have failed!)"
                                    )
                                    await self.close_position(
                                        symbol,
                                        exit_reason=f"BOT-SIDE TRAILING TP: Price rose above trailing stop (peak: {peak_pnl_pct:.2f}%, current: {pnl_pct:.2f}%)"
                                    )
                                    continue
                        else:
                            # Position just reached TP threshold - log for monitoring
                            if pnl_pct >= tp_threshold_pct * 1.1:  # 10% above threshold (e.g., 17.6% when threshold is 16%)
                                logger.warning(
                                    f"⚠️ [TP THRESHOLD REACHED] {symbol} | "
                                    f"Position has reached TP threshold ({tp_threshold_pct:.0f}%)! | "
                                    f"Current PnL: {pnl_pct:.2f}% | "
                                    f"Trailing TP should be active. Monitoring for trailing stop trigger..."
                                )
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check bot-side TP for {symbol}: {e}")
            
            # 🚨 CRITICAL: We use EXCHANGE-SIDE TP/SL orders - NO bot-side exit checking!
            # The exchange automatically closes positions when TP/SL triggers.
            # We only update position tracking data - we NEVER trigger exits from the bot!
            # 
            # What we do:
            # 1. Update prices for tracking (for PnL display and logging)
            # 2. Detect when exchange closes positions (done in sync logic above, lines 1097-1139)
            # 3. Monitor liquidation risk and close positions before liquidation
            # 4. Check for momentum reversal (strong opposite signal)
            # 5. Bot-side TP monitoring as backup (if exchange-side TP fails)
            # 
            # What we DON'T do:
            # - Check exit conditions (disabled - exchange handles it)
            # - Manually close positions (only when exchange already closed them OR liquidation risk OR momentum reversal OR bot-side TP backup)
            # - Trigger any exits (exchange TP/SL handles all exits automatically, bot-side is backup only)
            # 
            # This ensures positions close at EXACTLY the TP/SL prices we set on the exchange!
            self.position_manager.update_position_price(symbol, current_price)
            
            positions_checked += 1

    async def execute_trades(self, allocations: list[dict[str, Any]]) -> None:
        """Execute trades based on allocations."""
        logger.info(f"💼 Execute trades called with {len(allocations)} allocations")
        
        # 🚨 NO REBALANCING! Hold positions until TP/SL/trailing hit!
        # HOLD-AND-FILL STRATEGY:
        # - Open positions with A-grade signals
        # - HOLD until TP (6%) or SL (25%) or trailing (1%) triggers
        # - NO rebalancing = lower fees, let winners run!

        # Open new positions
        trades_attempted = 0
        trades_successful = 0
        
        for alloc in allocations:
            try:  # CRITICAL: Wrap each trade in try-except so one failure doesn't stop all trades!
                symbol = alloc["symbol"]
                signal_side = alloc["predicted_side"]
                signal_score = alloc["score"]  # Get signal score
                regime = alloc["regime"]
                position_size_multiplier = alloc["position_size_multiplier"]

                # 🚀 CRITICAL: Check dynamic entry threshold based on token performance tier!
                # Tier1 (best): 2.0 threshold (more opportunities)
                # Tier2 (good): 2.5 threshold (current)
                # Tier3 (average): 3.0 threshold (stricter)
                # Tier4 (poor): 3.5 threshold OR skip entirely
                if self.dynamic_params:
                    # Use dynamic threshold based on token performance
                    # Note: get_entry_threshold returns multipliers (0.65-1.25), so apply to base threshold
                    base_threshold = self.config.min_entry_score_short if signal_side == "short" else self.config.min_entry_score
                    threshold_multiplier = self.dynamic_params.get_entry_threshold(symbol, default_threshold=1.0)
                    min_score = base_threshold * threshold_multiplier
                else:
                    # Fallback to fixed thresholds
                    min_score = self.config.min_entry_score_short if signal_side == "short" else self.config.min_entry_score
                
                if signal_score < min_score:
                    logger.info(  # Changed to info to see why trades are rejected
                        f"🚫 [ENTRY REJECTED] {symbol} | {signal_side.upper()} signal score ({signal_score:.2f}) below dynamic threshold ({min_score:.2f}) | "
                        f"Skipping to reduce trade frequency"
                    )
                    continue
                
                # 🚀 PHASE 1.3: Skip Tier4 tokens entirely (bottom 20% performers)
                if self.dynamic_params:
                    tier = self.dynamic_params.get_performance_tier(symbol)
                    if tier == "tier4":
                        logger.debug(
                            f"🚫 [ENTRY REJECTED] {symbol} | Tier4 token (bottom 20% performers) - skipping to improve win rate"
                        )
                        continue
                
                # 🚀 PHASE 3.2: Real-time performance filtering
                # Check recent performance (last 10 trades) for symbol
                # If win rate < 50% in last 10 trades, skip symbol temporarily
                # Reset after 24 hours
                if symbol in self.symbol_recent_trades:
                    recent_trades = self.symbol_recent_trades[symbol]
                    if len(recent_trades) >= 10:
                        wins = sum(1 for t in recent_trades if t.get("is_win", False))
                        win_rate = wins / len(recent_trades)
                        if win_rate < 0.50:  # Less than 50% win rate
                            # Check if 24 hours have passed since last reset
                            reset_time = self.symbol_filter_reset_time.get(symbol)
                            if reset_time is None or (datetime.now() - reset_time).total_seconds() < 86400:
                                logger.debug(
                                    f"🚫 [ENTRY REJECTED] {symbol} | Recent win rate ({win_rate:.1%}) below 50% in last {len(recent_trades)} trades - skipping temporarily"
                                )
                                continue
                            else:
                                # Reset after 24 hours
                                self.symbol_recent_trades[symbol] = []
                                self.symbol_filter_reset_time[symbol] = datetime.now()
                                logger.debug(f"🔄 [FILTER RESET] {symbol} | Resetting performance filter after 24 hours")

                # Skip if already have position
                if symbol in self.position_manager.positions:
                    logger.debug(f"🚫 [ENTRY REJECTED] {symbol} | Already have position for this symbol")
                    continue

                # Skip if max positions reached
                if len(self.position_manager.positions) >= self.max_positions:
                    break

                # Calculate position size (SMART SIZING based on signal strength + regime)
                state = self.state_manager.get_state(symbol)
                if not state:
                    continue

                # 🚀 CRITICAL: Get FRESH price right before placing order to avoid slippage!
                # Price from state manager might be stale, so fetch fresh from exchange
                try:
                    ticker_data = await self.rest_client.get_ticker(symbol)
                    if ticker_data and ticker_data.get("code") == "00000":
                        ticker_list = ticker_data.get("data", [])
                        if ticker_list and len(ticker_list) > 0:
                            fresh_price = float(ticker_list[0].get("lastPr", 0))
                            if fresh_price > 0:
                                price = fresh_price
                                logger.debug(f"✅ [FRESH PRICE] {symbol} | Fetched fresh price: ${price:.4f}")
                            else:
                                # Fallback to state manager
                                price = state.last_price
                                logger.warning(f"⚠️ [PRICE FALLBACK] {symbol} | Using state price: ${price:.4f}")
                        else:
                            # Fallback to state manager
                            price = state.last_price
                            logger.warning(f"⚠️ [PRICE FALLBACK] {symbol} | Using state price: ${price:.4f}")
                    else:
                        # Fallback to state manager
                        price = state.last_price
                        logger.warning(f"⚠️ [PRICE FALLBACK] {symbol} | Using state price: ${price:.4f}")
                except Exception as e:
                    # Fallback to state manager
                    price = state.last_price
                    logger.warning(f"⚠️ [PRICE ERROR] {symbol} | Error fetching fresh price: {e} | Using state price: ${price:.4f}")
                
                if price == 0:
                    logger.error(f"❌ [PRICE ERROR] {symbol} | Price is 0, skipping trade")
                    continue
                
                # 🚀 PHASE 5.1: Spread Filter - reject if spread > 0.2% (20 bps) - RELAXED for faster entry
                # Only reject very wide spreads (relaxed threshold for faster trade placement)
                try:
                    if ticker_data and ticker_data.get("code") == "00000":
                        ticker_list = ticker_data.get("data", [])
                        if ticker_list and len(ticker_list) > 0:
                            ticker = ticker_list[0]
                            bid_price = float(ticker.get("bidPr", 0))
                            ask_price = float(ticker.get("askPr", 0))
                            if bid_price > 0 and ask_price > 0:
                                spread_pct = ((ask_price - bid_price) / bid_price) * 100
                                if spread_pct > 0.2:  # Spread > 0.2% (20 bps) - relaxed from 0.1% for faster entry
                                    logger.debug(
                                        f"🚫 [ENTRY REJECTED] {symbol} | Spread ({spread_pct:.3f}%) too wide (>0.2%) - skipping for better fills"
                                    )
                                    continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check spread for {symbol}: {e}")
                
                # 🚀 PHASE 5.2: Funding Rate Filter - reject negative carry trades
                # For longs: Reject if funding rate > 0.05% (negative carry)
                # For shorts: Reject if funding rate < -0.05% (negative carry)
                try:
                    features = self.state_manager.get_features(symbol)
                    if features:
                        funding_rate = features.get("funding_rate", 0.0)
                        if signal_side == "long" and funding_rate > 0.0005:  # > 0.05%
                            logger.debug(
                                f"🚫 [ENTRY REJECTED] {symbol} | LONG signal but funding rate ({funding_rate*100:.3f}%) is negative carry (>0.05%) - skipping"
                            )
                            continue
                        elif signal_side == "short" and funding_rate < -0.0005:  # < -0.05%
                            logger.debug(
                                f"🚫 [ENTRY REJECTED] {symbol} | SHORT signal but funding rate ({funding_rate*100:.3f}%) is negative carry (<-0.05%) - skipping"
                            )
                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check funding rate for {symbol}: {e}")
                
                # 🚀 PHASE 5.3: Correlation Filter - limit BTC-correlated positions to 3 max
                # If already have 3 BTC-correlated positions, skip new BTC-correlated signals
                try:
                    features = self.state_manager.get_features(symbol)
                    btc_features = self.state_manager.get_features("BTCUSDT")
                    if features and btc_features:
                        symbol_return = features.get("return_5min", 0.0)
                        btc_return = btc_features.get("return_5min", 0.0)
                        # Check if symbol moves with BTC (correlation)
                        if btc_return != 0 and abs(symbol_return) > 0:
                            correlation = (symbol_return / btc_return) if btc_return != 0 else 0
                            # If correlation > 0.5, consider it BTC-correlated
                            if abs(correlation) > 0.5:
                                # Count existing BTC-correlated positions
                                btc_correlated_count = 0
                                for pos_symbol in self.position_manager.positions.keys():
                                    pos_features = self.state_manager.get_features(pos_symbol)
                                    if pos_features:
                                        pos_return = pos_features.get("return_5min", 0.0)
                                        pos_correlation = (pos_return / btc_return) if btc_return != 0 else 0
                                        if abs(pos_correlation) > 0.5:
                                            btc_correlated_count += 1
                                
                                if btc_correlated_count >= 3:
                                    logger.debug(
                                        f"🚫 [ENTRY REJECTED] {symbol} | BTC-correlated position limit reached ({btc_correlated_count}/3) - skipping for better diversification"
                                    )
                                    continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check correlation for {symbol}: {e}")
                
                # 🚀 CRITICAL: Validate that price is actually moving in our direction!
                # This prevents entering longs during downtrends and shorts during uptrends
                try:
                    # Get recent price history (last 10-15 seconds for trend confirmation)
                    recent_prices = [p for _, p in list(state.price_history)[-15:]] if state.price_history else []
                    if len(recent_prices) >= 3:
                        # Check short-term momentum (last 3 prices = ~3-5 seconds)
                        short_term_change = ((recent_prices[-1] - recent_prices[-3]) / recent_prices[-3]) * 100 if len(recent_prices) >= 3 else 0
                        # Check medium-term momentum (last 5 prices = ~5-10 seconds)
                        medium_term_change = ((recent_prices[-1] - recent_prices[-5]) / recent_prices[-5]) * 100 if len(recent_prices) >= 5 else 0
                        # Check longer-term momentum (last 10 prices = ~10-15 seconds)
                        long_term_change = ((recent_prices[-1] - recent_prices[-10]) / recent_prices[-10]) * 100 if len(recent_prices) >= 10 else 0
                        
                        # For long: ALL timeframes should show rising price (positive change)
                        # For short: ALL timeframes should show falling price (negative change)
                        if signal_side == "long":
                            # 🚀 OPTIMIZED: Relaxed momentum confirmation - require MOST timeframes (not ALL) to show rising
                            # Long position: require at least 2 out of 3 timeframes to show rising price (faster entry)
                            rising_count = sum([
                                short_term_change > 0.02,  # Lowered threshold from 0.03% to 0.02%
                                medium_term_change > 0.03,  # Lowered threshold from 0.05% to 0.03%
                                long_term_change > 0.05     # Lowered threshold from 0.08% to 0.05%
                            ])
                            if rising_count < 2:  # Require at least 2 out of 3 (was ALL 3)
                                # Price is not rising in most timeframes - REJECT long entry!
                                logger.debug(
                                    f"🚫 [ENTRY REJECTED] {symbol} | LONG signal but price not rising in most timeframes ({rising_count}/3) | "
                                    f"Short: {short_term_change:.3f}% | Medium: {medium_term_change:.3f}% | "
                                    f"Long: {long_term_change:.3f}% | Skipping to avoid entering during wrong momentum"
                                )
                                continue
                            else:
                                # Price is rising in most timeframes - good to enter
                                logger.info(
                                    f"✅ [ENTRY CONFIRMED] {symbol} | LONG signal with RISING price in {rising_count}/3 timeframes | "
                                    f"Short: {short_term_change:.3f}% | Medium: {medium_term_change:.3f}% | "
                                    f"Long: {long_term_change:.3f}%"
                                )
                        else:  # short
                            # 🚀 OPTIMIZED: More relaxed short entry - only reject if STRONGLY rising
                            # Short position: Allow if price is falling, neutral, OR slightly rising (faster entry)
                            # This enables shorts during pullbacks and consolidations
                            is_strongly_rising = short_term_change > 0.08 and medium_term_change > 0.12 and long_term_change > 0.15  # Higher thresholds
                            
                            if is_strongly_rising:
                                # Price is STRONGLY rising - REJECT short entry!
                                logger.debug(
                                    f"🚫 [ENTRY REJECTED] {symbol} | SHORT signal but price is STRONGLY RISING! | "
                                    f"Short: {short_term_change:.3f}% | Medium: {medium_term_change:.3f}% | "
                                    f"Long: {long_term_change:.3f}% | Skipping to avoid entering during wrong momentum"
                                )
                                continue
                            else:
                                # Price is falling, neutral, or slightly rising - good to enter short
                                logger.info(
                                    f"✅ [ENTRY CONFIRMED] {symbol} | SHORT signal with acceptable price action | "
                                    f"Short: {short_term_change:.3f}% | Medium: {medium_term_change:.3f}% | "
                                    f"Long: {long_term_change:.3f}%"
                                )
                    else:
                        # Not enough price history - skip for now
                        logger.debug(f"⚠️ [ENTRY WAIT] {symbol} | Not enough price history ({len(recent_prices)} points), waiting...")
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ [ENTRY CONFIRMATION ERROR] {symbol} | Error: {e} | Proceeding with caution")
                
                # 🚀 PHASE 1: PULLBACK DETECTION - Wait for retracements instead of entering at peaks!
                # This is CRITICAL to avoid buying tops and selling bottoms
                try:
                    prices_for_pullback = [p for _, p in list(state.price_history)[-50:]] if state.price_history else []
                    if len(prices_for_pullback) >= 20:
                        prices_arr = np.array(prices_for_pullback)
                        is_pullback, pullback_pct, trend = self.indicators.detect_pullback(prices_arr, lookback=10)
                        
                        # For LONG: Only enter in uptrend with pullback OR ranging market
                        if signal_side == "long":
                            if trend == "uptrend" and not is_pullback:
                                logger.info(
                                    f"🚫 [ENTRY REJECTED] {symbol} | LONG signal but NO PULLBACK detected (buying top risk) | "
                                    f"Trend: {trend} | Wait for 0.3-1.5% retracement from high"
                                )
                                continue
                            elif trend == "downtrend":
                                logger.debug(f"🚫 [ENTRY REJECTED] {symbol} | LONG signal but in DOWNTREND | Trend: {trend}")
                                continue
                        
                        # For SHORT: RELAXED - Allow in any trend with pullback, OR ranging market
                        # Shorts can work in uptrends during pullbacks (short-term reversals)
                        elif signal_side == "short":
                            # Only reject if in strong uptrend without pullback
                            if trend == "uptrend" and not is_pullback:
                                logger.debug(
                                    f"🚫 [ENTRY REJECTED] {symbol} | SHORT signal in strong UPTREND without pullback | "
                                    f"Trend: {trend} | Need pullback for short entry in uptrend"
                                )
                                continue
                            # Allow shorts in downtrend (even without pullback) and ranging markets
                            # Also allow shorts in uptrend IF there's a pullback (counter-trend)
                        
                        if is_pullback:
                            logger.info(
                                f"✅ [PULLBACK CONFIRMED] {symbol} | {signal_side.upper()} signal with valid pullback | "
                                f"Trend: {trend} | Pullback: {pullback_pct:.2f}% | PERFECT ENTRY SETUP!"
                            )
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check pullback for {symbol}: {e}")
                
                # 🚀 PHASE 2: VELOCITY FILTER - Skip if price moved too fast (parabolic move)
                try:
                    prices_for_velocity = [p for _, p in list(state.price_history)[-10:]] if state.price_history else []
                    if len(prices_for_velocity) >= 6:
                        prices_arr = np.array(prices_for_velocity)
                        should_skip, velocity_pct = self.indicators.check_velocity_filter(prices_arr, window=6)
                        
                        if should_skip:
                            logger.info(
                                f"🚫 [ENTRY REJECTED] {symbol} | Price moved too fast: {velocity_pct:.2f}% in 30s (>1%) | "
                                f"Parabolic move - likely to reverse! Wait for consolidation"
                            )
                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check velocity for {symbol}: {e}")
                
                # 🚀 PHASE 3: VWAP DISTANCE CHECK - Skip if too far from VWAP (mean reversion expected)
                try:
                    prices_for_vwap = [p for _, p in list(state.price_history)[-20:]] if state.price_history else []
                    volumes_for_vwap = [state.features.get("volume", 1000) for _ in range(min(20, len(prices_for_vwap)))]
                    
                    if len(prices_for_vwap) >= 20:
                        prices_arr = np.array(prices_for_vwap)
                        volumes_arr = np.array(volumes_for_vwap)
                        distance_pct, is_extended = self.indicators.calculate_distance_from_vwap(prices_arr, volumes_arr)
                        
                        if is_extended:
                            logger.info(
                                f"🚫 [ENTRY REJECTED] {symbol} | Price too far from VWAP: {distance_pct:.2f}% (>1.5%) | "
                                f"Mean reversion expected! Wait for return to VWAP"
                            )
                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Failed to check VWAP distance for {symbol}: {e}")

                # 🚨 CRITICAL: Use TOTAL EQUITY (available + margin in positions + unrealized PnL) for position sizing
                # This ensures each trade gets 10% of TOTAL capital, not just remaining available balance
                # After first trade, available decreases but equity stays the same (includes locked margin)
                try:
                    balance = await self.rest_client.get_account_balance()
                    if balance and balance.get("code") == "00000":
                        data = balance.get("data", [{}])[0]
                        available_balance = float(data.get("available", 0))
                        frozen = float(data.get("frozen", 0))
                        unrealized_pnl = float(data.get("unrealizedPL", 0))
                        
                        # 🚨 CRITICAL FIX: Bitget's "equity" field doesn't correctly sum all locked margin!
                        # We MUST fetch all positions and sum their marginSize to get true total equity
                        
                        # Fetch all positions to get locked margin
                        all_positions_endpoint = "/api/v2/mix/position/all-position"
                        all_positions_params = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}
                        positions_response = await self.rest_client._request("GET", all_positions_endpoint, params=all_positions_params)
                        
                        total_margin_locked = 0.0
                        if positions_response.get("code") == "00000" and "data" in positions_response:
                            for pos in positions_response.get("data", []):
                                # Only count positions with actual size (filter out closed positions)
                                if float(pos.get("total", 0)) > 0:
                                    margin_size = float(pos.get("marginSize", 0))
                                    total_margin_locked += margin_size
                        
                        # Calculate TRUE total equity: available + locked margin + frozen + unrealized PnL
                        total_equity = available_balance + total_margin_locked + frozen + unrealized_pnl
                        base_position_value = total_equity * self.position_size_pct
                        
                        # Update self.equity for consistency
                        self.equity = total_equity
                        
                        logger.info(
                            f"📊 [TOTAL EQUITY CALC] Available: ${available_balance:.2f} + "
                            f"Margin Locked: ${total_margin_locked:.2f} + "
                            f"Frozen: ${frozen:.2f} + "
                            f"Unrealized PnL: ${unrealized_pnl:+.2f} = "
                            f"Total Equity: ${total_equity:.2f}"
                        )
                        
                        # 🚨 CRITICAL: Validate minimum margin requirements!
                        # Ensure we maintain at least 5% of equity as available margin for safety
                        min_available_margin_pct = 0.05  # 5% minimum available margin
                        min_available_margin = total_equity * min_available_margin_pct
                        
                        # Check if we have enough available balance for this position
                        required_margin = base_position_value  # Margin required = position value (not notional)
                        available_after_trade = available_balance - required_margin
                        
                        if available_after_trade < min_available_margin:
                            # Adjust position size to maintain minimum margin
                            max_allowed_position_value = available_balance - min_available_margin
                            
                            if max_allowed_position_value < min_order_value / self.leverage:
                                # Not enough margin even for minimum order - skip this trade
                                logger.error(
                                    f"🚨 [INSUFFICIENT MARGIN] {symbol} | "
                                    f"Available: ${available_balance:.2f} | Required: ${required_margin:.2f} | "
                                    f"Min Available Margin: ${min_available_margin:.2f} (5% of equity ${total_equity:.2f}) | "
                                    f"Available after trade would be: ${available_after_trade:.2f} | "
                                    f"SKIPPING TRADE - insufficient margin!"
                                )
                                continue
                            
                            # Reduce position size to maintain minimum margin
                            base_position_value = max_allowed_position_value
                            logger.warning(
                                f"⚠️ [MARGIN ADJUSTMENT] {symbol} | "
                                f"Reduced position size from ${total_equity * self.position_size_pct:.2f} to ${base_position_value:.2f} | "
                                f"To maintain minimum available margin: ${min_available_margin:.2f} (5% of equity)"
                            )
                        
                        logger.info(
                            f"💰 [EQUITY CHECK] {symbol} | Total Equity: ${total_equity:.2f} | "
                            f"Available: ${available_balance:.2f} | Frozen: ${frozen:.2f} | "
                            f"Unrealized PnL: ${unrealized_pnl:+.2f} | "
                            f"10% Position Size: ${base_position_value:.2f} | "
                            f"Available After: ${available_balance - base_position_value:.2f} | "
                            f"Min Required: ${min_available_margin:.2f}"
                        )
                    else:
                        # Fallback to tracked equity if balance fetch fails
                        base_position_value = self.equity * self.position_size_pct
                        logger.warning(f"⚠️ [BALANCE FALLBACK] {symbol} | Using tracked equity: ${self.equity:.2f}")
                except Exception as e:
                    # Fallback to tracked equity if balance fetch fails
                    logger.warning(f"⚠️ [BALANCE ERROR] {symbol} | Error: {e} | Using tracked equity: ${self.equity:.2f}")
                    base_position_value = self.equity * self.position_size_pct
                
                # 🚀 NEW: Apply dynamic position size multiplier (if enabled)
                if self.dynamic_params:
                    dynamic_multiplier = self.dynamic_params.get_position_size_multiplier(symbol)
                    position_size_multiplier = dynamic_multiplier
                    logger.info(
                        f"📊 [DYNAMIC PARAMS] {symbol} | Position size multiplier: {dynamic_multiplier:.2f}x"
                    )
                
                # Apply position size multiplier (but ensure we still use 10% base)
                adjusted_position_value = base_position_value * position_size_multiplier
                
                # 🚨 VERBOSE LOGGING FOR POSITION SIZING
                logger.info(
                    f"📊 [POS_SIZE_CALC] {symbol} | Equity: ${self.equity:.2f} | "
                    f"Pos Size Pct: {self.position_size_pct*100:.1f}% | "
                    f"Base Value: ${base_position_value:.2f} | "
                    f"Adjusted Value (Multiplier {position_size_multiplier:.2f}x): ${adjusted_position_value:.2f}"
                )
                
                # 🚨 CRITICAL: Final margin check after applying multipliers!
                # Re-check available balance to ensure we maintain minimum margin
                try:
                    balance = await self.rest_client.get_account_balance()
                    if balance and balance.get("code") == "00000":
                        data = balance.get("data", [{}])[0]
                        available_balance = float(data.get("available", 0))
                        total_equity = float(data.get("equity", 0)) or self.equity
                        
                        # Check if we have enough margin for the adjusted position
                        required_margin = adjusted_position_value
                        min_available_margin = total_equity * 0.05  # 5% minimum
                        min_order_value = 5.0 / self.leverage  # Minimum order value in margin terms
                        
                        if available_balance - required_margin < min_available_margin:
                            # Reduce position size to maintain minimum margin
                            max_allowed = available_balance - min_available_margin
                            if max_allowed < min_order_value:
                                logger.error(
                                    f"🚨 [INSUFFICIENT MARGIN] {symbol} | "
                                    f"Adjusted position requires ${required_margin:.2f} margin | "
                                    f"Available: ${available_balance:.2f} | "
                                    f"Would leave: ${available_balance - required_margin:.2f} (need ${min_available_margin:.2f}) | "
                                    f"SKIPPING TRADE!"
                                )
                                continue
                            
                            adjusted_position_value = max_allowed
                            logger.warning(
                                f"⚠️ [MARGIN ADJUSTMENT] {symbol} | "
                                f"Reduced adjusted position to ${adjusted_position_value:.2f} to maintain minimum margin"
                            )
                except Exception as e:
                    logger.warning(f"⚠️ [MARGIN CHECK ERROR] {symbol} | Error: {e} | Proceeding with calculated size")
                
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
                    
                    # Extract entry metadata for loss tracking (including all indicators)
                    # Get features from state to capture all indicators
                    features = state.compute_features() if state else {}
                    
                    # Calculate technical indicators for saving
                    prices = np.array([p for _, p in state.price_history]) if state and state.price_history else np.array([])
                    entry_indicators = {}
                    
                    if len(prices) >= 20:
                        # Calculate RSI
                        rsi = self.enhanced_ranker.technical_indicators.calculate_rsi(prices, period=14)
                        entry_indicators["rsi"] = rsi
                        
                        # Calculate MACD
                        macd_data = self.enhanced_ranker.technical_indicators.calculate_macd(prices, fast_period=3, slow_period=7, signal_period=2)
                        entry_indicators["macd_line"] = macd_data.get("macd_line", 0.0)
                        entry_indicators["macd_signal"] = macd_data.get("signal_line", 0.0)
                        entry_indicators["macd_histogram"] = macd_data.get("histogram", 0.0)
                        
                        # Calculate Bollinger Bands
                        bb_data = self.enhanced_ranker.technical_indicators.calculate_bollinger_bands(prices, period=20, std_dev=2.0)
                        entry_indicators["bb_upper"] = bb_data.get("upper_band", 0.0)
                        entry_indicators["bb_middle"] = bb_data.get("middle_band", 0.0)
                        entry_indicators["bb_lower"] = bb_data.get("lower_band", 0.0)
                        current_price = state.last_price if state else price
                        if bb_data.get("upper_band", 0) > bb_data.get("lower_band", 0):
                            entry_indicators["bb_position"] = (current_price - bb_data.get("middle_band", current_price)) / ((bb_data.get("upper_band", current_price) - bb_data.get("middle_band", current_price)) + 1e-8)
                        else:
                            entry_indicators["bb_position"] = 0.0
                        
                        # Calculate EMA Crossovers
                        ema_data = self.enhanced_ranker.technical_indicators.calculate_ema_crossovers(prices, fast_period=3, slow_period=7)
                        entry_indicators["ema_bullish"] = 1 if ema_data.get("is_bullish", False) else 0
                        entry_indicators["ema_bearish"] = 1 if ema_data.get("is_bearish", False) else 0
                        
                        # Calculate VWAP
                        vwap_data = self.enhanced_ranker.technical_indicators.calculate_vwap(prices, period=20)
                        entry_indicators["vwap"] = vwap_data.get("vwap", 0.0)
                        entry_indicators["vwap_deviation"] = vwap_data.get("deviation", 0.0)
                    else:
                        # Not enough data - use defaults
                        entry_indicators = {
                            "rsi": 50.0,
                            "macd_line": 0.0,
                            "macd_signal": 0.0,
                            "macd_histogram": 0.0,
                            "bb_upper": 0.0,
                            "bb_middle": 0.0,
                            "bb_lower": 0.0,
                            "bb_position": 0.0,
                            "ema_bullish": 0,
                            "ema_bearish": 0,
                            "vwap": 0.0,
                            "vwap_deviation": 0.0,
                        }
                    
                    # Extract entry metadata for loss tracking
                    entry_metadata = {
                        "grade": alloc.get("grade", "Unknown"),
                        "score": alloc.get("score", 0.0),
                        "confluence": alloc.get("confluence", 0.0),
                        "volume_ratio": alloc.get("volume_ratio", 1.0),
                        "entry_structure": alloc.get("market_structure", "unknown"),
                        "near_sr": alloc.get("near_sr", False),
                        "rr_ratio": alloc.get("rr_ratio", 0.0),
                        # Add all indicators
                        "indicators": entry_indicators,
                        "momentum_5s": features.get("return_5s", 0.0),
                        "momentum_15s": features.get("return_15s", 0.0),
                        "volatility_30s": features.get("volatility_30s", 0.0),
                        "volatility_60s": features.get("volatility_60s", 0.0),
                        "spread_bps": features.get("spread_bps", 0.0),
                        "ob_imbalance": features.get("ob_imbalance", 0.0),
                        "funding_rate": features.get("funding_rate", 0.0),
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
        - INSTANT ENTRY: Check for new entries every 0.1s (100ms) when slots available - PLACE TRADES IMMEDIATELY!
        
        KEY: Hold winners until TP/SL hit. No churning = minimal fees!
        """
        iteration = 0
        last_entry_check_time = datetime.now()
        entry_check_interval_sec = 0.01  # Check for new entries every 0.01 seconds (10ms - HYPER-FAST SIGNAL RESPONSE!)
        position_check_interval_sec = 0.005  # Check exits every 0.005 seconds (5ms - HYPER FAST! 10x faster!)

        logger.info("🚀 [TRADING LOOP] Starting trading loop...")
        logger.info(f"   Entry check interval: {entry_check_interval_sec}s")
        logger.info(f"   Position check interval: {position_check_interval_sec}s")
        logger.info(f"   Max positions: {self.max_positions}")
        logger.info(f"   Current positions: {len(self.position_manager.positions)}")

        # Rate limit ticker fetching to avoid 429 errors
        last_ticker_fetch = datetime.now()
        ticker_fetch_interval_sec = 1.0  # Fetch tickers every 1 second (not every 5ms!)

        while self.running:
            try:
                # ALWAYS: Update market data and check positions (FAST LOOP)
                # But rate-limit ticker fetching to avoid 429 errors
                time_since_ticker_fetch = (datetime.now() - last_ticker_fetch).total_seconds()
                if time_since_ticker_fetch >= ticker_fetch_interval_sec:
                    try:
                        ticker_dict = await self.universe_manager.fetch_tickers()
                        last_ticker_fetch = datetime.now()
                        # Cache ticker data for next iteration
                        self._cached_tickers = ticker_dict
                    except Exception as e:
                        logger.warning(f"⚠️ [TICKER FETCH ERROR] {e} - Using cached data")
                        # Use cached ticker data if fetch fails
                        ticker_dict = getattr(self, '_cached_tickers', {})
                        if not ticker_dict:
                            logger.warning("⚠️ [TICKER FETCH] No cached data available, skipping this iteration")
                            await asyncio.sleep(position_check_interval_sec)
                            continue
                else:
                    # Use cached ticker data if available
                    ticker_dict = getattr(self, '_cached_tickers', {})
                    if not ticker_dict:
                        # No cached data yet, wait a bit
                        await asyncio.sleep(position_check_interval_sec)
                        continue
                if ticker_dict:
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

                # Daily loss limit check removed - let positions use full SL (25%)

                # 🚀 HYPER-FAST ENTRY: Check for new entries IMMEDIATELY when slots available (NO WAITING!)
                # This ensures we place trades as soon as signals come in
                available_slots = self.max_positions - len(self.position_manager.positions)
                time_since_entry_check = (datetime.now() - last_entry_check_time).total_seconds()
                should_check_entries = time_since_entry_check >= entry_check_interval_sec  # Still track for logging

                # Debug logging every 200 iterations (1 second) to show bot is active
                loop_count = getattr(self, '_loop_count', 0)
                self._loop_count = loop_count + 1
                if loop_count % 200 == 0:  # Every 1 second (200 * 0.005s = 1s)
                    logger.info(  # Changed to info so it shows up
                        f"💓 [HEARTBEAT] Loop iteration {loop_count} | "
                        f"Available slots: {available_slots} | "
                        f"Time since entry check: {time_since_entry_check:.1f}s | "
                        f"Should check: {should_check_entries} | "
                        f"Positions: {len(self.position_manager.positions)}/{self.max_positions} | "
                        f"Equity: ${self.equity:.2f} ({pnl_pct:+.2f}%)"
                    )

                # 🚀 HYPER-FAST ENTRY: Check immediately when slots available (don't wait for interval)
                # Always check if slots available (remove interval wait for maximum speed)
                if available_slots > 0:
                    iteration += 1
                    last_entry_check_time = datetime.now()
                    
                    logger.info(f"\n{'='*70}")
                    logger.info(f"[ENTRY CHECK #{iteration}] Looking for {available_slots} new positions")
                    logger.info(f"[PROGRESS] Ranking {len(self.symbols)} symbols...")
                    logger.info(f"{'='*70}")

                    # 🚀 NEW: Filter symbols before ranking (if enabled)
                    symbols_to_rank = self.symbols
                    if self.symbol_filter:
                        symbols_to_rank = self.symbol_filter.filter_symbols(self.symbols)
                        logger.info(
                            f"🔍 [FILTER] Filtered {len(self.symbols)} symbols -> {len(symbols_to_rank)} passed "
                            f"({len(self.symbols) - len(symbols_to_rank)} filtered out)"
                        )
                    
                    # Rank ALL symbols - then pick top ones for available slots
                    # This ensures we're trading the BEST opportunities across ALL 300+ tokens!
                    logger.info(f"📊 [RANKING] Analyzing {len(symbols_to_rank)} symbols...")
                    all_ranked = self.enhanced_ranker.rank_symbols_enhanced(
                        self.state_manager,
                        top_k=len(symbols_to_rank),  # Rank filtered symbols
                    )
                    # Then take only the top ones for available slots
                    allocations = all_ranked[:available_slots] if len(all_ranked) > available_slots else all_ranked

                    logger.info(f"✅ [RANKING COMPLETE] Found {len(allocations)} high-quality signals for {available_slots} empty slots")
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
                    # Just log quick status - every 20th check (100ms @ 5ms interval = 1 second)
                    check_count = getattr(self, '_check_count', 0)
                    self._check_count = check_count + 1
                    
                    if check_count % 200 == 0:  # Every 1 second (200 * 5ms)
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
        
        # 🚨 CRITICAL: Set leverage to 25x for ALL symbols at startup (300+ tokens!)
        # ✨ BUT use cache to avoid redundant API calls (leverage persists on Bitget!)
        logger.info(f"🔧 [STARTUP] Checking leverage for {len(self.symbols)} symbols (using cache)...")
        leverage_set_count = 0
        leverage_cached_count = 0
        leverage_failed_count = 0
        try:
            # Set leverage for ALL symbols (not just top 50!) - but use cache to skip already-set ones
            for i, symbol in enumerate(self.symbols, 1):
                for hold_side in ["long", "short"]:
                    try:
                        # Check cache first - if already set, skip API call!
                        if self.leverage_cache.is_set(symbol, self.leverage, hold_side):
                            leverage_cached_count += 1
                            if i <= 5:  # Log first 5 cached ones
                                logger.debug(f"💾 [CACHE HIT] {symbol} {hold_side}: {self.leverage}x already set")
                            continue
                        
                        # Not in cache or expired - set leverage via API
                        response = await self.rest_client.set_leverage(
                            symbol=symbol,
                            leverage=self.leverage,
                            hold_side=hold_side,
                        )
                        if response.get("code") == "00000":
                            leverage_set_count += 1
                            # Update cache with success
                            self.leverage_cache.mark_set(symbol, self.leverage, hold_side)
                            if i <= 10 or i % 50 == 0:  # Log first 10 and every 50th
                                logger.info(f"✅ [STARTUP] {symbol} {hold_side}: {self.leverage}x ({i}/{len(self.symbols)})")
                        else:
                            leverage_failed_count += 1
                            error_code = response.get('code', 'unknown')
                            error_msg = response.get('msg', 'Unknown')
                            
                            # 🚨 CRITICAL: Mark as failed in cache to prevent retrying!
                            # Check if it's a "not supported" error (e.g., 40797 = max leverage exceeded)
                            if error_code in ["40797", "40798"] or "maximum settable leverage" in error_msg.lower() or "not supported" in error_msg.lower():
                                self.leverage_cache.mark_failed(symbol, self.leverage, hold_side, error_code)
                                if i <= 10:  # Log failures for first 10
                                    logger.warning(
                                        f"🚫 [STARTUP] {symbol} {hold_side}: Leverage {self.leverage}x not supported by Bitget | "
                                        f"Code: {error_code} | Cached to skip future attempts"
                                    )
                            else:
                                # Other error - don't cache as failed (might be temporary)
                                if i <= 10:  # Log failures for first 10
                                    logger.warning(
                                        f"⚠️ [STARTUP] {symbol} {hold_side}: Failed to set {self.leverage}x | "
                                        f"Code: {error_code} | Msg: {error_msg}"
                                    )
                    except Exception as e:
                        leverage_failed_count += 1
                        error_str = str(e)
                        error_repr = repr(e)
                        # 🚨 CRITICAL: Check if it's a "not supported" error in the exception message
                        is_not_supported = (
                            "40797" in error_str or "40798" in error_str or
                            "40797" in error_repr or "40798" in error_repr or
                            "maximum settable leverage" in error_str.lower() or
                            "exceeded the maximum" in error_str.lower() or
                            "maximum settable leverage" in error_repr.lower() or
                            "exceeded the maximum" in error_repr.lower()
                        )
                        
                        if is_not_supported:
                            # Cache as failed to prevent retrying
                            self.leverage_cache.mark_failed(symbol, self.leverage, hold_side, "40797")
                            if i <= 10:  # Log failures for first 10
                                logger.warning(
                                    f"🚫 [STARTUP] {symbol} {hold_side}: Leverage {self.leverage}x not supported (from exception) | "
                                    f"Cached to skip future attempts"
                                )
                        else:
                            # Don't cache exceptions as failures (might be network issues)
                            if i <= 10:  # Log errors for first 10
                                logger.warning(f"⚠️ [STARTUP] {symbol} {hold_side}: Error setting leverage: {e}")
            
            # Save cache to disk
            self.leverage_cache.save()
            
            logger.info(
                f"✅ [STARTUP] Leverage check complete: {leverage_set_count} set via API, "
                f"{leverage_cached_count} from cache, {leverage_failed_count} failed "
                f"(out of {len(self.symbols) * 2} total)"
            )
        except Exception as e:
            logger.error(f"❌ [STARTUP] Failed to set leverage at startup: {e}")

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
                state = self.state_manager.get_state(symbol)
                for candle in reversed(candles):
                    # Each candle: [timestamp, open, high, low, close, volume, ...]
                    timestamp = int(candle[0])
                    price = float(candle[4])
                    volume = float(candle[5]) if len(candle) > 5 else 0.0
                    self.state_manager.add_price_point(symbol, price, timestamp, volume)
                    
                    # 🚀 STORE MULTI-TIMEFRAME CANDLE DATA for pro-style indicator analysis
                    if state:
                        candle_data = {
                            "timestamp": timestamp,
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                            "volume": volume,
                        }
                        state.add_candle(timeframe, candle_data)
            except Exception as e:
                logger.warning(f"⚠️  Could not fetch history for {symbol} ({timeframe}): {e}")

        batch_size = 10  # Process 10 symbols concurrently for faster loading
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
        
        # 🚀 NEW: Start backtesting service (if enabled)
        if self.backtest_service and self.backtest_service.scheduler:
            # Update symbols in backtesting service
            self.backtest_service.scheduler.symbols = self.symbols
            # Start backtesting service (runs initial backtest in background, non-blocking)
            logger.info("🔄 [BACKTEST] Starting backtesting service in background (non-blocking)...")
            logger.info("📊 [BACKTEST] Using backtest data if available, but trading starts immediately!")
            logger.info("🔄 [BACKTEST] Background backtest will run slowly to avoid rate limits")
            asyncio.create_task(self.backtest_service.start())
            logger.info("✅ [BACKTEST] Backtesting service started (running in background, trading starts now!)")
            logger.info("📊 [BACKTEST] View stats file: python view_backtest_stats.py or cat data/symbol_performance_stats.txt")

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
        leverage=25,  # Fixed 25x leverage (hardcoded in code)
        position_size_pct=0.10,  # Fixed 10% per position (hardcoded in code)
        max_positions=int(os.getenv("MAX_POSITIONS", "10")),
        daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", "0.15")),
        paper_mode=paper_mode,
    )

    # Run trader
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())
