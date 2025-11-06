"""Tests for configuration module."""

import pytest

from src.bitget_trading.config import TradingConfig, get_config


def test_trading_config_defaults() -> None:
    """Test default configuration values."""
    config = TradingConfig()

    assert config.symbol == "SOL/USDT:USDT"
    assert config.timeframe == "1m"
    assert config.leverage == 50
    assert config.risk_per_trade == 0.008
    assert config.seq_len == 60
    assert config.sandbox is True


def test_trading_config_validation() -> None:
    """Test configuration validation."""
    # Valid leverage
    config = TradingConfig(leverage=50)
    assert config.leverage == 50

    # Invalid leverage (too high)
    with pytest.raises(Exception):
        TradingConfig(leverage=200)

    # Invalid leverage (too low)
    with pytest.raises(Exception):
        TradingConfig(leverage=0)


def test_validate_credentials() -> None:
    """Test credential validation."""
    # No credentials
    config = TradingConfig()
    assert not config.validate_credentials()

    # With credentials
    config = TradingConfig(
        bitget_api_key="key",
        bitget_api_secret="secret",
        bitget_passphrase="pass",
    )
    assert config.validate_credentials()


def test_get_config() -> None:
    """Test config getter."""
    config = get_config()
    assert isinstance(config, TradingConfig)


def test_risk_parameters() -> None:
    """Test risk parameter bounds."""
    config = TradingConfig(
        risk_per_trade=0.01,
        max_position_pct=0.5,
        daily_loss_limit=0.10,
    )

    assert 0 < config.risk_per_trade < 1
    assert 0 < config.max_position_pct <= 1
    assert 0 < config.daily_loss_limit < 1

