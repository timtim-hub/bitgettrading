"""
LightGBM Live Trading Predictor

Loads and uses trained LightGBM models for live trading predictions.
Optimized for short-term trading (1-10 minutes) with high win rate.
"""

import lightgbm as lgb
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple
import json
from datetime import datetime

from ml_feature_engineering import calculate_all_features, get_feature_list


class LightGBMLivePredictor:
    """
    LightGBM predictor for live trading.
    
    Loads per-token models and makes predictions for short-term trades.
    """
    
    def __init__(self, models_dir: Path = Path("models/live_trading")):
        """Initialize predictor with models directory."""
        self.models_dir = models_dir
        self.models: Dict[str, lgb.Booster] = {}
        self.features: Dict[str, list] = {}
        self.metadata: Dict[str, dict] = {}
        self.loaded_symbols = set()
        
    def load_model(self, symbol: str) -> bool:
        """
        Load LightGBM model for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            
        Returns:
            True if model loaded successfully, False otherwise
        """
        if symbol in self.loaded_symbols:
            return True  # Already loaded
        
        try:
            # Try to load latest model
            model_path = self.models_dir / f"{symbol}_latest.txt"
            
            if not model_path.exists() or not model_path.is_file():
                # Try to find any model for this symbol
                model_files = list(self.models_dir.glob(f"{symbol}_lightgbm_*.txt"))
                if not model_files:
                    return False
                model_path = max(model_files, key=lambda p: p.stat().st_mtime)
            
            # Resolve symlink if needed
            if model_path.is_symlink():
                model_path = model_path.resolve()
            
            # Load model
            model = lgb.Booster(model_file=str(model_path))
            self.models[symbol] = model
            
            # Load features
            feature_path = self.models_dir / f"{symbol}_features.txt"
            if feature_path.exists():
                with open(feature_path, 'r') as f:
                    features = [line.strip() for line in f if line.strip()]
                self.features[symbol] = features
            else:
                # Fallback to default features
                self.features[symbol] = get_feature_list()
            
            # Load metadata if available
            metadata_files = list(self.models_dir.glob(f"metadata/{symbol}_metadata_*.json"))
            if metadata_files:
                latest_metadata = max(metadata_files, key=lambda p: p.stat().st_mtime)
                with open(latest_metadata, 'r') as f:
                    self.metadata[symbol] = json.load(f)
            
            self.loaded_symbols.add(symbol)
            return True
            
        except Exception as e:
            print(f"⚠️ Error loading model for {symbol}: {e}")
            return False
    
    def predict(
        self, 
        symbol: str, 
        df: pd.DataFrame,
        confidence_threshold: float = 0.65
    ) -> Tuple[str, float, float]:
        """
        Make prediction for a symbol using latest data.
        
        Args:
            symbol: Trading symbol
            df: DataFrame with OHLCV data (must have enough history for features)
            confidence_threshold: Minimum confidence to return a signal (default 0.65 = 65%)
            
        Returns:
            Tuple of (direction, confidence, probability)
            - direction: "long", "short", or "neutral"
            - confidence: Signal confidence (0.0-1.0)
            - probability: Raw probability from model (0.0-1.0)
        """
        # Load model if not already loaded
        if symbol not in self.loaded_symbols:
            if not self.load_model(symbol):
                return "neutral", 0.0, 0.0
        
        if symbol not in self.models:
            return "neutral", 0.0, 0.0
        
        try:
            # Calculate features
            df_features = calculate_all_features(df.copy())
            
            if len(df_features) == 0:
                return "neutral", 0.0, 0.0
            
            # Get latest row
            latest = df_features.iloc[-1:].copy()
            
            # Get expected features
            expected_features = self.features.get(symbol, get_feature_list())
            
            # Fill missing features with 0
            for feat in expected_features:
                if feat not in latest.columns:
                    latest[feat] = 0.0
            
            # Select features in correct order
            X = latest[expected_features].values
            
            # Make prediction
            model = self.models[symbol]
            prob = model.predict(X, num_iteration=model.best_iteration if hasattr(model, 'best_iteration') else None)
            
            # Handle different output formats
            if len(prob.shape) > 1:
                prob = prob[0]
            
            # Binary classification: prob[0] = probability of class 1 (LONG)
            if isinstance(prob, np.ndarray) and len(prob) > 1:
                prob_long = float(prob[1]) if len(prob) > 1 else float(prob[0])
            else:
                prob_long = float(prob[0]) if isinstance(prob, np.ndarray) else float(prob)
            
            prob_short = 1.0 - prob_long
            
            # Determine direction and confidence
            if prob_long > 0.5:
                direction = "long"
                confidence = prob_long
                probability = prob_long
            else:
                direction = "short"
                confidence = prob_short
                probability = prob_short
            
            # Apply confidence threshold
            if confidence < confidence_threshold:
                return "neutral", confidence, probability
            
            return direction, confidence, probability
            
        except Exception as e:
            print(f"⚠️ Error predicting for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return "neutral", 0.0, 0.0
    
    def get_model_info(self, symbol: str) -> Optional[dict]:
        """Get model metadata for a symbol."""
        if symbol in self.metadata:
            return self.metadata[symbol]
        return None
    
    def is_model_available(self, symbol: str) -> bool:
        """Check if model is available for a symbol."""
        if symbol in self.loaded_symbols:
            return True
        
        # Check if model file exists
        model_path = self.models_dir / f"{symbol}_latest.txt"
        if model_path.exists() or model_path.is_symlink():
            return True
        
        # Check for any model file
        model_files = list(self.models_dir.glob(f"{symbol}_lightgbm_*.txt"))
        return len(model_files) > 0
    
    def preload_models(self, symbols: list[str]) -> dict:
        """
        Preload models for multiple symbols.
        
        Args:
            symbols: List of symbols to preload
            
        Returns:
            Dict with loading results: {symbol: success}
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.load_model(symbol)
        return results


# Global instance for live trading
_predictor_instance: Optional[LightGBMLivePredictor] = None


def get_predictor() -> LightGBMLivePredictor:
    """Get global predictor instance."""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = LightGBMLivePredictor()
    return _predictor_instance

