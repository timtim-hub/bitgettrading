"""
Train LightGBM Models for Live Trading - ALL Bitget Futures Tokens

This script trains optimized LightGBM models for short-term trading (1-10 min):
- Trains on 6 months of 5-minute candle data
- Optimized for high win rate on short-term predictions
- Saves models for each token individually
- Uses all CPU cores for maximum speed

Models are saved in models/live_trading/ directory.
"""

import asyncio
import pickle
import lightgbm as lgb
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import optuna
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, precision_score, recall_score, f1_score
import warnings
import time
from tqdm import tqdm
warnings.filterwarnings('ignore')

from data_fetcher import HistoricalDataFetcher
from ml_feature_engineering import calculate_all_features, get_feature_list

# Configuration - MAXIMUM POWER MODE! 💪
CPU_COUNT = mp.cpu_count()
# MAXIMUM POWER: Use 4x CPU cores for aggressive parallelization
# M1 Macs can handle this efficiently with good OS scheduling
N_JOBS = CPU_COUNT  # For LightGBM internal threading
TRAINING_WORKERS = CPU_COUNT * 4  # 4x for MAXIMUM POWER (32 workers on M1!)
DATA_FETCH_CONCURRENT = 100  # MAXIMUM concurrent requests for I/O-bound fetching

MODELS_DIR = Path("models/live_trading")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR = Path("models/live_trading/metadata")
METADATA_DIR.mkdir(parents=True, exist_ok=True)

# Training parameters optimized for MAXIMUM prediction accuracy
TRAINING_CONFIG = {
    "timeframe": "5m",  # 5-minute candles
    "days": 180,  # 6 months of data
    "prediction_horizon": 2,  # Predict 2 candles ahead (10 minutes)
    "min_price_change": 0.002,  # 0.2% minimum price change to be significant
    "min_samples": 1000,  # Minimum samples needed to train
    "train_test_split": 0.8,  # 80% train, 20% validation
    "early_stopping_rounds": 100,
    "num_boost_round": 3000,  # Increased for better accuracy
    "n_trials": 100,  # More Optuna trials for better hyperparameters
}


def create_short_term_target(df: pd.DataFrame, horizon: int = 2, threshold: float = 0.002) -> pd.Series:
    """
    Create target variable optimized for short-term trading (1-10 min).
    
    Target: Will price move up/down by threshold% in next 'horizon' candles?
    - 1: Price will go UP by threshold% (LONG signal)
    - 0: Price will go DOWN by threshold% (SHORT signal)
    - -1: No significant movement (NEUTRAL - excluded from training)
    
    Args:
        df: DataFrame with 'close' column
        horizon: Number of candles to look ahead (2 = 10 min for 5m candles)
        threshold: Minimum price change to be significant (0.002 = 0.2%)
    
    Returns:
        Series with target values (1, 0, or -1)
    """
    close = df['close'].values
    
    # Calculate future price change
    future_price = np.roll(close, -horizon)
    price_change = (future_price - close) / close
    
    # Create target: 1 = up, 0 = down, -1 = neutral
    target = np.where(price_change >= threshold, 1,  # Long
                     np.where(price_change <= -threshold, 0, -1))  # Short or Neutral
    
    # Set last 'horizon' values to -1 (no future data)
    target[-horizon:] = -1
    
    return pd.Series(target, index=df.index)


def optimize_lightgbm_params(X_train: pd.DataFrame, y_train: pd.Series, 
                            X_val: pd.DataFrame, y_val: pd.Series) -> dict:
    """
    Optimize LightGBM hyperparameters using Optuna for MAXIMUM prediction accuracy.
    
    Enhanced for highest win rate:
    - More aggressive hyperparameter search
    - Focus on accuracy (win rate) as primary metric
    - Better regularization to prevent overfitting
    """
    def objective(trial):
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            # Expanded search space for better results
            'num_leaves': trial.suggest_int('num_leaves', 31, 512),  # Increased range
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.2, log=True),  # Lower LR for stability
            'feature_fraction': trial.suggest_float('feature_fraction', 0.5, 1.0),
            'bagging_fraction': trial.suggest_float('bagging_fraction', 0.5, 1.0),
            'bagging_freq': trial.suggest_int('bagging_freq', 1, 10),
            'min_child_samples': trial.suggest_int('min_child_samples', 10, 200),  # Wider range
            'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 0.5),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 5.0),  # L1 regularization
            'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 5.0),  # L2 regularization
            'max_depth': trial.suggest_int('max_depth', 5, 20),  # Deeper trees
            'min_data_in_leaf': trial.suggest_int('min_data_in_leaf', 5, 100),
            'lambda_l1': trial.suggest_float('lambda_l1', 0.0, 5.0),
            'lambda_l2': trial.suggest_float('lambda_l2', 0.0, 5.0),
            'num_threads': 1,  # Use 1 thread per process (we have many processes)
            'verbosity': -1,
            'force_row_wise': True,
        }
        
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        model = lgb.train(
            params,
            train_data,
            num_boost_round=TRAINING_CONFIG['num_boost_round'],
            valid_sets=[val_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=TRAINING_CONFIG['early_stopping_rounds'], verbose=False),
                lgb.log_evaluation(period=0)
            ]
        )
        
        # Predict on validation set
        y_pred_proba = model.predict(X_val, num_iteration=model.best_iteration)
        y_pred = (y_pred_proba > 0.5).astype(int)
        
        # Calculate metrics (focus on win rate = accuracy)
        accuracy = accuracy_score(y_val, y_pred)
        precision = precision_score(y_val, y_pred, zero_division=0)
        recall = recall_score(y_val, y_pred, zero_division=0)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        
        # Optimize for MAXIMUM win rate (accuracy) - primary goal
        # Weighted score: 70% accuracy, 15% precision, 15% recall
        # Accuracy is most important for trading success
        score = 0.7 * accuracy + 0.15 * precision + 0.15 * recall
        
        return score
    
    # Use n_jobs=1 for Optuna since we're already parallelizing at the model level
    # Use unique study name with timestamp to avoid conflicts in parallel training
    study_name = f'lightgbm_opt_{int(time.time() * 1000000)}'  # Microsecond precision
    study = optuna.create_study(
        direction='maximize', 
        study_name=study_name,
        # Use in-memory storage to avoid conflicts in parallel training
        storage=None
    )
    # Optimize with progress tracking
    # Note: Optuna's progress bar might not show in parallel training, but trials are logged
    study.optimize(
        objective, 
        n_trials=TRAINING_CONFIG['n_trials'], 
        show_progress_bar=False,  # Disable to avoid conflicts with tqdm
        n_jobs=1
    )
    
    best_params = study.best_params
    
    # Add fixed parameters
    best_params.update({
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'num_threads': 1,  # Use 1 thread per process (we have many processes)
        'verbosity': -1,
        'force_row_wise': True,
    })
    
    return best_params


def train_model_for_token(symbol: str, df: pd.DataFrame) -> Optional[Dict]:
    """
    Train LightGBM model for a single token.
    
    Returns:
        Dict with model path, metrics, and metadata, or None if training failed
    """
    try:
        # Reduced verbosity for parallel training (progress bar handles main output)
        # Calculate features
        df_features = calculate_all_features(df.copy())
        
        if len(df_features) < TRAINING_CONFIG['min_samples']:
            return None
        
        # Create target variable
        target = create_short_term_target(df_features, 
                                         horizon=TRAINING_CONFIG['prediction_horizon'],
                                         threshold=TRAINING_CONFIG['min_price_change'])
        
        # Filter out neutral samples (-1)
        valid_mask = target != -1
        df_features = df_features[valid_mask].copy()
        target = target[valid_mask].copy()
        
        if len(df_features) < TRAINING_CONFIG['min_samples']:
            return None
        
        # Get feature list
        feature_list = get_feature_list()
        available_features = [f for f in feature_list if f in df_features.columns]
        
        if len(available_features) < len(feature_list) * 0.7:
            return None
        
        # Prepare data
        X = df_features[available_features].fillna(0)
        y = target.values
        
        # Train/test split
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, 
            test_size=1 - TRAINING_CONFIG['train_test_split'],
            random_state=42,
            stratify=y
        )
        
        # Optimize hyperparameters (reduced verbosity)
        best_params = optimize_lightgbm_params(X_train, y_train, X_val, y_val)
        
        # Train final model with best parameters
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        model = lgb.train(
            best_params,
            train_data,
            num_boost_round=TRAINING_CONFIG['num_boost_round'],
            valid_sets=[val_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=TRAINING_CONFIG['early_stopping_rounds'], verbose=False),
                lgb.log_evaluation(period=100)
            ]
        )
        
        # Evaluate model
        y_pred_proba = model.predict(X_val, num_iteration=model.best_iteration)
        y_pred = (y_pred_proba > 0.5).astype(int)
        
        accuracy = accuracy_score(y_val, y_pred)
        precision = precision_score(y_val, y_pred, zero_division=0)
        recall = recall_score(y_val, y_pred, zero_division=0)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        auc = roc_auc_score(y_val, y_pred_proba)
        
        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"{symbol}_lightgbm_{timestamp}.txt"
        model_path = MODELS_DIR / model_filename
        model.save_model(str(model_path))
        
        # Create symlink to latest
        latest_path = MODELS_DIR / f"{symbol}_latest.txt"
        if latest_path.exists() or latest_path.is_symlink():
            latest_path.unlink()
        latest_path.symlink_to(model_filename)
        
        # Save feature list
        feature_path = MODELS_DIR / f"{symbol}_features.txt"
        with open(feature_path, 'w') as f:
            for feat in available_features:
                f.write(f"{feat}\n")
        
        # Save metadata
        metadata = {
            "symbol": symbol,
            "timestamp": timestamp,
            "model_path": str(model_path),
            "feature_path": str(feature_path),
            "training_config": TRAINING_CONFIG,
            "metrics": {
                "accuracy": float(accuracy),
                "precision": float(precision),
                "recall": float(recall),
                "f1_score": float(f1),
                "auc": float(auc),
                "best_iteration": int(model.best_iteration),
            },
            "data_info": {
                "train_samples": int(len(X_train)),
                "val_samples": int(len(X_val)),
                "num_features": int(len(available_features)),
                "date_range": {
                    "start": str(df['timestamp'].min()),
                    "end": str(df['timestamp'].max()),
                }
            },
            "hyperparameters": best_params,
        }
        
        metadata_path = METADATA_DIR / f"{symbol}_metadata_{timestamp}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return metadata
        
    except Exception as e:
        print(f"  ❌ Error training {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def fetch_all_symbols() -> List[str]:
    """Fetch all active Bitget USDT-M futures symbols."""
    import aiohttp
    
    endpoint = "https://api.bitget.com/api/v2/mix/market/contracts"
    params = {"productType": "USDT-FUTURES"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as response:
                if response.status != 200:
                    print(f"❌ Failed to fetch symbols: HTTP {response.status}")
                    return []
                
                data = await response.json()
                
                if data.get("code") != "00000":
                    print(f"❌ API Error: {data.get('msg')}")
                    return []
                
                contracts = data.get("data", [])
                
                # Filter to active contracts only
                symbols = [
                    contract.get("symbol")
                    for contract in contracts
                    if contract.get("symbolStatus") == "normal" and contract.get("symbol")
                ]
                
                print(f"✅ Found {len(symbols)} active Bitget futures symbols")
                return symbols
                
    except Exception as e:
        print(f"❌ Exception fetching symbols: {e}")
        return []


def train_model_wrapper(args: Tuple[str, pd.DataFrame]) -> Optional[Dict]:
    """
    Wrapper function for parallel model training.
    Must be at module level for pickling.
    """
    symbol, df = args
    return train_model_for_token(symbol, df)


async def fetch_data_parallel(fetcher: HistoricalDataFetcher, symbols: List[str], 
                              max_concurrent: int = 20) -> Dict[str, pd.DataFrame]:
    """
    Fetch data for all symbols in parallel (async I/O) with progress bar.
    
    Args:
        fetcher: HistoricalDataFetcher instance
        symbols: List of symbols to fetch
        max_concurrent: Maximum concurrent requests
        
    Returns:
        Dict mapping symbol to DataFrame
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}
    start_time = time.time()
    
    async def fetch_one(symbol: str, pbar: tqdm):
        async with semaphore:
            try:
                df = await fetcher.fetch_candles(
                    symbol=symbol,
                    timeframe=TRAINING_CONFIG['timeframe'],
                    days=TRAINING_CONFIG['days'],
                    use_cache=True
                )
                pbar.update(1)
                return symbol, df
            except Exception as e:
                pbar.update(1)
                return symbol, None
    
    # Create progress bar
    pbar = tqdm(total=len(symbols), desc="📥 Fetching data", unit="symbol", 
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]')
    
    # Fetch all in parallel
    tasks = [fetch_one(symbol, pbar) for symbol in symbols]
    fetched = await asyncio.gather(*tasks)
    pbar.close()
    
    # Build results dict
    for symbol, df in fetched:
        if df is not None and len(df) >= TRAINING_CONFIG['min_samples']:
            results[symbol] = df
    
    elapsed = time.time() - start_time
    print(f"  ✅ Fetched data for {len(results)}/{len(symbols)} symbols ({elapsed:.1f}s)")
    
    return results


def train_models_parallel(symbol_data: Dict[str, pd.DataFrame], 
                          max_workers: int = None) -> List[Dict]:
    """
    Train models for all symbols in parallel (CPU-bound) with progress bar.
    
    Args:
        symbol_data: Dict mapping symbol to DataFrame
        max_workers: Number of parallel workers (default: CPU count)
        
    Returns:
        List of training results (metadata dicts)
    """
    if max_workers is None:
        max_workers = N_JOBS
    
    print(f"  🚀 Training {len(symbol_data)} models in parallel ({max_workers} workers)...")
    
    # Prepare arguments for parallel processing
    args_list = [(symbol, df) for symbol, df in symbol_data.items()]
    
    results = []
    successful = 0
    failed = 0
    start_time = time.time()
    completed_times = []
    
    # Create progress bar
    pbar = tqdm(total=len(symbol_data), desc="🚀 Training models", unit="model",
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]')
    
    # Use ProcessPoolExecutor for CPU-bound training
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_symbol = {
            executor.submit(train_model_wrapper, args): args[0] 
            for args in args_list
        }
        
        # Process completed tasks
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            task_start = time.time()
            try:
                result = future.result()
                task_time = time.time() - task_start
                completed_times.append(task_time)
                
                if result:
                    results.append(result)
                    successful += 1
                    accuracy = result['metrics']['accuracy'] * 100
                    # Update progress bar with accuracy info
                    pbar.set_postfix({
                        'success': successful,
                        'failed': failed,
                        'avg_acc': f"{np.mean([r['metrics']['accuracy']*100 for r in results]):.1f}%" if results else "0%"
                    })
                    pbar.update(1)
                else:
                    failed += 1
                    pbar.update(1)
            except Exception as e:
                failed += 1
                pbar.update(1)
    
    pbar.close()
    
    # Calculate timing stats
    elapsed = time.time() - start_time
    avg_time = np.mean(completed_times) if completed_times else 0
    remaining_estimate = avg_time * (len(symbol_data) - len(results)) / max_workers if max_workers > 0 else 0
    
    print(f"\n  📊 Training complete: {successful} successful, {failed} failed ({elapsed:.1f}s)")
    if completed_times:
        print(f"  ⏱️  Average time per model: {avg_time:.1f}s")
    
    return results


async def main():
    """Main training function with parallel processing."""
    print("="*80)
    print("🚀 LIGHTGBM TRAINING FOR LIVE TRADING (PARALLEL)")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  Timeframe: {TRAINING_CONFIG['timeframe']}")
    print(f"  Data period: {TRAINING_CONFIG['days']} days (6 months)")
    print(f"  Prediction horizon: {TRAINING_CONFIG['prediction_horizon']} candles ({TRAINING_CONFIG['prediction_horizon'] * 5} minutes)")
    print(f"  Min price change: {TRAINING_CONFIG['min_price_change']*100:.2f}%")
    print(f"  CPU cores: {CPU_COUNT}")
    print(f"  Training workers: {TRAINING_WORKERS} (4x CPU cores - MAXIMUM POWER! 💪)")
    print(f"  Data fetch concurrent: {DATA_FETCH_CONCURRENT} (MAXIMUM POWER! 🚀)")
    print(f"  Models directory: {MODELS_DIR}")
    print("="*80)
    
    start_time = time.time()
    
    # Fetch all symbols
    print("\n📋 Fetching all Bitget futures symbols...")
    all_symbols = await fetch_all_symbols()
    
    if not all_symbols:
        print("❌ No symbols found! Using fallback list...")
        # Fallback to symbols from file
        try:
            with open("all_bitget_symbols.txt", "r") as f:
                all_symbols = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print("❌ No symbols available!")
            return
    
    print(f"✅ Will train models for {len(all_symbols)} symbols\n")
    
    # Initialize data fetcher
    fetcher = HistoricalDataFetcher()
    
    # PHASE 1: Fetch all data in parallel (async I/O)
    print("="*80)
    print("PHASE 1: Fetching Historical Data (Parallel)")
    print("="*80)
    data_start = time.time()
    symbol_data = await fetch_data_parallel(fetcher, all_symbols, max_concurrent=DATA_FETCH_CONCURRENT)
    data_time = time.time() - data_start
    print(f"\n✅ Data fetching complete: {len(symbol_data)}/{len(all_symbols)} symbols ({data_time:.1f}s)")
    
    if not symbol_data:
        print("❌ No data available for training!")
        return
    
    # PHASE 2: Train all models in parallel (CPU-bound)
    print("\n" + "="*80)
    print("PHASE 2: Training Models (Parallel)")
    print("="*80)
    train_start = time.time()
    results = train_models_parallel(symbol_data, max_workers=TRAINING_WORKERS)
    train_time = time.time() - train_start
    print(f"\n✅ Model training complete: {len(results)} models ({train_time:.1f}s)")
    
    total_time = time.time() - start_time
    
    # Summary
    print("\n" + "="*80)
    print("🎯 TRAINING SUMMARY")
    print("="*80)
    print(f"Total symbols: {len(all_symbols)}")
    print(f"Symbols with data: {len(symbol_data)}")
    print(f"Successfully trained: {len(results)}")
    print(f"Failed: {len(symbol_data) - len(results)}")
    if len(symbol_data) > 0:
        print(f"Success rate: {len(results)/len(symbol_data)*100:.1f}%")
    
    print(f"\n⏱️  Timing:")
    print(f"  Data fetching: {data_time:.1f}s")
    print(f"  Model training: {train_time:.1f}s")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"  Average per model: {train_time/len(results):.1f}s" if results else "")
    
    if results:
        avg_accuracy = np.mean([r['metrics']['accuracy'] for r in results])
        avg_precision = np.mean([r['metrics']['precision'] for r in results])
        avg_recall = np.mean([r['metrics']['recall'] for r in results])
        avg_f1 = np.mean([r['metrics']['f1_score'] for r in results])
        
        print(f"\n📊 Average Metrics:")
        print(f"  Accuracy (Win Rate): {avg_accuracy:.4f} ({avg_accuracy*100:.2f}%)")
        print(f"  Precision: {avg_precision:.4f}")
        print(f"  Recall: {avg_recall:.4f}")
        print(f"  F1 Score: {avg_f1:.4f}")
        
        # Save summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(all_symbols),
            "symbols_with_data": len(symbol_data),
            "successful": len(results),
            "failed": len(symbol_data) - len(results),
            "success_rate": len(results)/len(symbol_data) if symbol_data else 0,
            "timing": {
                "data_fetching_seconds": float(data_time),
                "model_training_seconds": float(train_time),
                "total_seconds": float(total_time),
                "avg_per_model_seconds": float(train_time/len(results)) if results else 0,
            },
            "average_metrics": {
                "accuracy": float(avg_accuracy),
                "precision": float(avg_precision),
                "recall": float(avg_recall),
                "f1_score": float(avg_f1),
            },
            "training_config": TRAINING_CONFIG,
        }
        
        summary_path = MODELS_DIR / "training_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n💾 Summary saved: {summary_path}")
    
    print("="*80)
    print("✅ Training complete!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

