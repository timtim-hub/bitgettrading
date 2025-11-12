"""
Main Entry Point for Institutional Trading Strategy
Run backtest first, then optionally run live trading
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import sys

# Import institutional modules
from institutional_backtest import InstitutionalBacktester, print_backtest_report
from data_fetcher import HistoricalDataFetcher

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)7s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


async def fetch_historical_data(symbol: str, days: int = 90, timeframe: str = '5m') -> pd.DataFrame:
    """Fetch historical data for backtesting"""
    logger.info(f"📥 Fetching {days} days of {timeframe} data for {symbol}...")
    
    fetcher = HistoricalDataFetcher()
    
    try:
        df = await fetcher.fetch_candles(
            symbol=symbol,
            timeframe=timeframe,
            days=days,
            use_cache=True
        )
        
        if df is None or len(df) == 0:
            logger.error(f"❌ Failed to fetch data for {symbol}")
            return None
        
        logger.info(f"✅ Fetched {len(df)} candles for {symbol}")
        return df
    
    except Exception as e:
        logger.error(f"❌ Error fetching data for {symbol}: {e}")
        return None


async def run_backtest(config: dict, symbol: str, df: pd.DataFrame, initial_capital: float = 1000.0):
    """Run backtest for a single symbol"""
    logger.info(f"\n{'='*80}")
    logger.info(f"🚀 BACKTESTING: {symbol}")
    logger.info(f"{'='*80}\n")
    
    backtester = InstitutionalBacktester(config)
    
    try:
        result = backtester.run_backtest(
            symbol=symbol,
            df=df,
            initial_capital=initial_capital
        )
        
        # Print report
        print_backtest_report(result, symbol)
        
        # Save results
        results_dir = Path("backtest_results_institutional")
        results_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = results_dir / f"{symbol}_{timestamp}.json"
        
        # Save trade data
        trades_data = [
            {
                'entry_time': t.entry_time.isoformat(),
                'exit_time': t.exit_time.isoformat() if t.exit_time else None,
                'symbol': t.symbol,
                'side': t.side,
                'strategy': t.strategy,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'stop_price': t.stop_price,
                'size': t.size,
                'notional': t.notional,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct,
                'mae': t.mae,
                'mfe': t.mfe,
                'duration_min': t.duration_min,
                'exit_reason': t.exit_reason,
                'tp_hit': t.tp_hit,
                'fees_paid': t.fees_paid,
                'slippage_cost': t.slippage_cost
            }
            for t in result.trades
        ]
        
        results_summary = {
            'symbol': symbol,
            'start_date': result.start_date.isoformat(),
            'end_date': result.end_date.isoformat(),
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'total_pnl': result.total_pnl,
            'total_return_pct': result.total_return_pct,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'max_drawdown_pct': result.max_drawdown_pct,
            'avg_mae': result.avg_mae,
            'avg_mfe': result.avg_mfe,
            'profit_factor': result.profit_factor,
            'tp1_hits': result.tp1_hits,
            'tp2_hits': result.tp2_hits,
            'tp3_hits': result.tp3_hits,
            'sl_hits': result.sl_hits,
            'time_stops': result.time_stops,
            'tripwires': result.tripwires,
            'total_fees': result.total_fees,
            'total_slippage': result.total_slippage,
            'total_signals': result.total_signals,
            'signals_passed_gates': result.signals_passed_gates,
            'signals_failed_liq_guards': result.signals_failed_liq_guards,
            'pnl_by_hour': result.pnl_by_hour,
            'trades': trades_data
        }
        
        with open(result_file, 'w') as f:
            json.dump(results_summary, f, indent=2)
        
        logger.info(f"💾 Results saved to {result_file}")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Backtest failed for {symbol}: {e}", exc_info=True)
        return None


async def run_backtests_for_universe(config: dict, symbols: list, initial_capital: float = 1000.0):
    """Run backtests for multiple symbols"""
    logger.info(f"\n{'='*80}")
    logger.info(f"🌍 BACKTESTING UNIVERSE: {len(symbols)} symbols")
    logger.info(f"{'='*80}\n")
    
    results = {}
    
    for symbol in symbols:
        # Fetch data
        df = await fetch_historical_data(symbol, days=90, timeframe='5m')
        
        if df is None:
            continue
        
        # Run backtest
        result = await run_backtest(config, symbol, df, initial_capital)
        
        if result:
            results[symbol] = result
    
    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info(f"📊 BACKTEST SUMMARY: {len(results)} symbols tested")
    logger.info(f"{'='*80}\n")
    
    if results:
        # Sort by total return
        sorted_results = sorted(results.items(), key=lambda x: x[1].total_return_pct, reverse=True)
        
        print(f"\n{'Symbol':<15} {'Return %':>10} {'Win Rate':>10} {'Trades':>8} {'Sharpe':>8} {'Max DD%':>10}")
        print("-" * 80)
        
        for symbol, result in sorted_results:
            print(
                f"{symbol:<15} "
                f"{result.total_return_pct:>9.2f}% "
                f"{result.win_rate:>9.1f}% "
                f"{result.total_trades:>8} "
                f"{result.sharpe_ratio:>7.2f} "
                f"{result.max_drawdown_pct:>9.2f}%"
            )
        
        # Overall stats
        avg_return = sum(r.total_return_pct for r in results.values()) / len(results)
        avg_win_rate = sum(r.win_rate for r in results.values()) / len(results)
        profitable_count = sum(1 for r in results.values() if r.total_pnl > 0)
        
        print("-" * 80)
        print(f"{'AVERAGE':<15} {avg_return:>9.2f}% {avg_win_rate:>9.1f}%")
        print(f"{'PROFITABLE':<15} {profitable_count}/{len(results)} ({profitable_count/len(results)*100:.1f}%)")
        print()
    
    return results


async def main():
    """Main entry point"""
    logger.info("="*80)
    logger.info("🏦 INSTITUTIONAL TRADING STRATEGY")
    logger.info("25x Leverage | LSVR + VWAP-MR + Trend")
    logger.info("="*80)
    
    # Load config
    config_file = Path("institutional_strategy_config.json")
    
    if not config_file.exists():
        logger.error(f"❌ Config file not found: {config_file}")
        return
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    logger.info("✅ Config loaded")
    logger.info(f"  Leverage: {config['leverage']}x")
    logger.info(f"  Margin per trade: {config['margin_fraction_per_trade']*100:.0f}%")
    logger.info(f"  Max symbols: {config['concurrency']['max_symbols']}")
    
    # Test symbols (start with majors)
    test_symbols = [
        'BTCUSDT',
        'ETHUSDT',
        'SOLUSDT'
    ]
    
    logger.info(f"\n📋 Test symbols: {', '.join(test_symbols)}")
    
    # Run backtests
    backtest_config = config.get('backtesting', {})
    initial_capital = backtest_config.get('initial_capital_usdt', 1000.0)
    
    results = await run_backtests_for_universe(config, test_symbols, initial_capital)
    
    # Check if live trading is enabled
    if config['mode'].get('live_enabled', False):
        logger.warning("\n⚠️  Live trading is ENABLED in config")
        logger.warning("⚠️  This is a new strategy - recommend paper trading first")
        logger.warning("⚠️  Set 'live_enabled': false to disable live trading")
        
        # For now, we won't start live trading automatically
        logger.info("\n✋ Stopping here. Review backtest results before enabling live trading.")
    else:
        logger.info("\n✅ Live trading is DISABLED (safe mode)")
        logger.info("   Enable in config when ready: 'live_enabled': true")
    
    logger.info(f"\n{'='*80}")
    logger.info("✅ INSTITUTIONAL STRATEGY TEST COMPLETE")
    logger.info(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())

