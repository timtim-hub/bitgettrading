import pytest
from unittest.mock import MagicMock
from bitget_trading.position_manager import PositionManager, Position
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
    take_profit_pct = 0.10  # 10% capital TP
    trailing_stop_pct = 0.04 # 4% capital drop from peak
    position_manager.add_position(symbol, "long", entry_price, 0.01, capital, leverage, 
                                  take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct)
    pos = position_manager.get_position(symbol)

    # Price rises to TP threshold (10% capital profit) - use slightly above to trigger TP check
    tp_price = entry_price * (1 + (take_profit_pct + 0.001) / leverage)  # Slightly above 10% capital profit
    position_manager.update_position_price(symbol, tp_price)
    assert pos.highest_price == tp_price
    
    # Check that we're above TP threshold (should trigger TP exit)
    should_close, reason = position_manager.check_exit_conditions(symbol, tp_price)
    assert should_close is True
    assert "TAKE-PROFIT" in reason
    
    # Now test trailing stop: price continues higher (new peak), then drops to trigger trailing stop
    # Update position to new peak (slightly higher than TP)
    higher_peak = entry_price * (1 + (take_profit_pct + 0.01) / leverage)  # 11% capital profit
    position_manager.update_position_price(symbol, higher_peak)
    assert pos.highest_price == higher_peak
    
    # Price drops from peak enough to trigger trailing stop
    # BUT: Keep capital PnL above TP threshold (10%) so trailing stop can activate
    # Trailing stop price = peak_price * (1 - trailing_stop_pct / leverage)
    # We need: (trailing_stop_trigger_price - entry_price) / entry_price * leverage >= take_profit_pct
    # So: trailing_stop_trigger_price >= entry_price * (1 + take_profit_pct / leverage)
    # And: trailing_stop_trigger_price <= higher_peak * (1 - trailing_stop_pct / leverage)
    # Find a price that satisfies both conditions
    min_price_for_tp = entry_price * (1 + take_profit_pct / leverage)  # Minimum to stay above TP
    max_price_for_trail = higher_peak * (1 - trailing_stop_pct / leverage)  # Maximum for trailing stop
    
    # Use a price between these two (closer to trailing stop trigger)
    trailing_stop_trigger_price = max(min_price_for_tp * 1.001, max_price_for_trail * 0.999)  # Slightly trigger trailing stop
    
    # Now drop to trailing stop trigger price
    position_manager.update_position_price(symbol, trailing_stop_trigger_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, trailing_stop_trigger_price)
    assert should_close is True
    assert "TRAILING-STOP" in reason

def test_check_exit_trailing_stop_short(position_manager):
    symbol = "ETHUSDT"
    entry_price = 2000.0
    capital = 100.0
    leverage = 50
    take_profit_pct = 0.10  # 10% capital TP
    trailing_stop_pct = 0.04
    position_manager.add_position(symbol, "short", entry_price, 0.1, capital, leverage,
                                  take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct)
    pos = position_manager.get_position(symbol)

    # Price drops to TP threshold (10% capital profit) - use slightly below to trigger TP check
    tp_price = entry_price * (1 - (take_profit_pct + 0.001) / leverage)  # Slightly below entry (above 10% capital profit)
    position_manager.update_position_price(symbol, tp_price)
    assert pos.lowest_price == tp_price
    
    # Check that we're above TP threshold (should trigger TP exit)
    should_close, reason = position_manager.check_exit_conditions(symbol, tp_price)
    assert should_close is True
    assert "TAKE-PROFIT" in reason
    
    # Now test trailing stop: price drops further (new low), then rises to trigger trailing stop
    # Lower low = entry_price * (1 - (take_profit_pct + 0.01) / leverage)  # 11% capital profit
    lower_low = entry_price * (1 - (take_profit_pct + 0.01) / leverage)
    position_manager.update_position_price(symbol, lower_low)
    assert pos.lowest_price == lower_low
    
    # Price rises enough to trigger trailing stop
    # BUT: Keep capital PnL above TP threshold (10%) so trailing stop can activate
    # For shorts: price needs to stay below entry enough to maintain >10% capital profit
    # Trailing stop price = low_price * (1 + trailing_stop_pct / leverage)
    # We need: (entry_price - trailing_stop_trigger_price) / entry_price * leverage >= take_profit_pct
    # So: trailing_stop_trigger_price <= entry_price * (1 - take_profit_pct / leverage)
    # And: trailing_stop_trigger_price >= lower_low * (1 + trailing_stop_pct / leverage)
    # Find a price that satisfies both conditions
    max_price_for_tp = entry_price * (1 - take_profit_pct / leverage)  # Maximum to stay above TP
    min_price_for_trail = lower_low * (1 + trailing_stop_pct / leverage)  # Minimum for trailing stop
    
    # Use a price between these two (closer to trailing stop trigger)
    trailing_stop_trigger_price = min(max_price_for_tp * 0.999, min_price_for_trail * 1.001)  # Slightly trigger trailing stop
    
    position_manager.update_position_price(symbol, trailing_stop_trigger_price)
    should_close, reason = position_manager.check_exit_conditions(symbol, trailing_stop_trigger_price)
    assert should_close is True
    assert "TRAILING-STOP" in reason

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



