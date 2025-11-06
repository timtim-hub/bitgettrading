"""CNN-LSTM-GRU hybrid neural network model for trading signals."""

from pathlib import Path
from typing import Tuple

import torch
import torch.nn as nn

from bitget_trading.logger import get_logger

logger = get_logger()


class CNN_LSTM_GRU(nn.Module):
    """
    Hybrid CNN-LSTM-GRU model for time series prediction.

    Architecture:
        1. 2x Conv1D layers for feature extraction
        2. 2-layer LSTM for temporal dependencies
        3. GRU layer for final sequence processing
        4. Fully connected layers for classification

    Args:
        n_features: Number of input features per timestep
        lstm_hidden: LSTM hidden layer size
        gru_hidden: GRU hidden layer size
        dropout: Dropout rate for regularization
    """

    def __init__(
        self,
        n_features: int = 68,
        lstm_hidden: int = 178,
        gru_hidden: int = 92,
        dropout: float = 0.31,
    ) -> None:
        """Initialize model layers."""
        super().__init__()

        # Convolutional layers for local pattern detection
        self.conv1 = nn.Conv1d(n_features, 64, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(64)
        self.conv2 = nn.Conv1d(64, 32, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(32)

        # LSTM for long-term dependencies
        self.lstm = nn.LSTM(
            input_size=32,
            hidden_size=lstm_hidden,
            num_layers=2,
            batch_first=True,
            dropout=dropout,
        )

        # GRU for additional temporal processing
        self.gru = nn.GRU(
            input_size=lstm_hidden,
            hidden_size=gru_hidden,
            batch_first=True,
        )

        # Fully connected classification layers
        self.fc1 = nn.Linear(gru_hidden, 32)
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(32, 3)  # 3 classes: long, short, flat

        # Activation
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.

        Args:
            x: Input tensor of shape (batch_size, seq_len, n_features)

        Returns:
            Output logits of shape (batch_size, 3)
        """
        # CNN expects (batch, channels, length)
        x = x.permute(0, 2, 1)

        # Convolutional layers with batch norm
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.relu(self.bn2(self.conv2(x)))

        # Back to (batch, seq_len, features) for LSTM/GRU
        x = x.permute(0, 2, 1)

        # LSTM layer
        x, _ = self.lstm(x)

        # GRU layer
        x, _ = self.gru(x)

        # Take last timestep output
        x = x[:, -1, :]

        # Fully connected layers with dropout
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)

        return x


def load_model(
    model_path: str | Path,
    n_features: int = 68,
    lstm_hidden: int = 178,
    gru_hidden: int = 92,
    dropout: float = 0.31,
    device: str | None = None,
) -> CNN_LSTM_GRU:
    """
    Load trained model from disk.

    Args:
        model_path: Path to saved model weights
        n_features: Number of input features
        lstm_hidden: LSTM hidden size
        gru_hidden: GRU hidden size
        dropout: Dropout rate
        device: Device to load model on (cuda/cpu)

    Returns:
        Loaded model in evaluation mode

    Raises:
        FileNotFoundError: If model file doesn't exist
    """
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = CNN_LSTM_GRU(
        n_features=n_features,
        lstm_hidden=lstm_hidden,
        gru_hidden=gru_hidden,
        dropout=dropout,
    )

    model.load_state_dict(
        torch.load(model_path, map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()

    logger.info("model_loaded", path=str(model_path), device=device)
    return model



