"""LightGBM model for ultra-short-term trading signals."""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from src.bitget_trading.config import TradingConfig
from src.bitget_trading.logger import get_logger

logger = get_logger()


def create_labels(
    df: pd.DataFrame,
    horizon_sec: int = 10,
    threshold_bps: float = 1.0,
) -> np.ndarray:
    """
    Create trading labels based on future price movement.
    
    Args:
        df: DataFrame with 'mid_price' column
        horizon_sec: Prediction horizon in seconds
        threshold_bps: Minimum price change threshold in basis points
    
    Returns:
        Array of labels: 0=flat, 1=long, 2=short
    """
    mid_prices = df["mid_price"].values
    labels = np.zeros(len(mid_prices), dtype=np.int32)
    
    for i in range(len(mid_prices) - horizon_sec):
        current_price = mid_prices[i]
        future_price = mid_prices[i + horizon_sec]
        
        # Calculate percentage change
        pct_change = (future_price - current_price) / current_price
        pct_change_bps = pct_change * 10000  # Convert to basis points
        
        if pct_change_bps > threshold_bps:
            labels[i] = 1  # Long
        elif pct_change_bps < -threshold_bps:
            labels[i] = 2  # Short
        else:
            labels[i] = 0  # Flat
    
    # Pad remaining with flat
    labels[-horizon_sec:] = 0
    
    return labels


class TradingModel:
    """
    LightGBM-based trading signal model.
    
    Predicts: 0=flat, 1=long, 2=short
    """

    def __init__(self, config: TradingConfig) -> None:
        """
        Initialize model.
        
        Args:
            config: Trading configuration
        """
        self.config = config
        self.model: lgb.Booster | None = None
        self.feature_names: list[str] = []
        self.is_trained: bool = False

    def train(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        test_size: float = 0.2,
    ) -> dict[str, float]:
        """
        Train LightGBM model.
        
        Args:
            df: DataFrame with features and mid_price
            feature_cols: List of feature column names
            test_size: Test set size
        
        Returns:
            Training metrics
        """
        logger.info("training_started", n_samples=len(df), n_features=len(feature_cols))
        
        # Create labels
        labels = create_labels(
            df,
            horizon_sec=self.config.prediction_horizon_sec,
            threshold_bps=self.config.label_threshold_bps,
        )
        
        # Remove samples where label couldn't be computed
        valid_idx = labels >= 0
        X = df[feature_cols].iloc[valid_idx].values
        y = labels[valid_idx]
        
        # Class distribution
        unique, counts = np.unique(y, return_counts=True)
        class_dist = dict(zip(unique, counts))
        logger.info("class_distribution", distribution=class_dist)
        
        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Create LightGBM datasets
        train_data = lgb.Dataset(X_train, label=y_train)
        test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
        
        # LightGBM parameters
        params = {
            "objective": "multiclass",
            "num_class": 3,
            "metric": "multi_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": self.config.lgbm_learning_rate,
            "max_depth": self.config.lgbm_max_depth,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "num_threads": 4,  # M1 optimized
        }
        
        # Train model
        callbacks = [
            lgb.early_stopping(stopping_rounds=20),
            lgb.log_evaluation(period=10),
        ]
        
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=self.config.lgbm_n_estimators,
            valid_sets=[train_data, test_data],
            valid_names=["train", "test"],
            callbacks=callbacks,
        )
        
        self.feature_names = feature_cols
        self.is_trained = True
        
        # Evaluate on test set
        y_pred = self.model.predict(X_test)
        y_pred_class = np.argmax(y_pred, axis=1)
        
        # Calculate metrics
        report = classification_report(y_test, y_pred_class, output_dict=True)
        
        metrics = {
            "accuracy": report["accuracy"],
            "flat_f1": report.get("0", {}).get("f1-score", 0),
            "long_f1": report.get("1", {}).get("f1-score", 0),
            "short_f1": report.get("2", {}).get("f1-score", 0),
        }
        
        logger.info(
            "training_completed",
            accuracy=f"{metrics['accuracy']:.4f}",
            long_f1=f"{metrics['long_f1']:.4f}",
            short_f1=f"{metrics['short_f1']:.4f}",
        )
        
        return metrics

    def predict(self, features: pd.DataFrame) -> tuple[int, np.ndarray]:
        """
        Predict trading signal.
        
        Args:
            features: DataFrame with features
        
        Returns:
            Tuple of (predicted_class, probabilities)
        """
        if not self.is_trained or self.model is None:
            raise ValueError("Model not trained")
        
        # Ensure features are in correct order
        X = features[self.feature_names].values
        
        # Predict probabilities
        probs = self.model.predict(X)
        
        # Get predicted class
        if len(probs.shape) == 2:  # Multiple samples
            pred_class = np.argmax(probs, axis=1)[0]
            probs = probs[0]
        else:  # Single sample
            pred_class = int(np.argmax(probs))
        
        return pred_class, probs

    def predict_signal(
        self, features: pd.DataFrame
    ) -> tuple[str, float, np.ndarray]:
        """
        Predict trading signal with thresholds.
        
        Args:
            features: DataFrame with features
        
        Returns:
            Tuple of (signal, confidence, probabilities)
            signal: "long", "short", or "flat"
        """
        pred_class, probs = self.predict(features)
        
        prob_flat = probs[0]
        prob_long = probs[1]
        prob_short = probs[2]
        
        # Apply thresholds
        if (
            prob_long > self.config.signal_long_threshold
            and prob_long - prob_short > self.config.signal_margin
        ):
            return "long", prob_long, probs
        elif (
            prob_short > self.config.signal_short_threshold
            and prob_short - prob_long > self.config.signal_margin
        ):
            return "short", prob_short, probs
        else:
            return "flat", prob_flat, probs

    def save(self, path: str | Path) -> None:
        """Save model to disk."""
        if not self.is_trained or self.model is None:
            raise ValueError("No trained model to save")
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        self.model.save_model(str(path))
        
        # Save feature names
        feature_path = path.parent / f"{path.stem}_features.txt"
        with open(feature_path, "w") as f:
            f.write("\n".join(self.feature_names))
        
        logger.info("model_saved", path=str(path))

    def load(self, path: str | Path) -> None:
        """Load model from disk."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")
        
        self.model = lgb.Booster(model_file=str(path))
        
        # Load feature names
        feature_path = path.parent / f"{path.stem}_features.txt"
        if feature_path.exists():
            with open(feature_path) as f:
                self.feature_names = [line.strip() for line in f]
        
        self.is_trained = True
        logger.info("model_loaded", path=str(path), n_features=len(self.feature_names))

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance."""
        if not self.is_trained or self.model is None:
            raise ValueError("Model not trained")
        
        importance = self.model.feature_importance(importance_type="gain")
        
        df = pd.DataFrame({
            "feature": self.feature_names,
            "importance": importance,
        })
        
        df = df.sort_values("importance", ascending=False).head(top_n)
        
        return df

