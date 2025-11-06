"""Tests for backtesting module."""

import pandas as pd
import pytest

from src.bitget_trading.backtest import Backtester
from src.bitget_trading.config import TradingConfig
from src.bitget_trading.model import CNN_LSTM_GRU


def test_backtester_initialization(
    test_config: TradingConfig, sample_model: CNN_LSTM_GRU
) -> None:
    """Test backtester initialization."""
    backtester = Backtester(test_config, sample_model)

    assert backtester.config == test_config
    assert backtester.model == sample_model
    assert backtester.position == "flat"
    assert len(backtester.trades) == 0


def test_backtest_run(
    sample_ohlcv_data: pd.DataFrame,
    test_config: TradingConfig,
    sample_model: CNN_LSTM_GRU,
) -> None:
    """Test running backtest."""
    backtester = Backtester(test_config, sample_model)

    metrics, trades_df = backtester.run(sample_ohlcv_data, initial_balance=10000.0)

    # Check metrics
    assert metrics is not None
    assert metrics.total_trades >= 0
    assert 0 <= metrics.win_rate <= 1
    assert metrics.final_balance > 0

    # Check trades DataFrame
    assert isinstance(trades_df, pd.DataFrame)


def test_calculate_pnl(
    test_config: TradingConfig, sample_model: CNN_LSTM_GRU
) -> None:
    """Test PnL calculation."""
    backtester = Backtester(test_config, sample_model)

    # Test long position
    backtester.position = "long"
    backtester.entry_price = 100.0
    backtester.position_size = 1.0
    pnl = backtester._calculate_pnl(105.0)  # Price increased

    assert pnl > 0  # Should be profitable

    # Test short position
    backtester.position = "short"
    backtester.entry_price = 100.0
    backtester.position_size = 1.0
    pnl = backtester._calculate_pnl(105.0)  # Price increased

    assert pnl < 0  # Should be loss for short


def test_calculate_fees(
    test_config: TradingConfig, sample_model: CNN_LSTM_GRU
) -> None:
    """Test fee calculation."""
    backtester = Backtester(test_config, sample_model)

    position_value = 10000.0
    fees = backtester._calculate_fees(position_value)

    expected_fees = position_value * test_config.fee
    assert fees == expected_fees
    assert fees > 0


@pytest.mark.parametrize("leverage", [10, 25, 50, 100])
def test_different_leverages(
    sample_ohlcv_data: pd.DataFrame,
    sample_model: CNN_LSTM_GRU,
    leverage: int,
) -> None:
    """Test backtesting with different leverage values."""
    config = TradingConfig(leverage=leverage)
    backtester = Backtester(config, sample_model)

    metrics, _ = backtester.run(sample_ohlcv_data, initial_balance=10000.0)

    assert metrics is not None
    assert metrics.final_balance > 0

