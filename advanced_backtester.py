"""
Advanced Backtester - Run 40 strategies across 10 coins in parallel
"""

import asyncio
import json
import multiprocessing as mp
import pickle
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import pandas as pd
from tqdm import tqdm

from data_fetcher import HistoricalDataFetcher, TEST_SYMBOLS
from backtest_engine import BacktestEngine, BacktestResult
from metrics_calculator import MetricsCalculator, PerformanceMetrics


def run_single_backtest(args: tuple) -> PerformanceMetrics:
    """
    Run a single backtest (called by worker process).
    
    Args:
        args: (strategy_dict, symbol, df_dict, initial_capital)
    
    Returns:
        PerformanceMetrics object
    """
    strategy, symbol, df_dict, initial_capital = args
    
    # Get data for this symbol
    df = df_dict[symbol]
    
    # Run backtest
    engine = BacktestEngine(strategy)
    result = engine.run_backtest(df, symbol, initial_capital)
    
    # Calculate metrics
    metrics = MetricsCalculator.calculate_all_metrics(result)
    
    return metrics


class AdvancedBacktester:
    """Orchestrate parallel backtesting of multiple strategies across multiple symbols."""
    
    def __init__(self, strategies_dir: str = "strategies", data_dir: str = "backtest_data", results_dir: str = "backtest_results"):
        self.strategies_dir = Path(strategies_dir)
        self.data_dir = Path(data_dir)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
    
    def load_strategies(self) -> List[Dict[str, Any]]:
        """Load all strategy configurations."""
        print("📂 Loading strategies...")
        strategies = []
        
        for strategy_file in sorted(self.strategies_dir.glob("strategy_*.json")):
            with open(strategy_file, 'r') as f:
                strategy = json.load(f)
                strategies.append(strategy)
        
        print(f"✅ Loaded {len(strategies)} strategies")
        return strategies
    
    def load_historical_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Load historical data for all symbols."""
        print("\n📊 Loading historical data...")
        data = {}
        
        # Remove MATICUSDT if present (it was removed from exchange)
        symbols = [s for s in symbols if s != "MATICUSDT"]
        
        for symbol in symbols:
            # Try to load from cache
            cache_files = list(self.data_dir.glob(f"{symbol}_*.pkl"))
            if cache_files:
                cache_file = cache_files[0]  # Use first match
                with open(cache_file, 'rb') as f:
                    df = pickle.load(f)
                    data[symbol] = df
                    print(f"  ✅ {symbol}: {len(df)} candles")
            else:
                print(f"  ⚠️ {symbol}: No cached data found")
        
        print(f"✅ Loaded data for {len(data)} symbols")
        return data
    
    def run_all_backtests(self, strategies: List[Dict], data: Dict[str, pd.DataFrame], initial_capital: float = 50.0) -> List[PerformanceMetrics]:
        """
        Run all backtests in parallel.
        
        Args:
            strategies: List of strategy configurations
            data: Dictionary mapping symbol -> DataFrame
            initial_capital: Starting capital in USD
        
        Returns:
            List of PerformanceMetrics objects
        """
        print(f"\n🚀 Running {len(strategies)} strategies × {len(data)} symbols = {len(strategies) * len(data)} backtests...")
        print(f"💰 Initial capital per account: ${initial_capital}")
        
        # Create all tasks
        tasks = []
        for strategy in strategies:
            for symbol in data.keys():
                tasks.append((strategy, symbol, data, initial_capital))
        
        print(f"⚙️ Total tasks: {len(tasks)}")
        
        # Determine number of workers (use all available cores)
        num_workers = mp.cpu_count()
        print(f"👷 Using {num_workers} parallel workers (all CPU cores)")
        
        # Run in parallel with progress bar
        results = []
        with mp.Pool(num_workers) as pool:
            for result in tqdm(
                pool.imap_unordered(run_single_backtest, tasks),
                total=len(tasks),
                desc="Running backtests",
                unit="backtest"
            ):
                results.append(result)
        
        print(f"\n✅ Completed {len(results)} backtests!")
        return results
    
    def aggregate_by_strategy(self, all_metrics: List[PerformanceMetrics]) -> Dict[int, Dict[str, Any]]:
        """
        Aggregate metrics across all symbols for each strategy.
        
        Returns:
            Dictionary mapping strategy_id -> aggregated metrics
        """
        print("\n📊 Aggregating results by strategy...")
        
        strategy_results = {}
        
        for metrics in all_metrics:
            strategy_id = metrics.strategy_id
            
            if strategy_id not in strategy_results:
                strategy_results[strategy_id] = {
                    'strategy_id': strategy_id,
                    'strategy_name': metrics.strategy_name,
                    'symbols': [],
                    'total_trades': 0,
                    'total_wins': 0,
                    'total_losses': 0,
                    'total_pnl_usd': 0.0,
                    'total_roi_pct': 0.0,
                    'avg_win_rate_pct': 0.0,
                    'avg_sharpe': 0.0,
                    'avg_sortino': 0.0,
                    'avg_max_dd_pct': 0.0,
                    'avg_profit_factor': 0.0,
                    'avg_trades_per_day': 0.0,
                    'avg_trades_per_hour': 0.0,
                    'best_symbol': '',
                    'best_symbol_roi': 0.0,
                    'worst_symbol': '',
                    'worst_symbol_roi': 0.0,
                    'symbol_metrics': [],
                }
            
            # Add to aggregates
            strategy_results[strategy_id]['symbols'].append(metrics.symbol)
            strategy_results[strategy_id]['total_trades'] += metrics.total_trades
            strategy_results[strategy_id]['total_wins'] += metrics.winning_trades
            strategy_results[strategy_id]['total_losses'] += metrics.losing_trades
            strategy_results[strategy_id]['total_pnl_usd'] += metrics.total_pnl_usd
            strategy_results[strategy_id]['total_roi_pct'] += metrics.total_roi_pct
            strategy_results[strategy_id]['symbol_metrics'].append(metrics)
            
            # Track best/worst symbol
            if metrics.total_roi_pct > strategy_results[strategy_id]['best_symbol_roi']:
                strategy_results[strategy_id]['best_symbol'] = metrics.symbol
                strategy_results[strategy_id]['best_symbol_roi'] = metrics.total_roi_pct
            
            if metrics.total_roi_pct < strategy_results[strategy_id]['worst_symbol_roi'] or not strategy_results[strategy_id]['worst_symbol']:
                strategy_results[strategy_id]['worst_symbol'] = metrics.symbol
                strategy_results[strategy_id]['worst_symbol_roi'] = metrics.total_roi_pct
        
        # Calculate averages
        for strategy_id, data in strategy_results.items():
            num_symbols = len(data['symbols'])
            if num_symbols > 0:
                data['avg_win_rate_pct'] = data['total_wins'] / data['total_trades'] * 100 if data['total_trades'] > 0 else 0.0
                data['avg_sharpe'] = sum(m.sharpe_ratio for m in data['symbol_metrics']) / num_symbols
                data['avg_sortino'] = sum(m.sortino_ratio for m in data['symbol_metrics']) / num_symbols
                data['avg_max_dd_pct'] = sum(m.max_drawdown_pct for m in data['symbol_metrics']) / num_symbols
                data['avg_profit_factor'] = sum(m.profit_factor if m.profit_factor != float('inf') else 0 for m in data['symbol_metrics']) / num_symbols
                data['avg_trades_per_day'] = sum(m.trades_per_day for m in data['symbol_metrics']) / num_symbols
                data['avg_trades_per_hour'] = sum(m.trades_per_hour for m in data['symbol_metrics']) / num_symbols
                data['avg_roi_pct'] = data['total_roi_pct'] / num_symbols
        
        print(f"✅ Aggregated {len(strategy_results)} strategies")
        return strategy_results
    
    def save_results(self, all_metrics: List[PerformanceMetrics], aggregated: Dict[int, Dict[str, Any]]) -> str:
        """
        Save results to JSON files.
        
        Returns:
            Path to saved results
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed metrics
        detailed_path = self.results_dir / f"detailed_metrics_{timestamp}.json"
        detailed_data = [
            {
                'strategy_id': m.strategy_id,
                'strategy_name': m.strategy_name,
                'symbol': m.symbol,
                'total_trades': m.total_trades,
                'win_rate_pct': round(m.win_rate_pct, 2),
                'total_roi_pct': round(m.total_roi_pct, 2),
                'roi_per_day_pct': round(m.roi_per_day_pct, 2),
                'roi_per_week_pct': round(m.roi_per_week_pct, 2),
                'roi_per_month_pct': round(m.roi_per_month_pct, 2),
                'sharpe_ratio': round(m.sharpe_ratio, 2),
                'sortino_ratio': round(m.sortino_ratio, 2),
                'max_drawdown_pct': round(m.max_drawdown_pct, 2),
                'profit_factor': round(m.profit_factor, 2) if m.profit_factor != float('inf') else 999,
                'trades_per_day': round(m.trades_per_day, 2),
                'trades_per_hour': round(m.trades_per_hour, 3),
                'final_capital': round(m.final_capital, 2),
            }
            for m in all_metrics
        ]
        
        with open(detailed_path, 'w') as f:
            json.dump(detailed_data, f, indent=2)
        
        print(f"💾 Saved detailed metrics to {detailed_path}")
        
        # Save aggregated results
        aggregated_path = self.results_dir / f"aggregated_results_{timestamp}.json"
        with open(aggregated_path, 'w') as f:
            # Convert to serializable format
            serializable = {}
            for sid, data in aggregated.items():
                serializable[str(sid)] = {k: v for k, v in data.items() if k != 'symbol_metrics'}
            json.dump(serializable, f, indent=2)
        
        print(f"💾 Saved aggregated results to {aggregated_path}")
        
        return str(detailed_path)


async def main():
    """Run the complete backtesting suite."""
    print("="*80)
    print("ADVANCED BACKTESTING SYSTEM")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    start_time = datetime.now()
    
    # Initialize backtester
    backtester = AdvancedBacktester()
    
    # Load strategies
    strategies = backtester.load_strategies()
    
    # Load historical data
    symbols = [s for s in TEST_SYMBOLS if s != "MATICUSDT"]
    data = backtester.load_historical_data(symbols)
    
    if not data:
        print("❌ No historical data available! Run data_fetcher.py first.")
        return
    
    # Run all backtests in parallel
    all_metrics = backtester.run_all_backtests(strategies, data, initial_capital=50.0)
    
    # Aggregate by strategy
    aggregated = backtester.aggregate_by_strategy(all_metrics)
    
    # Save results
    results_path = backtester.save_results(all_metrics, aggregated)
    
    # Calculate execution time
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Total strategies tested: {len(strategies)}")
    print(f"Total symbols tested: {len(data)}")
    print(f"Total backtests run: {len(all_metrics)}")
    print(f"Execution time: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print(f"Backtests per second: {len(all_metrics)/duration:.1f}")
    print("="*80)
    
    print("\n🎉 Backtesting complete! Now generating markdown report...")
    
    # Import and run report generator
    from report_generator import ReportGenerator
    report_gen = ReportGenerator()
    report_path = report_gen.generate_report(all_metrics, aggregated, results_path)
    
    print(f"\n✅ Full report saved to: {report_path}")
    print("\n🚀 DONE! Check the results in the backtest_results/ directory.")


if __name__ == "__main__":
    asyncio.run(main())

