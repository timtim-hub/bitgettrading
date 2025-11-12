"""
Institutional Strategy Indicators
All indicators for LSVR, VWAP-MR, and Trend strategies
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Tuple, Optional, Dict
from dataclasses import dataclass


@dataclass
class VWAPBands:
    """VWAP with ±1σ bands"""
    vwap: float
    upper_band: float  # VWAP + 1σ
    lower_band: float  # VWAP - 1σ
    sigma: float


@dataclass
class Levels:
    """Key price levels"""
    pdh: Optional[float]  # Prior Day High
    pdl: Optional[float]  # Prior Day Low
    asia_high: Optional[float]  # Asia session high
    asia_low: Optional[float]  # Asia session low


class InstitutionalIndicators:
    """Calculate all indicators for institutional strategies"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.ind_config = config.get('indicators', {})
        
    def calculate_vwap_bands(self, df: pd.DataFrame, reset_utc: str = "00:00") -> pd.Series:
        """
        Calculate VWAP with daily reset at 00:00 UTC and ±1σ bands
        
        Returns:
            DataFrame with vwap, vwap_upper, vwap_lower, vwap_sigma columns
        """
        df = df.copy()
        
        # Ensure we have a datetime index
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            df['datetime'] = df.index
        else:
            df['datetime'] = df.index
        
        # Extract date for grouping
        df['date'] = df['datetime'].dt.date
        
        # Calculate typical price
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['tp_volume'] = df['typical_price'] * df['volume']
        
        # Calculate VWAP per day
        vwap_values = []
        sigma_values = []
        
        for date, group in df.groupby('date'):
            cum_tp_vol = group['tp_volume'].cumsum()
            cum_vol = group['volume'].cumsum()
            vwap = cum_tp_vol / cum_vol
            
            # Calculate standard deviation
            squared_diff = (group['typical_price'] - vwap) ** 2
            variance = (squared_diff * group['volume']).cumsum() / cum_vol
            sigma = np.sqrt(variance)
            
            vwap_values.extend(vwap.values)
            sigma_values.extend(sigma.values)
        
        df['vwap'] = vwap_values
        df['vwap_sigma'] = sigma_values
        df['vwap_upper'] = df['vwap'] + df['vwap_sigma']
        df['vwap_lower'] = df['vwap'] - df['vwap_sigma']
        
        # Calculate VWAP slope (change over last 20 bars in sigma units)
        df['vwap_slope_sigma'] = (df['vwap'].diff(20) / df['vwap_sigma']).fillna(0)
        
        return df[['vwap', 'vwap_upper', 'vwap_lower', 'vwap_sigma', 'vwap_slope_sigma']]
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: float = 2.0, 
                                   lookback: int = 120) -> pd.DataFrame:
        """
        Calculate Bollinger Bands and BB-width percentile
        
        Returns:
            DataFrame with bb_upper, bb_middle, bb_lower, bb_width, bb_width_pct columns
        """
        df = df.copy()
        
        # Calculate BB
        df['bb_middle'] = df['close'].rolling(period).mean()
        std_dev = df['close'].rolling(period).std()
        df['bb_upper'] = df['bb_middle'] + (std * std_dev)
        df['bb_lower'] = df['bb_middle'] - (std * std_dev)
        
        # Calculate BB width
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # Calculate BB width percentile over lookback period
        df['bb_width_pct'] = df['bb_width'].rolling(lookback).apply(
            lambda x: (x.iloc[-1] <= x).sum() / len(x) * 100 if len(x) > 0 else 50,
            raw=False
        )
        
        return df[['bb_upper', 'bb_middle', 'bb_lower', 'bb_width', 'bb_width_pct']]
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate ADX (Average Directional Index)"""
        df = df.copy()
        
        # Calculate True Range
        df['h_l'] = df['high'] - df['low']
        df['h_pc'] = abs(df['high'] - df['close'].shift(1))
        df['l_pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)
        
        # Calculate Directional Movement
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
        
        # Smooth with Wilder's method
        df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
        df['plus_di'] = 100 * (df['plus_dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'])
        df['minus_di'] = 100 * (df['minus_dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'])
        
        # Calculate DX and ADX
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['adx'] = df['dx'].ewm(alpha=1/period, adjust=False).mean()
        
        return df[['adx', 'plus_di', 'minus_di', 'atr']]
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI (Relative Strength Index)"""
        df = df.copy()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_stoch_rsi(self, df: pd.DataFrame, k_period: int = 3, d_period: int = 3,
                            rsi_period: int = 14, stoch_period: int = 14) -> pd.DataFrame:
        """
        Calculate Stochastic RSI
        
        Returns:
            DataFrame with stoch_rsi_k and stoch_rsi_d columns
        """
        df = df.copy()
        
        # Calculate RSI first
        rsi = self.calculate_rsi(df, rsi_period)
        
        # Calculate Stochastic of RSI
        rsi_min = rsi.rolling(stoch_period).min()
        rsi_max = rsi.rolling(stoch_period).max()
        
        stoch_rsi = 100 * (rsi - rsi_min) / (rsi_max - rsi_min)
        
        # Calculate %K and %D
        stoch_rsi_k = stoch_rsi.rolling(k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(d_period).mean()
        
        result = pd.DataFrame({
            'stoch_rsi_k': stoch_rsi_k,
            'stoch_rsi_d': stoch_rsi_d
        })
        
        return result
    
    def calculate_ema(self, df: pd.DataFrame, periods: list) -> pd.DataFrame:
        """Calculate multiple EMAs"""
        result = pd.DataFrame(index=df.index)
        
        for period in periods:
            result[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
        return result
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR (Average True Range)"""
        df = df.copy()
        
        df['h_l'] = df['high'] - df['low']
        df['h_pc'] = abs(df['high'] - df['close'].shift(1))
        df['l_pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)
        
        atr = df['tr'].ewm(alpha=1/period, adjust=False).mean()
        
        return atr
    
    def calculate_volume_ma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Volume Moving Average"""
        return df['volume'].rolling(period).mean()
    
    def calculate_levels(self, df: pd.DataFrame, current_time: datetime) -> Levels:
        """
        Calculate key price levels: PDH/PDL, Asia H/L
        
        Args:
            df: DataFrame with OHLCV data
            current_time: Current time in UTC
        """
        df = df.copy()
        
        # Ensure datetime index
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            df['datetime'] = df.index
        else:
            df['datetime'] = df.index
        
        df['date'] = df['datetime'].dt.date
        df['hour'] = df['datetime'].dt.hour
        
        # Get prior day
        current_date = current_time.date()
        df_sorted = df.sort_values('datetime')
        
        # Prior Day High/Low
        prior_day_data = df_sorted[df_sorted['date'] < current_date]
        if len(prior_day_data) > 0:
            last_full_day = prior_day_data['date'].max()
            pdh = prior_day_data[prior_day_data['date'] == last_full_day]['high'].max()
            pdl = prior_day_data[prior_day_data['date'] == last_full_day]['low'].min()
        else:
            pdh, pdl = None, None
        
        # Asia session high/low (00:00-08:00 UTC for current day)
        asia_data = df_sorted[
            (df_sorted['date'] == current_date) &
            (df_sorted['hour'] >= 0) &
            (df_sorted['hour'] < 8)
        ]
        
        if len(asia_data) > 0:
            asia_high = asia_data['high'].max()
            asia_low = asia_data['low'].min()
        else:
            asia_high, asia_low = None, None
        
        return Levels(
            pdh=pdh,
            pdl=pdl,
            asia_high=asia_high,
            asia_low=asia_low
        )
    
    def calculate_supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        """
        Calculate Supertrend indicator for trailing stops
        
        Returns:
            DataFrame with supertrend and supertrend_direction columns
        """
        df = df.copy()
        
        # Calculate ATR
        atr = self.calculate_atr(df, period)
        
        # Calculate basic upper and lower bands
        hl_avg = (df['high'] + df['low']) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        # Initialize
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        
        for i in range(len(df)):
            if i == 0:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
                continue
            
            # Calculate final bands
            if df['close'].iloc[i-1] <= supertrend.iloc[i-1]:
                # Downtrend
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1]) if upper_band.iloc[i] < supertrend.iloc[i-1] else upper_band.iloc[i]
                direction.iloc[i] = -1 if df['close'].iloc[i] <= supertrend.iloc[i] else 1
            else:
                # Uptrend
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1]) if lower_band.iloc[i] > supertrend.iloc[i-1] else lower_band.iloc[i]
                direction.iloc[i] = 1 if df['close'].iloc[i] >= supertrend.iloc[i] else -1
        
        result = pd.DataFrame({
            'supertrend': supertrend,
            'supertrend_direction': direction
        })
        
        return result
    
    def calculate_all_indicators(self, df: pd.DataFrame, timeframe: str = '5m') -> pd.DataFrame:
        """
        Calculate all indicators for a given timeframe
        
        Args:
            df: DataFrame with OHLCV data
            timeframe: '1m', '3m', '5m', or '15m'
        
        Returns:
            DataFrame with all indicators
        """
        result = df.copy()
        
        # VWAP and bands (all timeframes)
        vwap_bands = self.calculate_vwap_bands(result)
        result = pd.concat([result, vwap_bands], axis=1)
        
        # Bollinger Bands (5m)
        if timeframe in ['5m', '15m']:
            bb = self.calculate_bollinger_bands(result)
            result = pd.concat([result, bb], axis=1)
        
        # ADX (15m)
        if timeframe == '15m':
            adx_data = self.calculate_adx(result)
            result = pd.concat([result, adx_data], axis=1)
        
        # RSI (5m and short timeframes)
        if timeframe in ['1m', '3m', '5m']:
            result['rsi'] = self.calculate_rsi(result)
        
        # Stochastic RSI (1-3m)
        if timeframe in ['1m', '3m']:
            stoch_rsi = self.calculate_stoch_rsi(result, k_period=3, d_period=3, rsi_period=14, stoch_period=14)
            result = pd.concat([result, stoch_rsi], axis=1)
        
        # ATR (5m)
        if timeframe == '5m':
            result['atr'] = self.calculate_atr(result)
        
        # Volume MA (5m)
        if timeframe == '5m':
            result['volume_ma'] = self.calculate_volume_ma(result)
            result['volume_ratio'] = result['volume'] / result['volume_ma']
        
        # EMAs (15m for trend)
        if timeframe == '15m':
            emas = self.calculate_ema(result, [9, 21, 50, 200])
            result = pd.concat([result, emas], axis=1)
        
        # Supertrend (for trailing)
        if timeframe == '5m':
            supertrend = self.calculate_supertrend(result, period=10, multiplier=3.0)
            result = pd.concat([result, supertrend], axis=1)
        
        return result

