"""
Universe Filtering and Regime Classification
Implements bucket gates and regime detection for institutional strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Market data for universe filtering"""
    symbol: str
    spread_bps: float
    bid_depth_usd: float
    ask_depth_usd: float
    quote_vol_24h: float
    last_price: float


@dataclass
class RegimeData:
    """Regime classification result"""
    regime: str  # 'Range' or 'Trend'
    adx: float
    bb_width_pct: float
    vwap_slope_sigma: float
    bucket: str  # 'majors', 'midcaps', or 'micros'


class UniverseFilter:
    """Filter symbols based on bucket-specific gates"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.buckets = config.get('buckets', {})
        
        # Define major symbols
        self.major_symbols = self.buckets.get('majors', {}).get('symbols', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
        
        logger.info(f"✅ UniverseFilter initialized with {len(self.buckets)} buckets")
    
    def get_bucket(self, symbol: str) -> str:
        """Determine which bucket a symbol belongs to"""
        if symbol in self.major_symbols:
            return 'majors'
        # For now, we'll use volume to classify mid-caps vs micros
        # This will be updated with actual market data in real-time
        return 'midcaps'  # Default
    
    def update_bucket_from_volume(self, symbol: str, quote_vol_24h: float) -> str:
        """Update bucket classification based on 24h volume"""
        if symbol in self.major_symbols:
            return 'majors'
        
        # Use volume thresholds to distinguish mid-caps from micros
        midcap_vol = self.buckets.get('midcaps', {}).get('min_quote_vol_24h', 80_000_000)
        
        if quote_vol_24h >= midcap_vol:
            return 'midcaps'
        else:
            return 'micros'
    
    def passes_gates(self, market_data: MarketData, bucket: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if symbol passes bucket-specific gates
        
        Returns:
            (passes, reason) tuple
        """
        if bucket is None:
            bucket = self.get_bucket(market_data.symbol)
        
        bucket_config = self.buckets.get(bucket, {})
        
        # Check spread
        max_spread_bps = bucket_config.get('spread_bps_cap', 100)
        if market_data.spread_bps > max_spread_bps:
            return False, f"spread {market_data.spread_bps:.1f} bps > {max_spread_bps} bps cap"
        
        # Check TOB depth (each side)
        min_depth = bucket_config.get('min_depth_usd', 0)
        if market_data.bid_depth_usd < min_depth:
            return False, f"bid depth ${market_data.bid_depth_usd:.0f} < ${min_depth:.0f} min"
        if market_data.ask_depth_usd < min_depth:
            return False, f"ask depth ${market_data.ask_depth_usd:.0f} < ${min_depth:.0f} min"
        
        # Check 24h quote volume
        min_vol = bucket_config.get('min_quote_vol_24h', 0)
        if market_data.quote_vol_24h < min_vol:
            return False, f"24h volume ${market_data.quote_vol_24h:.0f} < ${min_vol:.0f} min"
        
        return True, "passed"
    
    def filter_universe(self, market_data_list: List[MarketData]) -> Dict[str, MarketData]:
        """
        Filter entire universe and return symbols that pass gates
        
        Returns:
            Dict mapping symbol to MarketData for symbols that pass
        """
        passed = {}
        failed_counts = {}
        
        for data in market_data_list:
            bucket = self.update_bucket_from_volume(data.symbol, data.quote_vol_24h)
            passes, reason = self.passes_gates(data, bucket)
            
            if passes:
                passed[data.symbol] = data
                logger.debug(f"✅ {data.symbol} ({bucket}): PASSED gates")
            else:
                failed_counts[reason] = failed_counts.get(reason, 0) + 1
                logger.debug(f"❌ {data.symbol} ({bucket}): FAILED - {reason}")
        
        logger.info(
            f"🔍 Universe filter: {len(passed)}/{len(market_data_list)} symbols passed | "
            f"Failed: {dict(failed_counts)}"
        )
        
        return passed


class RegimeClassifier:
    """Classify market regime (Range vs Trend) based on bucket-specific criteria"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.regime_config = config.get('regime', {})
        
        logger.info("✅ RegimeClassifier initialized")
    
    def classify(self, bucket: str, adx: float, bb_width_pct: float, 
                 vwap_slope_sigma: float) -> RegimeData:
        """
        Classify regime for a symbol
        
        Range if ALL true (bucket-specific):
        - ADX(14) < threshold (20/22/25 for majors/mids/micros)
        - BB-width percentile ≤ threshold (40/50/60%)
        - VWAP slope within [-0.05σ, +0.05σ]
        
        Else -> Trend
        
        Returns:
            RegimeData with classification
        """
        bucket_config = self.regime_config.get(bucket, self.regime_config.get('majors', {}))
        
        # Get thresholds
        adx_threshold = bucket_config.get('adx15m_lt', 20)
        bb_width_threshold = bucket_config.get('bb_width_pct_5m_le', 40)
        vwap_slope_range = bucket_config.get('vwap_slope_sigma_range', [-0.05, 0.05])
        
        # Check all conditions for Range
        is_range = (
            adx < adx_threshold and
            bb_width_pct <= bb_width_threshold and
            vwap_slope_range[0] <= vwap_slope_sigma <= vwap_slope_range[1]
        )
        
        regime = 'Range' if is_range else 'Trend'
        
        logger.debug(
            f"📊 Regime={regime} ({bucket}) | "
            f"ADX={adx:.1f} (< {adx_threshold}? {adx < adx_threshold}) | "
            f"BB-width%={bb_width_pct:.1f} (<= {bb_width_threshold}? {bb_width_pct <= bb_width_threshold}) | "
            f"VWAP-slope/σ={vwap_slope_sigma:.3f} (in {vwap_slope_range}? {vwap_slope_range[0] <= vwap_slope_sigma <= vwap_slope_range[1]})"
        )
        
        return RegimeData(
            regime=regime,
            adx=adx,
            bb_width_pct=bb_width_pct,
            vwap_slope_sigma=vwap_slope_sigma,
            bucket=bucket
        )
    
    def classify_from_indicators(self, indicators: pd.DataFrame, bucket: str, 
                                  current_idx: int = -1) -> RegimeData:
        """
        Classify regime from indicator DataFrame
        
        Args:
            indicators: DataFrame with adx, bb_width_pct, vwap_slope_sigma columns
            bucket: Symbol bucket (majors/midcaps/micros)
            current_idx: Index to use for classification (default: -1 for latest)
        
        Returns:
            RegimeData
        """
        adx = indicators['adx'].iloc[current_idx] if 'adx' in indicators.columns else 30
        bb_width_pct = indicators['bb_width_pct'].iloc[current_idx] if 'bb_width_pct' in indicators.columns else 50
        vwap_slope_sigma = indicators['vwap_slope_sigma'].iloc[current_idx] if 'vwap_slope_sigma' in indicators.columns else 0
        
        return self.classify(bucket, adx, bb_width_pct, vwap_slope_sigma)


def calculate_spread_bps(bid: float, ask: float) -> float:
    """Calculate spread in basis points"""
    if bid <= 0:
        return 999.0
    return ((ask - bid) / bid) * 10000


def calculate_depth_usd(depth: float, price: float) -> float:
    """Calculate depth in USD"""
    return depth * price


def estimate_24h_volume_from_candles(df: pd.DataFrame) -> float:
    """
    Estimate 24h quote volume from candle data
    
    Args:
        df: DataFrame with 'volume' and 'close' columns for last 24h
    
    Returns:
        Estimated 24h quote volume in USD
    """
    if len(df) == 0:
        return 0.0
    
    # Use last 24 hours of data
    recent_df = df.tail(288) if len(df) > 288 else df  # 288 = 24h * 12 (5min candles)
    
    # Calculate quote volume (volume * price)
    quote_vol = (recent_df['volume'] * recent_df['close']).sum()
    
    return float(quote_vol)

