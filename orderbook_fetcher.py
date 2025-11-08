"""
Order Book Fetcher and Simulator

Since historical order book data is not available, this module simulates
order book metrics from OHLCV data using volume distribution analysis.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple


class OrderBookSimulator:
    """
    Simulate order book metrics from OHLCV data.
    
    Uses volume profile and price action to estimate:
    - Bid/Ask imbalance
    - Spread
    - Depth levels
    - Order flow direction
    """
    
    def __init__(self):
        """Initialize the order book simulator."""
        pass
    
    def calculate_bid_ask_imbalance(
        self,
        df: pd.DataFrame,
        window: int = 5
    ) -> pd.Series:
        """
        Calculate bid/ask imbalance from volume and price action.
        
        Logic:
        - When price rises with high volume -> buying pressure (ask side eating bids)
        - When price falls with high volume -> selling pressure (bid side eating asks)
        - Imbalance = ratio of buy volume to sell volume
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window for calculation
            
        Returns:
            Series with bid/ask imbalance ratio (>1 = more buying, <1 = more selling)
        """
        # Calculate price change
        price_change = df['close'].diff()
        
        # Classify volume as buy or sell based on price direction
        buy_volume = np.where(price_change > 0, df['volume'], 0)
        sell_volume = np.where(price_change < 0, df['volume'], 0)
        
        # Rolling sum
        buy_vol_sum = pd.Series(buy_volume).rolling(window).sum()
        sell_vol_sum = pd.Series(sell_volume).rolling(window).sum()
        
        # Calculate imbalance ratio (avoid division by zero)
        imbalance = buy_vol_sum / (sell_vol_sum + 1e-10)
        
        # Normalize to 0-2 range (1 = balanced)
        imbalance = imbalance.clip(0, 2)
        
        return imbalance
    
    def calculate_spread_estimate(
        self,
        df: pd.DataFrame,
        window: int = 10
    ) -> pd.Series:
        """
        Estimate bid-ask spread from high-low range.
        
        Logic:
        - Spread correlates with volatility
        - Use percentage of high-low range as proxy
        - Normalize by average price
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window
            
        Returns:
            Series with estimated spread percentage
        """
        # Calculate high-low range
        hl_range = (df['high'] - df['low']) / df['close']
        
        # Rolling average
        avg_spread = hl_range.rolling(window).mean()
        
        # Spread is typically 10-30% of hl_range
        estimated_spread = avg_spread * 0.20
        
        return estimated_spread
    
    def calculate_depth_imbalance(
        self,
        df: pd.DataFrame,
        window: int = 20
    ) -> pd.Series:
        """
        Calculate order book depth imbalance.
        
        Logic:
        - Strong uptrend = more bids (support) than asks (resistance)
        - Strong downtrend = more asks than bids
        - Use trend strength + volume as proxy
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window
            
        Returns:
            Series with depth imbalance (-1 to 1, positive = more bids)
        """
        # Calculate trend strength (EMA crossover)
        ema_short = df['close'].ewm(span=5).mean()
        ema_long = df['close'].ewm(span=20).mean()
        
        trend_strength = (ema_short - ema_long) / ema_long
        
        # Multiply by volume factor (high volume = stronger signal)
        volume_factor = df['volume'] / df['volume'].rolling(window).mean()
        volume_factor = volume_factor.clip(0.5, 2.0)
        
        depth_imbalance = trend_strength * volume_factor
        
        # Normalize to -1 to 1
        depth_imbalance = depth_imbalance.clip(-1, 1)
        
        return depth_imbalance
    
    def calculate_order_flow(
        self,
        df: pd.DataFrame,
        window: int = 10
    ) -> pd.Series:
        """
        Calculate cumulative order flow direction.
        
        Logic:
        - Sum of (price_change * volume) over window
        - Positive = net buying, negative = net selling
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window
            
        Returns:
            Series with cumulative order flow
        """
        # Price change in percentage
        price_change_pct = df['close'].pct_change()
        
        # Order flow = price_change * volume
        order_flow = price_change_pct * df['volume']
        
        # Rolling sum
        cumulative_flow = order_flow.rolling(window).sum()
        
        # Normalize by rolling volume
        total_volume = df['volume'].rolling(window).sum()
        normalized_flow = cumulative_flow / (total_volume + 1e-10)
        
        return normalized_flow
    
    def calculate_liquidity_score(
        self,
        df: pd.DataFrame,
        window: int = 20
    ) -> pd.Series:
        """
        Calculate liquidity score (0-100).
        
        Logic:
        - High volume + tight spread = high liquidity
        - Low volume + wide spread = low liquidity
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window
            
        Returns:
            Series with liquidity score (0-100)
        """
        # Volume score (relative to average)
        avg_volume = df['volume'].rolling(window).mean()
        volume_score = (df['volume'] / (avg_volume + 1e-10)).clip(0, 2)
        
        # Spread score (tighter = better)
        spread_est = self.calculate_spread_estimate(df, window)
        spread_score = (1 / (spread_est + 0.001)).clip(0, 2)
        
        # Combined liquidity score
        liquidity = (volume_score + spread_score) / 2
        
        # Scale to 0-100
        liquidity_score = (liquidity / 2 * 100).clip(0, 100)
        
        return liquidity_score
    
    def calculate_support_resistance_strength(
        self,
        df: pd.DataFrame,
        window: int = 50
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate support and resistance strength based on volume clusters.
        
        Logic:
        - High volume at price levels = strong support/resistance
        - Current price vs. these levels indicates strength
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window
            
        Returns:
            Tuple of (support_strength, resistance_strength) Series
        """
        support_strength = []
        resistance_strength = []
        
        for i in range(len(df)):
            if i < window:
                support_strength.append(0.5)
                resistance_strength.append(0.5)
                continue
            
            # Get window of data
            window_df = df.iloc[max(0, i-window):i]
            current_price = df.iloc[i]['close']
            
            # Find support (prices below current)
            support_prices = window_df[window_df['close'] < current_price]
            if not support_prices.empty:
                # Weight by volume and proximity
                distances = (current_price - support_prices['close']) / current_price
                weights = support_prices['volume'] / (distances + 0.01)
                support_str = weights.sum() / (support_prices['volume'].sum() + 1e-10)
            else:
                support_str = 0.0
            
            # Find resistance (prices above current)
            resistance_prices = window_df[window_df['close'] > current_price]
            if not resistance_prices.empty:
                # Weight by volume and proximity
                distances = (resistance_prices['close'] - current_price) / current_price
                weights = resistance_prices['volume'] / (distances + 0.01)
                resistance_str = weights.sum() / (resistance_prices['volume'].sum() + 1e-10)
            else:
                resistance_str = 0.0
            
            # Normalize
            support_strength.append(min(support_str, 1.0))
            resistance_strength.append(min(resistance_str, 1.0))
        
        return pd.Series(support_strength), pd.Series(resistance_strength)
    
    def add_orderbook_features(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Add all simulated order book features to DataFrame.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with additional order book features
        """
        df = df.copy()
        
        print("  📊 Calculating order book features...")
        
        # Bid/ask imbalance
        df['ob_bid_ask_imbalance'] = self.calculate_bid_ask_imbalance(df, window=5)
        
        # Spread estimate
        df['ob_spread_pct'] = self.calculate_spread_estimate(df, window=10)
        
        # Depth imbalance
        df['ob_depth_imbalance'] = self.calculate_depth_imbalance(df, window=20)
        
        # Order flow
        df['ob_order_flow'] = self.calculate_order_flow(df, window=10)
        df['ob_order_flow_long'] = self.calculate_order_flow(df, window=30)
        
        # Liquidity score
        df['ob_liquidity_score'] = self.calculate_liquidity_score(df, window=20)
        
        # Support/resistance strength
        df['ob_support_strength'], df['ob_resistance_strength'] = \
            self.calculate_support_resistance_strength(df, window=50)
        
        # Combined signals
        df['ob_bullish_signal'] = (
            (df['ob_bid_ask_imbalance'] > 1.2) &  # More buying
            (df['ob_depth_imbalance'] > 0.3) &     # Bid depth > ask depth
            (df['ob_order_flow'] > 0)              # Positive flow
        ).astype(int)
        
        df['ob_bearish_signal'] = (
            (df['ob_bid_ask_imbalance'] < 0.8) &   # More selling
            (df['ob_depth_imbalance'] < -0.3) &    # Ask depth > bid depth
            (df['ob_order_flow'] < 0)              # Negative flow
        ).astype(int)
        
        # Fill NaN with neutral values
        df = df.fillna({
            'ob_bid_ask_imbalance': 1.0,
            'ob_spread_pct': 0.001,
            'ob_depth_imbalance': 0.0,
            'ob_order_flow': 0.0,
            'ob_order_flow_long': 0.0,
            'ob_liquidity_score': 50.0,
            'ob_support_strength': 0.5,
            'ob_resistance_strength': 0.5,
            'ob_bullish_signal': 0,
            'ob_bearish_signal': 0,
        })
        
        print(f"  ✅ Added {10} order book features")
        
        return df


def test_orderbook_simulator():
    """Test the order book simulator with sample data."""
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=200, freq='1H')
    
    # Simulate price walk with trend
    price = 100
    prices = []
    volumes = []
    
    for i in range(200):
        # Add trend + noise
        price += np.random.normal(0.1, 1.0)
        prices.append(price)
        volumes.append(np.random.uniform(1000, 5000))
    
    df = pd.DataFrame({
        'timestamp': [int(d.timestamp() * 1000) for d in dates],
        'close': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'open': prices,
        'volume': volumes,
    })
    
    # Add order book features
    simulator = OrderBookSimulator()
    df_with_ob = simulator.add_orderbook_features(df)
    
    print("\n" + "="*80)
    print("ORDER BOOK SIMULATOR TEST")
    print("="*80)
    print(f"\nDataFrame shape: {df_with_ob.shape}")
    print(f"\nOrder book features added:")
    ob_cols = [col for col in df_with_ob.columns if col.startswith('ob_')]
    for col in ob_cols:
        print(f"  - {col}: min={df_with_ob[col].min():.3f}, max={df_with_ob[col].max():.3f}, mean={df_with_ob[col].mean():.3f}")
    
    print("\n" + "="*80)
    print("✅ Order book simulator test complete!")
    print("="*80)


if __name__ == "__main__":
    test_orderbook_simulator()

