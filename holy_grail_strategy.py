"""
Holy Grail Strategy Integration Module

Implements the ML_ADX_Trend strategy (strategy_046.json) for live trading.
Uses ADX as primary signal with SMA distance confirmation.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


class HolyGrailStrategy:
    """
    Holy Grail Strategy: ML_ADX_Trend
    
    Strategy Parameters:
    - Entry threshold: 0.9 (high confidence)
    - Stop loss: 45% capital (0.18% price @ 25x)
    - Take profit: 22% capital (0.88% price @ 25x)
    - Trailing stop: 3.5% callback
    - Position size: 13% per position
    - Max positions: 15
    - Leverage: 25x
    """
    
    def __init__(self, strategy_file: str = "strategies/strategy_046.json"):
        """Initialize Holy Grail strategy."""
        self.strategy_file = Path(strategy_file)
        self.strategy = self._load_strategy()
        
        # Strategy parameters
        self.entry_threshold = self.strategy.get("entry_threshold", 0.9)
        self.stop_loss_pct = self.strategy.get("stop_loss_pct", 0.45)  # 45% capital
        self.take_profit_pct = self.strategy.get("take_profit_pct", 0.22)  # 22% capital
        self.trailing_callback = self.strategy.get("trailing_callback", 0.035)  # 3.5%
        self.volume_ratio = self.strategy.get("volume_ratio", 1.4)
        self.confluence_required = self.strategy.get("confluence_required", 3)
        self.position_size_pct = self.strategy.get("position_size_pct", 0.13)  # 13%
        self.leverage = self.strategy.get("leverage", 25)
        self.max_positions = self.strategy.get("max_positions", 15)
        self.min_liquidity = self.strategy.get("min_liquidity", 100000)
        
        # Load profitable tokens
        self.profitable_tokens = self._load_profitable_tokens()
        
        logger.info(
            f"✅ [HOLY GRAIL] Strategy loaded: {self.strategy.get('name', 'N/A')} | "
            f"Entry threshold: {self.entry_threshold} | "
            f"Leverage: {self.leverage}x | "
            f"Position size: {self.position_size_pct*100:.1f}% | "
            f"Max positions: {self.max_positions} | "
            f"Profitable tokens: {len(self.profitable_tokens)}"
        )
    
    def _load_strategy(self) -> Dict:
        """Load strategy configuration."""
        if not self.strategy_file.exists():
            raise FileNotFoundError(f"Strategy file not found: {self.strategy_file}")
        
        with open(self.strategy_file, 'r') as f:
            return json.load(f)
    
    def _load_profitable_tokens(self) -> List[str]:
        """Load profitable tokens with 25x leverage."""
        tokens_file = Path("holy_grail_tokens_25x.txt")
        
        if not tokens_file.exists():
            logger.warning(f"⚠️ [HOLY GRAIL] Tokens file not found: {tokens_file}")
            return []
        
        with open(tokens_file, 'r') as f:
            tokens = [line.strip() for line in f if line.strip()]
        
        logger.info(f"✅ [HOLY GRAIL] Loaded {len(tokens)} profitable tokens with 25x leverage")
        return tokens
    
    def filter_symbols(self, symbols: List[str]) -> List[str]:
        """
        Filter symbols to only profitable tokens.
        
        Args:
            symbols: List of all available symbols
            
        Returns:
            Filtered list of profitable tokens only
        """
        filtered = [s for s in symbols if s in self.profitable_tokens]
        
        logger.info(
            f"🔍 [HOLY GRAIL] Filtered {len(symbols)} symbols -> {len(filtered)} profitable tokens "
            f"({len(symbols) - len(filtered)} filtered out)"
        )
        
        return filtered
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ADX (Average Directional Index)."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        # Calculate smoothed TR and DM
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx
    
    def calculate_sma_distance(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate distance from SMA (normalized)."""
        close = df['close']
        sma = close.rolling(period).mean()
        distance = (close - sma) / sma
        return distance
    
    def calculate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        state_manager: any = None
    ) -> Tuple[str, float]:
        """
        Calculate trading signal using ADX-based strategy.
        
        Returns:
            (direction, score) where direction is "long", "short", or "neutral"
        """
        if len(df) < 30:
            return "neutral", 0.0
        
        # Calculate indicators
        adx = self.calculate_adx(df, period=14)
        sma_distance = self.calculate_sma_distance(df, period=20)
        
        if adx.isna().all() or sma_distance.isna().all():
            return "neutral", 0.0
        
        # Get latest values
        current_adx = adx.iloc[-1]
        current_sma_dist = sma_distance.iloc[-1]
        prev_adx = adx.iloc[-2] if len(adx) > 1 else current_adx
        
        # Calculate volume ratio
        current_volume = df['volume'].iloc[-1]
        volume_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1.0
        
        # Calculate returns
        returns_5 = (df['close'].iloc[-1] / df['close'].iloc[-6] - 1) if len(df) >= 6 else 0
        returns_10 = (df['close'].iloc[-1] / df['close'].iloc[-11] - 1) if len(df) >= 11 else 0
        
        # Signal calculation
        bullish_signals = 0
        bearish_signals = 0
        
        # 1. ADX strong trend (primary signal)
        if current_adx > 25:  # Strong trend
            if returns_5 > 0:
                bullish_signals += 2  # ADX is top feature, weight it more
            elif returns_5 < 0:
                bearish_signals += 2
        
        # 2. SMA distance confirmation (2nd & 3rd top features)
        if abs(current_sma_dist) > 0.01:  # >1% from SMA
            if current_sma_dist > 0 and returns_5 > 0:
                bullish_signals += 1
            elif current_sma_dist < 0 and returns_5 < 0:
                bearish_signals += 1
        
        # 3. Volume confirmation
        if volume_ratio >= self.volume_ratio:
            if returns_5 > 0:
                bullish_signals += 1
            elif returns_5 < 0:
                bearish_signals += 1
        
        # 4. Momentum confirmation
        if returns_5 > 0.005:  # >0.5%
            bullish_signals += 1
        elif returns_5 < -0.005:  # <-0.5%
            bearish_signals += 1
        
        # Determine direction and score
        if bullish_signals >= self.confluence_required:
            direction = "long"
            score = min(1.0, bullish_signals * 0.2)  # Scale to 0-1
        elif bearish_signals >= self.confluence_required:
            direction = "short"
            score = min(1.0, bearish_signals * 0.2)
        else:
            direction = "neutral"
            score = 0.0
        
        # Apply entry threshold
        if score < self.entry_threshold:
            return "neutral", score
        
        return direction, score
    
    def get_stop_loss_price(self, entry_price: float, side: str, leverage: int = None) -> float:
        """Calculate stop-loss price."""
        if leverage is None:
            leverage = self.leverage
        
        # Stop loss is 45% capital, convert to price % using leverage
        sl_price_pct = self.stop_loss_pct / leverage  # 45% ÷ 25x = 1.8% price
        
        if side == "long":
            return entry_price * (1 - sl_price_pct)
        else:  # short
            return entry_price * (1 + sl_price_pct)
    
    def get_take_profit_price(self, entry_price: float, side: str, leverage: int = None) -> float:
        """Calculate take-profit price."""
        if leverage is None:
            leverage = self.leverage
        
        # Take profit is 22% capital, convert to price % using leverage
        tp_price_pct = self.take_profit_pct / leverage  # 22% ÷ 25x = 0.88% price
        
        if side == "long":
            return entry_price * (1 + tp_price_pct)
        else:  # short
            return entry_price * (1 - tp_price_pct)
    
    def get_trailing_stop_callback(self) -> float:
        """Get trailing stop callback ratio."""
        return self.trailing_callback  # 3.5%


# Import logger at the top
try:
    from src.bitget_trading.logger import get_logger
    logger = get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

