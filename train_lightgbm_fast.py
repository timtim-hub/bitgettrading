"""
Train LightGBM Model FAST - Using All Processors

Optimizations:
- Parallel data loading
- Parallel feature calculation
- All CPU cores for training
- Fast feature engineering
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
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import os

# Use ALL CPU cores
N_JOBS = mp.cpu_count()
print(f"🚀 Using {N_JOBS} CPU cores for maximum speed!")

def load_single_token_data(args):
    """Load and process data for a single token (for parallel processing)."""
    cache_file, cache_dir = args
    try:
        symbol = cache_file.stem.split('_')[0]
        
        with open(cache_file, 'rb') as f:
            df = pickle.load(f)
        
        if len(df) < 50:
            return None
        
        df['symbol'] = symbol
        return df
    except Exception as e:
        return None

def load_all_token_data_parallel(cache_dir: Path = Path("backtest_data")) -> pd.DataFrame:
    """
    Load data from ALL tokens in parallel for maximum speed.
    """
    print("="*80)
    print("📊 LOADING DATA FROM ALL 338 TOKENS (PARALLEL)")
    print("="*80)
    
    # Find all cache files
    cache_files = list(cache_dir.glob("*_1m_30d.pkl"))
    
    if not cache_files:
        # Try alternative format
        cache_files = list(cache_dir.glob("*_1H_30d.pkl"))
    
    if not cache_files:
        raise ValueError("No cache files found! Run data fetcher first.")
    
    print(f"Found {len(cache_files)} cache files")
    print(f"🚀 Loading in parallel using {N_JOBS} cores...\n")
    
    # Load in parallel
    all_data = []
    args_list = [(cf, cache_dir) for cf in cache_files]
    
    with ProcessPoolExecutor(max_workers=N_JOBS) as executor:
        futures = {executor.submit(load_single_token_data, args): args[0] for args in args_list}
        
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                all_data.append(result)
            completed += 1
            if completed % 50 == 0:
                print(f"  ✅ Loaded {completed}/{len(cache_files)} tokens ({len(all_data)} valid)")
    
    if not all_data:
        raise ValueError("No data loaded! Check backtest_data/ directory")
    
    # Combine all data
    print(f"\n📊 Combining {len(all_data)} token datasets...")
    combined_df = pd.concat(all_data, ignore_index=True)
    
    print(f"\n{'='*80}")
    print(f"✅ LOADED {len(all_data)} TOKENS")
    print(f"📊 Total rows: {len(combined_df):,}")
    print(f"📅 Date range: {combined_df['timestamp'].min()} to {combined_df['timestamp'].max()}")
    print(f"{'='*80}\n")
    
    return combined_df

def create_target_variable(df: pd.DataFrame, horizon: int = 5, threshold: float = 0.003) -> pd.DataFrame:
    """
    Create binary target variable.
    
    Target: Price goes up by threshold%+ in next 'horizon' periods
    """
    df = df.copy()
    
    # Calculate future return
    future_price = df['close'].shift(-horizon)
    future_return = (future_price / df['close'] - 1)
    
    # Binary target: 1 if return >= threshold, 0 otherwise
    df['target'] = (future_return >= threshold).astype(int)
    
    # Remove rows where target couldn't be calculated
    df = df.dropna(subset=['target'])
    
    print(f"   Target threshold: {threshold*100:.2f}% in {horizon} periods")
    print(f"   Positive samples: {df['target'].sum():,} ({df['target'].mean()*100:.2f}%)")
    print(f"   Total samples: {len(df):,}\n")
    
    return df

def train_lightgbm_model_fast(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    params: dict = None
) -> Tuple[lgb.Booster, dict]:
    """
    Train LightGBM model with maximum speed optimizations.
    """
    print("="*80)
    print("🚀 TRAINING LIGHTGBM MODEL (FAST MODE)")
    print("="*80)
    
    if params is None:
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 63,  # Increased for better accuracy
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
            'num_threads': N_JOBS,  # Use ALL cores!
            'device': 'cpu',
            'max_bin': 255,
        }
    
    print(f"📊 Training samples: {len(X_train):,}")
    print(f"📊 Validation samples: {len(X_val):,}")
    print(f"📊 Features: {len(X_train.columns)}")
    print(f"🚀 Using {N_JOBS} CPU threads for training!\n")
    
    # Create datasets
    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
    
    # Train model with early stopping
    callbacks = [
        lgb.early_stopping(stopping_rounds=50),
        lgb.log_evaluation(period=100)
    ]
    
    print("🚀 Training model (this may take a few minutes)...\n")
    model = lgb.train(
        params,
        train_data,
        num_boost_round=1500,  # More rounds for better accuracy
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
    print(f"   AUC: {auc:.4f}")
    
    # Feature importance
    feature_importance = dict(zip(X_train.columns, model.feature_importance(importance_type='gain')))
    sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n📊 TOP 10 FEATURES:")
    for i, (feature, importance) in enumerate(sorted_features[:10], 1):
        print(f"   {i}. {feature}: {importance:.0f}")
    
    metrics = {
        'accuracy': accuracy,
        'auc': auc,
        'best_iteration': model.best_iteration,
        'num_features': len(X_train.columns),
        'train_samples': len(X_train),
        'val_samples': len(X_val),
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
    
    # Save feature names
    feature_path = models_dir / f"lightgbm_{version}_{timestamp}_features.txt"
    with open(feature_path, 'w') as f:
        for feature in sorted(feature_importance.keys(), key=lambda x: feature_importance[x], reverse=True):
            f.write(f"{feature}\n")
    print(f"✅ Feature names saved to: {feature_path}")
    
    # Save metadata
    metadata = {
        'version': version,
        'timestamp': timestamp,
        'model_path': str(model_path),
        'metrics': metrics,
        'top_10_features': sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]
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
    """Main training pipeline - FAST MODE."""
    print("\n" + "="*80)
    print("🧠 LIGHTGBM MODEL TRAINING - FAST MODE (ALL PROCESSORS)")
    print("="*80 + "\n")
    
    start_time = datetime.now()
    
    # 1. Load all token data in parallel
    print("📊 Step 1: Loading data from all tokens (parallel)...")
    df = load_all_token_data_parallel()
    
    # 2. Calculate features
    print("="*80)
    print("🔧 Step 2: CALCULATING FEATURES")
    print("="*80)
    print("🚀 Calculating features (this may take a few minutes)...")
    df_with_features = calculate_all_features(df)
    print(f"✅ Features calculated: {df_with_features.shape[1]} columns\n")
    
    # 3. Create target variable
    print("="*80)
    print("🎯 Step 3: CREATING TARGET VARIABLE")
    print("="*80)
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
    print("📊 Step 4: Splitting data...")
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"✅ Train: {len(X_train):,} | Val: {len(X_val):,}\n")
    
    # 6. Train model (FAST MODE - all processors)
    print("="*80)
    print("🚀 Step 5: TRAINING MODEL (FAST MODE)")
    print("="*80)
    model, feature_importance, metrics = train_lightgbm_model_fast(
        X_train, y_train, X_val, y_val
    )
    
    # 7. Save model
    print("\n" + "="*80)
    print("💾 Step 6: SAVING MODEL")
    print("="*80)
    model_path = save_model(model, feature_importance, metrics, version="v1")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "="*80)
    print("🎉 TRAINING COMPLETE!")
    print("="*80)
    print(f"\n📊 Final Metrics:")
    print(f"   Validation Accuracy: {metrics['accuracy']*100:.2f}%")
    print(f"   Validation AUC: {metrics['auc']:.4f}")
    print(f"   Best Iteration: {metrics['best_iteration']}")
    print(f"   Training Time: {elapsed/60:.1f} minutes")
    print(f"\n🎯 Model ready for backtesting!")
    print(f"   Use: models/lightgbm_v1_latest.txt")
    print(f"="*80 + "\n")
    
    return model, metrics

if __name__ == "__main__":
    # Set environment variable for maximum threads
    os.environ['OMP_NUM_THREADS'] = str(N_JOBS)
    os.environ['MKL_NUM_THREADS'] = str(N_JOBS)
    os.environ['NUMEXPR_NUM_THREADS'] = str(N_JOBS)
    
    main()

