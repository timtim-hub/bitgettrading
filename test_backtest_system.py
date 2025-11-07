#!/usr/bin/env python3
"""Test the automated backtesting system."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bitget_trading.backtest_service import BacktestService
from bitget_trading.bitget_rest import BitgetRestClient
from bitget_trading.config import get_config
from bitget_trading.dynamic_params import DynamicParams
from bitget_trading.enhanced_ranker import EnhancedRanker
from bitget_trading.logger import setup_logging
from bitget_trading.multi_symbol_state import MultiSymbolStateManager
from bitget_trading.symbol_backtester import BacktestResult, SymbolBacktester
from bitget_trading.symbol_filter import SymbolFilter
from bitget_trading.symbol_performance_tracker import SymbolPerformanceTracker
from bitget_trading.stats_generator import StatsGenerator
from datetime import datetime

logger = setup_logging()


async def test_performance_tracker():
    """Test performance tracker."""
    print("\n" + "=" * 70)
    print("TEST 1: Performance Tracker")
    print("=" * 70)
    
    tracker = SymbolPerformanceTracker()
    
    # Create mock backtest result
    result = BacktestResult(
        symbol="BTCUSDT",
        timestamp=datetime.now(),
        win_rate=0.65,
        roi=12.5,
        sharpe_ratio=1.5,
        total_trades=50,
        winning_trades=33,
        losing_trades=17,
        avg_win=0.08,
        avg_loss=-0.05,
        profit_factor=1.6,
        max_drawdown=0.15,
        total_pnl=125.0,
        net_pnl=125.0,
    )
    
    # Add backtest result
    tracker.add_backtest_result(result)
    print(f"✅ Added backtest result for {result.symbol}")
    
    # Update live result
    tracker.update_live_result("BTCUSDT", 0.68, 25, 50.0)
    print(f"✅ Updated live result for BTCUSDT")
    
    # Get performance
    perf = tracker.get_performance("BTCUSDT")
    if perf:
        print(f"✅ Retrieved performance: Win Rate {perf.combined_score:.2%}")
    else:
        print("❌ Failed to retrieve performance")
        return False
    
    # Check filtering
    should_filter, reason = tracker.should_filter_symbol("BTCUSDT")
    print(f"✅ Filter check: should_filter={should_filter}, reason={reason}")
    
    return True


def test_symbol_filter():
    """Test symbol filter."""
    print("\n" + "=" * 70)
    print("TEST 2: Symbol Filter")
    print("=" * 70)
    
    tracker = SymbolPerformanceTracker()
    
    # Add a losing token
    losing_result = BacktestResult(
        symbol="BADUSDT",
        timestamp=datetime.now(),
        win_rate=0.40,  # Below 50%
        roi=-5.0,  # Negative ROI
        sharpe_ratio=0.3,  # Below 0.5
        total_trades=25,
        winning_trades=10,
        losing_trades=15,
        avg_win=0.05,
        avg_loss=-0.08,
        profit_factor=0.8,  # Below 1.0
        max_drawdown=0.30,
        total_pnl=-25.0,
        net_pnl=-25.0,
    )
    tracker.add_backtest_result(losing_result)
    
    # Add a winning token
    winning_result = BacktestResult(
        symbol="GOODUSDT",
        timestamp=datetime.now(),
        win_rate=0.70,  # Above 50%
        roi=15.0,  # Positive ROI
        sharpe_ratio=1.8,  # Above 0.5
        total_trades=50,
        winning_trades=35,
        losing_trades=15,
        avg_win=0.10,
        avg_loss=-0.05,
        profit_factor=2.0,  # Above 1.0
        max_drawdown=0.10,
        total_pnl=150.0,
        net_pnl=150.0,
    )
    tracker.add_backtest_result(winning_result)
    
    # Create filter
    symbol_filter = SymbolFilter(
        performance_tracker=tracker,
        enabled=True,
        min_win_rate=0.50,
        min_roi=0.0,
        min_sharpe=0.5,
        min_profit_factor=1.0,
    )
    
    # Test filtering
    should_trade_bad, reason_bad = symbol_filter.should_trade_symbol("BADUSDT")
    should_trade_good, reason_good = symbol_filter.should_trade_symbol("GOODUSDT")
    
    print(f"✅ BADUSDT: should_trade={should_trade_bad}, reason={reason_bad}")
    print(f"✅ GOODUSDT: should_trade={should_trade_good}, reason={reason_good}")
    
    if not should_trade_bad and should_trade_good:
        print("✅ Filter working correctly!")
        return True
    else:
        print("❌ Filter not working correctly!")
        return False


def test_dynamic_params():
    """Test dynamic parameters."""
    print("\n" + "=" * 70)
    print("TEST 3: Dynamic Parameters")
    print("=" * 70)
    
    tracker = SymbolPerformanceTracker()
    
    # Add tier 1 token (best)
    tier1_result = BacktestResult(
        symbol="TIER1USDT",
        timestamp=datetime.now(),
        win_rate=0.70,
        roi=20.0,
        sharpe_ratio=2.0,
        total_trades=100,
        winning_trades=70,
        losing_trades=30,
        avg_win=0.12,
        avg_loss=-0.05,
        profit_factor=2.5,
        max_drawdown=0.08,
        total_pnl=200.0,
        net_pnl=200.0,
    )
    tracker.add_backtest_result(tier1_result)
    
    # Add tier 4 token (poor)
    tier4_result = BacktestResult(
        symbol="TIER4USDT",
        timestamp=datetime.now(),
        win_rate=0.40,
        roi=-10.0,
        sharpe_ratio=0.2,
        total_trades=30,
        winning_trades=12,
        losing_trades=18,
        avg_win=0.05,
        avg_loss=-0.10,
        profit_factor=0.6,
        max_drawdown=0.40,
        total_pnl=-30.0,
        net_pnl=-30.0,
    )
    tracker.add_backtest_result(tier4_result)
    
    # Create dynamic params
    dynamic_params = DynamicParams(
        performance_tracker=tracker,
        enabled=True,
    )
    
    # Test parameters
    tier1_callback = dynamic_params.get_trailing_tp_callback("TIER1USDT", 0.04)
    tier1_multiplier = dynamic_params.get_position_size_multiplier("TIER1USDT", 1.0)
    tier1_threshold = dynamic_params.get_entry_threshold("TIER1USDT", 0.5)
    
    tier4_callback = dynamic_params.get_trailing_tp_callback("TIER4USDT", 0.04)
    tier4_multiplier = dynamic_params.get_position_size_multiplier("TIER4USDT", 1.0)
    tier4_threshold = dynamic_params.get_entry_threshold("TIER4USDT", 0.5)
    
    print(f"✅ TIER1USDT: callback={tier1_callback:.2%}, multiplier={tier1_multiplier:.2f}x, threshold={tier1_threshold:.2f}")
    print(f"✅ TIER4USDT: callback={tier4_callback:.2%}, multiplier={tier4_multiplier:.2f}x, threshold={tier4_threshold:.2f}")
    
    # Verify tier 1 gets better parameters
    if tier1_callback > tier4_callback and tier1_multiplier > tier4_multiplier and tier1_threshold < tier4_threshold:
        print("✅ Dynamic parameters working correctly!")
        return True
    else:
        print("❌ Dynamic parameters not working correctly!")
        return False


def test_stats_generator():
    """Test stats generator."""
    print("\n" + "=" * 70)
    print("TEST 4: Stats Generator")
    print("=" * 70)
    
    tracker = SymbolPerformanceTracker()
    
    # Add some test data
    for i, symbol in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BADUSDT"]):
        result = BacktestResult(
            symbol=symbol,
            timestamp=datetime.now(),
            win_rate=0.60 + (i * 0.05),
            roi=10.0 + (i * 5.0),
            sharpe_ratio=1.0 + (i * 0.3),
            total_trades=50 + (i * 10),
            winning_trades=30 + (i * 5),
            losing_trades=20 + (i * 5),
            avg_win=0.08,
            avg_loss=-0.05,
            profit_factor=1.5 + (i * 0.2),
            max_drawdown=0.15,
            total_pnl=100.0 + (i * 20.0),
            net_pnl=100.0 + (i * 20.0),
        )
        tracker.add_backtest_result(result)
    
    # Generate stats
    stats_generator = StatsGenerator(tracker)
    stats_generator.generate_stats()
    
    # Check if stats file exists
    stats_file = Path("data/symbol_performance_stats.txt")
    if stats_file.exists():
        print(f"✅ Stats file generated: {stats_file}")
        print(f"✅ File size: {stats_file.stat().st_size} bytes")
        
        # Show first few lines
        with open(stats_file, "r") as f:
            lines = f.readlines()[:20]
            print("\nFirst 20 lines of stats file:")
            for line in lines:
                print(f"  {line.rstrip()}")
        
        return True
    else:
        print("❌ Stats file not generated!")
        return False


async def test_backtest_service():
    """Test backtesting service (without actually running backtests)."""
    print("\n" + "=" * 70)
    print("TEST 5: Backtesting Service")
    print("=" * 70)
    
    # Load config
    config = get_config()
    
    # Check if API credentials are available
    if not config.validate_credentials():
        print("⚠️  API credentials not available - skipping service test")
        print("   (This is expected if running without .env file)")
        return True
    
    # Create mock components
    rest_client = BitgetRestClient(
        config.bitget_api_key,
        config.bitget_api_secret,
        config.bitget_passphrase,
        sandbox=config.sandbox,
    )
    enhanced_ranker = EnhancedRanker()
    state_manager = MultiSymbolStateManager()
    
    # Create service (disabled for testing)
    service = BacktestService(
        config=config,
        rest_client=rest_client,
        enhanced_ranker=enhanced_ranker,
        state_manager=state_manager,
        symbols=["BTCUSDT", "ETHUSDT"],  # Small test set
        enabled=False,  # Disabled to avoid actual API calls
        interval_hours=6,
        lookback_days=7,
        min_trades=10,
        parallel_tokens=2,
    )
    
    print("✅ Backtesting service created")
    print(f"✅ Performance tracker: {service.get_performance_tracker()}")
    print(f"✅ Stats generator: {service.get_stats_generator()}")
    
    return True


async def main():
    """Run all tests."""
    print("=" * 70)
    print("TESTING AUTOMATED BACKTESTING SYSTEM")
    print("=" * 70)
    
    results = []
    
    # Test 1: Performance Tracker
    try:
        result = await test_performance_tracker()
        results.append(("Performance Tracker", result))
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        results.append(("Performance Tracker", False))
    
    # Test 2: Symbol Filter
    try:
        result = test_symbol_filter()
        results.append(("Symbol Filter", result))
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        results.append(("Symbol Filter", False))
    
    # Test 3: Dynamic Parameters
    try:
        result = test_dynamic_params()
        results.append(("Dynamic Parameters", result))
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        results.append(("Dynamic Parameters", False))
    
    # Test 4: Stats Generator
    try:
        result = test_stats_generator()
        results.append(("Stats Generator", result))
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
        results.append(("Stats Generator", False))
    
    # Test 5: Backtesting Service
    try:
        result = await test_backtest_service()
        results.append(("Backtesting Service", result))
    except Exception as e:
        print(f"❌ Test 5 failed: {e}")
        results.append(("Backtesting Service", False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

