"""
Train XGBoost and CatBoost Models for True Multi-Model Ensemble

Creates diverse models that can vote together:
- LightGBM (already trained)
- XGBoost (this file)
- CatBoost (this file)

Vote: Only trade when 2+ models agree (66%+ consensus)
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple
import json
from datetime import datetime
from sklearn.metrics import roc_auc_score, accuracy_score
from train_lightgbm_1m import LightGBM1mTrainer

# Try to import XGBoost and CatBoost
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("⚠️ XGBoost not available. Install with: pip install xgboost")

try:
    from catboost import CatBoostClassifier, Pool
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False
    print("⚠️ CatBoost not available. Install with: pip install catboost")


class EnsembleModelsTrainer:
    """
    Train XGBoost and CatBoost models for ensemble voting.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.models_dir = Path("/Users/macbookpro13/bitgettrading/models")
        self.models_dir.mkdir(exist_ok=True)
        self.base_trainer = LightGBM1mTrainer(cache_dir)
    
    def train_xgboost_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series
    ) -> Tuple[object, Dict]:
        """
        Train XGBoost model.
        
        Args:
            X_train, y_train: Training data
            X_val, y_val: Validation data
            
        Returns:
            Tuple of (model, metadata)
        """
        if not XGBOOST_AVAILABLE:
            print("❌ XGBoost not available, skipping...")
            return None, {}
        
        print("\n" + "="*80)
        print("🚀 Training XGBoost Model")
        print("="*80)
        
        # XGBoost parameters (similar to LightGBM but XGBoost style)
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 8,
            'learning_rate': 0.03,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 50,
            'reg_alpha': 0.1,
            'reg_lambda': 0.1,
            'tree_method': 'hist',
            'random_state': 42,
        }
        
        # Create DMatrix
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        
        # Train
        evals = [(dtrain, 'train'), (dval, 'val')]
        model = xgb.train(
            params,
            dtrain,
            num_boost_round=1000,
            evals=evals,
            early_stopping_rounds=50,
            verbose_eval=100
        )
        
        # Evaluate
        train_preds = model.predict(dtrain)
        val_preds = model.predict(dval)
        
        train_pred_labels = (train_preds > 0.5).astype(int)
        val_pred_labels = (val_preds > 0.5).astype(int)
        
        train_auc = roc_auc_score(y_train, train_preds)
        val_auc = roc_auc_score(y_val, val_preds)
        train_acc = accuracy_score(y_train, train_pred_labels)
        val_acc = accuracy_score(y_val, val_pred_labels)
        
        print(f"\n📊 XGBoost Performance:")
        print(f"Train AUC: {train_auc:.4f} | Train Accuracy: {train_acc:.4f}")
        print(f"Val AUC:   {val_auc:.4f} | Val Accuracy:   {val_acc:.4f}")
        
        metadata = {
            'model_type': 'xgboost',
            'train_auc': float(train_auc),
            'val_auc': float(val_auc),
            'train_accuracy': float(train_acc),
            'val_accuracy': float(val_acc),
            'best_iteration': model.best_iteration,
            'params': params
        }
        
        return model, metadata
    
    def train_catboost_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series
    ) -> Tuple[object, Dict]:
        """
        Train CatBoost model.
        
        Args:
            X_train, y_train: Training data
            X_val, y_val: Validation data
            
        Returns:
            Tuple of (model, metadata)
        """
        if not CATBOOST_AVAILABLE:
            print("❌ CatBoost not available, skipping...")
            return None, {}
        
        print("\n" + "="*80)
        print("🚀 Training CatBoost Model")
        print("="*80)
        
        # CatBoost parameters
        model = CatBoostClassifier(
            iterations=1000,
            learning_rate=0.03,
            depth=8,
            l2_leaf_reg=0.1,
            random_strength=0.1,
            bagging_temperature=0.8,
            border_count=128,
            loss_function='Logloss',
            eval_metric='AUC',
            early_stopping_rounds=50,
            random_seed=42,
            verbose=100
        )
        
        # Create Pool
        train_pool = Pool(X_train, y_train)
        val_pool = Pool(X_val, y_val)
        
        # Train
        model.fit(
            train_pool,
            eval_set=val_pool,
            use_best_model=True,
            verbose=100
        )
        
        # Evaluate
        train_preds = model.predict_proba(X_train)[:, 1]
        val_preds = model.predict_proba(X_val)[:, 1]
        
        train_pred_labels = (train_preds > 0.5).astype(int)
        val_pred_labels = (val_preds > 0.5).astype(int)
        
        train_auc = roc_auc_score(y_train, train_preds)
        val_auc = roc_auc_score(y_val, val_preds)
        train_acc = accuracy_score(y_train, train_pred_labels)
        val_acc = accuracy_score(y_val, val_pred_labels)
        
        print(f"\n📊 CatBoost Performance:")
        print(f"Train AUC: {train_auc:.4f} | Train Accuracy: {train_acc:.4f}")
        print(f"Val AUC:   {val_auc:.4f} | Val Accuracy:   {val_acc:.4f}")
        
        metadata = {
            'model_type': 'catboost',
            'train_auc': float(train_auc),
            'val_auc': float(val_auc),
            'train_accuracy': float(train_acc),
            'val_accuracy': float(val_acc),
            'best_iteration': model.get_best_iteration(),
            'params': model.get_params()
        }
        
        return model, metadata
    
    def train_all_ensemble_models(self):
        """Train XGBoost and CatBoost models."""
        
        print("="*100)
        print("🚀 ENSEMBLE MODELS TRAINING (XGBoost + CatBoost)")
        print("="*100)
        print()
        
        # Load and process data (reuse base trainer logic)
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
        print("🔄 Processing and combining data...")
        combined_features = []
        combined_targets = []
        
        for idx, df in enumerate(all_data, 1):
            if idx % 50 == 0:
                print(f"   Processing: {idx}/{len(all_data)} tokens...")
            
            # Calculate features
            df_features = self.base_trainer.calculate_advanced_features(df)
            
            # Create target
            target = self.base_trainer.create_target(df_features, lookahead=5, threshold_pct=0.15)
            
            # Remove NaN rows
            df_features = df_features.dropna()
            target = target[df_features.index]
            
            if len(df_features) > 20:
                combined_features.append(df_features)
                combined_targets.append(target)
        
        # Combine all
        X = pd.concat(combined_features, ignore_index=True)
        y = pd.concat(combined_targets, ignore_index=True)
        
        # Select numeric features
        feature_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [col for col in feature_cols if col not in ['timestamp', 'time']]
        X = X[feature_cols]
        
        print(f"\n✅ Combined dataset: {len(X)} samples, {len(feature_cols)} features")
        print(f"   Positive samples: {y.sum()} ({y.mean()*100:.2f}%)\n")
        
        # Train/val split (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"📊 Train: {len(X_train)} samples | Val: {len(X_val)} samples\n")
        
        # Train XGBoost
        xgb_model, xgb_metadata = self.train_xgboost_model(X_train, y_train, X_val, y_val)
        
        # Train CatBoost
        catboost_model, catboost_metadata = self.train_catboost_model(X_train, y_train, X_val, y_val)
        
        # Save models
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_metadata = {'timestamp': timestamp, 'models': {}}
        
        if xgb_model:
            xgb_file = self.models_dir / f"xgboost_1m_{timestamp}.json"
            xgb_model.save_model(str(xgb_file))
            print(f"\n✅ XGBoost saved: {xgb_file.name}")
            all_metadata['models']['xgboost'] = xgb_metadata
            all_metadata['models']['xgboost']['model_file'] = xgb_file.name
        
        if catboost_model:
            catboost_file = self.models_dir / f"catboost_1m_{timestamp}.cbm"
            catboost_model.save_model(str(catboost_file))
            print(f"✅ CatBoost saved: {catboost_file.name}")
            all_metadata['models']['catboost'] = catboost_metadata
            all_metadata['models']['catboost']['model_file'] = catboost_file.name
        
        # Save metadata
        metadata_file = self.models_dir / f"ensemble_models_metadata_{timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(all_metadata, f, indent=2)
        
        print(f"✅ Metadata saved: {metadata_file.name}")
        print()
        print("="*100)
        print("🎉 ENSEMBLE MODELS TRAINING COMPLETE!")
        print("="*100)
        print()
        print("📊 Ensemble Voting Strategy:")
        print("  - LightGBM (already trained)")
        print("  - XGBoost (just trained)" if xgb_model else "  - XGBoost (not available)")
        print("  - CatBoost (just trained)" if catboost_model else "  - CatBoost (not available)")
        print("  - Trade only when 2+ models agree (66%+ consensus)")
        print()
        
        return all_metadata


def main():
    """Train ensemble models."""
    cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    trainer = EnsembleModelsTrainer(cache_dir)
    trainer.train_all_ensemble_models()
    
    print("🚀 Ready to create ensemble voting strategies!")


if __name__ == "__main__":
    main()

