"""
Test Institutional Strategy with Synthetic Data
Quick validation that all components work together
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from institutional_backtest import InstitutionalBacktester, print_backtest_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_synthetic_data(bars: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing"""
    np.random.seed(seed)
    
    # Base price with trend
    base_price = 50000.0
    trend = np.linspace(0, 5000, bars)
    noise = np.cumsum(np.random.randn(bars) * 100)
    
    close_prices = base_price + trend + noise
    
    # Generate OHLCV
    data = []
    start_time = datetime.now() - timedelta(minutes=5*bars)
    
    for i in range(bars):
        timestamp = start_time + timedelta(minutes=5*i)
        close = close_prices[i]
        
        # Generate realistic OHLC
        high = close + abs(np.random.randn() * 50)
        low = close - abs(np.random.randn() * 50)
        open_price = low + (high - low) * np.random.rand()
        volume = abs(np.random.randn() * 1000 + 5000)
        
        data.append({
            'timestamp': int(timestamp.timestamp() * 1000),
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('datetime')
    
    return df


def test_strategy():
    """Test the institutional strategy"""
    logger.info("="*80)
    logger.info("🧪 TESTING INSTITUTIONAL STRATEGY")
    logger.info("="*80)
    
    # Load config
    with open('institutional_strategy_config.json', 'r') as f:
        config = json.load(f)
    
    logger.info("✅ Config loaded")
    
    # Generate synthetic data
    logger.info("📊 Generating synthetic data...")
    df = generate_synthetic_data(bars=2000)
    logger.info(f"✅ Generated {len(df)} bars")
    
    # Run backtest
    logger.info("\n🚀 Running backtest...")
    backtester = InstitutionalBacktester(config)
    
    result = backtester.run_backtest(
        symbol='TEST_USDT',
        df=df,
        initial_capital=1000.0
    )
    
    # Print results
    print_backtest_report(result, 'TEST_USDT')
    
    # Validate results
    logger.info("\n🔍 Validating results...")
    
    checks = {
        'Backtest completed': True,  # If we got here, it completed
        'Signals generated': result.total_signals > 0,
        'Win rate calculated': result.win_rate >= 0,
        'PnL calculated': isinstance(result.total_pnl, (int, float)),
        'Equity curve exists': len(result.equity_curve) > 0,
        'Sharpe calculated': not np.isnan(result.sharpe_ratio),
        'Max drawdown calculated': result.max_drawdown <= 0,
    }
    
    all_passed = all(checks.values())
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {check_name}")
    
    if all_passed:
        logger.info("\n✅ ALL TESTS PASSED!")
    else:
        logger.warning("\n⚠️  SOME TESTS FAILED")
    
    logger.info("="*80)
    
    return all_passed


if __name__ == "__main__":
    success = test_strategy()
    exit(0 if success else 1)

