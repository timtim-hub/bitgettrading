"""
Train LightGBM Model on ALL 338 Tokens
Trains a single model on combined data from all tokens for generalization.
"""

import pandas as pd
import numpy as np
import pickle
import lightgbm as lgb
from pathlib import Path
from typing import List, Tuple
from ml_feature_engineering import calculate_all_features, get_feature_list
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
import json
from datetime import datetime

def load_all_token_data(cache_dir: Path = Path("backtest_data")) -> pd.DataFrame:
    """
    Load data from ALL tokens and combine into single dataset.
    """
    print("="*80)
    print("📊 LOADING DATA FROM ALL 338 TOKENS")
    print("="*80)
    
    all_data = []
    cache_files = list(cache_dir.glob("*_1m_30d.pkl"))
    
    if not cache_files:
        # Try alternative format
        cache_files = list(cache_dir.glob("*_1H_30d.pkl"))
    
    print(f"Found {len(cache_files)} cache files\n")
    
    for i, cache_file in enumerate(cache_files, 1):
        try:
            symbol = cache_file.stem.split('_')[0]
            
            with open(cache_file, 'rb') as f:
                df = pickle.load(f)
            
            if len(df) < 50:
                continue
            
            df['symbol'] = symbol  # Add symbol column for tracking
            all_data.append(df)
            
            if i % 50 == 0:
                print(f"✅ Loaded {i}/{len(cache_files)} tokens ({len(all_data)} valid)")
        
        except Exception as e:
            print(f"❌ Error loading {cache_file.name}: {e}")
            continue
    
    if not all_data:
        raise ValueError("No data loaded! Check backtest_data/ directory")
    
    # Combine all data
    combined_df = pd.concat(all_data, ignore_index=True)
    
    print(f"\n{'='*80}")
    print(f"✅ LOADED {len(all_data)} TOKENS")
    print(f"📊 Total rows: {len(combined_df):,}")
    print(f"📅 Date range: {combined_df['timestamp'].min()} to {combined_df['timestamp'].max()}")
    print(f"{'='*80}\n")
    
    return combined_df

def create_target_variable(df: pd.DataFrame, horizon: int = 5, threshold: float = 0.003) -> pd.DataFrame:
    """
    Create target variable: will price go up by threshold% in next N candles?
    
    Args:
        horizon: Number of candles to look ahead
        threshold: Minimum % change to consider as "up" (0.003 = 0.3%)
    
    Returns:
        DataFrame with 'target' column (1 = up, 0 = down/flat)
    """
    print(f"🎯 Creating target variable (horizon={horizon}, threshold={threshold*100:.2f}%)")
    
    # Group by symbol to avoid look-ahead across different tokens
    df = df.sort_values(['symbol', 'timestamp']).reset_index(drop=True)
    
    # Calculate future return for each symbol separately
    df['future_return'] = df.groupby('symbol')['close'].transform(
        lambda x: x.pct_change(horizon).shift(-horizon)
    )
    
    # Binary classification: 1 if price goes up by threshold, 0 otherwise
    df['target'] = (df['future_return'] > threshold).astype(int)
    
    # Drop rows where we don't have future data
    df = df[df['target'].notna()].copy()
    
    # Print target distribution
    target_counts = df['target'].value_counts()
    print(f"✅ Target distribution:")
    print(f"   Class 0 (Down/Flat): {target_counts.get(0, 0):,} ({target_counts.get(0, 0)/len(df)*100:.1f}%)")
    print(f"   Class 1 (Up): {target_counts.get(1, 0):,} ({target_counts.get(1, 0)/len(df)*100:.1f}%)")
    print(f"   Total samples: {len(df):,}\n")
    
    return df

def train_lightgbm_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    params: dict = None
) -> Tuple[lgb.Booster, dict]:
    """
    Train LightGBM model with early stopping.
    """
    print("="*80)
    print("🚀 TRAINING LIGHTGBM MODEL")
    print("="*80)
    
    if params is None:
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'max_depth': -1,
            'min_data_in_leaf': 20,
            'lambda_l1': 0.1,
            'lambda_l2': 0.1,
            'verbose': -1,
            'force_col_wise': True,
            'num_threads': 8
        }
    
    print(f"📊 Training samples: {len(X_train):,}")
    print(f"📊 Validation samples: {len(X_val):,}")
    print(f"📊 Features: {len(X_train.columns)}")
    print(f"\nHyperparameters:")
    for k, v in params.items():
        print(f"  {k}: {v}")
    print()
    
    # Create datasets
    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
    
    # Train model with early stopping
    callbacks = [
        lgb.early_stopping(stopping_rounds=50),
        lgb.log_evaluation(period=100)
    ]
    
    model = lgb.train(
        params,
        train_data,
        num_boost_round=1000,
        valid_sets=[train_data, val_data],
        valid_names=['train', 'val'],
        callbacks=callbacks
    )
    
    print(f"\n✅ Training complete! Best iteration: {model.best_iteration}")
    
    # Evaluate on validation set
    y_pred_proba = model.predict(X_val, num_iteration=model.best_iteration)
    y_pred = (y_pred_proba > 0.5).astype(int)
    
    accuracy = accuracy_score(y_val, y_pred)
    auc = roc_auc_score(y_val, y_pred_proba)
    
    print(f"\n📊 VALIDATION METRICS:")
    print(f"   Accuracy: {accuracy*100:.2f}%")
    print(f"   AUC-ROC: {auc:.4f}")
    print(f"\n{classification_report(y_val, y_pred, target_names=['Down/Flat', 'Up'])}")
    
    # Feature importance (convert to native Python types for JSON serialization)
    feature_importance = dict(zip(X_train.columns, [int(x) for x in model.feature_importance()]))
    feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
    
    print(f"\n🔝 TOP 20 MOST IMPORTANT FEATURES:")
    for i, (feat, importance) in enumerate(list(feature_importance.items())[:20], 1):
        print(f"   {i:2d}. {feat:30s} {importance:8.0f}")
    
    metrics = {
        'accuracy': float(accuracy),
        'auc': float(auc),
        'best_iteration': int(model.best_iteration),
        'num_features': len(X_train.columns),
        'train_samples': len(X_train),
        'val_samples': len(X_val)
    }
    
    return model, feature_importance, metrics

def save_model(model: lgb.Booster, feature_importance: dict, metrics: dict, version: str = "v1"):
    """Save model, feature importance, and metadata."""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save model
    model_path = models_dir / f"lightgbm_{version}_{timestamp}.txt"
    model.save_model(str(model_path))
    print(f"\n✅ Model saved to: {model_path}")
    
    # Save feature importance
    importance_path = models_dir / f"feature_importance_{version}_{timestamp}.json"
    with open(importance_path, 'w') as f:
        json.dump(feature_importance, f, indent=2)
    print(f"✅ Feature importance saved to: {importance_path}")
    
    # Save metadata
    metadata = {
        'version': version,
        'timestamp': timestamp,
        'model_path': str(model_path),
        'metrics': metrics,
        'top_10_features': list(feature_importance.items())[:10]
    }
    
    metadata_path = models_dir / f"model_metadata_{version}_{timestamp}.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✅ Metadata saved to: {metadata_path}")
    
    # Save latest symlink
    latest_model = models_dir / f"lightgbm_{version}_latest.txt"
    if latest_model.exists():
        latest_model.unlink()
    latest_model.symlink_to(model_path.name)
    print(f"✅ Latest model link: {latest_model}")
    
    return model_path

def main():
    """Main training pipeline."""
    print("\n" + "="*80)
    print("🧠 LIGHTGBM MODEL TRAINING - ALL 338 TOKENS")
    print("="*80 + "\n")
    
    # 1. Load all token data
    df = load_all_token_data()
    
    # 2. Calculate features
    print("="*80)
    print("🔧 CALCULATING FEATURES")
    print("="*80)
    df_with_features = calculate_all_features(df)
    
    # 3. Create target variable
    df_with_features = create_target_variable(df_with_features, horizon=5, threshold=0.003)
    
    # 4. Prepare training data
    feature_cols = get_feature_list()
    # Filter to only features that exist in our dataframe
    feature_cols = [f for f in feature_cols if f in df_with_features.columns]
    
    X = df_with_features[feature_cols]
    y = df_with_features['target']
    
    print(f"="*80)
    print(f"📊 DATASET SUMMARY")
    print(f"="*80)
    print(f"Features: {len(feature_cols)}")
    print(f"Samples: {len(X):,}")
    print(f"Target mean: {y.mean():.3f} (class balance)")
    print(f"="*80 + "\n")
    
    # 5. Train/test split (stratified by target)
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # 6. Train model
    model, feature_importance, metrics = train_lightgbm_model(
        X_train, y_train, X_val, y_val
    )
    
    # 7. Save model
    model_path = save_model(model, feature_importance, metrics, version="v1")
    
    print("\n" + "="*80)
    print("🎉 TRAINING COMPLETE!")
    print("="*80)
    print(f"\n📊 Final Metrics:")
    print(f"   Validation Accuracy: {metrics['accuracy']*100:.2f}%")
    print(f"   Validation AUC: {metrics['auc']:.4f}")
    print(f"   Best Iteration: {metrics['best_iteration']}")
    print(f"\n🎯 Model ready for backtesting!")
    print(f"   Use: models/lightgbm_v1_latest.txt")
    print(f"="*80 + "\n")
    
    return model, metrics

if __name__ == "__main__":
    # Check if lightgbm is installed
    try:
        import lightgbm as lgb
    except ImportError:
        print("❌ LightGBM not installed!")
        print("📦 Install with: pip install lightgbm")
        exit(1)
    
    model, metrics = main()

