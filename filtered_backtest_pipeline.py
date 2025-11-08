"""
Filtered Backtest Pipeline - Progressive Token Filtering
Tests strategies on profitable tokens only, progressively narrowing down.
"""

import json
import asyncio
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
from backtest_engine import BacktestEngine
from metrics_calculator import MetricsCalculator
from data_fetcher import HistoricalDataFetcher
import multiprocessing as mp
from functools import partial
import os

def identify_profitable_tokens(detailed_metrics_file: str, strategy_id: int, min_roi_pct: float = 0.0) -> List[str]:
    """
    Identify tokens that meet the minimum ROI threshold for a specific strategy.
    
    Args:
        detailed_metrics_file: Path to detailed_metrics JSON
        strategy_id: Strategy ID to filter by
        min_roi_pct: Minimum ROI percentage (e.g., 5.0 for 5%)
    
    Returns:
        List of profitable token symbols
    """
    with open(detailed_metrics_file, 'r') as f:
        metrics = json.load(f)
    
    profitable_tokens = [
        m['symbol'] 
        for m in metrics 
        if m['strategy_id'] == strategy_id and m['total_roi_pct'] >= min_roi_pct
    ]
    
    return sorted(profitable_tokens)


def run_single_backtest(args):
    """Worker function for parallel backtesting."""
    strategy_path, symbol, data_dict = args
    
    try:
        # Load strategy
        with open(strategy_path, 'r') as f:
            strategy = json.load(f)
        
        # Get data for this symbol
        if symbol not in data_dict:
            return None
        
        df = data_dict[symbol]
        if df is None or len(df) < 50:
            return None
        
        # Run backtest
        engine = BacktestEngine(strategy)
        result = engine.run_backtest(df, symbol, initial_capital=50.0)
        
        # Calculate metrics
        perf_metrics = MetricsCalculator.calculate_all_metrics(result)
        
        # Convert to dict format
        metrics = {
            'total_trades': perf_metrics.total_trades,
            'win_rate_pct': perf_metrics.win_rate_pct,
            'total_roi_pct': perf_metrics.total_roi_pct,
            'roi_per_day_pct': perf_metrics.roi_per_day_pct,
            'roi_per_week_pct': perf_metrics.roi_per_week_pct,
            'roi_per_month_pct': perf_metrics.roi_per_month_pct,
            'sharpe_ratio': perf_metrics.sharpe_ratio,
            'sortino_ratio': perf_metrics.sortino_ratio,
            'max_drawdown_pct': perf_metrics.max_drawdown_pct,
            'profit_factor': perf_metrics.profit_factor,
            'trades_per_day': perf_metrics.trades_per_day,
            'trades_per_hour': perf_metrics.trades_per_hour,
            'final_capital': perf_metrics.final_capital
        }
        
        # Add metadata
        metrics['strategy_id'] = strategy['id']
        metrics['strategy_name'] = strategy['name']
        metrics['symbol'] = symbol
        
        return metrics
    except Exception as e:
        print(f"❌ Error backtesting {symbol}: {e}")
        return None


async def load_cached_data(symbols: List[str]) -> Dict[str, any]:
    """Load cached data for specified symbols."""
    import pickle
    cache_dir = Path("backtest_data")
    data_dict = {}
    
    print(f"📊 Loading cached data for {len(symbols)} tokens...")
    
    for symbol in symbols:
        # Try different cache file formats
        cache_patterns = [
            cache_dir / f"{symbol}_1H_30d.pkl",
            cache_dir / f"{symbol}_1m_30d.pkl",
            cache_dir / f"{symbol}_1H.pkl",
        ]
        
        loaded = False
        for cache_file in cache_patterns:
            if cache_file.exists():
                try:
                    with open(cache_file, 'rb') as f:
                        df = pickle.load(f)
                    data_dict[symbol] = df
                    loaded = True
                    break
                except Exception as e:
                    continue
        
        if not loaded:
            print(f"⚠️ No cached data for {symbol}")
    
    print(f"✅ Loaded {len(data_dict)} datasets")
    return data_dict


def save_results(results: List[Dict], test_name: str, timestamp: str):
    """Save backtest results."""
    output_dir = Path("backtest_results")
    output_dir.mkdir(exist_ok=True)
    
    # Save detailed metrics
    detailed_file = output_dir / f"{test_name}_detailed_{timestamp}.json"
    with open(detailed_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ Saved results to {detailed_file}")
    
    # Generate summary report
    profitable_count = len([r for r in results if r['total_roi_pct'] > 0])
    total_roi = sum(r['total_roi_pct'] for r in results)
    avg_roi = total_roi / len(results) if results else 0
    total_trades = sum(r['total_trades'] for r in results)
    
    # Calculate portfolio metrics
    initial_capital_per_token = 50.0
    total_initial = initial_capital_per_token * len(results)
    total_final = sum(initial_capital_per_token * (1 + r['total_roi_pct'] / 100.0) for r in results)
    portfolio_roi = ((total_final - total_initial) / total_initial) * 100
    
    summary = {
        'test_name': test_name,
        'timestamp': timestamp,
        'total_tokens': len(results),
        'profitable_tokens': profitable_count,
        'unprofitable_tokens': len(results) - profitable_count,
        'total_trades': total_trades,
        'avg_roi_pct': round(avg_roi, 2),
        'portfolio_roi_pct': round(portfolio_roi, 2),
        'portfolio_profit_usd': round(total_final - total_initial, 2),
        'best_token': max(results, key=lambda x: x['total_roi_pct'])['symbol'],
        'best_roi_pct': max(results, key=lambda x: x['total_roi_pct'])['total_roi_pct'],
        'worst_token': min(results, key=lambda x: x['total_roi_pct'])['symbol'],
        'worst_roi_pct': min(results, key=lambda x: x['total_roi_pct'])['total_roi_pct'],
    }
    
    summary_file = output_dir / f"{test_name}_summary_{timestamp}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY: {test_name}")
    print(f"{'='*80}")
    print(f"Total Tokens: {summary['total_tokens']}")
    print(f"Profitable: {summary['profitable_tokens']} ({summary['profitable_tokens']/summary['total_tokens']*100:.1f}%)")
    print(f"Total Trades: {summary['total_trades']}")
    print(f"Average ROI: {summary['avg_roi_pct']:.2f}%")
    print(f"Portfolio ROI: {summary['portfolio_roi_pct']:.2f}%")
    print(f"Portfolio P&L: ${summary['portfolio_profit_usd']:.2f}")
    print(f"Best Token: {summary['best_token']} ({summary['best_roi_pct']:.2f}%)")
    print(f"Worst Token: {summary['worst_token']} ({summary['worst_roi_pct']:.2f}%)")
    print(f"{'='*80}\n")
    
    return summary


async def run_filtered_backtest(strategy_path: str, symbols: List[str], test_name: str):
    """Run backtest on filtered token list."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n{'='*80}")
    print(f"🚀 STARTING: {test_name}")
    print(f"{'='*80}")
    print(f"Strategy: {strategy_path}")
    print(f"Tokens: {len(symbols)}")
    print(f"{'='*80}\n")
    
    # Load data
    data_dict = await load_cached_data(symbols)
    
    if not data_dict:
        print("❌ No data available!")
        return None
    
    # Prepare arguments for parallel processing
    args = [(strategy_path, symbol, data_dict) for symbol in symbols if symbol in data_dict]
    
    # Run backtests in parallel
    print(f"🔥 Running {len(args)} backtests in parallel...")
    num_workers = min(10, os.cpu_count())
    
    with mp.Pool(num_workers) as pool:
        results = pool.map(run_single_backtest, args)
    
    # Filter out None results
    results = [r for r in results if r is not None]
    
    if not results:
        print("❌ No successful backtests!")
        return None
    
    # Save results
    summary = save_results(results, test_name, timestamp)
    
    return {
        'summary': summary,
        'results': results,
        'timestamp': timestamp
    }


async def main():
    """Main pipeline execution."""
    
    print("\n" + "="*80)
    print("🎯 FILTERED BACKTEST PIPELINE")
    print("="*80 + "\n")
    
    # Step 1: Test WINNER strategy on profitable tokens only
    print("📍 STEP 1: Testing WINNER strategy on profitable tokens (ROI > 0%)")
    print("-" * 80)
    
    # Identify profitable tokens from previous full backtest
    previous_metrics = "backtest_results/detailed_metrics_20251108_030120.json"
    winner_strategy_id = 27  # From the comprehensive report
    
    profitable_tokens = identify_profitable_tokens(
        previous_metrics, 
        winner_strategy_id, 
        min_roi_pct=0.0
    )
    
    print(f"✅ Found {len(profitable_tokens)} profitable tokens for WINNER strategy")
    print(f"Top 10: {profitable_tokens[:10]}")
    
    step1_result = await run_filtered_backtest(
        "strategies/strategy_027.json",
        profitable_tokens,
        "WINNER_profitable_only"
    )
    
    # Step 2: Create new LightGBM strategy (NEVER overwrite existing!)
    print("\n📍 STEP 2: Creating new LightGBM-focused strategy")
    print("-" * 80)
    
    # Find next available strategy number
    strategy_dir = Path("strategies")
    existing_strategies = list(strategy_dir.glob("strategy_*.json"))
    next_id = max([int(s.stem.split('_')[1]) for s in existing_strategies]) + 1
    
    lightgbm_strategy = {
        "id": next_id,
        "name": "LightGBM_ML_Primary_Predictor",
        "category": "Machine Learning + Momentum",
        "rationale": "ML ensemble using LightGBM for price prediction with TA confirmation. Primary: ML prediction (65%+ confidence), Secondary: RSI/Volume/MACD alignment",
        "entry_threshold": 0.8,  # Lower threshold, ML prediction is primary
        "stop_loss_pct": 0.50,  # 50% capital = 2% price at 25x
        "take_profit_pct": 0.20,  # 20% capital = 0.8% price at 25x
        "trailing_callback": 0.03,  # Tight 3% trailing
        "volume_ratio": 1.3,  # Volume 30% above average
        "confluence_required": 2,  # ML + any 1 indicator
        "position_size_pct": 0.12,  # 12% per position
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ml_lightgbm",
        "entry_method": "ml_ensemble",
        "exit_method": "trailing_tp",
        "risk_style": "ml_aggressive",
        # Extended ML-specific parameters
        "ml_config": {
            "model": "lightgbm",
            "features": ["rsi", "macd", "bb_width", "volume_ratio", "price_change", "ema_cross"],
            "lookback": 100,
            "confidence_threshold": 0.65,
            "rsi_period": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            "volume_ma_period": 20
        }
    }
    
    lightgbm_path = strategy_dir / f"strategy_{next_id:03d}.json"
    with open(lightgbm_path, 'w') as f:
        json.dump(lightgbm_strategy, f, indent=2)
    
    print(f"✅ Created new strategy: {lightgbm_path}")
    print(f"Strategy ID: {next_id}")
    print(f"Strategy Name: {lightgbm_strategy['name']}")
    
    # Step 3: Test LightGBM on ALL 338 tokens
    print("\n📍 STEP 3: Testing LightGBM strategy on ALL 338 tokens")
    print("-" * 80)
    
    # Load all symbols
    with open("all_bitget_symbols.txt", "r") as f:
        all_symbols = [line.strip() for line in f if line.strip()]
    
    step3_result = await run_filtered_backtest(
        str(lightgbm_path),
        all_symbols,
        f"LightGBM_strategy{next_id:03d}_all338"
    )
    
    # Step 4: Test LightGBM on 5%+ ROI tokens from Step 3
    print("\n📍 STEP 4: Testing LightGBM strategy on 5%+ ROI tokens only")
    print("-" * 80)
    
    if step3_result and step3_result['results']:
        tokens_5pct_plus = [
            r['symbol'] 
            for r in step3_result['results'] 
            if r['total_roi_pct'] >= 5.0
        ]
        
        print(f"✅ Found {len(tokens_5pct_plus)} tokens with 5%+ ROI")
        print(f"Tokens: {tokens_5pct_plus[:20]}...")
        
        if len(tokens_5pct_plus) > 0:
            step4_result = await run_filtered_backtest(
                str(lightgbm_path),
                tokens_5pct_plus,
                f"LightGBM_strategy{next_id:03d}_5pct_plus"
            )
        else:
            print("⚠️ No tokens met 5%+ ROI threshold, skipping Step 4")
            step4_result = None
    else:
        print("⚠️ Step 3 failed, skipping Step 4")
        step4_result = None
    
    # Final Summary
    print("\n" + "="*80)
    print("🎉 PIPELINE COMPLETE!")
    print("="*80 + "\n")
    
    print("📊 RESULTS SUMMARY:")
    print("-" * 80)
    
    if step1_result:
        print(f"\n✅ STEP 1: WINNER on profitable tokens")
        print(f"   Portfolio ROI: {step1_result['summary']['portfolio_roi_pct']:.2f}%")
        print(f"   Tokens: {step1_result['summary']['total_tokens']}")
        print(f"   Profitable: {step1_result['summary']['profitable_tokens']}")
    
    if step3_result:
        print(f"\n✅ STEP 3: LightGBM on all 338 tokens")
        print(f"   Portfolio ROI: {step3_result['summary']['portfolio_roi_pct']:.2f}%")
        print(f"   Tokens: {step3_result['summary']['total_tokens']}")
        print(f"   Profitable: {step3_result['summary']['profitable_tokens']}")
    
    if step4_result:
        print(f"\n✅ STEP 4: LightGBM on 5%+ ROI tokens")
        print(f"   Portfolio ROI: {step4_result['summary']['portfolio_roi_pct']:.2f}%")
        print(f"   Tokens: {step4_result['summary']['total_tokens']}")
        print(f"   Profitable: {step4_result['summary']['profitable_tokens']}")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

