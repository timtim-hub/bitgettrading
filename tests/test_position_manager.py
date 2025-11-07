import pytest
from unittest.mock import MagicMock
from src.bitget_trading.position_manager import PositionManager, Position
from datetime import datetime, timedelta

# Mock the logger to prevent actual log output during tests
import logging
logging.getLogger('bitget_trading.logger').addHandler(logging.NullHandler())

@pytest.fixture
def position_manager():
    # Use a temporary file for positions.json for testing
    manager = PositionManager(save_path="test_positions.json")
    manager.positions = {}  # Ensure a clean state for each test
    yield manager
    # Clean up the test file after tests
    if manager.save_path.exists():
        manager.save_path.unlink()

@pytest.fixture
def mock_state_manager():
    manager = MagicMock()
    return manager

def test_add_position(position_manager):
    symbol = "BTCUSDT"
    position_manager.add_position(
        symbol=symbol,
        side="long",
        entry_price=30000.0,
        size=0.01,
        capital=50.0,
        leverage=50,
    )
    assert symbol in position_manager.positions
    pos = position_manager.get_position(symbol)
    assert pos.symbol == symbol
    assert pos.entry_price == 30000.0
    assert pos.highest_price == 30000.0  # Initial highest price for long
    assert pos.lowest_price == float('inf') # Initial lowest price for long

    position_manager.add_position(
        symbol="ETHUSDT",
        side="short",
        entry_price=2000.0,
        size=0.1,
        capital=50.0,
        leverage=50,
    )
    pos = position_manager.get_position("ETHUSDT")
    assert pos.lowest_price == 2000.0 # Initial lowest price for short
    assert pos.highest_price == 0.0 # Initial highest price for short

def test_remove_position(position_manager):
    symbol = "BTCUSDT"
    position_manager.add_position(symbol, "long", 30000, 0.01, 50.0, 50)
    assert position_manager.remove_position(symbol) is not None
    assert symbol not in position_manager.positions
    assert position_manager.remove_position("NONEXISTENT") is None

def test_update_position_price_long(position_manager):
    symbol = "BTCUSDT"
    entry_price = 30000.0
    position_manager.add_position(symbol, "long", entry_price, 0.01, 50.0, 50)
    pos = position_manager.get_position(symbol)

    # Price goes up, highest_price should update
    position_manager.update_position_price(symbol, 30100.0)
    assert pos.highest_price == 30100.0
    assert pos.unrealized_pnl > 0

    # Price goes down but still above entry, highest_price should not change
    position_manager.update_position_price(symbol, 30050.0)
    assert pos.highest_price == 30100.0
    assert pos.unrealized_pnl > 0

    # Price drops below entry
    position_manager.update_position_price(symbol, 29900.0)
    assert pos.highest_price == 30100.0
    assert pos.unrealized_pnl < 0

def test_update_position_price_short(position_manager):
    symbol = "ETHUSDT"
    entry_price = 2000.0
    position_manager.add_position(symbol, "short", entry_price, 0.1, 50.0, 50)
    pos = position_manager.get_position(symbol)

    # Price goes down, lowest_price should update
    position_manager.update_position_price(symbol, 1990.0)
    assert pos.lowest_price == 1990.0
    assert pos.unrealized_pnl > 0

    # Price goes up but still below entry, lowest_price should not change
    position_manager.update_position_price(symbol, 1995.0)
    assert pos.lowest_price == 1990.0
    assert pos.unrealized_pnl > 0

    # Price rises above entry
    position_manager.update_position_price(symbol, 2010.0)
    assert pos.lowest_price == 1990.0
    assert pos.unrealized_pnl < 0

def test_check_exit_stop_loss_long(position_manager):
    symbol = "BTCUSDT"
    entry_price = 30000.0
    capital = 100.0
    leverage = 50
    stop_loss_pct = 0.08  # 8% capital loss
    position_manager.add_position(symbol, "long", entry_price, 0.01, capital, leverage, stop_loss_pct=stop_loss_pct)
    pos = position_manager.get_position(symbol)

    # Price drop that hits stop loss
    # Required price drop for 8% capital loss at 50x leverage: 0.08 / 50 = 0.0016 (0.16%)
    stop_loss_price = entry_price * (1 - stop_loss_pct / leverage * 1.01) # Go slightly beyond for trigger
    position_manager.update_position_price(symbol, stop_loss_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, stop_loss_price)
    assert should_close is True
    assert "STOP-LOSS" in reason

def test_check_exit_stop_loss_short(position_manager):
    symbol = "ETHUSDT"
    entry_price = 2000.0
    capital = 100.0
    leverage = 50
    stop_loss_pct = 0.08
    position_manager.add_position(symbol, "short", entry_price, 0.1, capital, leverage, stop_loss_pct=stop_loss_pct)
    pos = position_manager.get_position(symbol)

    # Price rise that hits stop loss
    # Required price rise for 8% capital loss at 50x leverage: 0.08 / 50 = 0.0016 (0.16%)
    stop_loss_price = entry_price * (1 + stop_loss_pct / leverage * 1.01) # Go slightly beyond for trigger
    position_manager.update_position_price(symbol, stop_loss_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, stop_loss_price)
    assert should_close is True
    assert "STOP-LOSS" in reason

def test_check_exit_take_profit_long(position_manager):
    symbol = "BTCUSDT"
    entry_price = 30000.0
    capital = 100.0
    leverage = 50
    take_profit_pct = 0.20 # 20% capital gain
    position_manager.add_position(symbol, "long", entry_price, 0.01, capital, leverage, take_profit_pct=take_profit_pct)
    pos = position_manager.get_position(symbol)

    # Price rise that hits take profit
    # Required price rise for 20% capital gain at 50x leverage: 0.20 / 50 = 0.004 (0.4%)
    take_profit_price = entry_price * (1 + take_profit_pct / leverage * 1.01) # Go slightly beyond for trigger
    position_manager.update_position_price(symbol, take_profit_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, take_profit_price)
    assert should_close is True
    assert "TAKE-PROFIT" in reason

def test_check_exit_take_profit_short(position_manager):
    symbol = "ETHUSDT"
    entry_price = 2000.0
    capital = 100.0
    leverage = 50
    take_profit_pct = 0.20
    position_manager.add_position(symbol, "short", entry_price, 0.1, capital, leverage, take_profit_pct=take_profit_pct)
    pos = position_manager.get_position(symbol)

    # Price drop that hits take profit
    # Required price drop for 20% capital gain at 50x leverage: 0.20 / 50 = 0.004 (0.4%)
    take_profit_price = entry_price * (1 - take_profit_pct / leverage * 1.01) # Go slightly beyond for trigger
    position_manager.update_position_price(symbol, take_profit_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, take_profit_price)
    assert should_close is True
    assert "TAKE-PROFIT" in reason

def test_check_exit_trailing_stop_long(position_manager):
    symbol = "BTCUSDT"
    entry_price = 30000.0
    capital = 100.0
    leverage = 50
    trailing_stop_pct = 0.04 # 4% capital drop from peak
    position_manager.add_position(symbol, "long", entry_price, 0.01, capital, leverage, trailing_stop_pct=trailing_stop_pct)
    pos = position_manager.get_position(symbol)

    # Price rises significantly
    peak_price = entry_price * (1 + 0.10 / leverage) # 10% capital profit
    position_manager.update_position_price(symbol, peak_price)
    assert pos.highest_price == peak_price
    
    # Price drops enough to trigger trailing stop
    # Trailing stop price = peak_price * (1 - trailing_stop_pct / leverage)
    trailing_stop_trigger_price = peak_price * (1 - trailing_stop_pct / leverage * 1.01) # Go slightly beyond for trigger
    
    position_manager.update_position_price(symbol, trailing_stop_trigger_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, trailing_stop_trigger_price)
    assert should_close is True
    assert "TRAILING-STOP" in reason

def test_check_exit_trailing_stop_short(position_manager):
    symbol = "ETHUSDT"
    entry_price = 2000.0
    capital = 100.0
    leverage = 50
    trailing_stop_pct = 0.04
    position_manager.add_position(symbol, "short", entry_price, 0.1, capital, leverage, trailing_stop_pct=trailing_stop_pct)
    pos = position_manager.get_position(symbol)

    # Price drops significantly
    low_price = entry_price * (1 - 0.10 / leverage) # 10% capital profit
    position_manager.update_position_price(symbol, low_price)
    assert pos.lowest_price == low_price
    
    # Price rises enough to trigger trailing stop
    # Trailing stop price = low_price * (1 + trailing_stop_pct / leverage)
    trailing_stop_trigger_price = low_price * (1 + trailing_stop_pct / leverage * 1.01) # Go slightly beyond for trigger
    
    position_manager.update_position_price(symbol, trailing_stop_trigger_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, trailing_stop_trigger_price)
    assert should_close is True
    assert "TRAILING-STOP" in reason

# REMOVED: test_check_exit_quick_profit_exit, test_check_exit_time_exit, test_check_exit_max_time_exit
# These time-based exit rules were removed from position_manager.py
# Positions now run to full TP (20%) or hit SL/trailing stop only

def test_check_exit_minimum_profit_lock(position_manager):
    symbol = "BTCUSDT"
    entry_price = 30000.0
    capital = 100.0
    leverage = 50
    position_manager.add_position(symbol, "long", entry_price, 0.01, capital, leverage)
    pos = position_manager.get_position(symbol)

    # Price changes within the -1% to +1.5% capital return range
    current_price_small_profit = entry_price * (1 + 0.01 / leverage) # 1% capital gain
    position_manager.update_position_price(symbol, current_price_small_profit)
    should_close, _ = position_manager.check_exit_conditions(symbol, current_price_small_profit)
    assert should_close is False

    current_price_small_loss = entry_price * (1 - 0.005 / leverage) # -0.5% capital loss
    position_manager.update_position_price(symbol, current_price_small_loss)
    should_close, _ = position_manager.check_exit_conditions(symbol, current_price_small_loss)
    assert should_close is False




