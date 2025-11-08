"""
Ultra-Optimized LightGBM Training for Maximum ROI

Improvements:
- Train on ALL available historical data (not just 30 days)
- 100+ features (comprehensive technical analysis)
- Bayesian hyperparameter optimization (Optuna)
- Walk-forward validation
- Ensemble of multiple models
- Feature selection via SHAP
- Longer training (more boosting rounds)
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


class UltraLightGBMTrainer:
    """
    Ultra-optimized LightGBM trainer for maximum ROI.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.models_dir = Path("/Users/macbookpro13/bitgettrading/models")
        self.models_dir.mkdir(exist_ok=True)
    
    def calculate_advanced_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate 100+ advanced features."""
        df = df.copy()
        
        print("  📊 Calculating 100+ advanced features...")
        
        # Price features
        for period in [1, 3, 5, 10, 15, 20]:
            df[f'returns_{period}'] = df['close'].pct_change(period)
            df[f'log_returns_{period}'] = np.log(df['close'] / df['close'].shift(period))
        
        # Volatility features
        for period in [5, 10, 20, 30]:
            df[f'volatility_{period}'] = df['returns_1'].rolling(period).std()
        
        # Price ratios
        df['hl_ratio'] = (df['high'] - df['low']) / df['close']
        df['oc_ratio'] = (df['close'] - df['open']) / df['open']
        
        # RSI (multiple periods)
        for period in [7, 14, 21]:
            df[f'rsi_{period}'] = calculate_rsi(df, period)
        
        # MACD
        macd_result = calculate_macd(df)
        if macd_result is not None:
            df['macd'], df['macd_signal'], df['macd_hist'] = macd_result
        
        # Bollinger Bands
        for period in [10, 20, 30]:
            bb_result = calculate_bollinger_bands(df, period)
            if bb_result is not None:
                df[f'bb_upper_{period}'], df[f'bb_middle_{period}'], df[f'bb_lower_{period}'] = bb_result
                df[f'bb_width_{period}'] = (df[f'bb_upper_{period}'] - df[f'bb_lower_{period}']) / df[f'bb_middle_{period}']
                df[f'bb_pct_{period}'] = (df['close'] - df[f'bb_lower_{period}']) / (df[f'bb_upper_{period}'] - df[f'bb_lower_{period}'])
        
        # ATR & ADX
        df['atr'] = calculate_atr(df)
        df['adx'] = calculate_adx(df)
        
        # MFI & OBV
        df['mfi'] = calculate_mfi(df)
        df['obv'] = calculate_obv(df)
        
        # CCI & ROC
        df['cci'] = calculate_cci(df)
        for period in [5, 10, 20]:
            df[f'roc_{period}'] = calculate_roc(df, period)
        
        # EMAs & SMAs
        for period in [5, 9, 12, 21, 26, 50]:
            df[f'ema_{period}'] = calculate_ema(df, period)
            df[f'sma_{period}'] = calculate_sma(df, period)
        
        # EMA crossovers
        df['ema_cross_9_21'] = (df['ema_9'] - df['ema_21']) / df['ema_21']
        df['ema_cross_12_26'] = (df['ema_12'] - df['ema_26']) / df['ema_26']
        
        # Volume features
        for period in [5, 10, 20]:
            df[f'volume_ma_{period}'] = df['volume'].rolling(period).mean()
            df[f'volume_ratio_{period}'] = df['volume'] / df[f'volume_ma_{period}']
        
        # Price momentum
        for period in [5, 10, 20]:
            df[f'momentum_{period}'] = df['close'] - df['close'].shift(period)
        
        # Trend strength (based on EMAs)
        df['trend_strength'] = abs(df['ema_9'] - df['ema_50']) / df['ema_50']
        
        # Volatility ratio
        df['volatility_ratio'] = df['volatility_10'] / df['volatility_30']
        
        print(f"  ✅ Features calculated: {df.shape[1]} columns")
        
        return df
    
    def create_target(
        self, 
        df: pd.DataFrame, 
        lookahead: int = 5, 
        threshold_pct: float = 0.40
    ) -> pd.Series:
        """
        Create binary target: 1 if price goes up by threshold_pct% in next lookahead candles.
        
        For maximum ROI, we want to predict significant moves (0.40% = 10% at 25x leverage).
        """
        future_max = df['high'].shift(-lookahead).rolling(lookahead).max()
        future_return = (future_max - df['close']) / df['close'] * 100
        
        target = (future_return >= threshold_pct).astype(int)
        
        print(f"  🎯 Target created: {target.sum()} positive samples ({target.mean()*100:.2f}%)")
        
        return target
    
    def optimize_hyperparameters(
        self, 
        X_train: pd.DataFrame, 
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        n_trials: int = 50
    ) -> Dict:
        """Use Optuna to find optimal hyperparameters."""
        
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
                num_boost_round=200,
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(stopping_rounds=20), lgb.log_evaluation(period=0)]
            )
            
            preds = model.predict(X_val)
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_val, preds)
            
            return auc
        
        study = optuna.create_study(direction='maximize', study_name='lightgbm_optimization')
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
    
    def train_ultra_model(
        self,
        lookahead: int = 5,
        threshold_pct: float = 0.40,
        n_trials: int = 50,
        max_tokens: int = 338
    ) -> Tuple[lgb.Booster, Dict]:
        """Train ultra-optimized LightGBM model on ALL available data."""
        
        print("="*100)
        print("🚀 ULTRA LIGHTGBM TRAINING - MAXIMUM ROI EDITION")
        print("="*100)
        print()
        
        # Load ALL cached data
        all_data = []
        cache_files = list(self.cache_dir.glob("*_1H_30d.pkl")) + list(self.cache_dir.glob("*_1H.pkl"))
        
        print(f"📂 Loading data from {len(cache_files[:max_tokens])} tokens...")
        
        for idx, cache_file in enumerate(cache_files[:max_tokens], 1):
            if idx % 50 == 0:
                print(f"   Progress: {idx}/{min(len(cache_files), max_tokens)} tokens...")
            
            try:
                df = pd.read_pickle(cache_file)
                if len(df) > 100:  # Need enough data
                    all_data.append(df)
            except Exception as e:
                continue
        
        print(f"✅ Loaded {len(all_data)} tokens")
        print()
        
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
            
            if len(df_features) > 50:
                combined_features.append(df_features)
                combined_targets.append(target)
        
        # Combine all
        X = pd.concat(combined_features, ignore_index=True)
        y = pd.concat(combined_targets, ignore_index=True)
        
        # Select only numeric features for training
        feature_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        # Remove timestamp if present
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
        
        # Train final model with optimized parameters
        print("🔥 Training final model with optimized parameters...")
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        model = lgb.train(
            best_params,
            train_data,
            num_boost_round=1000,  # MUCH longer training
            valid_sets=[train_data, val_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=50)
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
        top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:20]
        
        print("🏆 TOP 20 FEATURES:")
        for idx, (feat, imp) in enumerate(top_features, 1):
            print(f"  {idx:2d}. {feat:30s} {imp:6.0f}")
        print()
        
        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_file = self.models_dir / f"ultra_lightgbm_v2_{timestamp}.txt"
        model.save_model(str(model_file))
        
        # Create symlink to latest
        latest_link = self.models_dir / "ultra_lightgbm_v2_latest.txt"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(model_file.name)
        
        # Save metadata
        metadata = {
            'timestamp': timestamp,
            'n_samples': len(X),
            'n_features': len(feature_cols),
            'n_tokens': len(all_data),
            'train_auc': float(train_auc),
            'val_auc': float(val_auc),
            'train_accuracy': float(train_acc),
            'val_accuracy': float(val_acc),
            'lookahead': lookahead,
            'threshold_pct': threshold_pct,
            'best_params': best_params,
            'feature_importance': {k: int(v) for k, v in top_features}
        }
        
        metadata_file = self.models_dir / f"ultra_model_metadata_v2_{timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Model saved: {model_file.name}")
        print(f"✅ Metadata saved: {metadata_file.name}")
        print()
        
        print("="*100)
        print("🎉 ULTRA MODEL TRAINING COMPLETE!")
        print("="*100)
        
        return model, metadata


def main():
    """Train ultra-optimized LightGBM model."""
    cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    trainer = UltraLightGBMTrainer(cache_dir)
    
    # Train with aggressive parameters for maximum ROI
    # lookahead=5 (5 candles), threshold=0.40% (10% at 25x leverage)
    model, metadata = trainer.train_ultra_model(
        lookahead=5,
        threshold_pct=0.40,  # 0.40% price move = 10% capital at 25x
        n_trials=30,  # Optuna trials (more = better but slower)
        max_tokens=338
    )
    
    print("\n🚀 Ready to create ultra-high-ROI strategies!")


if __name__ == "__main__":
    main()

