"""
Multi-Position Backtest Engine - Support for 30-50 simultaneous positions

Major enhancements:
- Multiple simultaneous positions
- Correlation risk calculation
- Slippage modeling (volume-based)
- Position queue management
- Per-position tracking
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Try to import LightGBM for strategy 160
try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("⚠️ LightGBM not available, strategy 160 will use ADX fallback")


@dataclass
class Trade:
    """Represents a single trade."""
    entry_time: int  # timestamp in ms
    exit_time: int  # timestamp in ms
    entry_price: float
    exit_price: float
    side: str  # "long" or "short"
    size_usd: float
    leverage: int
    pnl_usd: float
    pnl_pct: float  # % of capital
    exit_reason: str  # "tp", "sl", "signal", "reversal", "end"
    slippage_cost: float = 0.0  # Cost from slippage
    
    def duration_hours(self) -> float:
        """Calculate trade duration in hours."""
        return (self.exit_time - self.entry_time) / (1000 * 3600)


@dataclass
class Position:
    """Represents an open position."""
    position_id: int
    side: str
    entry_price: float
    entry_time: int
    entry_idx: int
    size_usd: float
    peak_price: float
    leverage: int


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    strategy_id: int
    strategy_name: str
    symbol: str
    initial_capital: float
    final_capital: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[int, float]] = field(default_factory=list)  # (timestamp, equity)
    max_concurrent_positions: int = 0  # Track max positions held
    correlation_violations: int = 0  # Times correlation risk was exceeded
    total_slippage_cost: float = 0.0  # Total slippage costs
    
    def total_trades(self) -> int:
        return len(self.trades)
    
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_usd > 0)
    
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_usd < 0)
    
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return self.winning_trades() / len(self.trades)
    
    def total_pnl(self) -> float:
        return self.final_capital - self.initial_capital
    
    def roi_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.final_capital - self.initial_capital) / self.initial_capital * 100


class MultiPositionBacktestEngine:
    """
    Enhanced backtest engine supporting multiple simultaneous positions.
    
    Features:
    - 30-50 simultaneous positions
    - Correlation risk management
    - Slippage modeling based on volume
    - Position queue management
    """
    
    def __init__(self, strategy: Dict[str, Any]):
        """Initialize the backtest engine with a strategy configuration."""
        self.strategy = strategy
        self.entry_threshold = strategy["entry_threshold"]
        self.stop_loss_pct = strategy["stop_loss_pct"]  # Capital %
        self.take_profit_pct = strategy["take_profit_pct"]  # Capital %
        self.trailing_callback = strategy["trailing_callback"]
        self.volume_ratio = strategy["volume_ratio"]
        self.confluence_required = strategy["confluence_required"]
        self.position_size_pct = strategy["position_size_pct"]
        self.leverage = strategy["leverage"]
        self.max_positions = strategy["max_positions"]
        
        # Trading fees (Bitget taker fee: 0.06% per side)
        self.taker_fee_pct = 0.0006  # 0.06%
        self.fee_per_trade = self.taker_fee_pct * 2  # Entry + Exit = 0.12%
        
        # Load LightGBM model for strategy 160
        self.lgbm_model = None
        self.lgbm_features = []
        if strategy.get("id") == 160 and LIGHTGBM_AVAILABLE:
            self._load_lightgbm_model()
        
        # Slippage parameters (based on volume and volatility)
        self.high_volume_slippage = 0.0002  # 0.02% for high volume tokens
        self.low_volume_slippage = 0.0005   # 0.05% for low volume tokens
        
        # Position tracking
        self.next_position_id = 0
        
        # Correlation tracking (simplified - track long/short ratio)
        self.max_correlation_ratio = 0.8  # Max 80% in same direction
    
    def estimate_slippage(self, df: pd.DataFrame, idx: int, size_usd: float) -> float:
        """
        Estimate slippage based on volume and trade size.
        
        Logic:
        - High volume tokens: 0.02% slippage
        - Low volume tokens: 0.05% slippage
        - Larger trades: More slippage
        
        Args:
            df: DataFrame with OHLCV data
            idx: Current index
            size_usd: Trade size in USD
            
        Returns:
            Slippage percentage
        """
        if idx < 20:
            return self.high_volume_slippage
        
        # Get recent volume
        recent_volume = df['volume'].iloc[max(0, idx-20):idx].mean()
        current_volume = df['volume'].iloc[idx]
        
        # Volume ratio
        volume_ratio = current_volume / (recent_volume + 1e-10)
        
        # Base slippage
        if volume_ratio > 1.5:  # High volume
            base_slippage = self.high_volume_slippage
        else:  # Lower volume
            base_slippage = self.low_volume_slippage
        
        # Adjust for trade size (larger trades = more slippage)
        # Assuming average volume is ~$1M, adjust proportionally
        size_factor = min(size_usd / 10000, 2.0)  # Cap at 2x
        
        return base_slippage * size_factor
    
    def calculate_correlation_risk(self, positions: List[Position]) -> float:
        """
        Calculate correlation risk of current positions.
        
        Simplified approach: Check long/short ratio.
        If >80% in same direction, correlation risk is high.
        
        Args:
            positions: List of current open positions
            
        Returns:
            Correlation risk score (0-1, higher = more risky)
        """
        if not positions:
            return 0.0
        
        long_count = sum(1 for p in positions if p.side == "long")
        short_count = sum(1 for p in positions if p.side == "short")
        total = len(positions)
        
        # Calculate directional concentration
        max_directional = max(long_count, short_count)
        concentration = max_directional / total
        
        # Risk is 0 if balanced, 1 if all same direction
        risk = max(0, (concentration - 0.5) / 0.5)
        
        return risk
    
    def can_open_position(
        self,
        positions: List[Position],
        new_side: str,
        capital: float
    ) -> bool:
        """
        Check if we can open a new position.
        
        Checks:
        - Max positions not exceeded
        - Correlation risk acceptable
        - Sufficient capital
        
        Args:
            positions: Current open positions
            new_side: Side of new position ("long" or "short")
            capital: Available capital
            
        Returns:
            True if can open position
        """
        # Check max positions
        if len(positions) >= self.max_positions:
            return False
        
        # Check capital
        if capital <= 0:
            return False
        
        # Check correlation risk
        # Simulate adding new position and check risk
        temp_positions = positions.copy()
        temp_pos = Position(
            position_id=0,
            side=new_side,
            entry_price=0,
            entry_time=0,
            entry_idx=0,
            size_usd=0,
            peak_price=0,
            leverage=self.leverage
        )
        temp_positions.append(temp_pos)
        
        correlation_risk = self.calculate_correlation_risk(temp_positions)
        
        # If correlation risk > 0.8, only allow if it reduces concentration
        if correlation_risk > 0.8:
            # First position is always allowed (no existing positions)
            if len(positions) == 0:
                return True
            
            # Check if new position reduces concentration
            long_count = sum(1 for p in positions if p.side == "long")
            short_count = sum(1 for p in positions if p.side == "short")
            
            # Allow if new position is minority direction
            if new_side == "long" and long_count >= short_count:
                return False
            if new_side == "short" and short_count >= long_count:
                return False
        
        return True
    
    def calculate_signal(self, df: pd.DataFrame, idx: int) -> Tuple[str, float]:
        """
        Calculate trading signal based on strategy configuration.
        
        For strategy 046 (Holy Grail ADX), uses ADX-based signals.
        For strategy 160 (Holy Grail LightGBM), uses LightGBM + ADX hybrid.
        Otherwise, uses simplified momentum indicators.
        
        Returns:
            (direction, score) where direction is "long", "short", or "neutral"
            and score is the signal strength (0.0-5.0)
        """
        # Strategy-specific signal calculation
        strategy_id = self.strategy.get("id", 0)
        
        # Holy Grail ADX (Strategy 046)
        if strategy_id == 46:
            return self._calculate_signal_holy_grail_adx(df, idx)
        
        # Holy Grail LightGBM (Strategy 160)
        if strategy_id == 160:
            return self._calculate_signal_holy_grail_lightgbm(df, idx)
        
        # Default: simplified momentum indicators
        if idx < 20:  # Need history for indicators
            return "neutral", 0.0
        
        # Get recent price data
        prices = df['close'].iloc[max(0, idx-20):idx+1].values
        volumes = df['volume'].iloc[max(0, idx-20):idx+1].values
        current_price = prices[-1]
        
        if len(prices) < 10:
            return "neutral", 0.0
        
        # Calculate simple indicators
        sma_10 = np.mean(prices[-10:])
        sma_20 = np.mean(prices[-20:]) if len(prices) >= 20 else sma_10
        volume_avg = np.mean(volumes[-10:])
        current_volume = volumes[-1]
        
        # Price momentum
        returns_5 = (prices[-1] / prices[-6] - 1) if len(prices) >= 6 else 0
        returns_10 = (prices[-1] / prices[-11] - 1) if len(prices) >= 11 else 0
        returns_20 = (prices[-1] / prices[-20] - 1) if len(prices) >= 20 else 0
        
        # Simplified RSI
        changes = np.diff(prices[-14:]) if len(prices) >= 14 else np.diff(prices)
        gains = changes[changes > 0].sum() if len(changes[changes > 0]) > 0 else 0.0001
        losses = abs(changes[changes < 0].sum()) if len(changes[changes < 0]) > 0 else 0.0001
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        
        # Check confluence (simplified)
        bullish_signals = 0
        bearish_signals = 0
        
        # 1. SMA crossover
        if current_price > sma_10 > sma_20:
            bullish_signals += 1
        elif current_price < sma_10 < sma_20:
            bearish_signals += 1
        
        # 2. RSI
        if rsi < 40:
            bullish_signals += 1
        elif rsi > 60:
            bearish_signals += 1
        
        # 3. Volume confirmation
        if current_volume > volume_avg * self.volume_ratio:
            if returns_5 > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # 4. Short-term momentum
        if returns_5 > 0.01:  # +1%
            bullish_signals += 1
        elif returns_5 < -0.01:  # -1%
            bearish_signals += 1
        
        # 5. Medium-term momentum
        if returns_10 > 0.02:  # +2%
            bullish_signals += 1
        elif returns_10 < -0.02:  # -2%
            bearish_signals += 1
        
        # 6. Long-term momentum
        if returns_20 > 0.03:  # +3%
            bullish_signals += 1
        elif returns_20 < -0.03:  # -3%
            bearish_signals += 1
        
        # Determine signal direction and score
        if bullish_signals >= self.confluence_required:
            direction = "long"
            score = bullish_signals * 0.5
        elif bearish_signals >= self.confluence_required:
            direction = "short"
            score = bearish_signals * 0.5
        else:
            direction = "neutral"
            score = 0.0
        
        # Apply entry threshold
        if score < self.entry_threshold:
            return "neutral", score
        
        return direction, score
    
    def _calculate_signal_holy_grail_adx(self, df: pd.DataFrame, idx: int) -> Tuple[str, float]:
        """Calculate signal using Holy Grail ADX strategy (Strategy 046) - REAL ADX."""
        if idx < 30:
            return "neutral", 0.0
        
        # Get data up to current index
        df_slice = df.iloc[:idx+1].copy()
        
        # Use REAL ADX calculation from ml_feature_engineering
        try:
            from ml_feature_engineering import add_adx, add_sma, add_volume_features
            
            # Calculate ADX using real method
            df_with_adx = add_adx(df_slice.copy(), period=14)
            current_adx = df_with_adx['adx'].iloc[-1] if not df_with_adx['adx'].isna().all() else 0.0
            plus_di = df_with_adx['plus_di'].iloc[-1] if 'plus_di' in df_with_adx.columns and not df_with_adx['plus_di'].isna().all() else 0.0
            minus_di = df_with_adx['minus_di'].iloc[-1] if 'minus_di' in df_with_adx.columns and not df_with_adx['minus_di'].isna().all() else 0.0
            
            if pd.isna(current_adx) or current_adx == 0:
                return "neutral", 0.0
        except Exception as e:
            # Fallback to manual calculation if import fails
            high = df_slice['high']
            low = df_slice['low']
            close = df_slice['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm < 0] = 0
            
            period = 14
            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
            minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
            
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean()
            
            if adx.isna().all():
                return "neutral", 0.0
            
            current_adx = adx.iloc[-1]
            plus_di = plus_di.iloc[-1] if not plus_di.isna().all() else 0.0
            minus_di = minus_di.iloc[-1] if not minus_di.isna().all() else 0.0
        
        # Get close price for later use
        close = df_slice['close']
        
        # Calculate SMA distance using real method
        try:
            df_with_sma = add_sma(df_slice.copy(), periods=[20])
            sma_20 = df_with_sma['sma_20']
            sma_distance = (df_with_sma['close'] - sma_20) / sma_20
            current_sma_dist = sma_distance.iloc[-1] if not sma_distance.isna().all() else 0.0
        except:
            sma_20 = close.rolling(20).mean()
            sma_distance = (close - sma_20) / sma_20
            current_sma_dist = sma_distance.iloc[-1] if not sma_distance.isna().all() else 0.0
        
        # Calculate volume ratio using real method
        try:
            df_with_vol = add_volume_features(df_slice.copy())
            volume_ratio = df_with_vol['volume_ratio_20'].iloc[-1] if 'volume_ratio_20' in df_with_vol.columns and not df_with_vol['volume_ratio_20'].isna().all() else 1.0
        except:
            current_volume = df_slice['volume'].iloc[-1]
            volume_avg = df_slice['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1.0
        
        # Calculate returns
        close = df_slice['close']
        returns_5 = (close.iloc[-1] / close.iloc[-6] - 1) if len(df_slice) >= 6 else 0
        
        # IMPROVED Signal calculation for HIGHER TRADE FREQUENCY
        bullish_signals = 0
        bearish_signals = 0
        
        # 1. ADX strong trend (primary signal) - LOWERED THRESHOLD for more trades
        if current_adx > 20:  # Lowered from 25 to 20 for more signals
            if plus_di > minus_di and returns_5 > 0:
                bullish_signals += 3  # Increased weight
            elif minus_di > plus_di and returns_5 < 0:
                bearish_signals += 3
        
        # 2. SMA distance confirmation - LOWERED THRESHOLD
        if abs(current_sma_dist) > 0.005:  # Lowered from 0.01 to 0.005 (0.5% vs 1%)
            if current_sma_dist > 0 and returns_5 > 0:
                bullish_signals += 1
            elif current_sma_dist < 0 and returns_5 < 0:
                bearish_signals += 1
        
        # 3. Volume confirmation - LOWERED THRESHOLD
        if volume_ratio >= 1.2:  # Lowered from 1.4 to 1.2
            if returns_5 > 0:
                bullish_signals += 1
            elif returns_5 < 0:
                bearish_signals += 1
        
        # 4. Momentum confirmation - LOWERED THRESHOLD
        if returns_5 > 0.003:  # Lowered from 0.005 to 0.003 (0.3% vs 0.5%)
            bullish_signals += 1
        elif returns_5 < -0.003:
            bearish_signals += 1
        
        # 5. DI crossover (additional signal for more trades)
        if plus_di > minus_di and current_adx > 20:
            bullish_signals += 1
        elif minus_di > plus_di and current_adx > 20:
            bearish_signals += 1
        
        # Determine direction and score - REDUCED CONFLUENCE for more trades
        min_confluence = max(2, self.confluence_required - 1)  # Reduce by 1, minimum 2
        
        if bullish_signals >= min_confluence:
            direction = "long"
            score = min(1.0, bullish_signals * 0.25)  # Higher score per signal
        elif bearish_signals >= min_confluence:
            direction = "short"
            score = min(1.0, bearish_signals * 0.25)
        else:
            direction = "neutral"
            score = 0.0
        
        # LOWERED entry threshold for more trades (but still quality)
        effective_threshold = max(0.6, self.entry_threshold - 0.2)  # Lower by 0.2, minimum 0.6
        
        if score < effective_threshold:
            return "neutral", score
        
        return direction, score
    
    def _load_lightgbm_model(self):
        """Load LightGBM model for strategy 160."""
        if not LIGHTGBM_AVAILABLE:
            return
        
        try:
            # Try to load latest model
            model_path = Path("models/lightgbm_v1_latest.txt")
            if not model_path.exists():
                # Try alternative paths
                model_paths = list(Path("models").glob("lightgbm_*.txt"))
                if model_paths:
                    model_path = max(model_paths, key=lambda p: p.stat().st_mtime)
                else:
                    return
            
            self.lgbm_model = lgb.Booster(model_file=str(model_path))
            
            # Load feature names
            feature_path = model_path.parent / f"{model_path.stem}_features.txt"
            if not feature_path.exists():
                # Try alternative feature file
                feature_path = Path("models/lgbm_model_features.txt")
            
            if feature_path.exists():
                with open(feature_path, 'r') as f:
                    file_features = [line.strip() for line in f if line.strip()]
                # Check if these are the correct features (58 features from ml_feature_engineering)
                # Model was trained on 58 features, not order book features
                if len(file_features) >= 50:  # Real features have 58+
                    self.lgbm_features = file_features
                    print(f"✅ Loaded {len(self.lgbm_features)} features from file")
                else:
                    # Wrong features, use real features from ml_feature_engineering
                    from ml_feature_engineering import get_feature_list
                    self.lgbm_features = get_feature_list()
                    print(f"✅ Using REAL feature list from ml_feature_engineering: {len(self.lgbm_features)} features")
            else:
                # No feature file, use real features from ml_feature_engineering
                from ml_feature_engineering import get_feature_list
                self.lgbm_features = get_feature_list()
                print(f"✅ Using REAL feature list from ml_feature_engineering: {len(self.lgbm_features)} features")
        except Exception as e:
            print(f"❌ Error loading LightGBM model: {e}")
            import traceback
            traceback.print_exc()
            self.lgbm_model = None
    
    def _calculate_features_for_lgbm(self, df: pd.DataFrame, idx: int) -> Optional[pd.DataFrame]:
        """Calculate features for LightGBM model - REAL feature engineering."""
        if not self.lgbm_features or idx < 50:
            return None
        
        try:
            from ml_feature_engineering import calculate_all_features
            
            # Get data up to current index
            df_slice = df.iloc[:idx+1].copy()
            
            # Calculate ALL features using real feature engineering
            df_features = calculate_all_features(df_slice)
            
            # Get latest row
            latest = df_features.iloc[-1:].copy()
            
            # Select only features that model expects
            available_features = [f for f in self.lgbm_features if f in latest.columns]
            
            if len(available_features) < len(self.lgbm_features) * 0.7:  # Lowered to 70% for more flexibility
                return None
            
            # Fill any missing features with 0
            for feat in self.lgbm_features:
                if feat not in latest.columns:
                    latest[feat] = 0.0
            
            return latest[self.lgbm_features]
        except Exception as e:
            return None
    
    def _calculate_signal_holy_grail_lightgbm(self, df: pd.DataFrame, idx: int) -> Tuple[str, float]:
        """Calculate signal using Holy Grail LightGBM strategy (Strategy 160) - REAL LightGBM."""
        # Try to use REAL LightGBM model if available
        if self.lgbm_model is not None:
            features_df = self._calculate_features_for_lgbm(df, idx)
            if features_df is not None:
                try:
                    # REAL LightGBM prediction
                    X = features_df.values
                    
                    # Use best iteration if available
                    num_iteration = None
                    if hasattr(self.lgbm_model, 'best_iteration'):
                        num_iteration = self.lgbm_model.best_iteration
                    
                    probs = self.lgbm_model.predict(X, num_iteration=num_iteration)
                    
                    # Handle different output formats
                    if len(probs.shape) > 1:
                        # Multiclass: [flat_prob, long_prob, short_prob] or [prob_class_0, prob_class_1]
                        if probs.shape[1] == 2:
                            # Binary classification
                            prob_0, prob_1 = probs[0]
                            lgbm_score = prob_1  # Probability of positive class
                            lgbm_direction = "long" if prob_1 > 0.5 else "short"
                        else:
                            # Multiclass
                            flat_prob, long_prob, short_prob = probs[0]
                            lgbm_score = max(long_prob, short_prob)
                            lgbm_direction = "long" if long_prob > short_prob else "short"
                    else:
                        # Binary: probability of positive class
                        lgbm_score = float(probs[0])
                        lgbm_direction = "long" if lgbm_score > 0.5 else "short"
                    
                    # Combine with REAL ADX confirmation
                    adx_direction, adx_score = self._calculate_signal_holy_grail_adx(df, idx)
                    
                    # IMPROVED weighting for higher trade frequency
                    # If both agree, use combined score with lower threshold
                    if lgbm_direction == adx_direction and adx_score > 0:
                        # Both agree - boost score significantly
                        combined_score = (lgbm_score * 0.7) + (adx_score * 0.3)  # More weight to LightGBM
                        effective_threshold = max(0.6, self.entry_threshold - 0.2)  # Lower threshold
                        if combined_score >= effective_threshold:
                            return lgbm_direction, combined_score
                    elif lgbm_score > 0.65:  # Lowered from 0.7 for more trades
                        # LightGBM high confidence, use it even if ADX disagrees
                        effective_threshold = max(0.6, self.entry_threshold - 0.2)
                        if lgbm_score >= effective_threshold:
                            return lgbm_direction, lgbm_score
                    elif adx_score > 0.6:  # ADX can also trigger if strong enough
                        # Strong ADX signal even if LightGBM is neutral
                        effective_threshold = max(0.6, self.entry_threshold - 0.2)
                        if adx_score >= effective_threshold:
                            return adx_direction, adx_score
                except Exception as e:
                    # Fallback to ADX if LightGBM prediction fails
                    pass
        
        # Fallback to ADX strategy
        return self._calculate_signal_holy_grail_adx(df, idx)
    
    def run_backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 50.0
    ) -> BacktestResult:
        """
        Run backtest with multiple simultaneous positions.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading pair symbol
            initial_capital: Starting capital in USD
            
        Returns:
            BacktestResult object with all trades and metrics
        """
        capital = initial_capital
        positions: List[Position] = []  # Active positions
        trades = []
        equity_curve = []
        max_concurrent = 0
        correlation_violations = 0
        total_slippage = 0.0
        
        for idx in range(len(df)):
            timestamp = int(df.iloc[idx]['timestamp'])
            current_price = float(df.iloc[idx]['close'])
            
            # Calculate total unrealized PnL
            total_unrealized_pnl = 0.0
            for pos in positions:
                if pos.side == "long":
                    unrealized = (current_price / pos.entry_price - 1) * pos.size_usd * pos.leverage
                else:  # short
                    unrealized = (pos.entry_price / current_price - 1) * pos.size_usd * pos.leverage
                total_unrealized_pnl += unrealized
            
            current_equity = capital + total_unrealized_pnl
            equity_curve.append((timestamp, current_equity))
            
            # Update max concurrent positions
            max_concurrent = max(max_concurrent, len(positions))
            
            # Check exits for all positions
            positions_to_close = []
            
            for pos in positions:
                entry_price = pos.entry_price
                side = pos.side
                size_usd = pos.size_usd
                
                # Calculate price change
                if side == "long":
                    price_change = (current_price / entry_price - 1)
                    stop_price = entry_price * (1 - self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 + self.take_profit_pct / self.leverage)
                    
                    # Update peak for trailing
                    if current_price > pos.peak_price:
                        pos.peak_price = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price <= stop_price:
                        exit_reason = "sl"
                    elif current_price >= tp_price:
                        # Check trailing
                        trailing_stop = pos.peak_price * (1 - self.trailing_callback)
                        if current_price <= trailing_stop:
                            exit_reason = "tp_trailing"
                        else:
                            exit_reason = "tp"
                
                else:  # short
                    price_change = (entry_price / current_price - 1)
                    stop_price = entry_price * (1 + self.stop_loss_pct / self.leverage)
                    tp_price = entry_price * (1 - self.take_profit_pct / self.leverage)
                    
                    # Update peak (min for shorts)
                    if current_price < pos.peak_price:
                        pos.peak_price = current_price
                    
                    # Check exits
                    exit_reason = None
                    if current_price >= stop_price:
                        exit_reason = "sl"
                    elif current_price <= tp_price:
                        # Check trailing
                        trailing_stop = pos.peak_price * (1 + self.trailing_callback)
                        if current_price >= trailing_stop:
                            exit_reason = "tp_trailing"
                        else:
                            exit_reason = "tp"
                
                # Check for reversal signal
                signal_direction, signal_score = self.calculate_signal(df, idx)
                if signal_direction == ("short" if side == "long" else "long"):
                    if signal_score >= self.entry_threshold * 1.5:
                        exit_reason = "reversal"
                
                # Mark for closing if exit reason found
                if exit_reason:
                    # Calculate slippage
                    slippage = self.estimate_slippage(df, idx, size_usd)
                    slippage_cost = size_usd * self.leverage * slippage
                    total_slippage += slippage_cost
                    
                    # Calculate gross PnL
                    pnl_usd = price_change * size_usd * self.leverage
                    
                    # Deduct fees and slippage
                    notional_value = size_usd * self.leverage
                    fee_usd = notional_value * self.fee_per_trade
                    
                    # Net PnL after fees and slippage
                    net_pnl_usd = pnl_usd - fee_usd - slippage_cost
                    net_pnl_pct = (net_pnl_usd / size_usd) * 100
                    
                    trade = Trade(
                        entry_time=pos.entry_time,
                        exit_time=timestamp,
                        entry_price=entry_price,
                        exit_price=current_price,
                        side=side,
                        size_usd=size_usd,
                        leverage=self.leverage,
                        pnl_usd=net_pnl_usd,
                        pnl_pct=net_pnl_pct,
                        exit_reason=exit_reason,
                        slippage_cost=slippage_cost,
                    )
                    trades.append(trade)
                    capital += net_pnl_usd
                    positions_to_close.append(pos)
            
            # Remove closed positions
            for pos in positions_to_close:
                positions.remove(pos)
            
            # Check for new entries
            signal_direction, signal_score = self.calculate_signal(df, idx)
            
            if signal_direction in ["long", "short"]:
                # Check if we can open position
                if self.can_open_position(positions, signal_direction, capital):
                    # Calculate position size
                    position_size_usd = capital * self.position_size_pct
                    
                    # Ensure we don't exceed available capital
                    total_allocated = sum(p.size_usd for p in positions)
                    available = capital - total_allocated
                    position_size_usd = min(position_size_usd, available * 0.9)  # Leave 10% buffer
                    
                    if position_size_usd > 0:
                        # Calculate slippage for entry
                        slippage = self.estimate_slippage(df, idx, position_size_usd)
                        slippage_cost = position_size_usd * self.leverage * slippage
                        total_slippage += slippage_cost
                        capital -= slippage_cost  # Deduct slippage from capital
                        
                        # Open position
                        new_pos = Position(
                            position_id=self.next_position_id,
                            side=signal_direction,
                            entry_price=current_price,
                            entry_time=timestamp,
                            entry_idx=idx,
                            size_usd=position_size_usd,
                            peak_price=current_price,
                            leverage=self.leverage,
                        )
                        positions.append(new_pos)
                        self.next_position_id += 1
                else:
                    # Track correlation violations
                    if len(positions) < self.max_positions:
                        correlation_risk = self.calculate_correlation_risk(positions)
                        if correlation_risk > 0.8:
                            correlation_violations += 1
        
        # Close any remaining positions at end
        if positions:
            current_price = float(df.iloc[-1]['close'])
            timestamp = int(df.iloc[-1]['timestamp'])
            
            for pos in positions:
                entry_price = pos.entry_price
                side = pos.side
                size_usd = pos.size_usd
                
                if side == "long":
                    price_change = (current_price / entry_price - 1)
                else:
                    price_change = (entry_price / current_price - 1)
                
                # Calculate slippage
                slippage = self.estimate_slippage(df, len(df)-1, size_usd)
                slippage_cost = size_usd * self.leverage * slippage
                total_slippage += slippage_cost
                
                # Calculate PnL
                pnl_usd = price_change * size_usd * self.leverage
                notional_value = size_usd * self.leverage
                fee_usd = notional_value * self.fee_per_trade
                
                net_pnl_usd = pnl_usd - fee_usd - slippage_cost
                net_pnl_pct = (net_pnl_usd / size_usd) * 100
                
                trade = Trade(
                    entry_time=pos.entry_time,
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=current_price,
                    side=side,
                    size_usd=size_usd,
                    leverage=self.leverage,
                    pnl_usd=net_pnl_usd,
                    pnl_pct=net_pnl_pct,
                    exit_reason="end",
                    slippage_cost=slippage_cost,
                )
                trades.append(trade)
                capital += net_pnl_usd
        
        result = BacktestResult(
            strategy_id=self.strategy['id'],
            strategy_name=self.strategy['name'],
            symbol=symbol,
            initial_capital=initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
            max_concurrent_positions=max_concurrent,
            correlation_violations=correlation_violations,
            total_slippage_cost=total_slippage,
        )
        
        return result


# Alias for backward compatibility
BacktestEngine = MultiPositionBacktestEngine

