"""Model training module with real training loop."""

from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

from bitget_trading.features import create_sequences
from bitget_trading.logger import get_logger
from bitget_trading.model import CNN_LSTM_GRU

logger = get_logger()


def create_labels(df: pd.DataFrame, lookahead: int = 5, threshold: float = 0.002) -> np.ndarray:
    """
    Create trading labels based on future price movement.
    
    Args:
        df: DataFrame with OHLCV data
        lookahead: Number of periods to look ahead
        threshold: Minimum price change threshold
        
    Returns:
        Array of labels: 0=long, 1=short, 2=flat
    """
    close_prices = df["close"].values
    labels = []
    
    for i in range(len(close_prices) - lookahead):
        current_price = close_prices[i]
        future_price = close_prices[i + lookahead]
        pct_change = (future_price - current_price) / current_price
        
        if pct_change > threshold:
            labels.append(0)  # Long
        elif pct_change < -threshold:
            labels.append(1)  # Short
        else:
            labels.append(2)  # Flat
    
    # Pad remaining with flat signals
    labels.extend([2] * lookahead)
    
    return np.array(labels)


def train_model(
    df: pd.DataFrame,
    n_features: int,
    lstm_hidden: int,
    gru_hidden: int,
    dropout: float,
    seq_len: int = 60,
    epochs: int = 20,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    save_path: str | Path | None = None,
) -> CNN_LSTM_GRU:
    """
    Train the CNN-LSTM-GRU model on historical data.
    
    Args:
        df: Training data with OHLCV
        n_features: Number of features
        lstm_hidden: LSTM hidden size
        gru_hidden: GRU hidden size
        dropout: Dropout rate
        seq_len: Sequence length
        epochs: Training epochs
        batch_size: Batch size
        learning_rate: Learning rate
        save_path: Path to save trained model
        
    Returns:
        Trained model
    """
    logger.info("training_started", epochs=epochs, batch_size=batch_size)
    
    # Create sequences and labels
    sequences, feature_cols = create_sequences(df, seq_len)
    
    if len(sequences) == 0:
        raise ValueError("No sequences generated from data")
    
    # Create labels
    labels = create_labels(df, lookahead=5, threshold=0.002)
    
    # Align sequences and labels
    # Sequences start from seq_len-1 index
    labels_aligned = labels[seq_len - 1 : seq_len - 1 + len(sequences)]
    
    # Split into train and validation
    split_idx = int(len(sequences) * 0.8)
    
    X_train = sequences[:split_idx]
    y_train = labels_aligned[:split_idx]
    X_val = sequences[split_idx:]
    y_val = labels_aligned[split_idx:]
    
    # Convert to tensors
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
    y_train_tensor = torch.tensor(y_train, dtype=torch.long)
    X_val_tensor = torch.tensor(X_val, dtype=torch.float32)
    y_val_tensor = torch.tensor(y_val, dtype=torch.long)
    
    # Create data loaders
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    
    # Initialize model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CNN_LSTM_GRU(
        n_features=n_features,
        lstm_hidden=lstm_hidden,
        gru_hidden=gru_hidden,
        dropout=dropout,
    ).to(device)
    
    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)
    
    logger.info(
        "training_setup",
        device=device,
        train_samples=len(X_train),
        val_samples=len(X_val),
        n_features=len(feature_cols),
    )
    
    # Training loop
    best_val_loss = float("inf")
    
    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            train_total += batch_y.size(0)
            train_correct += (predicted == batch_y).sum().item()
        
        train_loss /= len(train_loader)
        train_acc = 100 * train_correct / train_total
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                
                val_loss += loss.item()
                _, predicted = torch.max(outputs.data, 1)
                val_total += batch_y.size(0)
                val_correct += (predicted == batch_y).sum().item()
        
        val_loss /= len(val_loader)
        val_acc = 100 * val_correct / val_total
        
        scheduler.step(val_loss)
        
        logger.info(
            "epoch_completed",
            epoch=epoch + 1,
            train_loss=f"{train_loss:.4f}",
            train_acc=f"{train_acc:.2f}%",
            val_loss=f"{val_loss:.4f}",
            val_acc=f"{val_acc:.2f}%",
        )
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            if save_path:
                path = Path(save_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                torch.save(model.state_dict(), path)
                logger.info("model_saved", path=str(path), val_loss=f"{val_loss:.4f}")
    
    logger.info("training_completed", best_val_loss=f"{best_val_loss:.4f}")
    
    return model

