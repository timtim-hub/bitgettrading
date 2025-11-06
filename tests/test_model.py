"""Tests for model module."""

from pathlib import Path

import pytest
import torch

from src.bitget_trading.model import CNN_LSTM_GRU, create_dummy_model, load_model


def test_model_initialization() -> None:
    """Test model can be initialized."""
    model = CNN_LSTM_GRU(n_features=68, lstm_hidden=178, gru_hidden=92, dropout=0.31)
    assert model is not None
    assert isinstance(model, CNN_LSTM_GRU)


def test_model_forward_pass() -> None:
    """Test model forward pass."""
    model = CNN_LSTM_GRU(n_features=68)
    model.eval()

    # Create dummy input (batch_size=4, seq_len=60, n_features=68)
    x = torch.randn(4, 60, 68)

    with torch.no_grad():
        output = model(x)

    assert output.shape == (4, 3)  # 3 classes


def test_model_output_range() -> None:
    """Test model outputs valid logits."""
    model = CNN_LSTM_GRU(n_features=68)
    model.eval()

    x = torch.randn(2, 60, 68)

    with torch.no_grad():
        output = model(x)
        probs = torch.softmax(output, dim=1)

    # Probabilities should sum to 1
    assert torch.allclose(probs.sum(dim=1), torch.ones(2), atol=1e-5)

    # All probabilities should be between 0 and 1
    assert (probs >= 0).all() and (probs <= 1).all()


def test_create_dummy_model(tmp_path: Path) -> None:
    """Test dummy model creation."""
    model_path = tmp_path / "test_model.pth"
    create_dummy_model(model_path)

    assert model_path.exists()
    assert model_path.stat().st_size > 0


def test_load_model(temp_model_path: Path) -> None:
    """Test model loading."""
    model = load_model(temp_model_path, device="cpu")

    assert model is not None
    assert isinstance(model, CNN_LSTM_GRU)


def test_load_model_not_found() -> None:
    """Test loading non-existent model raises error."""
    with pytest.raises(FileNotFoundError):
        load_model("nonexistent_model.pth")


def test_model_device_placement() -> None:
    """Test model can be placed on correct device."""
    model = CNN_LSTM_GRU()

    if torch.cuda.is_available():
        model = model.cuda()
        assert next(model.parameters()).is_cuda
    else:
        model = model.cpu()
        assert not next(model.parameters()).is_cuda

