"""
Train LightGBM on 1-Minute Data for Maximum ROI

Enhancements for 15% daily ROI target:
- 1-minute candle data (200 candles = 3.3 hours per token)
- 1500 boosting rounds (vs 1000 for 1H data)
- 100+ comprehensive features
- Optuna optimization with 50 trials
- Target: Predict 0.15% move in next 5 candles (5 minutes)
- Expected samples: 200 candles × 338 tokens = 67,600 samples
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
import json
from datetime import datetime
from ml_feature_engineering import (
    calculate_rsi, calculate_macd, calculate_bollinger_bands,
    calculate_atr, calculate_adx, calculate_mfi, calculate_obv,
    calculate_ema, calculate_sma, calculate_cci, calculate_roc
)

# Try to import optuna for hyperparameter optimization
try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    print("⚠️ Optuna not available, using default hyperparameters")


class LightGBM1mTrainer:
    """
    Train LightGBM on 1-minute data for extreme ROI strategies.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.models_dir = Path("/Users/macbookpro13/bitgettrading/models")
        self.models_dir.mkdir(exist_ok=True)
    
    def calculate_advanced_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate 100+ advanced features optimized for 1-minute data.
        
        For 1m data, use shorter periods than 1H data.
        """
        df = df.copy()
        
        print("  📊 Calculating 100+ features for 1m data...")
        
        # Price features (shorter periods for 1m)
        for period in [1, 2, 3, 5, 10, 15]:  # 1-15 minutes
            df[f'returns_{period}'] = df['close'].pct_change(period)
            df[f'log_returns_{period}'] = np.log(df['close'] / df['close'].shift(period))
        
        # Volatility features (shorter windows)
        for period in [5, 10, 15, 20]:  # 5-20 minutes
            df[f'volatility_{period}'] = df['returns_1'].rolling(period).std()
        
        # Price ratios
        df['hl_ratio'] = (df['high'] - df['low']) / df['close']
        df['oc_ratio'] = (df['close'] - df['open']) / df['open']
        
        # RSI (shorter periods for 1m)
        for period in [5, 10, 14]:  # 5-14 minutes
            df[f'rsi_{period}'] = calculate_rsi(df, period)
        
        # MACD (adjusted for 1m)
        macd_result = calculate_macd(df, fast=8, slow=17, signal=9)  # Faster than default
        if macd_result is not None:
            df['macd'], df['macd_signal'], df['macd_hist'] = macd_result
        
        # Bollinger Bands (shorter periods)
        for period in [10, 20, 30]:  # 10-30 minutes
            bb_result = calculate_bollinger_bands(df, period)
            if bb_result is not None:
                df[f'bb_upper_{period}'], df[f'bb_middle_{period}'], df[f'bb_lower_{period}'] = bb_result
                df[f'bb_width_{period}'] = (df[f'bb_upper_{period}'] - df[f'bb_lower_{period}']) / df[f'bb_middle_{period}']
                df[f'bb_pct_{period}'] = (df['close'] - df[f'bb_lower_{period}']) / (df[f'bb_upper_{period}'] - df[f'bb_lower_{period}'])
        
        # ATR & ADX (shorter periods)
        df['atr'] = calculate_atr(df, period=10)
        df['adx'] = calculate_adx(df, period=10)
        
        # MFI & OBV
        df['mfi'] = calculate_mfi(df, period=10)
        df['obv'] = calculate_obv(df)
        
        # CCI & ROC
        df['cci'] = calculate_cci(df, period=10)
        for period in [5, 10, 15]:  # 5-15 minutes
            df[f'roc_{period}'] = calculate_roc(df, period)
        
        # EMAs & SMAs (shorter periods for 1m)
        for period in [3, 5, 8, 13, 21, 34]:  # Fibonacci periods
            df[f'ema_{period}'] = calculate_ema(df, period)
            df[f'sma_{period}'] = calculate_sma(df, period)
        
        # EMA crossovers
        df['ema_cross_3_8'] = (df['ema_3'] - df['ema_8']) / df['ema_8']
        df['ema_cross_8_21'] = (df['ema_8'] - df['ema_21']) / df['ema_21']
        
        # Volume features
        for period in [5, 10, 15]:  # 5-15 minutes
            df[f'volume_ma_{period}'] = df['volume'].rolling(period).mean()
            df[f'volume_ratio_{period}'] = df['volume'] / df[f'volume_ma_{period}']
        
        # Price momentum (shorter periods)
        for period in [3, 5, 10]:  # 3-10 minutes
            df[f'momentum_{period}'] = df['close'] - df['close'].shift(period)
        
        # Trend strength
        df['trend_strength'] = abs(df['ema_8'] - df['ema_34']) / df['ema_34']
        
        # Volatility ratio
        df['volatility_ratio'] = df['volatility_5'] / df['volatility_15']
        
        # High/Low patterns
        df['higher_high'] = ((df['high'] > df['high'].shift(1)) & 
                             (df['high'].shift(1) > df['high'].shift(2))).astype(int)
        df['lower_low'] = ((df['low'] < df['low'].shift(1)) & 
                           (df['low'].shift(1) < df['low'].shift(2))).astype(int)
        
        # Price position in range
        df['price_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)
        
        # Candle patterns
        df['body_size'] = abs(df['close'] - df['open']) / df['close']
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close']
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close']
        
        print(f"  ✅ Features calculated: {df.shape[1]} columns")
        
        return df
    
    def create_target(
        self, 
        df: pd.DataFrame, 
        lookahead: int = 5, 
        threshold_pct: float = 0.15
    ) -> pd.Series:
        """
        Create binary target for 1m data.
        
        Target: Price goes up by 0.15%+ in next 5 candles (5 minutes)
        At 75x leverage, 0.15% = 11.25% capital gain
        At 100x leverage, 0.15% = 15% capital gain (target!)
        
        Args:
            df: DataFrame with OHLCV data
            lookahead: Number of candles to look ahead
            threshold_pct: Price move threshold
            
        Returns:
            Binary target series
        """
        # Find max high in next N candles
        future_max = df['high'].shift(-lookahead).rolling(lookahead).max()
        
        # Calculate return from current close to future max
        future_return = (future_max - df['close']) / df['close'] * 100
        
        # Target: 1 if price goes up by threshold%+
        target = (future_return >= threshold_pct).astype(int)
        
        positive_samples = target.sum()
        total_samples = len(target) - target.isna().sum()
        positive_pct = (positive_samples / total_samples * 100) if total_samples > 0 else 0
        
        print(f"  🎯 Target created: {positive_samples} positive samples ({positive_pct:.2f}%)")
        
        return target
    
    def optimize_hyperparameters(
        self, 
        X_train: pd.DataFrame, 
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        n_trials: int = 50
    ) -> Dict:
        """Use Optuna to find optimal hyperparameters (50 trials)."""
        
        if not OPTUNA_AVAILABLE:
            print("  ⚠️ Optuna not available, using default hyperparameters")
            return {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': 63,
                'learning_rate': 0.03,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'max_depth': 8,
                'min_data_in_leaf': 50,
                'lambda_l1': 0.1,
                'lambda_l2': 0.1,
                'verbose': -1,
                'force_col_wise': True
            }
        
        print(f"  🔍 Optimizing hyperparameters with {n_trials} trials...")
        
        def objective(trial):
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': trial.suggest_int('num_leaves', 31, 127),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1, log=True),
                'feature_fraction': trial.suggest_float('feature_fraction', 0.6, 1.0),
                'bagging_fraction': trial.suggest_float('bagging_fraction', 0.6, 1.0),
                'bagging_freq': trial.suggest_int('bagging_freq', 1, 7),
                'max_depth': trial.suggest_int('max_depth', 5, 15),
                'min_data_in_leaf': trial.suggest_int('min_data_in_leaf', 20, 100),
                'lambda_l1': trial.suggest_float('lambda_l1', 0.0, 1.0),
                'lambda_l2': trial.suggest_float('lambda_l2', 0.0, 1.0),
                'verbose': -1,
                'force_col_wise': True
            }
            
            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
            
            model = lgb.train(
                params,
                train_data,
                num_boost_round=300,  # Shorter for optimization
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(stopping_rounds=30), lgb.log_evaluation(period=0)]
            )
            
            preds = model.predict(X_val)
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_val, preds)
            
            return auc
        
        study = optuna.create_study(direction='maximize', study_name='lightgbm_1m_optimization')
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
        
        print(f"  ✅ Best AUC: {study.best_value:.4f}")
        print(f"  📊 Best parameters: {study.best_params}")
        
        # Convert best params to full params dict
        best_params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'verbose': -1,
            'force_col_wise': True,
            **study.best_params
        }
        
        return best_params
    
    def train_1m_model(
        self,
        lookahead: int = 5,
        threshold_pct: float = 0.15,
        n_trials: int = 50,
        max_tokens: int = 338
    ) -> Tuple[lgb.Booster, Dict]:
        """Train LightGBM model on 1-minute data."""
        
        print("="*100)
        print("🚀 LIGHTGBM 1-MINUTE TRAINING - EXTREME ROI EDITION")
        print("="*100)
        print()
        print(f"Target: Predict {threshold_pct}% move in next {lookahead} minutes")
        print(f"At 100x leverage: {threshold_pct}% price move = {threshold_pct * 100}% capital gain")
        print()
        
        # Load ALL 1m cached data
        all_data = []
        cache_files = list(self.cache_dir.glob("*_1m_200.pkl")) + list(self.cache_dir.glob("*_1m_*.pkl"))
        
        if not cache_files:
            print("❌ No 1m cached data found!")
            print("   Please run: python data_fetcher.py with timeframe='1m'")
            return None, {}
        
        print(f"📂 Loading 1m data from {len(cache_files[:max_tokens])} tokens...")
        
        for idx, cache_file in enumerate(cache_files[:max_tokens], 1):
            if idx % 50 == 0:
                print(f"   Progress: {idx}/{min(len(cache_files), max_tokens)} tokens...")
            
            try:
                df = pd.read_pickle(cache_file)
                if len(df) > 30:  # Need enough data
                    all_data.append(df)
            except Exception as e:
                continue
        
        print(f"✅ Loaded {len(all_data)} tokens")
        print()
        
        if not all_data:
            print("❌ No valid data loaded!")
            return None, {}
        
        # Combine all data
        print("🔄 Processing and combining data...")
        combined_features = []
        combined_targets = []
        
        for idx, df in enumerate(all_data, 1):
            if idx % 50 == 0:
                print(f"   Processing: {idx}/{len(all_data)} tokens...")
            
            # Calculate features
            df_features = self.calculate_advanced_features(df)
            
            # Create target
            target = self.create_target(df_features, lookahead, threshold_pct)
            
            # Remove NaN rows
            df_features = df_features.dropna()
            target = target[df_features.index]
            
            if len(df_features) > 20:
                combined_features.append(df_features)
                combined_targets.append(target)
        
        # Combine all
        X = pd.concat(combined_features, ignore_index=True)
        y = pd.concat(combined_targets, ignore_index=True)
        
        # Select only numeric features for training
        feature_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [col for col in feature_cols if col not in ['timestamp', 'time']]
        
        X = X[feature_cols]
        
        print(f"\n✅ Combined dataset: {len(X)} samples, {len(feature_cols)} features")
        print(f"   Positive samples: {y.sum()} ({y.mean()*100:.2f}%)")
        print()
        
        # Train/val split (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"📊 Train: {len(X_train)} samples | Val: {len(X_val)} samples")
        print()
        
        # Optimize hyperparameters
        best_params = self.optimize_hyperparameters(X_train, y_train, X_val, y_val, n_trials)
        print()
        
        # Train final model with 1500 rounds
        print("🔥 Training final model with 1500 boosting rounds...")
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        model = lgb.train(
            best_params,
            train_data,
            num_boost_round=1500,  # LONG training for 1m data
            valid_sets=[train_data, val_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=100),  # More patience
                lgb.log_evaluation(period=100)
            ]
        )
        
        print()
        
        # Evaluate
        from sklearn.metrics import roc_auc_score, accuracy_score, classification_report
        
        train_preds = model.predict(X_train)
        val_preds = model.predict(X_val)
        
        train_pred_labels = (train_preds > 0.5).astype(int)
        val_pred_labels = (val_preds > 0.5).astype(int)
        
        train_auc = roc_auc_score(y_train, train_preds)
        val_auc = roc_auc_score(y_val, val_preds)
        train_acc = accuracy_score(y_train, train_pred_labels)
        val_acc = accuracy_score(y_val, val_pred_labels)
        
        print("="*100)
        print("📊 MODEL PERFORMANCE")
        print("="*100)
        print(f"Train AUC: {train_auc:.4f} | Train Accuracy: {train_acc:.4f}")
        print(f"Val AUC:   {val_auc:.4f} | Val Accuracy:   {val_acc:.4f}")
        print()
        
        print("Classification Report (Validation):")
        print(classification_report(y_val, val_pred_labels))
        print()
        
        # Feature importance
        feature_importance = dict(zip(feature_cols, model.feature_importance()))
        top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:30]
        
        print("🏆 TOP 30 FEATURES:")
        for idx, (feat, imp) in enumerate(top_features, 1):
            print(f"  {idx:2d}. {feat:30s} {imp:6.0f}")
        print()
        
        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_file = self.models_dir / f"lightgbm_1m_{timestamp}.txt"
        model.save_model(str(model_file))
        
        # Create symlink to latest
        latest_link = self.models_dir / "lightgbm_1m_latest.txt"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(model_file.name)
        
        # Save metadata
        metadata = {
            'timestamp': timestamp,
            'timeframe': '1m',
            'n_samples': len(X),
            'n_features': len(feature_cols),
            'n_tokens': len(all_data),
            'train_auc': float(train_auc),
            'val_auc': float(val_auc),
            'train_accuracy': float(train_acc),
            'val_accuracy': float(val_acc),
            'lookahead': lookahead,
            'threshold_pct': threshold_pct,
            'num_boost_rounds': 1500,
            'best_params': best_params,
            'feature_importance': {k: int(v) for k, v in top_features}
        }
        
        metadata_file = self.models_dir / f"lightgbm_1m_metadata_{timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Model saved: {model_file.name}")
        print(f"✅ Metadata saved: {metadata_file.name}")
        print()
        
        print("="*100)
        print("🎉 1-MINUTE MODEL TRAINING COMPLETE!")
        print("="*100)
        
        return model, metadata


def main():
    """Train 1-minute LightGBM model."""
    cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    trainer = LightGBM1mTrainer(cache_dir)
    
    # Train with aggressive parameters for maximum ROI
    # lookahead=5 (5 minutes), threshold=0.15% (15% capital at 100x leverage)
    model, metadata = trainer.train_1m_model(
        lookahead=5,
        threshold_pct=0.15,  # 0.15% price move = 15% capital at 100x
        n_trials=50,  # Optuna trials
        max_tokens=338
    )
    
    if model:
        print("\n🚀 Ready to create extreme ROI strategies with 1m model!")


if __name__ == "__main__":
    main()

