"""
Institutional Live Trading Module
Real-time execution with post-only entries, funding blackout, and tripwires
"""

import asyncio
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
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
        
        logger.info("✅ InstitutionalLiveTrader initialized")
        logger.info(f"  Mode: {'LIVE' if self.mode_config.get('live_enabled') else 'BACKTEST ONLY'}")
        logger.info(f"  Max symbols: {self.concurrency_config.get('max_symbols', 3)}")
        logger.info(f"  Max per sector: {self.concurrency_config.get('max_per_sector', 2)}")
    
    async def fetch_candles(self, symbol: str, timeframe: str, days: int = 7) -> Optional[pd.DataFrame]:
        """Fetch historical candles"""
        try:
            # Calculate how many candles we need
            candles_per_day = {'1m': 1440, '3m': 480, '5m': 288, '15m': 96, '1h': 24}
            total_candles = days * candles_per_day.get(timeframe, 288)
            
            # Bitget returns max 200 candles per request
            all_candles = []
            limit = min(200, total_candles)
            
            response = await self.rest_client.get_historical_candles(
                symbol=symbol,
                granularity=timeframe,
                limit=limit
            )
            
            if response.get('code') == '00000' and 'data' in response:
                candles = response['data']
                if candles:
                    # Convert to DataFrame
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
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
        now = datetime.now()
        
        # Check cache
        if not force_check and symbol in self.last_gate_check:
            if now - self.last_gate_check[symbol] < self.gate_check_interval:
                # Use cached result (assume passed if we checked recently)
                return True
        
        # Get market data
        market_data = await self.get_market_data(symbol)
        
        if not market_data:
            logger.warning(f"⚠️ Could not get market data for {symbol}")
            return False
        
        # Update bucket
        bucket = self.universe_filter.update_bucket_from_volume(symbol, market_data.quote_vol_24h)
        
        # Check gates
        passes, reason = self.universe_filter.passes_gates(market_data, bucket)
        
        if not passes:
            logger.debug(f"❌ {symbol} failed gates: {reason}")
        
        # Update cache
        self.last_gate_check[symbol] = now
        
        return passes
    
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
        Place entry order (post-only first, taker fallback after 2 bars)
        
        Returns:
            Order ID if successful, None otherwise
        """
        # Try post-only first (maker)
        try:
            logger.info(
                f"📍 Placing POST-ONLY entry | {symbol} {signal.side.upper()} | "
                f"Size: {size:.4f} @ ${signal.entry_price:.4f}"
            )
            
            response = await self.rest_client.place_order(
                symbol=symbol,
                side='buy' if signal.side == 'long' else 'sell',
                order_type='limit',
                size=str(size),
                price=str(signal.entry_price),
                post_only=True  # Maker only
            )
            
            if response.get('code') == '00000':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"✅ Post-only order placed | Order ID: {order_id}")
                
                # Wait 2 bars (10 seconds for 5m bars) to see if filled
                await asyncio.sleep(10)
                
                # Check if filled
                fill_status = await self.rest_client.get_order(symbol, order_id)
                
                if fill_status.get('data', {}).get('status') == 'filled':
                    logger.info(f"✅ Post-only order FILLED | {symbol}")
                    return order_id
                else:
                    logger.warning(f"⚠️ Post-only order NOT filled after 2 bars | Canceling...")
                    await self.rest_client.cancel_order(symbol, order_id)
            
        except Exception as e:
            logger.error(f"❌ Post-only order failed: {e}")
        
        # Fallback to taker (market order with limit protection)
        try:
            logger.info(f"📍 Placing TAKER entry (fallback) | {symbol} {signal.side.upper()}")
            
            # Reduce size by 30% for taker
            taker_size = size * 0.7
            
            # Get current market price
            market_data = await self.get_market_data(symbol)
            if not market_data:
                logger.error(f"❌ Could not get market price for taker order")
                return None
            
            # Place limit order at slightly worse price (acts like taker)
            taker_price = market_data.last_price * 1.001 if signal.side == 'long' else market_data.last_price * 0.999
            
            response = await self.rest_client.place_order(
                symbol=symbol,
                side='buy' if signal.side == 'long' else 'sell',
                order_type='limit',
                size=str(taker_size),
                price=str(taker_price),
                post_only=False
            )
            
            if response.get('code') == '00000':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"✅ Taker order placed | Order ID: {order_id}")
                return order_id
            else:
                logger.error(f"❌ Taker order failed: {response}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Taker order failed: {e}")
            return None
    
    async def place_stop_loss(self, position: LivePosition) -> Optional[str]:
        """Place stop-loss order"""
        try:
            response = await self.rest_client.place_stop_order(
                symbol=position.symbol,
                side='sell' if position.side == 'long' else 'buy',  # Opposite of entry
                trigger_price=str(position.stop_price),
                size=str(position.remaining_size),
                order_type='market'
            )
            
            if response.get('code') == '00000':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"✅ Stop-loss placed | {position.symbol} @ ${position.stop_price:.4f}")
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
            
            # Place new stop at BE
            position.stop_price = position.entry_price
            position.stop_order_id = await self.place_stop_loss(position)
            position.moved_to_be = True
            
            logger.info(f"✅ Stop moved to BE | {position.symbol} @ ${position.entry_price:.4f}")
        
        except Exception as e:
            logger.error(f"❌ Error moving stop to BE: {e}")
    
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
        
        for symbol, position in list(self.positions.items()):
            try:
                # Get current price
                market_data = await self.get_market_data(symbol)
                if not market_data:
                    continue
                
                current_price = market_data.last_price
                
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
                        else:
                            hit = current_price <= tp_price
                        
                        if hit:
                            logger.info(f"🎯 TP{tp_idx + 1} HIT | {symbol} @ ${tp_price:.4f}")
                            
                            position.tp_hit_count += 1
                            exit_size = position.size * tp_size_frac
                            position.remaining_size -= exit_size
                            
                            # Move SL to BE after TP1
                            if tp_idx == 0 and not position.moved_to_be:
                                await self.update_stop_to_breakeven(position)
                            
                            # If all size exited, close position
                            if position.remaining_size <= 0.001:
                                await self.close_position(position, f'tp{tp_idx + 1}')
                                break
            
            except Exception as e:
                logger.error(f"❌ Error monitoring position {symbol}: {e}")
    
    async def scan_for_signals(self, symbols: List[str]):
        """Scan symbols for trading signals"""
        for symbol in symbols:
            try:
                # Check if can open position
                if not await self.can_open_position(symbol, 'any'):
                    continue
                
                # Check universe gates
                if not await self.passes_universe_gates(symbol):
                    continue
                
                # Get data
                df_5m = await self.fetch_candles(symbol, timeframe='5m', days=7)
                if df_5m is None or len(df_5m) < 100:
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
                    continue
                
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
                    logger.warning(f"⚠️ Signal rejected - liq guards: {position_size.reason}")
                    continue
                
                # Place entry order
                order_id = await self.place_entry_order(signal, symbol, position_size.contracts, equity)
                
                if not order_id:
                    continue
                
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
                    stop_price=signal.stop_price,
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
        
        while True:
            try:
                # Monitor existing positions
                await self.monitor_positions()
                
                # Scan for new signals
                await self.scan_for_signals(symbols)
                
                # Wait before next scan
                await asyncio.sleep(scan_interval_seconds)
            
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

