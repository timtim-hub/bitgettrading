"""
Train Specialized LightGBM Models for Different Market Regimes

4 Regimes:
1. High Vol Trending: Strong directional movement with high volatility
2. Low Vol Ranging: Sideways movement in tight range
3. Breakout: Price breaking out of consolidation
4. Reversal: Trend reversals and pullbacks

Each regime gets its own specialized model optimized for that condition.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
import json
from datetime import datetime
from sklearn.metrics import roc_auc_score, accuracy_score, classification_report
from train_lightgbm_1m import LightGBM1mTrainer


class RegimeModelsTrainer:
    """
    Train specialized models for different market regimes.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.models_dir = Path("/Users/macbookpro13/bitgettrading/models")
        self.models_dir.mkdir(exist_ok=True)
        self.base_trainer = LightGBM1mTrainer(cache_dir)
    
    def detect_regime(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        Detect market regime for each candle.
        
        Regimes:
        0 = High Vol Trending
        1 = Low Vol Ranging
        2 = Breakout
        3 = Reversal
        
        Args:
            df: DataFrame with OHLCV data
            window: Window for regime detection
            
        Returns:
            Series with regime labels
        """
        regimes = []
        
        for i in range(len(df)):
            if i < window:
                regimes.append(-1)  # Not enough data
                continue
            
            # Get window of data
            window_df = df.iloc[max(0, i-window):i+1]
            
            # Calculate metrics
            returns = window_df['close'].pct_change()
            volatility = returns.std()
            
            # Calculate trend strength (linear regression slope)
            prices = window_df['close'].values
            x = np.arange(len(prices))
            slope = np.polyfit(x, prices, 1)[0]
            trend_strength = abs(slope) / prices.mean()
            
            # Calculate range (max - min) / mean
            price_range = (prices.max() - prices.min()) / prices.mean()
            
            # Detect regime
            if volatility > 0.015 and trend_strength > 0.005:
                # High volatility + strong trend = High Vol Trending
                regime = 0
            elif volatility < 0.008 and price_range < 0.02:
                # Low volatility + tight range = Low Vol Ranging
                regime = 1
            elif i > window + 5:
                # Check for breakout: recent tight range followed by expansion
                prev_range = (df['close'].iloc[i-window:i-5].max() - df['close'].iloc[i-window:i-5].min()) / df['close'].iloc[i-5]
                recent_move = abs(df['close'].iloc[i] - df['close'].iloc[i-5]) / df['close'].iloc[i-5]
                if prev_range < 0.01 and recent_move > 0.01:
                    # Breakout
                    regime = 2
                elif trend_strength > 0.003:  # Otherwise trending
                    regime = 0
                else:
                    regime = 1
            else:
                # Check for reversal: recent price change opposite to window trend
                recent_return = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
                if (slope > 0 and recent_return < -0.01) or (slope < 0 and recent_return > 0.01):
                    # Reversal
                    regime = 3
                elif trend_strength > 0.003:
                    regime = 0
                else:
                    regime = 1
            
            regimes.append(regime)
        
        return pd.Series(regimes, index=df.index)
    
    def train_regime_specific_model(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        regime_mask: pd.Series,
        regime_name: str
    ) -> Tuple[lgb.Booster, Dict]:
        """
        Train a model specific to one regime.
        
        Args:
            X: Features
            y: Target
            regime_mask: Boolean mask for regime
            regime_name: Name of the regime
            
        Returns:
            Tuple of (model, metadata)
        """
        # Filter to regime
        X_regime = X[regime_mask]
        y_regime = y[regime_mask]
        
        if len(X_regime) < 100:
            print(f"  ⚠️ Not enough samples for {regime_name}: {len(X_regime)}")
            return None, {}
        
        print(f"\n{'='*80}")
        print(f"Training {regime_name} Model")
        print(f"{'='*80}")
        print(f"Samples: {len(X_regime)} | Positive: {y_regime.sum()} ({y_regime.mean()*100:.2f}%)")
        
        # Train/val split
        split_idx = int(len(X_regime) * 0.8)
        X_train, X_val = X_regime[:split_idx], X_regime[split_idx:]
        y_train, y_val = y_regime[:split_idx], y_regime[split_idx:]
        
        # Train model
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 63,
            'learning_rate': 0.03,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'max_depth': 8,
            'min_data_in_leaf': 30,
            'lambda_l1': 0.1,
            'lambda_l2': 0.1,
            'verbose': -1,
            'force_col_wise': True
        }
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            valid_sets=[train_data, val_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=100)
            ]
        )
        
        # Evaluate
        train_preds = model.predict(X_train)
        val_preds = model.predict(X_val)
        
        train_pred_labels = (train_preds > 0.5).astype(int)
        val_pred_labels = (val_preds > 0.5).astype(int)
        
        train_auc = roc_auc_score(y_train, train_preds)
        val_auc = roc_auc_score(y_val, val_preds)
        train_acc = accuracy_score(y_train, train_pred_labels)
        val_acc = accuracy_score(y_val, val_pred_labels)
        
        print(f"\n📊 Performance:")
        print(f"Train AUC: {train_auc:.4f} | Train Accuracy: {train_acc:.4f}")
        print(f"Val AUC:   {val_auc:.4f} | Val Accuracy:   {val_acc:.4f}")
        
        # Feature importance
        feature_importance = dict(zip(X.columns, model.feature_importance()))
        top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:15]
        
        print(f"\n🏆 Top 15 Features for {regime_name}:")
        for idx, (feat, imp) in enumerate(top_features, 1):
            print(f"  {idx:2d}. {feat:30s} {imp:6.0f}")
        
        # Metadata
        metadata = {
            'regime': regime_name,
            'n_samples': len(X_regime),
            'n_train': len(X_train),
            'n_val': len(X_val),
            'train_auc': float(train_auc),
            'val_auc': float(val_auc),
            'train_accuracy': float(train_acc),
            'val_accuracy': float(val_acc),
            'top_features': {k: int(v) for k, v in top_features}
        }
        
        return model, metadata
    
    def train_all_regime_models(self):
        """Train models for all 4 regimes."""
        
        print("="*100)
        print("🚀 REGIME-SPECIFIC MODEL TRAINING")
        print("="*100)
        print()
        
        # Load and process data (same as base trainer)
        cache_files = list(self.cache_dir.glob("*_1m_200.pkl")) + list(self.cache_dir.glob("*_1m_*.pkl"))
        
        if not cache_files:
            print("❌ No 1m cached data found!")
            return {}
        
        print(f"📂 Loading data from {len(cache_files[:338])} tokens...")
        
        all_data = []
        for idx, cache_file in enumerate(cache_files[:338], 1):
            if idx % 50 == 0:
                print(f"   Progress: {idx}/{min(len(cache_files), 338)} tokens...")
            
            try:
                df = pd.read_pickle(cache_file)
                if len(df) > 30:
                    all_data.append(df)
            except Exception:
                continue
        
        print(f"✅ Loaded {len(all_data)} tokens\n")
        
        # Process data
        print("🔄 Processing data and detecting regimes...")
        combined_features = []
        combined_targets = []
        combined_regimes = []
        
        for idx, df in enumerate(all_data, 1):
            if idx % 50 == 0:
                print(f"   Processing: {idx}/{len(all_data)} tokens...")
            
            # Calculate features
            df_features = self.base_trainer.calculate_advanced_features(df)
            
            # Detect regimes
            regimes = self.detect_regime(df_features)
            
            # Create target
            target = self.base_trainer.create_target(df_features, lookahead=5, threshold_pct=0.15)
            
            # Remove NaN rows
            valid_idx = df_features.notna().all(axis=1) & target.notna() & (regimes >= 0)
            df_features = df_features[valid_idx]
            target = target[valid_idx]
            regimes = regimes[valid_idx]
            
            if len(df_features) > 20:
                combined_features.append(df_features)
                combined_targets.append(target)
                combined_regimes.append(regimes)
        
        # Combine all
        X = pd.concat(combined_features, ignore_index=True)
        y = pd.concat(combined_targets, ignore_index=True)
        all_regimes = pd.concat(combined_regimes, ignore_index=True)
        
        # Select numeric features
        feature_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [col for col in feature_cols if col not in ['timestamp', 'time']]
        X = X[feature_cols]
        
        print(f"\n✅ Combined dataset: {len(X)} samples, {len(feature_cols)} features\n")
        
        # Count regimes
        regime_names = ["High_Vol_Trending", "Low_Vol_Ranging", "Breakout", "Reversal"]
        print("📊 Regime Distribution:")
        for idx, name in enumerate(regime_names):
            count = (all_regimes == idx).sum()
            pct = count / len(all_regimes) * 100
            print(f"  {name:20s}: {count:6d} samples ({pct:5.2f}%)")
        print()
        
        # Train model for each regime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_metadata = {'timestamp': timestamp, 'regimes': {}}
        
        for regime_idx, regime_name in enumerate(regime_names):
            regime_mask = (all_regimes == regime_idx)
            
            model, metadata = self.train_regime_specific_model(
                X, y, regime_mask, regime_name
            )
            
            if model:
                # Save model
                model_file = self.models_dir / f"regime_{regime_name.lower()}_{timestamp}.txt"
                model.save_model(str(model_file))
                print(f"✅ Saved: {model_file.name}\n")
                
                all_metadata['regimes'][regime_name] = metadata
                all_metadata['regimes'][regime_name]['model_file'] = model_file.name
        
        # Save combined metadata
        metadata_file = self.models_dir / f"regime_models_metadata_{timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(all_metadata, f, indent=2)
        
        print(f"✅ Metadata saved: {metadata_file.name}")
        print()
        print("="*100)
        print("🎉 REGIME MODELS TRAINING COMPLETE!")
        print("="*100)
        
        return all_metadata


def main():
    """Train regime-specific models."""
    cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    trainer = RegimeModelsTrainer(cache_dir)
    trainer.train_all_regime_models()
    
    print("\n🚀 Ready to use regime-specific models in strategies!")


if __name__ == "__main__":
    main()

