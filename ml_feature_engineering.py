"""
Machine Learning Feature Engineering for Trading
Calculates 50+ technical indicators as features for LightGBM models.
"""

import pandas as pd
import numpy as np
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Add return features."""
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_5'] = df['close'].pct_change(5)
    df['return_10'] = df['close'].pct_change(10)
    df['return_15'] = df['close'].pct_change(15)
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    return df

def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add price-based features."""
    df['hl_spread'] = (df['high'] - df['low']) / df['close']
    df['co_spread'] = (df['close'] - df['open']) / df['open']
    df['price_volatility_5'] = df['close'].pct_change().rolling(5).std()
    df['price_volatility_10'] = df['close'].pct_change().rolling(10).std()
    df['price_volatility_20'] = df['close'].pct_change().rolling(20).std()
    return df

def add_rsi(df: pd.DataFrame, periods: List[int] = [14, 21]) -> pd.DataFrame:
    """Add RSI indicators."""
    for period in periods:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df[f'rsi_{period}'] = 100 - (100 / (1 + rs))
    return df

def add_stoch_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Stochastic RSI."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
    df['stoch_rsi'] = stoch_rsi
    return df

def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Add MACD indicators."""
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=signal).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    return df

def add_ema(df: pd.DataFrame, periods: List[int] = [9, 21, 50]) -> pd.DataFrame:
    """Add EMA indicators."""
    for period in periods:
        df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
        df[f'ema_{period}_distance'] = (df['close'] - df[f'ema_{period}']) / df[f'ema_{period}']
    return df

def add_sma(df: pd.DataFrame, periods: List[int] = [20, 50, 200]) -> pd.DataFrame:
    """Add SMA indicators."""
    for period in periods:
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
        df[f'sma_{period}_distance'] = (df['close'] - df[f'sma_{period}']) / df[f'sma_{period}']
    return df

def add_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Add Bollinger Bands."""
    sma = df['close'].rolling(period).mean()
    rolling_std = df['close'].rolling(period).std()
    df['bb_upper'] = sma + (rolling_std * std)
    df['bb_lower'] = sma - (rolling_std * std)
    df['bb_middle'] = sma
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    return df

def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Average True Range."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(period).mean()
    df['atr_pct'] = df['atr'] / df['close']
    return df

def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ADX (trend strength)."""
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(period).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    return df

def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add volume-based features."""
    df['volume_ma_5'] = df['volume'].rolling(5).mean()
    df['volume_ma_10'] = df['volume'].rolling(10).mean()
    df['volume_ma_20'] = df['volume'].rolling(20).mean()
    df['volume_ratio_5'] = df['volume'] / df['volume_ma_5']
    df['volume_ratio_10'] = df['volume'] / df['volume_ma_10']
    df['volume_ratio_20'] = df['volume'] / df['volume_ma_20']
    return df

def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    """Add On-Balance Volume."""
    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv'] = obv
    df['obv_ma_10'] = obv.rolling(10).mean()
    df['obv_ratio'] = obv / df['obv_ma_10']
    return df

def add_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Money Flow Index."""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    
    positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0).rolling(period).sum()
    negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0).rolling(period).sum()
    
    mfi_ratio = positive_flow / negative_flow
    df['mfi'] = 100 - (100 / (1 + mfi_ratio))
    return df

def add_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Williams %R."""
    highest_high = df['high'].rolling(period).max()
    lowest_low = df['low'].rolling(period).min()
    df['williams_r'] = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    return df

def add_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Add Commodity Channel Index."""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    sma = typical_price.rolling(period).mean()
    mad = typical_price.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (typical_price - sma) / (0.015 * mad)
    return df

def add_roc(df: pd.DataFrame, periods: List[int] = [5, 10, 20]) -> pd.DataFrame:
    """Add Rate of Change."""
    for period in periods:
        df[f'roc_{period}'] = ((df['close'] - df['close'].shift(period)) / df['close'].shift(period)) * 100
    return df

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time-based features."""
    df['hour'] = pd.to_datetime(df.index).hour
    df['day_of_week'] = pd.to_datetime(df.index).dayofweek
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    return df

def calculate_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate ALL features for ML model.
    Returns DataFrame with 50+ features.
    """
    print(f"📊 Calculating features for {len(df)} candles...")
    
    # Price features
    df = add_returns(df)
    df = add_price_features(df)
    
    # Momentum indicators
    df = add_rsi(df, periods=[14, 21])
    df = add_stoch_rsi(df)
    df = add_williams_r(df)
    df = add_cci(df)
    df = add_roc(df, periods=[5, 10, 20])
    
    # Trend indicators
    df = add_macd(df)
    df = add_ema(df, periods=[9, 21, 50])
    df = add_sma(df, periods=[20, 50, 200])
    df = add_adx(df)
    
    # Volatility indicators
    df = add_bollinger_bands(df)
    df = add_atr(df)
    
    # Volume indicators
    df = add_volume_features(df)
    df = add_obv(df)
    df = add_mfi(df)
    
    # Time features
    df = add_time_features(df)
    
    # Drop NaN values
    initial_len = len(df)
    df = df.dropna()
    dropped = initial_len - len(df)
    
    print(f"✅ Calculated {len([c for c in df.columns if c not in ['open', 'high', 'low', 'close', 'volume']])} features")
    print(f"⚠️ Dropped {dropped} rows with NaN values")
    
    return df

def get_feature_list() -> List[str]:
    """Return list of all feature names (excluding OHLCV)."""
    features = [
        # Returns
        'return_1', 'return_3', 'return_5', 'return_10', 'return_15', 'log_return',
        # Price
        'hl_spread', 'co_spread', 'price_volatility_5', 'price_volatility_10', 'price_volatility_20',
        # RSI
        'rsi_14', 'rsi_21', 'stoch_rsi',
        # MACD
        'macd', 'macd_signal', 'macd_hist',
        # EMA
        'ema_9', 'ema_9_distance', 'ema_21', 'ema_21_distance', 'ema_50', 'ema_50_distance',
        # SMA
        'sma_20', 'sma_20_distance', 'sma_50', 'sma_50_distance', 'sma_200', 'sma_200_distance',
        # Bollinger Bands
        'bb_upper', 'bb_lower', 'bb_middle', 'bb_width', 'bb_pct',
        # ATR
        'atr', 'atr_pct',
        # ADX
        'adx', 'plus_di', 'minus_di',
        # Volume
        'volume_ma_5', 'volume_ma_10', 'volume_ma_20', 
        'volume_ratio_5', 'volume_ratio_10', 'volume_ratio_20',
        # OBV
        'obv', 'obv_ma_10', 'obv_ratio',
        # MFI
        'mfi',
        # Williams %R
        'williams_r',
        # CCI
        'cci',
        # ROC
        'roc_5', 'roc_10', 'roc_20',
        # Time
        'hour', 'day_of_week', 'hour_sin', 'hour_cos'
    ]
    return features


if __name__ == "__main__":
    # Test feature engineering
    import pickle
    from pathlib import Path
    
    # Load sample data
    cache_dir = Path("backtest_data")
    cache_file = list(cache_dir.glob("BTCUSDT_*.pkl"))[0]
    
    with open(cache_file, 'rb') as f:
        df = pickle.load(f)
    
    print(f"Original data: {len(df)} rows, {len(df.columns)} columns")
    print(f"Columns: {list(df.columns)}")
    
    # Calculate features
    df_with_features = calculate_all_features(df.copy())
    
    print(f"\nWith features: {len(df_with_features)} rows, {len(df_with_features.columns)} columns")
    print(f"\nFeature columns:")
    for col in sorted(df_with_features.columns):
        if col not in ['open', 'high', 'low', 'close', 'volume']:
            print(f"  - {col}")
    
    print(f"\n✅ Feature engineering test complete!")
    print(f"📊 Ready for LightGBM training!")

