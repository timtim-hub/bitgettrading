"""
Institutional Trading Strategies
- LSVR (Liquidity Sweep → VWAP Reversion)
- VWAP Mean-Reversion (VWAP-MR)
- Trend Fallback
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """Trade signal output"""
    strategy: str  # 'LSVR', 'VWAP_MR', or 'Trend'
    side: str  # 'long' or 'short'
    entry_price: float  # Limit entry price
    stop_price: float  # Stop loss price
    tp_levels: List[Tuple[float, float]]  # [(price, size_fraction), ...]
    confidence: float  # 0.0-1.0
    reason: str  # Entry reason
    metadata: Dict  # Additional context


class LSVRStrategy:
    """
    Liquidity Sweep → VWAP Reversion (Range only)
    
    Entry logic (Long, mirror for Short):
    1. Sweep: Wick beyond PDL or Asia Low by ≥ sweep_atr_x * ATR and close back inside ≤ 3 bars
    2. Confirm: RSI bull divergence (1-3m) + sweep bar tail ≥ 0.6× body (OF disabled)
    3. Trigger: First 1m structure break up AND 1-3m close above VWAP-1σ
    4. Entry: Limit on retest of swept level (preferred) or VWAP-1σ if no retest in 2 bars
    5. SL: Below sweep extreme by 1.2-1.5× ATR (bucket-specific)
    
    Exits (25x-tuned):
    - TP1: VWAP, exit 75%, move SL → BE immediately
    - TP2: VWAP + 1σ or +1.2R, exit 20%
    - TP3: Prior intraday pivot or +1.8-2.0R, exit 5%
    - Trail: After TP1 with Parabolic SAR or 5m swing
    - Time-stop: 15-25 min
    - Tripwires: Skip if sweep volume ≥ 2.2× avg; instant exit if re-sweep within 10 min
    """
    
    def __init__(self, config: Dict, bucket: str):
        self.config = config.get('strategies', {}).get('LSVR', {})
        self.bucket = bucket
        self.sweep_atr_x = self.config.get('sweep_atr_x', {}).get(bucket, 0.6)
        self.sl_atr_x = self.config.get('sl_atr_x', {}).get(bucket, 1.35)
        self.tp_config = self.config.get('tp', {})
        self.time_stop_range = self.config.get('time_stop_min', [15, 25])
        self.volume_skip_x = self.config.get('volume_skip_x', 2.2)
        self.tail_body_ratio = self.config.get('tail_body_min_ratio', 0.6)
        
        logger.info(f"✅ LSVR Strategy initialized for {bucket} | sweep_atr={self.sweep_atr_x}x | sl_atr={self.sl_atr_x}x")
    
    def detect_sweep(self, df: pd.DataFrame, levels: Dict, current_idx: int = -1) -> Optional[Dict]:
        """
        Detect liquidity sweep
        
        Returns:
            Dict with sweep details if detected, None otherwise
        """
        if current_idx < -len(df):
            return None
        
        # Get current and recent bars
        current_bar = df.iloc[current_idx]
        atr = current_bar.get('atr', 0)
        
        if atr == 0 or pd.isna(atr):
            return None
        
        # Check if wick swept below PDL or Asia Low
        pdl = levels.get('pdl')
        asia_low = levels.get('asia_low')
        
        swept_level = None
        level_name = None
        
        # Check PDL sweep (long)
        if pdl and current_bar['low'] < pdl - (self.sweep_atr_x * atr):
            if current_bar['close'] > pdl:  # Closed back inside
                swept_level = pdl
                level_name = 'PDL'
        
        # Check Asia Low sweep (long)
        if not swept_level and asia_low and current_bar['low'] < asia_low - (self.sweep_atr_x * atr):
            if current_bar['close'] > asia_low:
                swept_level = asia_low
                level_name = 'Asia Low'
        
        # Check PDH sweep (short)
        pdh = levels.get('pdh')
        asia_high = levels.get('asia_high')
        
        if not swept_level and pdh and current_bar['high'] > pdh + (self.sweep_atr_x * atr):
            if current_bar['close'] < pdh:
                swept_level = pdh
                level_name = 'PDH'
        
        # Check Asia High sweep (short)
        if not swept_level and asia_high and current_bar['high'] > asia_high + (self.sweep_atr_x * atr):
            if current_bar['close'] < asia_high:
                swept_level = asia_high
                level_name = 'Asia High'
        
        if swept_level:
            # Check if close back happened within 3 bars
            close_back_confirmed = True  # Already checked above
            
            # Calculate tail-to-body ratio
            body = abs(current_bar['close'] - current_bar['open'])
            if swept_level < current_bar['close']:  # Long sweep
                tail = current_bar['close'] - current_bar['low']
                side = 'long'
            else:  # Short sweep
                tail = current_bar['high'] - current_bar['close']
                side = 'short'
            
            tail_body_ratio = tail / body if body > 0 else 0
            
            # Check volume (skip if too high)
            volume_ratio = current_bar.get('volume_ratio', 1.0)
            if volume_ratio >= self.volume_skip_x:
                logger.debug(f"⚠️ LSVR: Sweep detected but volume too high ({volume_ratio:.1f}x >= {self.volume_skip_x}x), skipping")
                return None
            
            logger.info(
                f"🎯 LSVR: Sweep detected! | "
                f"Level={level_name} @ ${swept_level:.4f} | "
                f"Side={side} | "
                f"Tail/Body={tail_body_ratio:.2f} | "
                f"Volume={volume_ratio:.1f}x"
            )
            
            return {
                'swept_level': swept_level,
                'level_name': level_name,
                'side': side,
                'sweep_extreme': current_bar['low'] if side == 'long' else current_bar['high'],
                'tail_body_ratio': tail_body_ratio,
                'volume_ratio': volume_ratio,
                'sweep_bar_idx': current_idx,
                'atr': atr
            }
        
        return None
    
    def check_confirmation(self, df: pd.DataFrame, sweep_data: Dict, 
                           current_idx: int = -1) -> bool:
        """
        Check sweep confirmation (RSI divergence + tail ratio)
        
        OF disabled, so only checking:
        - RSI bull divergence (price LL with RSI HL) for long
        - Sweep bar tail ≥ 0.6× body
        """
        side = sweep_data['side']
        tail_body_ratio = sweep_data['tail_body_ratio']
        
        # Check tail ratio
        if tail_body_ratio < self.tail_body_ratio:
            logger.debug(f"⚠️ LSVR: Confirmation failed - tail/body {tail_body_ratio:.2f} < {self.tail_body_ratio}")
            return False
        
        # Check RSI divergence (simplified - check if RSI rising while price fell)
        sweep_idx = sweep_data['sweep_bar_idx']
        lookback_bars = min(5, abs(sweep_idx) + 5)  # Look back 5 bars before sweep
        
        if sweep_idx - lookback_bars < -len(df):
            logger.debug("⚠️ LSVR: Not enough data for RSI divergence")
            return False
        
        rsi_values = df['rsi'].iloc[sweep_idx - lookback_bars:sweep_idx + 1]
        price_values = df['close'].iloc[sweep_idx - lookback_bars:sweep_idx + 1]
        
        if len(rsi_values) < 2 or len(price_values) < 2:
            return False
        
        if side == 'long':
            # Price LL (lower low)
            price_ll = price_values.iloc[-1] < price_values.iloc[0]
            # RSI HL (higher low)
            rsi_hl = rsi_values.iloc[-1] > rsi_values.iloc[0]
            
            divergence = price_ll and rsi_hl
        else:  # short
            # Price HH (higher high)
            price_hh = price_values.iloc[-1] > price_values.iloc[0]
            # RSI LH (lower high)
            rsi_lh = rsi_values.iloc[-1] < rsi_values.iloc[0]
            
            divergence = price_hh and rsi_lh
        
        if divergence:
            logger.info(f"✅ LSVR: Confirmation passed - RSI divergence detected")
        else:
            logger.debug(f"⚠️ LSVR: Confirmation failed - no RSI divergence")
        
        return divergence
    
    def check_trigger(self, df: pd.DataFrame, sweep_data: Dict, 
                      vwap_data: Dict, current_idx: int = -1) -> Optional[float]:
        """
        Check trigger conditions:
        - First 1m structure break up (price breaks above previous high)
        - 1-3m close above VWAP-1σ (for long) or below VWAP+1σ (for short)
        
        Returns:
            Entry price if triggered, None otherwise
        """
        side = sweep_data['side']
        current_bar = df.iloc[current_idx]
        
        vwap = vwap_data.get('vwap', current_bar.get('vwap', 0))
        vwap_lower = vwap_data.get('vwap_lower', current_bar.get('vwap_lower', 0))
        vwap_upper = vwap_data.get('vwap_upper', current_bar.get('vwap_upper', 0))
        
        if side == 'long':
            # Check if close above VWAP-1σ
            if current_bar['close'] <= vwap_lower:
                logger.debug(f"⚠️ LSVR: Trigger not met - close ${current_bar['close']:.4f} not above VWAP-1σ ${vwap_lower:.4f}")
                return None
            
            # Check structure break (current high > previous high)
            if current_idx > -len(df):
                prev_bar = df.iloc[current_idx - 1]
                if current_bar['high'] <= prev_bar['high']:
                    logger.debug("⚠️ LSVR: Trigger not met - no structure break up")
                    return None
            
            # Entry on retest of swept level or VWAP-1σ
            entry_price = max(sweep_data['swept_level'], vwap_lower)
            
        else:  # short
            # Check if close below VWAP+1σ
            if current_bar['close'] >= vwap_upper:
                logger.debug(f"⚠️ LSVR: Trigger not met - close ${current_bar['close']:.4f} not below VWAP+1σ ${vwap_upper:.4f}")
                return None
            
            # Check structure break (current low < previous low)
            if current_idx > -len(df):
                prev_bar = df.iloc[current_idx - 1]
                if current_bar['low'] >= prev_bar['low']:
                    logger.debug("⚠️ LSVR: Trigger not met - no structure break down")
                    return None
            
            # Entry on retest of swept level or VWAP+1σ
            entry_price = min(sweep_data['swept_level'], vwap_upper)
        
        logger.info(f"✅ LSVR: Trigger confirmed! Entry @ ${entry_price:.4f}")
        return entry_price
    
    def generate_signal(self, df: pd.DataFrame, levels: Dict, 
                        current_idx: int = -1) -> Optional[TradeSignal]:
        """
        Generate LSVR trade signal
        
        Returns:
            TradeSignal if all conditions met, None otherwise
        """
        # 1. Detect sweep
        sweep_data = self.detect_sweep(df, levels, current_idx)
        if not sweep_data:
            return None
        
        # 2. Check confirmation
        if not self.check_confirmation(df, sweep_data, current_idx):
            return None
        
        # 3. Check trigger
        current_bar = df.iloc[current_idx]
        vwap_data = {
            'vwap': current_bar.get('vwap', 0),
            'vwap_lower': current_bar.get('vwap_lower', 0),
            'vwap_upper': current_bar.get('vwap_upper', 0),
            'vwap_sigma': current_bar.get('vwap_sigma', 0)
        }
        
        entry_price = self.check_trigger(df, sweep_data, vwap_data, current_idx)
        if not entry_price:
            return None
        
        # 4. Calculate stop loss
        side = sweep_data['side']
        atr = sweep_data['atr']
        sweep_extreme = sweep_data['sweep_extreme']
        
        if side == 'long':
            stop_price = sweep_extreme - (self.sl_atr_x * atr)
        else:
            stop_price = sweep_extreme + (self.sl_atr_x * atr)
        
        # 5. Calculate TP levels
        tp_levels = self._calculate_tp_levels(entry_price, stop_price, vwap_data, side)
        
        logger.info(
            f"🚀 LSVR SIGNAL | "
            f"{side.upper()} @ ${entry_price:.4f} | "
            f"SL @ ${stop_price:.4f} | "
            f"TPs: {len(tp_levels)} levels"
        )
        
        return TradeSignal(
            strategy='LSVR',
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            tp_levels=tp_levels,
            confidence=0.85,  # High confidence for LSVR
            reason=f"Liquidity sweep of {sweep_data['level_name']} with RSI divergence",
            metadata=sweep_data
        )
    
    def _calculate_tp_levels(self, entry: float, stop: float, vwap_data: Dict, 
                             side: str) -> List[Tuple[float, float]]:
        """Calculate TP levels for LSVR"""
        vwap = vwap_data['vwap']
        vwap_sigma = vwap_data['vwap_sigma']
        
        tp_levels = []
        
        # TP1: VWAP (75%)
        tp1_price = vwap
        tp_levels.append((tp1_price, 0.75))
        
        # TP2: VWAP + 1σ or +1.2R (20%)
        risk = abs(entry - stop)
        if side == 'long':
            tp2_vwap = vwap + vwap_sigma
            tp2_r = entry + (1.2 * risk)
            tp2_price = max(tp2_vwap, tp2_r)
        else:
            tp2_vwap = vwap - vwap_sigma
            tp2_r = entry - (1.2 * risk)
            tp2_price = min(tp2_vwap, tp2_r)
        
        tp_levels.append((tp2_price, 0.20))
        
        # TP3: +1.8-2.0R (5%)
        if side == 'long':
            tp3_price = entry + (1.9 * risk)
        else:
            tp3_price = entry - (1.9 * risk)
        
        tp_levels.append((tp3_price, 0.05))
        
        return tp_levels


class VWAPMRStrategy:
    """
    VWAP Mean-Reversion (Range only)
    
    Entry logic (Long, mirror for Short):
    - 5m touch lower BB(20,2) or VWAP-1σ
    - Stoch RSI up-cross 20 (1-3m) within 3 bars
    - RSI(14,5m) ≥ 42
    - Volume on tag < 1.8× 20-bar avg
    
    Exits (25x-tuned):
    - TP1: VWAP, exit 65%, move SL → BE immediately
    - TP2: Opposite 1σ or +1.2R, exit 30%
    - TP3: Opposite BB or +1.8-2.0R, exit 5%
    - Time-stop: 20-30 min
    - Tripwire: Any 1-3m candle ≥ 1.7× ATR against position → flat immediately
    """
    
    def __init__(self, config: Dict, bucket: str):
        self.config = config.get('strategies', {}).get('VWAP_MR', {})
        self.bucket = bucket
        
        entry_config = self.config.get('entry', {})
        self.bb_touch_sigma = entry_config.get('bb_touch_or_sigma', -1)
        self.stoch_level = entry_config.get('stoch_rsi_level', 20)
        self.stoch_within_bars = entry_config.get('stoch_within_bars', 3)
        self.rsi_min = entry_config.get('rsi5m_min', 42)
        self.vol_spike_max = entry_config.get('vol_spike_max_x', 1.8)
        
        self.sl_atr_x = self.config.get('sl_atr_x', {}).get(bucket, 1.35)
        self.tp_config = self.config.get('tp', {})
        self.time_stop_range = self.config.get('time_stop_min', [20, 30])
        self.adverse_spike_x = self.config.get('adverse_spike_exit_x', 1.7)
        
        logger.info(f"✅ VWAP-MR Strategy initialized for {bucket} | sl_atr={self.sl_atr_x}x")
    
    def check_entry_conditions(self, df: pd.DataFrame, current_idx: int = -1) -> Optional[str]:
        """
        Check VWAP-MR entry conditions
        
        Returns:
            'long' or 'short' if conditions met, None otherwise
        """
        current_bar = df.iloc[current_idx]
        
        # Get indicators
        bb_lower = current_bar.get('bb_lower', 0)
        bb_upper = current_bar.get('bb_upper', 0)
        vwap = current_bar.get('vwap', 0)
        vwap_lower = current_bar.get('vwap_lower', 0)
        vwap_upper = current_bar.get('vwap_upper', 0)
        rsi = current_bar.get('rsi', 50)
        volume_ratio = current_bar.get('volume_ratio', 1.0)
        
        # Check LONG conditions
        # 1. Touch lower BB or VWAP-1σ
        touch_lower = (current_bar['low'] <= bb_lower or current_bar['low'] <= vwap_lower)
        
        if touch_lower:
            # 2. Check RSI ≥ 42
            if rsi < self.rsi_min:
                logger.debug(f"⚠️ VWAP-MR LONG: RSI {rsi:.1f} < {self.rsi_min}")
                return None
            
            # 3. Check volume not too high
            if volume_ratio >= self.vol_spike_max:
                logger.debug(f"⚠️ VWAP-MR LONG: Volume ratio {volume_ratio:.1f}x >= {self.vol_spike_max}x")
                return None
            
            # 4. Check Stoch RSI up-cross 20 within last 3 bars
            if self._check_stoch_rsi_cross(df, current_idx, direction='up'):
                logger.info(f"✅ VWAP-MR: LONG conditions met @ ${current_bar['close']:.4f}")
                return 'long'
        
        # Check SHORT conditions
        touch_upper = (current_bar['high'] >= bb_upper or current_bar['high'] >= vwap_upper)
        
        if touch_upper:
            # RSI ≤ 58 (mirror of 42)
            if rsi > (100 - self.rsi_min):
                logger.debug(f"⚠️ VWAP-MR SHORT: RSI {rsi:.1f} > {100 - self.rsi_min}")
                return None
            
            # Volume check
            if volume_ratio >= self.vol_spike_max:
                logger.debug(f"⚠️ VWAP-MR SHORT: Volume ratio {volume_ratio:.1f}x >= {self.vol_spike_max}x")
                return None
            
            # Stoch RSI down-cross 80
            if self._check_stoch_rsi_cross(df, current_idx, direction='down'):
                logger.info(f"✅ VWAP-MR: SHORT conditions met @ ${current_bar['close']:.4f}")
                return 'short'
        
        return None
    
    def _check_stoch_rsi_cross(self, df: pd.DataFrame, current_idx: int, 
                                direction: str) -> bool:
        """Check if Stoch RSI crossed threshold within last N bars"""
        lookback = self.stoch_within_bars
        
        if current_idx - lookback < -len(df):
            return False
        
        stoch_k = df['stoch_rsi_k'].iloc[current_idx - lookback:current_idx + 1]
        
        if len(stoch_k) < 2:
            return False
        
        if direction == 'up':
            # Check if crossed above 20
            for i in range(1, len(stoch_k)):
                if stoch_k.iloc[i-1] <= self.stoch_level and stoch_k.iloc[i] > self.stoch_level:
                    return True
        else:  # down
            # Check if crossed below 80
            for i in range(1, len(stoch_k)):
                if stoch_k.iloc[i-1] >= (100 - self.stoch_level) and stoch_k.iloc[i] < (100 - self.stoch_level):
                    return True
        
        return False
    
    def generate_signal(self, df: pd.DataFrame, current_idx: int = -1) -> Optional[TradeSignal]:
        """
        Generate VWAP-MR trade signal
        
        Returns:
            TradeSignal if conditions met, None otherwise
        """
        # Check entry conditions
        side = self.check_entry_conditions(df, current_idx)
        if not side:
            return None
        
        current_bar = df.iloc[current_idx]
        
        # Entry price (at touch level)
        if side == 'long':
            entry_price = min(current_bar.get('bb_lower', current_bar['close']), 
                              current_bar.get('vwap_lower', current_bar['close']))
        else:
            entry_price = max(current_bar.get('bb_upper', current_bar['close']), 
                              current_bar.get('vwap_upper', current_bar['close']))
        
        # Calculate stop loss
        atr = current_bar.get('atr', 0)
        if atr == 0 or pd.isna(atr):
            logger.warning("⚠️ VWAP-MR: ATR is 0, cannot calculate stop")
            return None
        
        if side == 'long':
            stop_price = current_bar['low'] - (self.sl_atr_x * atr)
        else:
            stop_price = current_bar['high'] + (self.sl_atr_x * atr)
        
        # Calculate TP levels
        vwap_data = {
            'vwap': current_bar.get('vwap', 0),
            'vwap_lower': current_bar.get('vwap_lower', 0),
            'vwap_upper': current_bar.get('vwap_upper', 0),
            'vwap_sigma': current_bar.get('vwap_sigma', 0),
            'bb_lower': current_bar.get('bb_lower', 0),
            'bb_upper': current_bar.get('bb_upper', 0)
        }
        
        tp_levels = self._calculate_tp_levels(entry_price, stop_price, vwap_data, side)
        
        logger.info(
            f"🚀 VWAP-MR SIGNAL | "
            f"{side.upper()} @ ${entry_price:.4f} | "
            f"SL @ ${stop_price:.4f} | "
            f"TPs: {len(tp_levels)} levels"
        )
        
        return TradeSignal(
            strategy='VWAP_MR',
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            tp_levels=tp_levels,
            confidence=0.75,
            reason=f"VWAP/BB touch with Stoch RSI cross and volume confirmation",
            metadata={'atr': atr, 'rsi': current_bar.get('rsi', 0)}
        )
    
    def _calculate_tp_levels(self, entry: float, stop: float, vwap_data: Dict, 
                             side: str) -> List[Tuple[float, float]]:
        """Calculate TP levels for VWAP-MR"""
        vwap = vwap_data['vwap']
        vwap_sigma = vwap_data['vwap_sigma']
        bb_upper = vwap_data['bb_upper']
        bb_lower = vwap_data['bb_lower']
        
        tp_levels = []
        risk = abs(entry - stop)
        
        # TP1: VWAP (65%)
        tp1_price = vwap
        tp_levels.append((tp1_price, 0.65))
        
        # TP2: Opposite 1σ or +1.2R (30%)
        if side == 'long':
            tp2_vwap = vwap + vwap_sigma
            tp2_r = entry + (1.2 * risk)
            tp2_price = max(tp2_vwap, tp2_r)
        else:
            tp2_vwap = vwap - vwap_sigma
            tp2_r = entry - (1.2 * risk)
            tp2_price = min(tp2_vwap, tp2_r)
        
        tp_levels.append((tp2_price, 0.30))
        
        # TP3: Opposite BB or +1.8R (5%)
        if side == 'long':
            tp3_bb = bb_upper
            tp3_r = entry + (1.8 * risk)
            tp3_price = max(tp3_bb, tp3_r)
        else:
            tp3_bb = bb_lower
            tp3_r = entry - (1.8 * risk)
            tp3_price = min(tp3_bb, tp3_r)
        
        tp_levels.append((tp3_price, 0.05))
        
        return tp_levels


class TrendStrategy:
    """
    Trend Fallback (Trend regime only)
    
    Entry logic:
    - Bias: Above/below 200-EMA(15m) and VWAP slope aligned
    - Trigger: Pullback to VWAP ±1σ, 9/21 EMA recross, RSI(14) >50 (<50)
    - SL: Last swing ± 1.4-1.5× ATR(5m)
    - TP1: +1.2× ATR
    - Trail: Supertrend(10,3) or 5m swing
    """
    
    def __init__(self, config: Dict):
        self.config = config.get('strategies', {}).get('Trend', {})
        self.ema_periods = self.config.get('ema', [9, 21, 50, 200])
        self.sl_atr_x = self.config.get('sl_atr_x', 1.5)
        self.tp1_atr_x = self.config.get('tp1_atr_x', 1.2)
        self.rsi_bull_threshold = self.config.get('rsi_bull_threshold', 50)
        self.rsi_bear_threshold = self.config.get('rsi_bear_threshold', 50)
        
        logger.info(f"✅ Trend Strategy initialized | sl_atr={self.sl_atr_x}x | tp1_atr={self.tp1_atr_x}x")
    
    def generate_signal(self, df: pd.DataFrame, current_idx: int = -1) -> Optional[TradeSignal]:
        """
        Generate Trend trade signal
        
        Returns:
            TradeSignal if conditions met, None otherwise
        """
        current_bar = df.iloc[current_idx]
        
        # Get indicators
        ema_200 = current_bar.get('ema_200', 0)
        ema_21 = current_bar.get('ema_21', 0)
        ema_9 = current_bar.get('ema_9', 0)
        vwap = current_bar.get('vwap', 0)
        vwap_lower = current_bar.get('vwap_lower', 0)
        vwap_upper = current_bar.get('vwap_upper', 0)
        vwap_slope_sigma = current_bar.get('vwap_slope_sigma', 0)
        rsi = current_bar.get('rsi', 50)
        atr = current_bar.get('atr', 0)
        
        if ema_200 == 0 or atr == 0:
            return None
        
        price = current_bar['close']
        
        # Determine bias
        bullish_bias = price > ema_200 and vwap_slope_sigma > 0
        bearish_bias = price < ema_200 and vwap_slope_sigma < 0
        
        # Check for LONG signal
        if bullish_bias:
            # Pullback to VWAP or VWAP-1σ
            near_vwap = abs(price - vwap) / price < 0.01 or price <= vwap_lower * 1.01
            
            # EMA 9/21 recross (9 crosses above 21)
            if current_idx > -len(df):
                prev_bar = df.iloc[current_idx - 1]
                ema_9_prev = prev_bar.get('ema_9', 0)
                ema_21_prev = prev_bar.get('ema_21', 0)
                ema_recross = (ema_9_prev <= ema_21_prev) and (ema_9 > ema_21)
            else:
                ema_recross = False
            
            # RSI > 50
            rsi_ok = rsi > self.rsi_bull_threshold
            
            if near_vwap and ema_recross and rsi_ok:
                side = 'long'
                entry_price = vwap_lower
                stop_price = self._find_last_swing_low(df, current_idx) - (self.sl_atr_x * atr)
                
                tp_levels = [(entry_price + (self.tp1_atr_x * atr), 1.0)]
                
                logger.info(f"🚀 TREND SIGNAL | LONG @ ${entry_price:.4f} | SL @ ${stop_price:.4f}")
                
                return TradeSignal(
                    strategy='Trend',
                    side=side,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    tp_levels=tp_levels,
                    confidence=0.70,
                    reason="Bullish trend pullback to VWAP with EMA recross",
                    metadata={'ema_200': ema_200, 'rsi': rsi}
                )
        
        # Check for SHORT signal
        elif bearish_bias:
            # Pullback to VWAP or VWAP+1σ
            near_vwap = abs(price - vwap) / price < 0.01 or price >= vwap_upper * 0.99
            
            # EMA 9/21 recross (9 crosses below 21)
            if current_idx > -len(df):
                prev_bar = df.iloc[current_idx - 1]
                ema_9_prev = prev_bar.get('ema_9', 0)
                ema_21_prev = prev_bar.get('ema_21', 0)
                ema_recross = (ema_9_prev >= ema_21_prev) and (ema_9 < ema_21)
            else:
                ema_recross = False
            
            # RSI < 50
            rsi_ok = rsi < self.rsi_bear_threshold
            
            if near_vwap and ema_recross and rsi_ok:
                side = 'short'
                entry_price = vwap_upper
                stop_price = self._find_last_swing_high(df, current_idx) + (self.sl_atr_x * atr)
                
                tp_levels = [(entry_price - (self.tp1_atr_x * atr), 1.0)]
                
                logger.info(f"🚀 TREND SIGNAL | SHORT @ ${entry_price:.4f} | SL @ ${stop_price:.4f}")
                
                return TradeSignal(
                    strategy='Trend',
                    side=side,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    tp_levels=tp_levels,
                    confidence=0.70,
                    reason="Bearish trend pullback to VWAP with EMA recross",
                    metadata={'ema_200': ema_200, 'rsi': rsi}
                )
        
        return None
    
    def _find_last_swing_low(self, df: pd.DataFrame, current_idx: int, 
                             lookback: int = 20) -> float:
        """Find last swing low (for long stop)"""
        start_idx = max(current_idx - lookback, -len(df))
        lows = df['low'].iloc[start_idx:current_idx + 1]
        return lows.min() if len(lows) > 0 else df['low'].iloc[current_idx]
    
    def _find_last_swing_high(self, df: pd.DataFrame, current_idx: int, 
                              lookback: int = 20) -> float:
        """Find last swing high (for short stop)"""
        start_idx = max(current_idx - lookback, -len(df))
        highs = df['high'].iloc[start_idx:current_idx + 1]
        return highs.max() if len(highs) > 0 else df['high'].iloc[current_idx]

