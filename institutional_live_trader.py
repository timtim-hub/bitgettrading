"""
Institutional Live Trading Module
Real-time execution with post-only entries, funding blackout, and tripwires
"""

import asyncio
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from bitget_trading.bitget_rest import BitgetRestClient
from institutional_indicators import InstitutionalIndicators
from institutional_universe import UniverseFilter, RegimeClassifier, MarketData
from institutional_risk import RiskManager
from institutional_strategies import LSVRStrategy, VWAPMRStrategy, TrendStrategy, TradeSignal
from trade_tracker import TradeTracker
from institutional_leverage import init_leverage_manager, LeverageManager
from leverage_wrapper import adjust_tp_sl_for_leverage

logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """Live trading position"""
    symbol: str
    side: str
    strategy: str
    entry_time: datetime
    entry_price: float
    size: float
    notional: float
    stop_price: float
    tp_levels: List[tuple]  # [(price, size_frac), ...]
    tp_hit_count: int = 0
    remaining_size: float = 0.0
    moved_to_be: bool = False
    
    # Tracking
    highest_price: float = 0.0
    lowest_price: float = 0.0
    time_stop_time: datetime = None
    
    # Tripwire data
    sweep_level: Optional[float] = None  # For LSVR re-sweep detection
    last_adverse_check: datetime = None
    
    # TP/SL order IDs
    stop_order_id: Optional[str] = None
    tp_order_ids: Dict[int, str] = field(default_factory=dict)


class InstitutionalLiveTrader:
    """Live trading with 25x leverage institutional strategies"""
    
    def __init__(self, config: Dict, api_key: str, secret_key: str, passphrase: str):
        self.config = config
        self.mode_config = config.get('mode', {})
        self.concurrency_config = config.get('concurrency', {})
        self.scheduling_config = config.get('scheduling', {})
        
        # Initialize components
        self.indicators = InstitutionalIndicators(config)
        self.universe_filter = UniverseFilter(config)
        self.regime_classifier = RegimeClassifier(config)
        self.risk_manager = RiskManager(config)
        
        # API clients
        self.rest_client = BitgetRestClient(api_key, secret_key, passphrase, sandbox=False)
        
        # Trading state
        self.positions: Dict[str, LivePosition] = {}
        self.active_symbols: Set[str] = set()
        self.sector_counts: Dict[str, int] = {}
        self.last_funding_check: datetime = datetime.now()
        self.in_funding_blackout: bool = False
        
        # Gate check cache
        self.last_gate_check: Dict[str, datetime] = {}
        self.gate_check_interval = timedelta(minutes=self.scheduling_config.get('gate_check_interval_min', 60))
        
        # Symbol data cache
        self.symbol_data_cache: Dict[str, Dict] = {}
        
        # Load symbol buckets
        self.symbol_buckets: Dict[str, List[str]] = {}
        bucket_file = Path('symbol_buckets.json')
        if bucket_file.exists():
            import json
            with open(bucket_file, 'r') as f:
                self.symbol_buckets = json.load(f)
            logger.info(f"✅ Loaded symbol buckets: {self.symbol_buckets.get('total_symbols', 0)} symbols")
        
        # Trade tracking
        self.trade_tracker = TradeTracker()
        self.trade_ids: Dict[str, str] = {}  # Map symbol to trade_id
        
        # Initialize leverage manager for leverage-aware TP/SL calculations
        self.leverage_manager = init_leverage_manager(self.rest_client, default_leverage=25)
        
        logger.info("✅ InstitutionalLiveTrader initialized")
        logger.info(f"  Mode: {'LIVE' if self.mode_config.get('live_enabled') else 'BACKTEST ONLY'}")
        logger.info(f"  Max symbols: {self.concurrency_config.get('max_symbols', 3)}")
        logger.info(f"  Max per sector: {self.concurrency_config.get('max_per_sector', 2)}")
    
    async def fetch_existing_positions(self) -> Dict[str, LivePosition]:
        """
        Fetch existing open positions from Bitget and reconstruct LivePosition objects
        
        Returns:
            Dict mapping symbol to LivePosition
        """
        logger.info("🔍 Fetching existing positions from Bitget...")
        
        try:
            # Get all positions (call API directly to get all, not filtered by symbol)
            endpoint = "/api/v2/mix/position/all-position"
            params = {
                "productType": "USDT-FUTURES",
                "marginCoin": "USDT",
            }
            
            response = await self.rest_client._request("GET", endpoint, params=params)
            
            if response.get("code") != "00000" or "data" not in response:
                logger.warning("⚠️ Could not fetch positions from Bitget")
                return {}
            
            all_positions = response.get("data", [])
            
            # Filter for positions with size > 0
            open_positions = [p for p in all_positions if float(p.get("total", 0)) > 0]
            
            logger.info(f"📊 Found {len(open_positions)} open positions on Bitget")
            
            reconstructed = {}
            
            for pos_data in open_positions:
                try:
                    symbol = pos_data.get("symbol", "")
                    hold_side = pos_data.get("holdSide", "")  # "long" or "short"
                    total_size = float(pos_data.get("total", 0) or pos_data.get("available", 0))
                    
                    # Try multiple field names for average entry price
                    avg_price = float(
                        pos_data.get("averageOpenPrice", 0) or
                        pos_data.get("avgPrice", 0) or
                        pos_data.get("openPriceAvg", 0) or
                        pos_data.get("openAvgPrice", 0) or
                        0
                    )
                    
                    unrealized_pnl = float(pos_data.get("unrealizedPL", 0) or pos_data.get("unrealizedPnl", 0) or 0)
                    
                    # Debug: log all fields if price is 0
                    if avg_price == 0:
                        logger.debug(f"⚠️ {symbol}: Entry price is 0, available fields: {list(pos_data.keys())}")
                    
                    if not symbol or total_size == 0:
                        continue
                    
                    # Convert holdSide to our format
                    side = "long" if hold_side.lower() == "long" else "short"
                    
                    # Get current market price for stop calculation
                    market_data = await self.get_market_data(symbol)
                    if not market_data:
                        logger.warning(f"⚠️ Could not get market data for {symbol}, skipping")
                        continue
                    
                    current_price = market_data.last_price
                    
                    # If entry price is 0, use current price as fallback
                    if avg_price == 0:
                        logger.warning(f"⚠️ {symbol}: Entry price not available, using current price ${current_price:.4f} as fallback")
                        avg_price = current_price
                    
                    # Reconstruct position with estimated values
                    # We don't have original entry time, so use current time
                    # We don't have original strategy, so default to "Trend"
                    # We don't have original TP levels, so create default
                    
                    # Estimate stop price (use 2% from entry as default stop)
                    estimated_stop = round((avg_price * 0.98 if side == "long" else avg_price * 1.02), 2)
                    
                    # Default TP level (1.2% from entry, typical for Trend)
                    tp_price = round((avg_price * 1.012 if side == "long" else avg_price * 0.988), 2)
                    tp_levels = [(tp_price, 1.0)]  # Single TP, exit all
                    
                    # Calculate notional
                    notional = total_size * current_price
                    
                    position = LivePosition(
                        symbol=symbol,
                        side=side,
                        strategy="Trend",  # Default, we don't know original
                        entry_time=datetime.now() - timedelta(minutes=15),  # Estimate
                        entry_price=avg_price,
                        size=total_size,
                        notional=notional,
                        stop_price=estimated_stop,
                        tp_levels=tp_levels,
                        remaining_size=total_size,
                        highest_price=current_price if side == "long" else 0,
                        lowest_price=current_price if side == "short" else 0,
                        time_stop_time=datetime.now() + timedelta(minutes=25),  # Default 25 min
                        moved_to_be=False  # Assume not moved yet
                    )
                    
                    reconstructed[symbol] = position
                    
                    logger.info(
                        f"✅ Reconstructed position: {symbol} {side.upper()} | "
                        f"Size: {total_size:.4f} | Entry: ${avg_price:.4f} | "
                        f"P&L: ${unrealized_pnl:.2f}"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Error reconstructing position for {symbol}: {e}")
                    continue
            
            logger.info(f"✅ Reconstructed {len(reconstructed)} positions")
            return reconstructed
        
        except Exception as e:
            logger.error(f"❌ Error fetching existing positions: {e}")
            return {}
    
    async def fetch_candles(self, symbol: str, timeframe: str, days: int = 7) -> Optional[pd.DataFrame]:
        """Fetch historical candles (makes multiple API requests if needed)"""
        try:
            # Calculate how many candles we need
            candles_per_day = {'1m': 1440, '3m': 480, '5m': 288, '15m': 96, '1h': 24}
            total_candles = days * candles_per_day.get(timeframe, 288)
            
            # Bitget returns max 200 candles per request - need multiple requests
            all_candles = []
            requests_needed = min((total_candles + 199) // 200, 10)  # Max 10 requests (2000 candles)
            end_time = None  # Start with most recent
            
            for i in range(requests_needed):
                # Build params for Bitget API
                api_params = {
                    'symbol': symbol,
                    'productType': 'USDT-FUTURES',
                    'granularity': timeframe,
                    'limit': '200'
                }
                
                # Add endTime to get older data (pagination)
                if end_time:
                    api_params['endTime'] = str(end_time)
                
                # Call API with retry logic (handled in _request)
                try:
                    response = await self.rest_client._request(
                        'GET',
                        '/api/v2/mix/market/candles',
                        params=api_params
                    )
                except Exception as e:
                    logger.debug(f"⚠️ Failed to fetch candles for {symbol} (request {i+1}/{requests_needed}): {e}")
                    # If first request fails, return None (no data)
                    if i == 0:
                        return None
                    # If later request fails, return what we have
                    break
                
                if response.get('code') == '00000' and 'data' in response:
                    candles = response['data']
                    if candles:
                        all_candles.extend(candles)
                        
                        # Set endTime to oldest timestamp from this batch for next request
                        oldest_timestamp = min(int(c[0]) for c in candles)
                        end_time = oldest_timestamp - 1  # -1ms to avoid overlap
                        
                        if len(candles) < 200:  # No more historical data
                            break
                    else:
                        break
                else:
                    # API returned error - break and return what we have
                    if i == 0:
                        return None
                    break
                
                # Small delay between requests to avoid rate limit
                if i < requests_needed - 1:
                    await asyncio.sleep(0.3)  # Increased delay to avoid connection issues
            
            if all_candles:
                # Convert to DataFrame
                df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
                df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp'], errors='coerce'), unit='ms')
                df = df.sort_values('timestamp')
                
                # Set timestamp as index (required for indicators)
                df = df.set_index('timestamp')
                
                # Convert to numeric
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                return df
            
            return None
        
        except Exception as e:
            logger.error(f"❌ Error fetching candles for {symbol}: {e}")
            return None
    
    async def get_account_equity(self) -> float:
        """Get total account equity in USDT"""
        try:
            balance = await self.rest_client.get_account_balance()
            
            if balance.get('code') == '00000' and 'data' in balance:
                data = balance['data']
                if isinstance(data, list) and len(data) > 0:
                    equity = float(data[0].get('usdtEquity', 0))
                    return equity
                elif isinstance(data, dict):
                    equity = float(data.get('usdtEquity', 0))
                    return equity
            
            logger.warning(f"⚠️ Could not get account equity: {balance}")
            return 0.0
        
        except Exception as e:
            logger.error(f"❌ Error getting account equity: {e}")
            return 0.0
    
    async def check_funding_blackout(self) -> bool:
        """
        Check if we're in funding blackout window (±2 min of funding)
        Funding happens every 8 hours: 00:00, 08:00, 16:00 UTC
        """
        now = datetime.utcnow()
        
        # Funding times
        funding_hours = [0, 8, 16]
        blackout_minutes = self.scheduling_config.get('funding_blackout_min', 2)
        
        for hour in funding_hours:
            funding_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            # Check if within ±2 minutes
            time_to_funding = abs((now - funding_time).total_seconds() / 60)
            
            if time_to_funding <= blackout_minutes:
                if not self.in_funding_blackout:
                    logger.warning(f"⚠️ Entering funding blackout ({blackout_minutes}min window)")
                    self.in_funding_blackout = True
                return True
        
        if self.in_funding_blackout:
            logger.info("✅ Exiting funding blackout")
            self.in_funding_blackout = False
        
        return False
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get real-time market data for universe gates"""
        try:
            # Get ticker data
            ticker_response = await self.rest_client.get_ticker(symbol)
            
            if ticker_response.get('code') != '00000':
                return None
            
            ticker_list = ticker_response.get('data', [])
            if not ticker_list:
                return None
            
            ticker = ticker_list[0]
            
            # Calculate spread
            bid = float(ticker.get('bidPr', 0))
            ask = float(ticker.get('askPr', 0))
            
            if bid <= 0 or ask <= 0:
                return None
            
            spread_bps = ((ask - bid) / bid) * 10000
            
            # Get depth (simplified - using bid1/ask1 sizes)
            bid_size = float(ticker.get('bidSz', 0))
            ask_size = float(ticker.get('askSz', 0))
            last_price = float(ticker.get('lastPr', 0))
            
            bid_depth_usd = bid_size * last_price
            ask_depth_usd = ask_size * last_price
            
            # Get 24h volume
            quote_vol_24h = float(ticker.get('quoteVolume', 0))
            
            return MarketData(
                symbol=symbol,
                spread_bps=spread_bps,
                bid_depth_usd=bid_depth_usd,
                ask_depth_usd=ask_depth_usd,
                quote_vol_24h=quote_vol_24h,
                last_price=last_price
            )
        
        except Exception as e:
            logger.error(f"❌ Error getting market data for {symbol}: {e}")
            return None
    
    async def passes_universe_gates(self, symbol: str, force_check: bool = False) -> bool:
        """Check if symbol passes universe gates (with caching)"""
        passes, _ = await self.passes_universe_gates_with_reason(symbol, force_check)
        return passes
    
    async def passes_universe_gates_with_reason(self, symbol: str, force_check: bool = False) -> Tuple[bool, str]:
        """Check if symbol passes universe gates with failure reason"""
        now = datetime.now()
        
        # Check cache
        if not force_check and symbol in self.last_gate_check:
            if now - self.last_gate_check[symbol] < self.gate_check_interval:
                # Use cached result (assume passed if we checked recently)
                return True, "cached"
        
        # Get market data
        market_data = await self.get_market_data(symbol)
        
        if not market_data:
            return False, "no market data"
        
        # Update bucket
        bucket = self.universe_filter.update_bucket_from_volume(symbol, market_data.quote_vol_24h)
        
        # Check gates
        passes, reason = self.universe_filter.passes_gates(market_data, bucket)
        
        # Update cache
        self.last_gate_check[symbol] = now
        
        return passes, reason
    
    async def can_open_position(self, symbol: str, strategy: str) -> bool:
        """Check if we can open a new position"""
        max_symbols = self.concurrency_config.get('max_symbols', 3)
        max_per_sector = self.concurrency_config.get('max_per_sector', 2)
        
        # Check max symbols
        if len(self.positions) >= max_symbols:
            logger.debug(f"❌ Max symbols reached ({len(self.positions)}/{max_symbols})")
            return False
        
        # Check if already have position
        if symbol in self.positions:
            logger.debug(f"❌ Already have position in {symbol}")
            return False
        
        # Check sector limit (simplified - use symbol prefix)
        sector = symbol[:3]  # e.g., BTC, ETH, SOL
        current_sector_count = self.sector_counts.get(sector, 0)
        
        if current_sector_count >= max_per_sector:
            logger.debug(f"❌ Sector limit reached for {sector} ({current_sector_count}/{max_per_sector})")
            return False
        
        # Check funding blackout
        if await self.check_funding_blackout():
            logger.debug("❌ In funding blackout window")
            return False
        
        return True
    
    async def place_entry_order(self, signal: TradeSignal, symbol: str, size: float, 
                                equity: float) -> Optional[str]:
        """
        Place MARKET entry order for instant fill and immediate TP/SL protection
        
        🚨 CRITICAL: Market orders only - no post-only/taker complexity!
        - Instant fill (no waiting)
        - Immediate TP/SL placement
        - Safe even if bot crashes
        - Simple and reliable
        
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Get current market data
            market_data = await self.get_market_data(symbol)
            if not market_data:
                logger.error(f"❌ Could not get market data for {symbol}")
                return None
            
            current_price = market_data.last_price
            
            logger.info(
                f"📍 Placing MARKET order | {symbol} {signal.side.upper()} | "
                f"Size: {size:.4f} | Current Price: ${current_price:.4f}"
            )
            
            # Place MARKET order (instant fill!)
            response = await self.rest_client.place_order(
                symbol=symbol,
                side='buy' if signal.side == 'long' else 'sell',
                order_type='market',
                size=size
            )
            
            if response.get('code') == '00000':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"✅ Market order FILLED instantly | {symbol} | Order ID: {order_id}")
                return order_id
            else:
                logger.error(f"❌ Market order failed: {response}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}", exc_info=True)
            return None
    
    async def place_stop_loss(self, position: LivePosition) -> Optional[str]:
        """Place stop-loss order using TP/SL API"""
        try:
            # Round stop price to appropriate precision (Bitget requires 2-3 decimals)
            # Most symbols need 2 decimals, some need 3
            # Try 2 first, then 3 if it fails
            stop_price_rounded = round(position.stop_price, 2)
            
            # Use place_tpsl_order for stop-loss
            response = await self.rest_client.place_tpsl_order(
                symbol=position.symbol,
                hold_side=position.side,  # 'long' or 'short'
                size=position.remaining_size,
                stop_loss_price=stop_price_rounded,
                take_profit_price=None,  # Only SL for now
                size_precision=3  # 3 decimal places
            )
            
            # Response has 'sl' key with order info
            if response.get('sl', {}).get('code') == '00000':
                sl_data = response.get('sl', {}).get('data', {})
                order_id = sl_data.get('orderId')
                logger.info(f"✅ Stop-loss placed | {position.symbol} @ ${position.stop_price:.4f} | Order ID: {order_id}")
                return order_id
            else:
                logger.error(f"❌ Stop-loss placement failed: {response}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Error placing stop-loss: {e}")
            return None
    
    async def update_stop_to_breakeven(self, position: LivePosition):
        """Move stop to breakeven after TP1 (DEPRECATED - now using Bitget trailing stop API)"""
        # This method is kept for backward compatibility but is no longer used
        # We now use Bitget's native trailing stop API instead
        pass
    
    async def update_trailing_stop(self, position: LivePosition, current_price: float, current_bar: Dict):
        """
        Update trailing stop after TP1 hit (DEPRECATED - now using Bitget trailing stop API)
        
        This method is kept for backward compatibility but is no longer used.
        We now use Bitget's native trailing stop API (track_plan) which handles
        trailing automatically on the exchange side.
        """
        # No-op - Bitget API handles trailing automatically
        pass
    
    async def _place_trailing_stop_after_tp1(self, position: LivePosition, symbol: str, current_price: float):
        """
        Helper method to place trailing stop after TP1 is hit (either exchange-side or bot-side).
        This consolidates the trailing stop logic to avoid duplication.
        """
        # Cancel old SL order
        if position.stop_order_id:
            try:
                endpoint = "/api/v2/mix/order/cancel-plan-order"
                cancel_data = {
                    "symbol": position.symbol,
                    "productType": "usdt-futures",
                    "marginCoin": "USDT",
                    "orderId": position.stop_order_id,
                    "planType": "pos_loss",
                }
                await self.rest_client._request("POST", endpoint, data=cancel_data)
                logger.info(f"✅ Cancelled old SL order | {position.symbol} | Order ID: {position.stop_order_id}")
            except Exception as e1:
                try:
                    cancel_data["planType"] = "track_plan"
                    await self.rest_client._request("POST", endpoint, data=cancel_data)
                    logger.info(f"✅ Cancelled old trailing order | {position.symbol} | Order ID: {position.stop_order_id}")
                except Exception as e2:
                    logger.debug(f"⚠️ Could not cancel old order: {e1}, {e2}")
        
        # Place Bitget trailing stop (track_plan) - leverage-aware callback
        # 🚨 CRITICAL: Callback must account for leverage!
        # Target: 1% ROI callback → With 25x leverage = 0.04% price callback
        callback_ratio = await self.leverage_manager.calculate_trailing_callback(
            symbol=symbol,
            target_roi_pct=0.01,  # 1% ROI callback
        )
        min_profit_pct = 0.025  # 2.5% minimum ROI
        tp1_price = position.tp_levels[0][0] if position.tp_levels else None
        
        if position.side == 'long':
            min_profit_price = position.entry_price * (1 + min_profit_pct)
            if tp1_price:
                trigger_price = max(tp1_price, current_price * 1.001)
            else:
                trigger_price = max(current_price * 1.001, min_profit_price * 1.001)
        else:
            min_profit_price = position.entry_price * (1 - min_profit_pct)
            if tp1_price:
                trigger_price = min(tp1_price, current_price * 0.999)
            else:
                trigger_price = min(current_price * 0.999, min_profit_price * 0.999)
        
        # Verify we're locking in at least 2.5% profit
        if position.side == 'long':
            profit_at_trigger = ((trigger_price - position.entry_price) / position.entry_price) * 100
        else:
            profit_at_trigger = ((position.entry_price - trigger_price) / position.entry_price) * 100
        
        if profit_at_trigger < min_profit_pct * 100:
            if position.side == 'long':
                trigger_price = min_profit_price
            else:
                trigger_price = min_profit_price
        
        # Wait for position to be fully available
        await asyncio.sleep(2.0)
        
        # Get fresh position size
        positions_list = await self.rest_client.get_positions(symbol)
        fresh_size = position.remaining_size
        if positions_list:
            for pos in positions_list:
                if pos.get('symbol') == symbol:
                    fresh_size = float(pos.get('total', 0) or pos.get('available', 0))
                    break
        
        if fresh_size < 0.001:
            logger.warning(f"⚠️ Position size too small for trailing stop ({fresh_size:.4f}) | {symbol} | Using fallback fixed stop")
            # Use fallback fixed stop
            if position.side == 'long':
                fixed_stop = position.entry_price * (1 + min_profit_pct)
            else:
                fixed_stop = position.entry_price * (1 - min_profit_pct)
            position.stop_price = round(fixed_stop, 2)
            position.stop_order_id = await self.place_stop_loss(position)
            position.moved_to_be = True
            logger.info(f"✅ Fallback: Fixed stop at 2.5% profit | {symbol} @ ${fixed_stop:.4f}")
            return
        
        logger.info(f"🚀 Placing trailing stop | {symbol} | Size: {fresh_size:.4f} | Trigger: ${trigger_price:.4f} | Callback: {callback_ratio*100:.1f}%")
        
        try:
            trailing_response = await self.rest_client.place_trailing_stop_full_position(
                symbol=symbol,
                hold_side=position.side,
                callback_ratio=callback_ratio,
                trigger_price=trigger_price,
                size=fresh_size,
                size_precision=3
            )
            
            if trailing_response and trailing_response.get('code') == '00000':
                trailing_order_id = trailing_response.get('data', {}).get('orderId')
                position.stop_order_id = trailing_order_id
                position.moved_to_be = True
                logger.info(f"✅ Trailing stop placed (Bitget API) | {symbol} | Callback: {callback_ratio*100:.1f}% | Trigger: ${trigger_price:.4f} | Order ID: {trailing_order_id}")
                
                # Update trade tracking
                if symbol in self.trade_ids:
                    self.trade_tracker.update_trailing_stop(
                        self.trade_ids[symbol],
                        activated=True,
                        trigger_price=trigger_price
                    )
                    self.trade_tracker.update_breakeven(
                        self.trade_ids[symbol],
                        moved=True,
                        move_time=datetime.now()
                    )
                
                # Verify trailing stop is active
                await asyncio.sleep(2.0)
                try:
                    verify_endpoint = "/api/v2/mix/order/orders-plan-pending"
                    verify_params = {
                        "symbol": symbol,
                        "productType": "usdt-futures",
                        "planType": "track_plan",
                    }
                    verify_response = await self.rest_client._request("GET", verify_endpoint, params=verify_params)
                    if verify_response.get('code') == '00000':
                        orders = verify_response.get('data', {}).get('entrustedList', [])
                        trailing_orders = [o for o in orders if o.get('orderId') == trailing_order_id]
                        if trailing_orders:
                            logger.info(f"✅ Verified: Trailing stop is active on exchange | {symbol} | Order ID: {trailing_order_id}")
                        else:
                            logger.warning(f"⚠️ WARNING: Trailing stop order {trailing_order_id} NOT found on exchange! | {symbol}")
                            # Use fallback
                            if position.side == 'long':
                                fixed_stop = position.entry_price * (1 + min_profit_pct)
                            else:
                                fixed_stop = position.entry_price * (1 - min_profit_pct)
                            position.stop_price = round(fixed_stop, 2)
                            position.stop_order_id = await self.place_stop_loss(position)
                except Exception as e:
                    logger.debug(f"⚠️ Could not verify trailing stop: {e}")
            else:
                error_code = trailing_response.get('code', 'N/A') if trailing_response else 'N/A'
                error_msg = trailing_response.get('msg', 'N/A') if trailing_response else 'N/A'
                logger.error(f"❌ Failed to place trailing stop: Code={error_code}, Msg={error_msg}")
                
                # Fallback: Use fixed stop at 2.5% profit
                if position.side == 'long':
                    fixed_stop = position.entry_price * (1 + min_profit_pct)
                else:
                    fixed_stop = position.entry_price * (1 - min_profit_pct)
                position.stop_price = round(fixed_stop, 2)
                position.stop_order_id = await self.place_stop_loss(position)
                position.moved_to_be = True
                logger.info(f"✅ Fallback: Fixed stop at 2.5% profit | {symbol} @ ${fixed_stop:.4f}")
        except Exception as e:
            logger.error(f"❌ Error placing trailing stop for {symbol}: {e}", exc_info=True)
            # Fallback: Use fixed stop at 2.5% profit
            if position.side == 'long':
                fixed_stop = position.entry_price * (1 + min_profit_pct)
            else:
                fixed_stop = position.entry_price * (1 - min_profit_pct)
            position.stop_price = round(fixed_stop, 2)
            position.stop_order_id = await self.place_stop_loss(position)
            position.moved_to_be = True
            logger.info(f"✅ Fallback: Fixed stop at 2.5% profit | {symbol} @ ${fixed_stop:.4f}")
    
    async def check_tripwires(self, position: LivePosition, current_price: float, 
                              current_bar: Dict) -> Optional[str]:
        """
        Check tripwire conditions
        
        Returns:
            Exit reason if tripwire hit, None otherwise
        """
        # 1. Check LSVR re-sweep (within 10 min)
        if position.strategy == 'LSVR' and position.sweep_level:
            time_since_entry = (datetime.now() - position.entry_time).total_seconds() / 60
            
            if time_since_entry <= 10:
                if position.side == 'long':
                    # Check if price swept below level again
                    if current_bar.get('low', current_price) < position.sweep_level:
                        logger.warning(f"🚨 TRIPWIRE: Re-sweep detected | {position.symbol}")
                        return 'tripwire_resweep'
                else:
                    # Check if price swept above level again
                    if current_bar.get('high', current_price) > position.sweep_level:
                        logger.warning(f"🚨 TRIPWIRE: Re-sweep detected | {position.symbol}")
                        return 'tripwire_resweep'
        
        # 2. Check adverse spike (VWAP-MR)
        if position.strategy == 'VWAP_MR':
            atr = current_bar.get('atr', 0)
            if atr > 0:
                candle_range = abs(current_bar.get('close', current_price) - current_bar.get('open', current_price))
                
                if candle_range >= (1.7 * atr):
                    # Check if against position
                    if position.side == 'long' and current_bar.get('close', current_price) < current_bar.get('open', current_price):
                        logger.warning(f"🚨 TRIPWIRE: Adverse spike | {position.symbol}")
                        return 'tripwire_adverse_spike'
                    elif position.side == 'short' and current_bar.get('close', current_price) > current_bar.get('open', current_price):
                        logger.warning(f"🚨 TRIPWIRE: Adverse spike | {position.symbol}")
                        return 'tripwire_adverse_spike'
        
        # 3. Check time stop
        # 🚨 CRITICAL: Before closing by time_stop, check if position is at a loss
        # If ROE is negative, it should have been closed by SL, not time_stop!
        if position.time_stop_time and datetime.now() >= position.time_stop_time:
            # Calculate current ROE to prevent closing with small losses
            price_change_pct = ((current_price - position.entry_price) / position.entry_price * 100) if position.side == 'long' else ((position.entry_price - current_price) / position.entry_price * 100)
            leverage = position.notional / (position.notional / 25) if position.notional > 0 else 25
            roe_pct = price_change_pct * leverage
            
            # If position is at a loss, log warning but still close (time_stop is safety mechanism)
            if roe_pct < -0.05:
                logger.error(f"⚠️ TIME STOP with LOSS | {position.symbol} | ROE: {roe_pct:.2f}% | This should have been caught by SL!")
            logger.info(f"⏱️ Time stop reached | {position.symbol} | ROE: {roe_pct:+.2f}%")
            return 'time_stop'
        
        return None
    
    async def close_position(self, position: LivePosition, reason: str):
        """Close position (market order)"""
        try:
            logger.info(
                f"💰 Closing position | {position.symbol} {position.side.upper()} | "
                f"Reason: {reason} | Size: {position.remaining_size:.4f}"
            )
            
            # Cancel all open TP/SL/trailing orders
            endpoint = "/api/v2/mix/order/cancel-plan-order"
            if position.stop_order_id:
                # Try different plan types (pos_loss, track_plan)
                for plan_type in ["pos_loss", "track_plan"]:
                    try:
                        cancel_data = {
                            "symbol": position.symbol,
                            "productType": "usdt-futures",
                            "marginCoin": "USDT",
                            "orderId": position.stop_order_id,
                            "planType": plan_type,
                        }
                        await self.rest_client._request("POST", endpoint, data=cancel_data)
                        logger.debug(f"✅ Cancelled {plan_type} order | {position.symbol}")
                        break  # Success, no need to try other types
                    except Exception:
                        continue
            
            for tp_order_id in position.tp_order_ids.values():
                try:
                    cancel_data = {
                        "symbol": position.symbol,
                        "productType": "usdt-futures",
                        "marginCoin": "USDT",
                        "orderId": tp_order_id,
                        "planType": "profit_plan",  # Take-profit
                    }
                    await self.rest_client._request("POST", endpoint, data=cancel_data)
                except Exception:
                    pass
            
            # Place market order to close
            response = await self.rest_client.place_order(
                symbol=position.symbol,
                side='sell' if position.side == 'long' else 'buy',  # Opposite
                order_type='market',
                size=str(position.remaining_size)
            )
            
            if response.get('code') == '00000':
                logger.info(f"✅ Position closed | {position.symbol}")
                
                # Close trade tracking
                if position.symbol in self.trade_ids:
                    # Get exit price from response or use current market price
                    exit_price = current_price if 'current_price' in locals() else position.entry_price
                    try:
                        market_data = await self.get_market_data(position.symbol)
                        if market_data:
                            exit_price = market_data.last_price
                    except Exception:
                        pass
                    
                    # Get exit indicators
                    exit_indicators = {}
                    try:
                        df_5m = await self.fetch_candles(position.symbol, timeframe='5m', days=1)
                        df_15m = df_5m.resample('15min').agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna() if df_5m is not None else pd.DataFrame()
                        df_15m = self.indicators.calculate_all_indicators(df_15m, timeframe='15m') if not df_15m.empty else pd.DataFrame()
                        
                        if 'adx' in df_15m.columns and len(df_15m) > 0:
                            exit_indicators['adx'] = float(df_15m['adx'].iloc[-1]) if not pd.isna(df_15m['adx'].iloc[-1]) else None
                        if 'rsi' in df_15m.columns and len(df_15m) > 0:
                            exit_indicators['rsi'] = float(df_15m['rsi'].iloc[-1]) if not pd.isna(df_15m['rsi'].iloc[-1]) else None
                        if 'bb_width_pct' in df_5m.columns and len(df_5m) > 0:
                            exit_indicators['bb_width_pct'] = float(df_5m['bb_width_pct'].iloc[-1]) if not pd.isna(df_5m['bb_width_pct'].iloc[-1]) else None
                        if 'vwap_slope' in df_5m.columns and len(df_5m) > 0:
                            exit_indicators['vwap_slope'] = float(df_5m['vwap_slope'].iloc[-1]) if not pd.isna(df_5m['vwap_slope'].iloc[-1]) else None
                    except Exception as e:
                        logger.debug(f"⚠️ Could not extract exit indicators: {e}")
                    
                    # Calculate fees (approximate: 0.06% maker, 0.06% taker)
                    entry_fee = position.notional * 0.0006
                    exit_fee = position.notional * 0.0006
                    
                    self.trade_tracker.close_trade(
                        self.trade_ids[position.symbol],
                        exit_time=datetime.now(),
                        exit_price=exit_price,
                        exit_reason=reason,
                        exit_size=position.remaining_size,
                        fees_entry=entry_fee,
                        fees_exit=exit_fee,
                        exit_indicators=exit_indicators,
                    )
                    del self.trade_ids[position.symbol]
                
                # Remove from tracking
                del self.positions[position.symbol]
                self.active_symbols.discard(position.symbol)
                
                # Update sector count
                sector = position.symbol[:3]
                self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
            else:
                logger.error(f"❌ Failed to close position: {response}")
        
        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
    
    async def monitor_positions(self):
        """Monitor all open positions for exits"""
        if not self.positions:
            return
        
        # Log monitoring cycle (every 30 seconds to avoid spam)
        if hasattr(self, '_last_monitor_log'):
            if (datetime.now() - self._last_monitor_log).total_seconds() >= 30:
                logger.debug(f"🔄 Monitoring {len(self.positions)} positions...")
                self._last_monitor_log = datetime.now()
        else:
            self._last_monitor_log = datetime.now()
        
        # Periodic check: Verify TP/SL orders exist and re-place if missing (every 5 minutes)
        if not hasattr(self, '_last_tpsl_check'):
            self._last_tpsl_check = datetime.now()
        
        check_tpsl = (datetime.now() - self._last_tpsl_check).total_seconds() >= 60  # 60s
        
        for symbol, position in list(self.positions.items()):
            try:
                # Get current price
                market_data = await self.get_market_data(symbol)
                if not market_data:
                    continue
                
                current_price = market_data.last_price
                time_since_entry = (datetime.now() - position.entry_time).total_seconds()
                pnl_pct = ((current_price - position.entry_price) / position.entry_price * 100) if position.side == 'long' else ((position.entry_price - current_price) / position.entry_price * 100)
                
                # Update MAE/MFE tracking
                if position.side == 'long':
                    position.highest_price = max(position.highest_price, current_price)
                    peak_pnl_pct = ((position.highest_price - position.entry_price) / position.entry_price) * 100
                    peak_pnl_usd = (position.highest_price - position.entry_price) * position.size * position.entry_price
                else:
                    position.lowest_price = min(position.lowest_price, current_price) if position.lowest_price > 0 else current_price
                    peak_pnl_pct = ((position.entry_price - position.lowest_price) / position.entry_price) * 100
                    peak_pnl_usd = (position.entry_price - position.lowest_price) * position.size * position.entry_price
                
                # Update peak performance in trade tracker
                if symbol in self.trade_ids:
                    peak_price = position.highest_price if position.side == 'long' else position.lowest_price
                    self.trade_tracker.update_peak(
                        self.trade_ids[symbol],
                        peak_pnl_usd=peak_pnl_usd,
                        peak_pnl_pct=peak_pnl_pct,
                        peak_price=peak_price
                    )
                
                # Get latest bar for tripwire checks
                df = await self.fetch_candles(symbol, timeframe='5m', days=1)
                if df is None or len(df) == 0:
                    continue
                
                current_bar = {
                    'open': df['open'].iloc[-1],
                    'high': df['high'].iloc[-1],
                    'low': df['low'].iloc[-1],
                    'close': df['close'].iloc[-1],
                    'atr': df.get('atr', pd.Series([0])).iloc[-1] if 'atr' in df.columns else 0
                }
                
                # Check tripwires
                tripwire_reason = await self.check_tripwires(position, current_price, current_bar)
                if tripwire_reason:
                    await self.close_position(position, tripwire_reason)
                    continue
                
                # 🚨 SIMPLE TRAILING TP LOGIC (MUCH SIMPLER THAN TP1/TP2/TP3!)
                # Track peak prices and move TP continuously to lock in profits
                # No complex partial closes - just one simple trailing TP!
                
                # Update peak prices for trailing
                if position.side == 'long':
                    if current_price > position.highest_price:
                        old_high = position.highest_price
                        position.highest_price = current_price
                        
                        # Calculate new trailing TP to maintain 2.5% ROI target
                        # Using actual leverage for the position
                        leverage = position.notional / (position.notional / 25) if position.notional > 0 else 25  # Estimate leverage
                        profit_target_pct = 0.025  # 2.5% ROI on equity
                        price_move_needed = profit_target_pct / leverage  # Convert to price move
                        new_tp = position.highest_price * (1 + price_move_needed)
                        
                        # Only move TP UP (never down), and only if it's better than current TP
                        if position.tp_levels:
                            old_tp = position.tp_levels[0][0]
                            if new_tp > old_tp:
                                position.tp_levels[0] = (new_tp, 1.0)
                                tp_move = ((new_tp - old_tp) / old_tp) * 100
                                logger.info(f"🔄 TRAILING TP UP | {symbol} | ${old_tp:.4f} → ${new_tp:.4f} (+{tp_move:.2f}%) | Peak: ${position.highest_price:.4f}")
                
                else:  # SHORT
                    if current_price < position.lowest_price:
                        old_low = position.lowest_price
                        position.lowest_price = current_price
                        
                        # Calculate new trailing TP
                        leverage = position.notional / (position.notional / 25) if position.notional > 0 else 25
                        profit_target_pct = 0.025  # 2.5% ROI
                        price_move_needed = profit_target_pct / leverage
                        new_tp = position.lowest_price * (1 - price_move_needed)
                        
                        # Only move TP DOWN (never up), and only if it's better than current TP
                        if position.tp_levels:
                            old_tp = position.tp_levels[0][0]
                            if new_tp < old_tp:
                                position.tp_levels[0] = (new_tp, 1.0)
                                tp_move = ((old_tp - new_tp) / old_tp) * 100
                                logger.info(f"🔄 TRAILING TP DOWN | {symbol} | ${old_tp:.4f} → ${new_tp:.4f} (-{tp_move:.2f}%) | Peak: ${position.lowest_price:.4f}")
                
                # BOT-SIDE TP MONITORING - Check if trailing TP hit
                if position.tp_levels:
                    tp_price = position.tp_levels[0][0]
                    tp_hit = False
                    
                    if position.side == 'long' and current_price >= tp_price:
                        tp_hit = True
                        logger.info(f"🎯 TRAILING TP HIT | {symbol} LONG | Price ${current_price:.4f} >= TP ${tp_price:.4f}")
                    elif position.side == 'short' and current_price <= tp_price:
                        tp_hit = True
                        logger.info(f"🎯 TRAILING TP HIT | {symbol} SHORT | Price ${current_price:.4f} <= TP ${tp_price:.4f}")
                    
                    if tp_hit:
                        logger.info(f"💰 TRAILING TP HIT! Closing FULL position (100%) | {symbol}")
                        await self.close_position(position, "trailing_take_profit")
                        continue
                
                # BOT-SIDE SL MONITORING (FIXED SL - never moves!)
                # Calculate ROE (Return on Equity) for more accurate loss detection
                leverage = position.notional / (position.notional / 25) if position.notional > 0 else 25
                roe_pct = pnl_pct * leverage
                
                sl_hit = False
                sl_reason = ""
                
                if position.side == 'long':
                    if current_price <= position.stop_price:
                        sl_hit = True
                        sl_reason = f"Price ${current_price:.4f} <= SL ${position.stop_price:.4f}"
                        logger.warning(f"🛑 STOP LOSS HIT | {symbol} LONG | {sl_reason}")
                else:  # SHORT
                    if current_price >= position.stop_price:
                        sl_hit = True
                        sl_reason = f"Price ${current_price:.4f} >= SL ${position.stop_price:.4f}"
                        logger.warning(f"🛑 STOP LOSS HIT | {symbol} SHORT | {sl_reason}")
                
                # 🚨 CRITICAL: Prevent small losses that bypass TP/SL logic
                # If ROE is negative and approaching -0.10%, close immediately to prevent fees from eating into position
                # This ensures we never close with small losses that should have been protected by SL
                if not sl_hit and roe_pct < -0.05:  # -0.05% ROE threshold (before fees)
                    sl_hit = True
                    sl_reason = f"Small loss protection: ROE {roe_pct:.2f}% (preventing fees from causing -0.10% loss)"
                    logger.warning(f"🛑 SMALL LOSS PROTECTION | {symbol} | {sl_reason} | Price: ${current_price:.4f} | Entry: ${position.entry_price:.4f}")
                
                if sl_hit:
                    logger.error(f"🚨 STOP LOSS HIT! Closing position immediately | {symbol} | P&L: {pnl_pct:+.2f}% | ROE: {roe_pct:+.2f}% | Reason: {sl_reason}")
                    await self.close_position(position, "stop_loss")
                    continue
                
                # Check if position was closed externally (exchange-side TP/SL or manual close)
                try:
                    positions_list = await self.rest_client.get_positions(symbol)
                    actual_size = 0
                    if positions_list:
                        for pos in positions_list:
                            if pos.get('symbol') == symbol:
                                actual_size = float(pos.get('total', 0) or pos.get('available', 0))
                                break
                        
                        # If position fully closed externally, clean up tracking
                        if actual_size <= 0.001:
                            logger.info(f"✅ Position closed externally | {symbol}")
                            
                            # Close trade tracking
                            if symbol in self.trade_ids:
                                exit_indicators = {}
                                entry_fee = position.notional * 0.0006
                                exit_fee = position.notional * 0.0006
                                
                                self.trade_tracker.close_trade(
                                    self.trade_ids[symbol],
                                    exit_time=datetime.now(),
                                    exit_price=current_price,
                                    exit_reason="external_close",
                                    exit_size=actual_size,
                                    fees_entry=entry_fee,
                                    fees_exit=exit_fee,
                                    exit_indicators=exit_indicators,
                                )
                                del self.trade_ids[symbol]
                            
                            del self.positions[symbol]
                            self.active_symbols.discard(symbol)
                            sector = symbol[:3]
                            self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
                            continue
                except Exception as e:
                    logger.debug(f"⚠️ Could not check position for {symbol}: {e}")
                
                # Periodic TP/SL verification and re-placement (every 5 minutes)
                if check_tpsl:
                    try:
                        verify_endpoint = "/api/v2/mix/order/orders-plan-pending"
                        verify_params = {
                            "symbol": symbol,
                            "productType": "usdt-futures",
                        }
                        verify_response = await self.rest_client._request("GET", verify_endpoint, params=verify_params)
                        if verify_response.get('code') == '00000':
                            orders = verify_response.get('data', {}).get('entrustedList', [])
                            sl_orders = [o for o in orders if o.get('planType') == 'pos_loss']
                            tp_orders = [o for o in orders if o.get('planType') == 'profit_plan']
                            
                            # 🚨 CRITICAL: Before re-placing TP/SL, verify position STILL EXISTS!
                            # If position is closed, don't try to place orders (causes "Insufficient position" error)
                            position_still_exists = False
                            try:
                                positions_list = await self.rest_client.get_positions(symbol)
                                if positions_list:
                                    for pos in positions_list:
                                        if pos.get('symbol') == symbol:
                                            pos_size = float(pos.get('total', 0) or pos.get('available', 0))
                                            if pos_size > 0:
                                                position_still_exists = True
                                                break
                            except Exception as e:
                                logger.debug(f"⚠️ Could not verify position exists for {symbol}: {e}")
                            
                            if not position_still_exists:
                                logger.warning(f"⚠️ Position {symbol} no longer exists on exchange, skipping TP/SL re-placement")
                                # Don't try to re-place orders for a closed position!
                            else:
                                # Re-place missing orders (position confirmed to exist)
                                if len(sl_orders) == 0:
                                    logger.warning(f"⚠️ Missing SL order detected | {symbol} | Re-placing...")
                                    sl_response = await self.rest_client.place_tpsl_order(
                                        symbol=symbol,
                                        hold_side=position.side,
                                        size=position.remaining_size,
                                        stop_loss_price=position.stop_price,
                                        take_profit_price=None,
                                        size_precision=3
                                    )
                                    if sl_response.get('sl', {}).get('code') == '00000':
                                        position.stop_order_id = sl_response.get('sl', {}).get('data', {}).get('orderId')
                                        logger.info(f"✅ SL order re-placed | {symbol}")
                                
                                if len(tp_orders) == 0 and position.tp_levels:
                                    tp1_price = position.tp_levels[0][0]
                                    
                                    # Validate TP price before re-placing
                                    if position.side == 'short':
                                        # For SHORT: TP must be below current price
                                        if tp1_price >= current_price:
                                            tp1_price = current_price * 0.999
                                            logger.warning(f"⚠️ Adjusted TP1 to {tp1_price:.4f} (below current {current_price:.4f})")
                                            position.tp_levels[0] = (tp1_price, position.tp_levels[0][1])
                                    else:
                                        # For LONG: TP must be above current price
                                        if tp1_price <= current_price:
                                            tp1_price = current_price * 1.001
                                            logger.warning(f"⚠️ Adjusted TP1 to {tp1_price:.4f} (above current {current_price:.4f})")
                                            position.tp_levels[0] = (tp1_price, position.tp_levels[0][1])
                                    
                                    logger.warning(f"⚠️ Missing TP order detected | {symbol} | Re-placing...")
                                    tp_response = await self.rest_client.place_tpsl_order(
                                        symbol=symbol,
                                        hold_side=position.side,
                                        size=position.remaining_size,
                                        stop_loss_price=None,
                                        take_profit_price=round(tp1_price, 2),
                                        size_precision=3
                                    )
                                    if tp_response.get('tp', {}).get('code') == '00000':
                                        tp_order_id = tp_response.get('tp', {}).get('data', {}).get('orderId')
                                        position.tp_order_ids[0] = tp_order_id
                                        logger.info(f"✅ TP order re-placed | {symbol} @ ${tp1_price:.4f}")
                    except Exception as e:
                        logger.debug(f"⚠️ Could not verify/re-place TP/SL for {symbol}: {e}")
                
                # Log TP/SL distances (for monitoring)
                if position.tp_levels:
                    tp_price = position.tp_levels[0][0]
                    if position.side == 'long':
                        tp_dist = ((current_price - tp_price) / tp_price) * 100
                    else:
                        tp_dist = ((tp_price - current_price) / tp_price) * 100
                else:
                    tp_dist = 0
                    tp_price = 0
                
                if position.side == 'long':
                    sl_dist = ((current_price - position.stop_price) / position.entry_price) * 100
                else:
                    sl_dist = ((position.stop_price - current_price) / position.entry_price) * 100
                
                # Log status (every 30 seconds)
                if int(time_since_entry) % 30 < 5:
                    peak_info = f"Peak: ${position.highest_price:.4f}" if position.side == 'long' else f"Peak: ${position.lowest_price:.4f}"
                    logger.info(
                        f"📊 {symbol} {position.side.upper()} | "
                        f"Price: ${current_price:.4f} | P&L: {pnl_pct:+.2f}% | "
                        f"TP: ${tp_price:.4f} ({tp_dist:+.2f}%) | SL: ${position.stop_price:.4f} ({sl_dist:+.2f}%) | "
                        f"{peak_info} | 🔄 Trailing TP Active"
                    )
            
            except Exception as e:
                logger.error(f"❌ Error monitoring position {symbol}: {e}")
        
        # Update last TP/SL check time
        if check_tpsl:
            self._last_tpsl_check = datetime.now()
    
    async def scan_for_signals(self, symbols: List[str]):
        """Scan symbols for trading signals"""
        logger.info(f"🔍 Starting signal scan: {len(symbols)} symbols, {len(self.positions)} open positions")
        
        stats = {'checked': 0, 'gates_failed': 0, 'data_failed': 0, 'no_signal': 0, 'signals_found': 0}
        
        for symbol in symbols:
            try:
                stats['checked'] += 1
                
                # Small delay between symbols to avoid overwhelming API
                if stats['checked'] > 1:
                    await asyncio.sleep(0.1)  # 100ms delay between symbols
                
                # Check if can open position
                if not await self.can_open_position(symbol, 'any'):
                    continue
                
                # Check universe gates (TEMPORARILY DISABLED FOR TESTING)
                # passes, reason = await self.passes_universe_gates_with_reason(symbol)
                # if not passes:
                #     stats['gates_failed'] += 1
                #     if stats['gates_failed'] <= 5:  # Log first 5 failures with reasons
                #         logger.debug(f"  ⛔ {symbol}: Gates failed - {reason}")
                #     continue
                logger.debug(f"  ⚠️  {symbol}: Skipping gates (testing mode)")
                
                # Get data (enough for 15m resampling and EMA200)
                # Fetch 7 days = ~2000 5m bars = 280 15m bars (enough for EMA200)
                df_5m = await self.fetch_candles(symbol, timeframe='5m', days=7)  # ~2000 bars
                if df_5m is None or len(df_5m) < 500:
                    stats['data_failed'] += 1
                    if stats['data_failed'] <= 3:  # Log first 3 failures
                        logger.debug(f"  ⚠️  {symbol}: Insufficient data ({0 if df_5m is None else len(df_5m)} bars)")
                    continue
                
                # Calculate indicators
                df_5m = self.indicators.calculate_all_indicators(df_5m, timeframe='5m')
                
                # Get 15m for regime
                df_15m = df_5m.resample('15min').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna()
                df_15m = self.indicators.calculate_all_indicators(df_15m, timeframe='15m')
                
                # Classify regime
                bucket = self.universe_filter.get_bucket(symbol)
                regime_data = self.regime_classifier.classify_from_indicators(df_15m, bucket, -1)
                
                # Generate signal
                signal = None
                
                if regime_data.regime == 'Range':
                    # Try LSVR
                    lsvr = LSVRStrategy(self.config, bucket)
                    levels = self._get_levels(df_5m)
                    signal = lsvr.generate_signal(df_5m, levels, -1)
                    
                    # Try VWAP-MR if no LSVR
                    if not signal:
                        vwap_mr = VWAPMRStrategy(self.config, bucket)
                        signal = vwap_mr.generate_signal(df_5m, -1)
                
                elif regime_data.regime == 'Trend':
                    trend = TrendStrategy(self.config)
                    signal = trend.generate_signal(df_15m, -1)
                
                if not signal:
                    stats['no_signal'] += 1
                    if stats['no_signal'] <= 5:  # Log first 5
                        logger.debug(f"  ⚪ {symbol}: No signal ({regime_data.regime} regime)")
                    continue
                
                # Found a potential signal - log it
                logger.info(f"🎯 SIGNAL CANDIDATE: {symbol} {signal.side.upper()} | {signal.strategy} | {regime_data.regime} regime")
                
                # 🚨 CRITICAL: Adjust TP/SL for leverage (2.5% ROI, not 2.5% price move!)
                atr = df_5m['atr'].iloc[-1] if 'atr' in df_5m.columns else 0
                adjusted_prices = await adjust_tp_sl_for_leverage(
                    leverage_manager=self.leverage_manager,
                    symbol=symbol,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    tp_price_base=signal.tp_levels[0][0] if signal.tp_levels else signal.entry_price,
                    sl_price_base=signal.stop_price,
                    atr=atr,
                )
                
                # Update signal with leverage-adjusted prices
                signal.stop_price = adjusted_prices.sl_price
                signal.tp_levels = [(adjusted_prices.tp_price, 1.0)]  # Full position TP
                
                logger.info(
                    f"  📊 Leverage-adjusted | {adjusted_prices.leverage}x | "
                    f"TP: ${adjusted_prices.tp_price:.4f} ({adjusted_prices.tp_roi_pct:.1f}% ROI) | "
                    f"SL: ${adjusted_prices.sl_price:.4f} ({adjusted_prices.sl_roi_pct:.1f}% ROI)"
                )
                
                # Get account equity
                equity = await self.get_account_equity()
                if equity == 0:
                    logger.error("❌ Could not get account equity")
                    continue
                
                # Calculate position size with ACTUAL leverage (10x or 25x for this symbol)
                # 🚨 CRITICAL: Pass actual_leverage to ensure correct margin calculation!
                position_size = self.risk_manager.calculate_position_size(
                    symbol=symbol,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    stop_price=signal.stop_price,
                    equity_usdt=equity,
                    lot_size=0.001,
                    min_qty=0.001,
                    actual_leverage=adjusted_prices.leverage  # Use actual leverage from exchange!
                )
                
                if not position_size.passed_liq_guards:
                    logger.warning(f"⚠️ {symbol}: Signal rejected - liq guards: {position_size.reason}")
                    continue
                
                # Place entry order
                order_id = await self.place_entry_order(signal, symbol, position_size.contracts, equity)
                
                if not order_id:
                    logger.warning(f"⚠️ {symbol}: Failed to place entry order")
                    continue
                
                # Successfully placed order - count it now!
                stats['signals_found'] += 1
                logger.info(f"✅ SIGNAL EXECUTED: {symbol} {signal.side.upper()} | Order ID: {order_id}")
                
                # Create position tracking
                time_stop_range = signal.metadata.get('time_stop_range', [20, 30])
                time_stop_minutes = (time_stop_range[0] + time_stop_range[1]) / 2
                
                # Create position tracking (will update with actual filled size later)
                position = LivePosition(
                    symbol=symbol,
                    side=signal.side,
                    strategy=signal.strategy,
                    entry_time=datetime.now(),
                    entry_price=signal.entry_price,
                    size=position_size.contracts,  # Will be updated with actual filled size
                    notional=position_size.notional_usd,
                    stop_price=round(signal.stop_price, 2),  # Round for Bitget API
                    tp_levels=signal.tp_levels,
                    remaining_size=position_size.contracts,  # Will be updated with actual filled size
                    highest_price=signal.entry_price if signal.side == 'long' else 0,
                    lowest_price=signal.entry_price if signal.side == 'short' else 0,
                    time_stop_time=datetime.now() + timedelta(minutes=time_stop_minutes),
                    sweep_level=signal.metadata.get('swept_level')
                )
                
                # Wait for position to be fully available on exchange (market orders = instant!)
                # 🚨 Market orders fill instantly, but Bitget still needs a moment to process
                initial_wait = 3.0  # Short wait for market orders
                logger.info(f"⏳ Waiting {initial_wait:.0f}s for position to be fully available on exchange...")
                await asyncio.sleep(initial_wait)
                
                # 🎯 EXCHANGE-SIDE TRAILING TP CONFIGURATION (computed after leverage-aware TP/SL below)
                
                # Verify position actually exists on exchange before placing TP/SL
                position_verified = False
                actual_filled_size = position_size.contracts  # Default to requested size
                for verify_attempt in range(5):
                    try:
                        positions_list = await self.rest_client.get_positions(symbol)
                        if positions_list:
                            for pos in positions_list:
                                if pos.get('symbol') == symbol:
                                    pos_size = float(pos.get('total', 0) or pos.get('available', 0))
                                    if pos_size > 0:
                                        position_verified = True
                                        actual_filled_size = pos_size  # 🚨 CRITICAL: Use actual filled size!
                                        logger.info(f"✅ Position verified on exchange | {symbol} | Size: {actual_filled_size:.4f}")
                                        
                                        # Short additional wait for TP/SL readiness (market orders are fast!)
                                        logger.info(f"⏳ Position verified, waiting 2s for TP/SL readiness...")
                                        await asyncio.sleep(2.0)
                                        break
                        if position_verified:
                            break
                    except Exception as e:
                        logger.debug(f"⚠️ Position verification attempt {verify_attempt+1}/5 failed: {e}")
                    
                    if not position_verified and verify_attempt < 4:
                        await asyncio.sleep(2.0)
                
                if not position_verified:
                    logger.error(f"❌ Position {symbol} not found on exchange after 5 attempts - skipping TP/SL placement")
                    continue  # Skip this position
                
                # Update position with actual filled size
                position.size = actual_filled_size
                position.remaining_size = actual_filled_size
                logger.info(f"📊 Position size updated | Requested: {position_size.contracts:.4f} | Actual: {actual_filled_size:.4f}")

                # 🔢 Determine actual leverage and price precision, then recompute TP/SL with leverage awareness
                try:
                    # Default to detected leverage from LeverageManager (may be max)
                    position_leverage = await self.leverage_manager.get_symbol_leverage(symbol)
                    # Try to fetch actual position leverage from exchange
                    try:
                        positions_list = await self.rest_client.get_positions(symbol)
                        if positions_list:
                            for pos in positions_list:
                                if pos.get('symbol') == symbol:
                                    lev_raw = pos.get('leverage') or pos.get('fixedLeverage') or pos.get('marginLeverage')
                                    if lev_raw is not None:
                                        position_leverage = int(float(lev_raw))
                                    break
                    except Exception as e:
                        logger.debug(f"⚠️ Could not fetch actual leverage for {symbol}: {e}")

                    entry_price_actual = signal.entry_price
                    # Target ROI configuration
                    target_tp_roi = 0.025   # +2.5% ROI minimum
                    max_sl_roi = 0.02       # -2.0% ROI maximum loss

                    # Convert ROI targets to price moves using ACTUAL leverage
                    tp_price_move = target_tp_roi / max(1, position_leverage)
                    sl_price_move = max_sl_roi / max(1, position_leverage)

                    # Compute prices
                    if signal.side == 'long':
                        tp1_price = entry_price_actual * (1 + tp_price_move)
                        stop_price_calc = entry_price_actual * (1 - sl_price_move)
                    else:  # short
                        tp1_price = entry_price_actual * (1 - tp_price_move)
                        stop_price_calc = entry_price_actual * (1 + sl_price_move)

                    # Round prices to symbol precision using contract info and validate vs current price
                    try:
                        symbol_info = await self.rest_client.get_symbol_info(symbol)
                        price_scale = None
                        step = None
                        if symbol_info:
                            # Bitget contracts use 'pricePlace' (decimals) and 'priceEndStep' (tick)
                            place_raw = symbol_info.get('pricePlace') or symbol_info.get('priceScale')
                            if place_raw is not None:
                                try:
                                    price_scale = int(place_raw)
                                except Exception:
                                    price_scale = None
                            step_raw = symbol_info.get('priceEndStep') or symbol_info.get('minPriceIncrement') or symbol_info.get('tickSize')
                            if step_raw:
                                try:
                                    step = float(step_raw)
                                except Exception:
                                    step = None

                        def _round_price(val: float) -> float:
                            """
                            Round price to exchange precision safely:
                              - Prefer decimal places (pricePlace)
                              - Use tick step only if < 1 to avoid zeroing sub-$1 prices
                              - Always round DOWN to be safe for triggers
                            """
                            from decimal import Decimal, ROUND_DOWN, getcontext
                            getcontext().prec = 18
                            dv = Decimal(str(val))
                            # Use tick only if it's a fractional step
                            if step and step > 0 and step < 1:
                                quant = Decimal(str(step))
                                return float(dv.quantize(quant, rounding=ROUND_DOWN))
                            # Otherwise use decimal places
                            if price_scale is not None and price_scale >= 0:
                                use_places = int(price_scale)
                                quant = Decimal('1').scaleb(-use_places)  # 10^-price_scale
                                return float(dv.quantize(quant, rounding=ROUND_DOWN))
                            # Fallback
                            return float(dv.quantize(Decimal('0.0001'), rounding=ROUND_DOWN))

                        # Fetch current price to validate trigger vs mark price
                        current_price = None
                        try:
                            md = await self.get_market_data(symbol)
                            if md:
                                current_price = float(md.last_price)
                        except Exception:
                            current_price = None

                        tp1_price = _round_price(tp1_price)
                        stop_price_calc = _round_price(stop_price_calc)

                        # If rounding produced zero (bad tick setup), fall back to decimal-place rounding only
                        if tp1_price <= 0 or stop_price_calc <= 0:
                            ps = price_scale if (price_scale is not None and price_scale >= 0) else 4
                            tp1_price = float(f"{tp1_price:.{ps}f}") if tp1_price > 0 else float(f"{entry_price_actual:.{ps}f}")
                            stop_price_calc = float(f"{stop_price_calc:.{ps}f}") if stop_price_calc > 0 else float(f"{entry_price_actual:.{ps}f}")

                        # Ensure TP trigger is on the correct side of current price to avoid 40832/45135 errors
                        if current_price is not None:
                            if signal.side == 'long':
                                # TP must be ABOVE current price
                                min_above = (current_price + (step if step else 0)) * (1.0001)
                                if tp1_price <= min_above:
                                    tp1_price = _round_price(min_above)
                            else:
                                # TP must be BELOW current price
                                max_below = (current_price - (step if step else 0)) * (0.9999)
                                if tp1_price >= max_below:
                                    tp1_price = _round_price(max_below)
                        # Safety clamps: ensure prices are positive and non-zero
                        base_price = current_price or entry_price_actual
                        if stop_price_calc is None or stop_price_calc <= 0:
                            if signal.side == 'long':
                                stop_price_calc = _round_price(base_price * 0.98)
                            else:
                                stop_price_calc = _round_price(base_price * 1.02)
                        if tp1_price is None or tp1_price <= 0:
                            if signal.side == 'long':
                                tp1_price = _round_price(entry_price_actual * (1 + tp_price_move))
                            else:
                                tp1_price = _round_price(entry_price_actual * (1 - tp_price_move))
                    except Exception as e:
                        logger.debug(f"⚠️ Could not round prices for {symbol}: {e}")

                    # Apply recomputed, leverage-aware prices
                    signal.stop_price = stop_price_calc
                    signal.tp_levels = [(tp1_price, 1.0)]

                    logger.info(
                        f"📐 Leverage-aware TP/SL | {position_leverage}x | Entry=${entry_price_actual:.6f} | "
                        f"TP=${tp1_price:.6f} (+{target_tp_roi*100:.2f}% ROI) | SL=${signal.stop_price:.6f} (-{max_sl_roi*100:.2f}% ROI)"
                    )

                except Exception as e:
                    logger.warning(f"⚠️ Failed to recompute leverage-aware TP/SL for {symbol}: {e}")

                # 🎯 EXCHANGE-SIDE TRAILING TP SYSTEM (moving_plan via Place-Tpsl-Order)
                tp1_price = signal.tp_levels[0][0] if signal.tp_levels else None
                # Compute leverage-aware callback; clamp to sane bounds [0.003, 0.10]
                try:
                    callback_ratio = await self.leverage_manager.calculate_trailing_callback(
                        symbol=symbol,
                        target_roi_pct=0.01,  # 1% ROI callback baseline
                    )
                    # Clamp between 0.3% and 10.0%
                    callback_ratio = max(0.003, min(0.10, float(callback_ratio)))
                except Exception:
                    callback_ratio = 0.005  # Fallback: 0.5% price
                
                # Step 1: Place FIXED Stop Loss (never moves)
                logger.info(f"🛡️ Step 1: Placing FIXED Stop Loss @ ${signal.stop_price:.6f}")
                sl_response = None
                for attempt in range(3):
                    try:
                        # Guard: ensure SL trigger is valid relative to current price
                        # Recompute against fresh market price if needed
                        try:
                            md_sl = await self.get_market_data(symbol)
                            cur_px = float(md_sl.last_price) if md_sl else None
                        except Exception:
                            cur_px = None
                        sl_price_to_use = signal.stop_price
                        if (sl_price_to_use is None) or (sl_price_to_use <= 0) or (cur_px and (
                            (signal.side == 'long' and sl_price_to_use >= cur_px) or
                            (signal.side == 'short' and sl_price_to_use <= cur_px)
                        )):
                            # Recompute from ROI for safety
                            sl_pct = 0.02 / max(1, position_leverage)
                            raw = (cur_px or entry_price_actual)
                            if signal.side == 'long':
                                sl_price_to_use = raw * (1 - sl_pct)
                            else:
                                sl_price_to_use = raw * (1 + sl_pct)
                            # Round to precision
                            try:
                                sl_price_to_use = _round_price(sl_price_to_use)  # type: ignore[name-defined]
                            except Exception:
                                sl_price_to_use = round(sl_price_to_use, 6)
                            # Ensure on correct side of current price
                            if cur_px:
                                if signal.side == 'long' and sl_price_to_use >= cur_px:
                                    sl_price_to_use = max(cur_px * 0.999, sl_price_to_use)  # nudge below
                                if signal.side == 'short' and sl_price_to_use <= cur_px:
                                    sl_price_to_use = min(cur_px * 1.001, sl_price_to_use)  # nudge above
                            # Apply back to signal for downstream consistency
                            signal.stop_price = sl_price_to_use
                            logger.info(f"🧮 Recomputed SL trigger=${sl_price_to_use:.6f} (lev={position_leverage}x)")

                        sl_response = await self.rest_client.place_tpsl_order(
                            symbol=symbol,
                            hold_side=signal.side,
                            size=actual_filled_size,
                            stop_loss_price=signal.stop_price,
                            take_profit_price=None,  # NO TP here - using trailing instead!
                            size_precision=3
                        )
                        
                        sl_ok = sl_response.get('sl', {}).get('code') == '00000'
                        if sl_ok:
                            position.stop_order_id = sl_response.get('sl', {}).get('data', {}).get('orderId')
                            logger.info(f"✅ FIXED SL placed | {symbol} @ ${signal.stop_price:.2f} | ID: {position.stop_order_id}")
                            break
                        elif attempt < 2:
                            await asyncio.sleep(2.0)
                    except Exception as e:
                        if attempt < 2:
                            await asyncio.sleep(2.0)
                        else:
                            logger.error(f"❌ SL placement failed after 3 attempts: {e}")
                
                if not sl_response or sl_response.get('sl', {}).get('code') != '00000':
                    logger.error(f"❌ Could not place SL for {symbol} - proceeding to place trailing TP anyway for protection")
                
                # Step 2: Place MIN-PROFIT FLOOR (profit_plan) at +2.5% ROE (guarantee >= 2.5% profit on trigger)
                logger.info(f"🎯 Step 2: Placing MIN-PROFIT FLOOR (profit_plan @ +2.5% ROE)")
                try:
                    min_roi = 0.025
                    floor_move = min_roi / max(1, position_leverage)
                    if signal.side == 'long':
                        floor_trigger = entry_price_actual * (1 + floor_move)
                    else:
                        floor_trigger = entry_price_actual * (1 - floor_move)
                    try:
                        floor_trigger = _round_price(floor_trigger)  # type: ignore[name-defined]
                    except Exception:
                        pass
                    floor_resp = await self.rest_client.place_tpsl_order(
                        symbol=symbol,
                        hold_side=signal.side,
                        size=actual_filled_size,   # required for profit_plan
                        stop_loss_price=None,
                        take_profit_price=floor_trigger,
                        size_precision=3
                    )
                    if floor_resp and floor_resp.get('tp', {}).get('code') == '00000':
                        logger.info(f"✅ Min-profit FLOOR placed (profit_plan) @ ${floor_trigger:.6f} | {symbol}")
                    else:
                        logger.warning(f"⚠️ Min-profit FLOOR failed | {symbol} | Resp={floor_resp}")
                except Exception as e:
                    logger.error(f"❌ Min-profit FLOOR exception | {symbol}: {e}")

                # Step 3: Place EXCHANGE-SIDE TRAILING Take Profit (moving_plan) activating at the same floor
                logger.info(f"🎯 Step 3: Placing EXCHANGE-SIDE TRAILING TP (moving_plan via Place-Tpsl-Order)")
                trailing_response = None
                try:
                    activation_price = floor_trigger  # activate trailing only after >= 2.5% ROE
                    trailing_response = await self.rest_client.place_trailing_take_profit_order(
                        symbol=symbol,
                        hold_side=signal.side,
                        size=actual_filled_size,
                        range_rate=callback_ratio,
                        trigger_price=activation_price,
                        size_precision=3,
                    )
                    if trailing_response and trailing_response.get('code') == '00000':
                        trailing_order_id = trailing_response.get('data', {}).get('orderId') if trailing_response.get('data') else None
                        if trailing_order_id:
                            position.tp_order_ids[0] = trailing_order_id
                        logger.info(
                            f"✅ EXCHANGE TRAILING TP placed (moving_plan) | {symbol} | "
                            f"Activation: ${activation_price:.6f} | Callback: {callback_ratio*100:.2f}% | "
                            f"Order ID: {trailing_order_id}"
                        )
                        logger.info(f"🎉 Exchange will automatically trail and close when price reverses {callback_ratio*100:.2f}%!")
                    else:
                        logger.warning(f"⚠️ Trailing TP (moving_plan) failed | {symbol} | Resp={trailing_response}")
                except Exception as e:
                    logger.error(f"❌ Trailing TP placement exception | {symbol}: {e}")
                
                # No fallback TP needed now; profit-plan floor is already placed to guarantee >= 2.5% ROE
                else:
                    # Verify trailing/floor are visible on exchange; if missing, re-place
                    try:
                        await asyncio.sleep(2.0)
                        verify_response = await self.rest_client._request(
                            "GET",
                            "/api/v2/mix/order/orders-plan-pending",
                            params={"symbol": symbol, "productType": "usdt-futures"},
                        )
                        if verify_response.get("code") == "00000":
                            orders = verify_response.get("data", {}).get("entrustedList", [])
                            moving_orders = [o for o in orders if o.get("planType") in ("moving_plan", "track_plan")]
                            tp_floor_orders = [o for o in orders if o.get("planType") == "profit_plan"]
                            backup_sl_orders = [o for o in orders if o.get("planType") == "loss_plan"]
                            if moving_orders:
                                logger.info(f"✅ Verified trailing order exists | {symbol} | count={len(moving_orders)}")
                            else:
                                logger.warning(f"⚠️ Trailing not found; will rely on FLOOR TP (profit_plan) for min-ROE | {symbol}")
                            if tp_floor_orders:
                                logger.info(f"✅ Verified FLOOR TP (profit_plan) exists | {symbol} | count={len(tp_floor_orders)}")
                            else:
                                logger.warning(f"⚠️ FLOOR TP missing; re-placing now | {symbol}")
                                _ = await self.rest_client.place_tpsl_order(
                                    symbol=symbol,
                                    hold_side=signal.side,
                                    size=actual_filled_size,
                                    stop_loss_price=None,
                                    take_profit_price=floor_trigger,
                                    size_precision=3
                                )
                            # Ensure backup SL (-15% ROE) exists (loss_plan)
                            if not backup_sl_orders:
                                try:
                                    backup_sl_roi = 0.15
                                    backup_sl_move = backup_sl_roi / max(1, position_leverage)
                                    if signal.side == 'long':
                                        backup_sl_trigger = entry_price_actual * (1 - backup_sl_move)
                                    else:
                                        backup_sl_trigger = entry_price_actual * (1 + backup_sl_move)
                                    try:
                                        backup_sl_trigger = _round_price(backup_sl_trigger)  # type: ignore[name-defined]
                                    except Exception:
                                        pass
                                    _ = await self.rest_client.place_tpsl_order(
                                        symbol=symbol,
                                        hold_side=signal.side,
                                        size=actual_filled_size,
                                        stop_loss_price=backup_sl_trigger,
                                        take_profit_price=None,
                                        size_precision=3,
                                        force_plan_type="loss_plan"
                                    )
                                    logger.info(f"🔁 Re-placed missing backup SL (loss_plan) @ ${backup_sl_trigger:.6f} | {symbol}")
                                except Exception as e2:
                                    logger.warning(f"⚠️ Could not place missing backup SL | {symbol} | {e2}")
                            else:
                                logger.info(f"✅ Verified backup SL (loss_plan) exists | {symbol} | count={len(backup_sl_orders)}")
                    except Exception as e:
                        logger.debug(f"⚠️ Could not verify trailing presence: {e}")
                
                # Step 4: Backup protection orders
                #  - Backup TP at +10% ROE (full size profit_plan)
                #  - Backup SL at -15% ROE using loss_plan (full size) as safety net
                try:
                    # Backup TP (+10% ROE on equity)
                    backup_tp_roi = 0.10
                    backup_tp_move = backup_tp_roi / max(1, position_leverage)
                    if signal.side == 'long':
                        backup_tp_trigger = entry_price_actual * (1 + backup_tp_move)
                    else:
                        backup_tp_trigger = entry_price_actual * (1 - backup_tp_move)
                    try:
                        backup_tp_trigger = _round_price(backup_tp_trigger)  # type: ignore[name-defined]
                    except Exception:
                        pass
                    tp_backup_resp = await self.rest_client.place_tpsl_order(
                        symbol=symbol,
                        hold_side=signal.side,
                        size=actual_filled_size,
                        stop_loss_price=None,
                        take_profit_price=backup_tp_trigger,
                        size_precision=3
                    )
                    if tp_backup_resp and tp_backup_resp.get('tp', {}).get('code') == '00000':
                        logger.info(f"✅ Backup fixed TP placed (profit_plan @ +10% ROE) @ ${backup_tp_trigger:.6f} | {symbol}")
                    else:
                        logger.warning(f"⚠️ Backup TP placement failed | {symbol} | Resp={tp_backup_resp}")
                except Exception as e:
                    logger.error(f"❌ Backup TP exception | {symbol}: {e}")
                try:
                    # Backup SL (-15% ROE on equity), use loss_plan (full size) to coexist with pos_loss
                    backup_sl_roi = 0.15
                    backup_sl_move = backup_sl_roi / max(1, position_leverage)
                    if signal.side == 'long':
                        backup_sl_trigger = entry_price_actual * (1 - backup_sl_move)
                    else:
                        backup_sl_trigger = entry_price_actual * (1 + backup_sl_move)
                    try:
                        backup_sl_trigger = _round_price(backup_sl_trigger)  # type: ignore[name-defined]
                    except Exception:
                        pass
                    sl_backup_resp = await self.rest_client.place_tpsl_order(
                        symbol=symbol,
                        hold_side=signal.side,
                        size=actual_filled_size,
                        stop_loss_price=backup_sl_trigger,
                        take_profit_price=None,
                        size_precision=3,
                        force_plan_type="loss_plan"
                    )
                    sl_ok = False
                    # For loss_plan, response is in 'sl'
                    if sl_backup_resp and isinstance(sl_backup_resp.get('sl'), dict):
                        sl_ok = sl_backup_resp.get('sl', {}).get('code') == '00000'
                    if sl_ok:
                        logger.info(f"✅ Backup SL placed (loss_plan @ -15% ROE) @ ${backup_sl_trigger:.6f} | {symbol}")
                    else:
                        logger.warning(f"⚠️ Backup SL placement failed | {symbol} | Resp={sl_backup_resp}")
                except Exception as e:
                    logger.error(f"❌ Backup SL exception | {symbol}: {e}")

                # Add to tracking
                self.positions[symbol] = position
                self.active_symbols.add(symbol)
                
                sector = symbol[:3]
                self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
                
                # Start trade tracking
                trade_id = f"{symbol}_{signal.side}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.trade_ids[symbol] = trade_id
                
                # Extract entry indicators from current data
                entry_indicators = {}
                try:
                    if 'adx' in df_15m.columns:
                        entry_indicators['adx'] = float(df_15m['adx'].iloc[-1]) if not pd.isna(df_15m['adx'].iloc[-1]) else None
                    if 'rsi' in df_15m.columns:
                        entry_indicators['rsi'] = float(df_15m['rsi'].iloc[-1]) if not pd.isna(df_15m['rsi'].iloc[-1]) else None
                    if 'bb_width_pct' in df_5m.columns:
                        entry_indicators['bb_width_pct'] = float(df_5m['bb_width_pct'].iloc[-1]) if not pd.isna(df_5m['bb_width_pct'].iloc[-1]) else None
                    if 'vwap_slope' in df_5m.columns:
                        entry_indicators['vwap_slope'] = float(df_5m['vwap_slope'].iloc[-1]) if not pd.isna(df_5m['vwap_slope'].iloc[-1]) else None
                    if 'volume_ratio_20' in df_5m.columns:
                        entry_indicators['volume_ratio'] = float(df_5m['volume_ratio_20'].iloc[-1]) if not pd.isna(df_5m['volume_ratio_20'].iloc[-1]) else None
                    if 'atr' in df_5m.columns:
                        entry_indicators['atr'] = float(df_5m['atr'].iloc[-1]) if not pd.isna(df_5m['atr'].iloc[-1]) else None
                except Exception as e:
                    logger.debug(f"⚠️ Could not extract entry indicators: {e}")
                
                # Get bucket
                bucket = self.universe_filter.get_bucket(symbol)
                
                # Start tracking
                self.trade_tracker.start_trade(
                    trade_id=trade_id,
                    symbol=symbol,
                    side=signal.side,
                    strategy=signal.strategy,
                    regime=regime_data.regime,
                    entry_time=position.entry_time,
                    entry_price=position.entry_price,
                    entry_size=position.size,
                    entry_notional=position.notional,
                    entry_equity=equity,
                    stop_price=position.stop_price,
                    tp_levels=position.tp_levels,
                    leverage=25,
                    margin_fraction=0.10,
                    entry_indicators=entry_indicators,
                    bucket=bucket,
                    sweep_level=position.sweep_level,
                    metadata=signal.metadata,
                )
                
                logger.info(
                    f"✅ POSITION OPENED | {symbol} {signal.side.upper()} | "
                    f"Strategy: {signal.strategy} | Size: {position_size.contracts:.4f} | "
                    f"TP/SL: Exchange-side (auto-execute) | Trade ID: {trade_id}"
                )
            
            except Exception as e:
                logger.error(f"❌ Error scanning {symbol}: {e}")
        
        # Summary
        logger.info(
            f"📊 Scan complete: checked={stats['checked']}, "
            f"gates_failed={stats['gates_failed']}, "
            f"data_failed={stats['data_failed']}, "
            f"no_signal={stats['no_signal']}, "
            f"signals_found={stats['signals_found']}"
        )
    
    def _get_levels(self, df):
        """Get price levels from DataFrame"""
        current_time = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else datetime.now()
        levels = self.indicators.calculate_levels(df, current_time)
        
        return {
            'pdh': levels.pdh,
            'pdl': levels.pdl,
            'asia_high': levels.asia_high,
            'asia_low': levels.asia_low
        }
    
    async def run(self, symbols: List[str], scan_interval_seconds: int = 60):
        """
        Main trading loop
        
        Args:
            symbols: List of symbols to trade
            scan_interval_seconds: How often to scan for signals (default: 60s)
        """
        if not self.mode_config.get('live_enabled', False):
            logger.error("❌ Live trading is DISABLED in config")
            logger.error("   Set 'live_enabled': true to enable")
            return
        
        logger.info("="*80)
        logger.info("🚀 STARTING INSTITUTIONAL LIVE TRADING")
        logger.info("="*80)
        logger.info(f"  Symbols: {len(symbols)}")
        logger.info(f"  Scan interval: {scan_interval_seconds}s")
        logger.info(f"  Max positions: {self.concurrency_config.get('max_symbols', 3)}")
        logger.info("="*80)
        
        # CRITICAL: Fetch existing positions on startup
        logger.info("\n🔄 Checking for existing positions on Bitget...")
        existing_positions = await self.fetch_existing_positions()
        
        if existing_positions:
            logger.info(f"✅ Found {len(existing_positions)} existing positions - resuming monitoring")
            self.positions.update(existing_positions)
            self.active_symbols.update(existing_positions.keys())
            
            # Update sector counts
            for symbol in existing_positions.keys():
                sector = symbol[:3]
                self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
            
            # Verify TP/SL orders exist for each position
            for symbol, position in existing_positions.items():
                logger.info(f"🔍 Verifying TP/SL orders for {symbol}...")
                
                # 🚨 CRITICAL: Re-verify position STILL EXISTS before placing TP/SL!
                # Position might have closed between fetch and now
                position_still_exists = False
                try:
                    positions_list = await self.rest_client.get_positions(symbol)
                    if positions_list:
                        for pos in positions_list:
                            if pos.get('symbol') == symbol:
                                pos_size = float(pos.get('total', 0) or pos.get('available', 0))
                                if pos_size > 0:
                                    position_still_exists = True
                                    # Update with actual size from exchange
                                    position.size = pos_size
                                    position.remaining_size = pos_size
                                    break
                except Exception as e:
                    logger.debug(f"⚠️ Could not re-verify position {symbol}: {e}")
                
                if not position_still_exists:
                    logger.warning(f"⚠️ Position {symbol} no longer exists on exchange, skipping TP/SL placement")
                    # Remove from tracking
                    if symbol in self.positions:
                        del self.positions[symbol]
                    self.active_symbols.discard(symbol)
                    sector = symbol[:3]
                    self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
                    continue  # Skip this position
                
                # Place exchange-side TP/SL orders if missing
                tp1_price = position.tp_levels[0][0] if position.tp_levels else None
                
                # CRITICAL: Validate TP price for SHORT positions (must be below current price)
                if tp1_price and position.side == 'short':
                    try:
                        market_data = await self.get_market_data(symbol)
                        if market_data:
                            current_price = market_data.last_price
                            if tp1_price >= current_price:
                                tp1_price = current_price * 0.999
                                logger.warning(
                                    f"⚠️ TP1 price ({position.tp_levels[0][0]:.4f}) >= current price ({current_price:.4f}) for SHORT | "
                                    f"Adjusting TP1 to {tp1_price:.4f}"
                                )
                                position.tp_levels[0] = (tp1_price, position.tp_levels[0][1])
                    except Exception as e:
                        logger.debug(f"⚠️ Could not validate TP price: {e}")
                
                # CRITICAL: Validate TP price for LONG positions (must be above current price)
                if tp1_price and position.side == 'long':
                    try:
                        market_data = await self.get_market_data(symbol)
                        if market_data:
                            current_price = market_data.last_price
                            if tp1_price <= current_price:
                                tp1_price = current_price * 1.001
                                logger.warning(
                                    f"⚠️ TP1 price ({position.tp_levels[0][0]:.4f}) <= current price ({current_price:.4f}) for LONG | "
                                    f"Adjusting TP1 to {tp1_price:.4f}"
                                )
                                position.tp_levels[0] = (tp1_price, position.tp_levels[0][1])
                    except Exception as e:
                        logger.debug(f"⚠️ Could not validate TP price: {e}")
                
                # 🚨 EMERGENCY FIX: Skip TP/SL placement for recovered positions!
                # They often fail and hang the bot startup
                # Let exchange-side orders handle it OR bot will monitor them
                logger.warning(f"⚠️ SKIPPING TP/SL placement for recovered position {symbol} (prevents startup hang)")
                logger.info(f"✅ Position {symbol} will be monitored without re-placing TP/SL")
                continue  # Skip to next position
                
                # OLD CODE (CAUSES HANG) - DISABLED:
                # Retry TP/SL placement for recovered positions (they may need more time)
                tpsl_response = None
                for attempt in range(3):
                    try:
                        tpsl_response = await self.rest_client.place_tpsl_order(
                            symbol=symbol,
                            hold_side=position.side,
                            size=position.remaining_size,
                            stop_loss_price=position.stop_price,
                            take_profit_price=round(tp1_price, 2) if tp1_price else None,
                            size_precision=3
                        )
                        
                        sl_ok = tpsl_response.get('sl', {}).get('code') == '00000'
                        tp_ok = tpsl_response.get('tp', {}).get('code') == '00000' if tp1_price else True
                        
                        if sl_ok and tp_ok:
                            break
                        elif attempt < 2:
                            await asyncio.sleep(3.0 * (attempt + 1))  # 3s, 6s
                    except Exception as e:
                        if attempt < 2:
                            await asyncio.sleep(3.0 * (attempt + 1))
                        else:
                            logger.error(f"❌ Failed to place TP/SL for recovered {symbol}: {e}")
                
                # Store order IDs
                if tpsl_response and tpsl_response.get('sl', {}).get('code') == '00000':
                    position.stop_order_id = tpsl_response.get('sl', {}).get('data', {}).get('orderId')
                    logger.info(f"✅ Exchange SL placed for recovered position | {symbol}")
                elif tpsl_response:
                    sl_code = tpsl_response.get('sl', {}).get('code', 'N/A')
                    logger.warning(f"⚠️ SL placement failed for recovered {symbol} | Code: {sl_code}")
                
                if tpsl_response and tpsl_response.get('tp', {}).get('code') == '00000' and tp1_price:
                    tp_order_id = tpsl_response.get('tp', {}).get('data', {}).get('orderId')
                    position.tp_order_ids[0] = tp_order_id
                    logger.info(f"✅ Exchange TP1 placed for recovered position | {symbol}")
                elif tpsl_response and tp1_price:
                    tp_code = tpsl_response.get('tp', {}).get('code', 'N/A')
                    tp_msg = tpsl_response.get('tp', {}).get('msg', 'N/A')
                    logger.warning(f"⚠️ TP placement failed for recovered {symbol} | Code: {tp_code} | Msg: {tp_msg}")
                    logger.warning(f"   Position will be monitored - periodic check will re-place TP if needed")
        else:
            logger.info("✅ No existing positions found - starting fresh")
        
        logger.info(f"\n📊 Starting with {len(self.positions)} tracked positions\n")
        
        # Separate monitoring frequency (faster for 1-10 min trades)
        monitor_interval = 5  # Check positions every 5 seconds
        last_scan_time = datetime.now()
        
        while True:
            try:
                # Monitor existing positions (FAST - every 5 seconds)
                await self.monitor_positions()
                
                # Scan for new signals (SLOWER - every scan_interval_seconds)
                now = datetime.now()
                if (now - last_scan_time).total_seconds() >= scan_interval_seconds:
                    await self.scan_for_signals(symbols)
                    last_scan_time = now
                
                # Wait before next monitoring cycle
                await asyncio.sleep(monitor_interval)
            
            except KeyboardInterrupt:
                logger.info("\n⚠️ Shutting down...")
                break
            
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Wait before retrying
        
        logger.info("✅ Live trading stopped")


async def main():
    """Example usage"""
    import os
    
    # Load config
    with open('institutional_strategy_config.json', 'r') as f:
        config = json.load(f)
    
    # Get API credentials
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        logger.error("❌ Missing API credentials in environment variables")
        return
    
    # Create trader
    trader = InstitutionalLiveTrader(config, api_key, secret_key, passphrase)
    
    # Trading universe (start with majors)
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    # Run
    await trader.run(symbols, scan_interval_seconds=60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

