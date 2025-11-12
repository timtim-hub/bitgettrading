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
                
                # Call API directly with endTime support
                response = await self.rest_client._request(
                    'GET',
                    '/api/v2/mix/market/candles',
                    params=api_params
                )
                
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
                    break
                
                # Small delay between requests to avoid rate limit
                if i < requests_needed - 1:
                    await asyncio.sleep(0.05)
            
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
        Place entry order - SIMPLIFIED for testing (market order)
        
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            logger.info(
                f"📍 Placing MARKET entry | {symbol} {signal.side.upper()} | "
                f"Size: {size:.4f}"
            )
            
            response = await self.rest_client.place_order(
                symbol=symbol,
                side='buy' if signal.side == 'long' else 'sell',
                order_type='market',
                size=size
            )
            
            if response.get('code') == '00000':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"✅ Market order placed | Order ID: {order_id}")
                return order_id
            else:
                logger.error(f"❌ Market order failed: {response}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}")
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
        """Move stop to breakeven after TP1"""
        try:
            # Cancel old stop
            if position.stop_order_id:
                await self.rest_client.cancel_order(position.symbol, position.stop_order_id)
            
            # Place new stop at BE (rounded)
            position.stop_price = round(position.entry_price, 2)
            position.stop_order_id = await self.place_stop_loss(position)
            position.moved_to_be = True
            
            logger.info(f"✅ Stop moved to BE | {position.symbol} @ ${position.entry_price:.4f}")
        
        except Exception as e:
            logger.error(f"❌ Error moving stop to BE: {e}")
    
    async def update_trailing_stop(self, position: LivePosition, current_price: float, current_bar: Dict):
        """
        Update trailing stop after TP1 hit
        
        Uses last swing low/high (simpler than Parabolic SAR for now)
        """
        try:
            atr = current_bar.get('atr', 0)
            if atr == 0:
                return
            
            # Get recent candles for swing detection
            df = await self.fetch_candles(position.symbol, timeframe='5m', days=1)
            if df is None or len(df) < 20:
                return
            
            # Calculate trailing stop price
            if position.side == 'long':
                # Use last 5 bars swing low
                recent_lows = df['low'].iloc[-5:].min()
                new_stop = recent_lows - (0.5 * atr)  # 0.5 ATR buffer
                
                # Only move stop up, never down
                if new_stop > position.stop_price:
                    # Cancel old stop
                    if position.stop_order_id:
                        await self.rest_client.cancel_order(position.symbol, position.stop_order_id)
                    
                    # Round to 2 decimals for Bitget
                    new_stop_rounded = round(new_stop, 2)
                    position.stop_price = new_stop_rounded
                    position.stop_order_id = await self.place_stop_loss(position)
                    logger.info(f"📈 Trailing stop updated | {position.symbol} @ ${new_stop_rounded:.2f}")
            else:  # short
                # Use last 5 bars swing high
                recent_highs = df['high'].iloc[-5:].max()
                new_stop = recent_highs + (0.5 * atr)  # 0.5 ATR buffer
                
                # Only move stop down, never up
                if new_stop < position.stop_price or position.stop_price == 0:
                    # Cancel old stop
                    if position.stop_order_id:
                        await self.rest_client.cancel_order(position.symbol, position.stop_order_id)
                    
                    # Round to 2 decimals for Bitget
                    new_stop_rounded = round(new_stop, 2)
                    position.stop_price = new_stop_rounded
                    position.stop_order_id = await self.place_stop_loss(position)
                    logger.info(f"📉 Trailing stop updated | {position.symbol} @ ${new_stop_rounded:.2f}")
        
        except Exception as e:
            logger.error(f"❌ Error updating trailing stop: {e}")
    
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
        if position.time_stop_time and datetime.now() >= position.time_stop_time:
            logger.info(f"⏱️ Time stop reached | {position.symbol}")
            return 'time_stop'
        
        return None
    
    async def close_position(self, position: LivePosition, reason: str):
        """Close position (market order)"""
        try:
            logger.info(
                f"💰 Closing position | {position.symbol} {position.side.upper()} | "
                f"Reason: {reason} | Size: {position.remaining_size:.4f}"
            )
            
            # Cancel all open orders
            if position.stop_order_id:
                await self.rest_client.cancel_order(position.symbol, position.stop_order_id)
            
            for tp_order_id in position.tp_order_ids.values():
                await self.rest_client.cancel_order(position.symbol, tp_order_id)
            
            # Place market order to close
            response = await self.rest_client.place_order(
                symbol=position.symbol,
                side='sell' if position.side == 'long' else 'buy',  # Opposite
                order_type='market',
                size=str(position.remaining_size)
            )
            
            if response.get('code') == '00000':
                logger.info(f"✅ Position closed | {position.symbol}")
                
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
        
        for symbol, position in list(self.positions.items()):
            try:
                # Get current price
                market_data = await self.get_market_data(symbol)
                if not market_data:
                    continue
                
                current_price = market_data.last_price
                
                # Log monitoring (every 10 seconds to see activity)
                time_since_entry = (datetime.now() - position.entry_time).total_seconds()
                if int(time_since_entry) % 10 < 5:  # Log roughly every 10 seconds
                    pnl_pct = ((current_price - position.entry_price) / position.entry_price * 100) if position.side == 'long' else ((position.entry_price - current_price) / position.entry_price * 100)
                    
                    # Calculate distance to TP/SL
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
                    
                    logger.info(
                        f"📊 {symbol} {position.side.upper()} | "
                        f"Price: ${current_price:.4f} | P&L: {pnl_pct:+.2f}% | "
                        f"TP1: ${tp_price:.4f} ({tp_dist:+.2f}%) | SL: ${position.stop_price:.4f} ({sl_dist:+.2f}%)"
                    )
                
                # Update MAE/MFE tracking
                if position.side == 'long':
                    position.highest_price = max(position.highest_price, current_price)
                else:
                    position.lowest_price = min(position.lowest_price, current_price) if position.lowest_price > 0 else current_price
                
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
                
                # Check TP levels
                for tp_idx, (tp_price, tp_size_frac) in enumerate(position.tp_levels):
                    if position.tp_hit_count <= tp_idx:
                        hit = False
                        if position.side == 'long':
                            hit = current_price >= tp_price
                            distance_to_tp = ((current_price - tp_price) / tp_price) * 100
                        else:
                            hit = current_price <= tp_price
                            distance_to_tp = ((tp_price - current_price) / tp_price) * 100
                        
                        # Log TP check (every 30 seconds)
                        if int(time_since_entry) % 30 < 5:
                            logger.debug(
                                f"  TP{tp_idx + 1} check: {symbol} | "
                                f"Current: ${current_price:.4f} | TP: ${tp_price:.4f} | "
                                f"Distance: {distance_to_tp:+.2f}% | Hit: {hit}"
                            )
                        
                        if hit:
                            logger.info(f"🎯 TP{tp_idx + 1} HIT | {symbol} @ ${tp_price:.4f} | Current: ${current_price:.4f}")
                            logger.info(f"  📊 Position details: Entry=${position.entry_price:.4f}, Size={position.size:.4f}, Remaining={position.remaining_size:.4f}")
                            
                            position.tp_hit_count += 1
                            exit_size = position.size * tp_size_frac
                            
                            logger.info(f"  💰 Exiting {exit_size:.4f} contracts ({tp_size_frac*100:.0f}%) | Notional: ${exit_size * current_price:.2f}")
                            
                            # ACTUALLY EXECUTE THE EXIT TRADE
                            try:
                                logger.info(f"  📤 Placing market order to exit TP{tp_idx + 1}...")
                                response = await self.rest_client.place_order(
                                    symbol=symbol,
                                    side='sell' if position.side == 'long' else 'buy',
                                    order_type='market',
                                    size=exit_size,
                                    reduce_only=True
                                )
                                
                                logger.info(f"  📥 API Response: {response.get('code')} - {response.get('msg', 'N/A')}")
                                
                                if response.get('code') == '00000':
                                    order_id = response.get('data', {}).get('orderId') or response.get('data', {}).get('order_id')
                                    logger.info(f"✅ TP{tp_idx + 1} EXIT EXECUTED | Order ID: {order_id}")
                                    
                                    # Update remaining size
                                    position.remaining_size -= exit_size
                                    logger.info(f"  ✅ Remaining size: {position.remaining_size:.4f}")
                                else:
                                    logger.error(f"❌ TP{tp_idx + 1} exit failed: {response}")
                                    # Revert tp_hit_count if trade failed
                                    position.tp_hit_count -= 1
                                    continue  # Don't update tracking if trade failed
                            except Exception as e:
                                logger.error(f"❌ Error executing TP{tp_idx + 1} exit: {e}", exc_info=True)
                                # Revert tp_hit_count if trade failed
                                position.tp_hit_count -= 1
                                continue
                            
                            # Move SL to BE after TP1
                            if tp_idx == 0 and not position.moved_to_be:
                                await self.update_stop_to_breakeven(position)
                            
                            # If all size exited, close position tracking
                            if position.remaining_size <= 0.001:
                                logger.info(f"✅ Position fully exited via TP{tp_idx + 1}")
                                del self.positions[symbol]
                                self.active_symbols.discard(symbol)
                                sector = symbol[:3]
                                self.sector_counts[sector] = max(0, self.sector_counts.get(sector, 0) - 1)
                                break
                
                # Check stop-loss (exchange-side should handle, but verify)
                if position.side == 'long':
                    sl_hit = current_price <= position.stop_price
                    distance_to_sl = ((current_price - position.stop_price) / position.entry_price) * 100
                else:
                    sl_hit = current_price >= position.stop_price
                    distance_to_sl = ((position.stop_price - current_price) / position.entry_price) * 100
                
                if sl_hit:
                    logger.warning(f"🚨 STOP-LOSS HIT | {symbol} | Current: ${current_price:.4f} | Stop: ${position.stop_price:.4f}")
                    await self.close_position(position, 'stop_loss')
                    continue
                
                # Trailing stop (enabled after TP1 hit)
                if position.tp_hit_count > 0 and position.moved_to_be:
                    # Log trailing stop activity (every 30 seconds)
                    if int(time_since_entry) % 30 < 5:
                        logger.debug(f"  🔄 Trailing stop active for {symbol} | Current stop: ${position.stop_price:.2f}")
                    await self.update_trailing_stop(position, current_price, current_bar)
                elif position.tp_hit_count == 0:
                    # Log when trailing is waiting for TP1 (every 30 seconds)
                    if int(time_since_entry) % 30 < 5:
                        logger.debug(f"  ⏳ Trailing stop waiting for TP1 | {symbol} | tp_hit_count={position.tp_hit_count}, moved_to_be={position.moved_to_be}")
            
            except Exception as e:
                logger.error(f"❌ Error monitoring position {symbol}: {e}")
    
    async def scan_for_signals(self, symbols: List[str]):
        """Scan symbols for trading signals"""
        logger.info(f"🔍 Starting signal scan: {len(symbols)} symbols, {len(self.positions)} open positions")
        
        stats = {'checked': 0, 'gates_failed': 0, 'data_failed': 0, 'no_signal': 0, 'signals_found': 0}
        
        for symbol in symbols:
            try:
                stats['checked'] += 1
                
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
                
                # Get account equity
                equity = await self.get_account_equity()
                if equity == 0:
                    logger.error("❌ Could not get account equity")
                    continue
                
                # Calculate position size
                position_size = self.risk_manager.calculate_position_size(
                    symbol=symbol,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    stop_price=signal.stop_price,
                    equity_usdt=equity,
                    lot_size=0.001,
                    min_qty=0.001
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
                
                position = LivePosition(
                    symbol=symbol,
                    side=signal.side,
                    strategy=signal.strategy,
                    entry_time=datetime.now(),
                    entry_price=signal.entry_price,
                    size=position_size.contracts,
                    notional=position_size.notional_usd,
                    stop_price=round(signal.stop_price, 2),  # Round for Bitget API
                    tp_levels=signal.tp_levels,
                    remaining_size=position_size.contracts,
                    highest_price=signal.entry_price if signal.side == 'long' else 0,
                    lowest_price=signal.entry_price if signal.side == 'short' else 0,
                    time_stop_time=datetime.now() + timedelta(minutes=time_stop_minutes),
                    sweep_level=signal.metadata.get('swept_level')
                )
                
                # Place stop-loss
                position.stop_order_id = await self.place_stop_loss(position)
                
                # Add to tracking
                self.positions[symbol] = position
                self.active_symbols.add(symbol)
                
                sector = symbol[:3]
                self.sector_counts[sector] = self.sector_counts.get(sector, 0) + 1
                
                logger.info(
                    f"✅ POSITION OPENED | {symbol} {signal.side.upper()} | "
                    f"Strategy: {signal.strategy} | Size: {position_size.contracts:.4f}"
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
            
            # Verify stop-loss orders exist for each position
            for symbol, position in existing_positions.items():
                logger.info(f"🔍 Verifying stop-loss for {symbol}...")
                # Try to place stop-loss if missing (will fail gracefully if exists)
                if not position.stop_order_id:
                    position.stop_order_id = await self.place_stop_loss(position)
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

