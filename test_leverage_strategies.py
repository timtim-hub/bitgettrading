"""
Test Leverage-Aware Strategies - Comprehensive Testing Pipeline

Tests all strategies (060-089) on:
1. All 338 tokens first
2. Then re-test on tokens with >5% ROI
3. Compare leverage performance (25x vs 50x vs 100x)
4. Generate comprehensive reports
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
import time
from datetime import datetime

from backtest_engine import BacktestEngine
from metrics_calculator import MetricsCalculator
from data_fetcher import HistoricalDataFetcher
import pandas as pd


class LeverageStrategyTester:
    """
    Test multiple strategies across different leverage levels.
    """
    
    def __init__(self):
        self.backtest_results_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        self.backtest_results_dir.mkdir(exist_ok=True)
        self.strategies_dir = Path("/Users/macbookpro13/bitgettrading/strategies")
        self.cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    def load_strategies(self, start_id: int = 60, end_id: int = 89) -> List[Dict]:
        """Load strategies from JSON files."""
        strategies = []
        for strategy_id in range(start_id, end_id + 1):
            filepath = self.strategies_dir / f"strategy_{strategy_id:03d}.json"
            if filepath.exists():
                with open(filepath, 'r') as f:
                    strategy = json.load(f)
                    strategies.append(strategy)
        return strategies
    
    async def load_cached_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Load cached historical data for all symbols."""
        data_dict = {}
        
        print(f"📂 Loading cached data for {len(symbols)} symbols...")
        
        for symbol in symbols:
            # Try multiple cache file patterns
            cache_patterns = [
                self.cache_dir / f"{symbol}_1H_30d.pkl",
                self.cache_dir / f"{symbol}_1m_30d.pkl",
                self.cache_dir / f"{symbol}_1H.pkl",
            ]
            
            loaded = False
            for cache_file in cache_patterns:
                if cache_file.exists():
                    try:
                        df = pd.read_pickle(cache_file)
                        data_dict[symbol] = df
                        loaded = True
                        break
                    except Exception as e:
                        continue
            
            if not loaded:
                print(f"⚠️ No cached data for {symbol}, skipping...")
        
        print(f"✅ Loaded data for {len(data_dict)} symbols")
        return data_dict
    
    async def run_backtest_for_symbol(
        self, 
        strategy: Dict, 
        symbol: str, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> Optional[Dict]:
        """Run backtest for a single symbol with a strategy."""
        if symbol not in data_dict:
            return None
        
        df = data_dict[symbol]
        
        try:
            engine = BacktestEngine(strategy)
            result = engine.run_backtest(df, symbol, initial_capital=50.0)
            
            # Calculate metrics
            perf_metrics = MetricsCalculator.calculate_all_metrics(result)
            
            # Convert to dict
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
            metrics['leverage'] = strategy['leverage']
            
            return metrics
        except Exception as e:
            print(f"❌ Error backtesting {symbol} with {strategy['name']}: {e}")
            return None
    
    async def test_strategy_phase1(
        self, 
        strategy: Dict, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> List[Dict]:
        """Phase 1: Test strategy on all 338 tokens."""
        print(f"\n📊 Phase 1: Testing {strategy['name']} on {len(data_dict)} tokens...")
        
        results = []
        for idx, symbol in enumerate(data_dict.keys(), 1):
            if idx % 50 == 0:
                print(f"   Progress: {idx}/{len(data_dict)} tokens...")
            
            metrics = await self.run_backtest_for_symbol(strategy, symbol, data_dict)
            if metrics:
                results.append(metrics)
        
        print(f"✅ Completed Phase 1: {len(results)} results")
        return results
    
    async def test_strategy_phase2(
        self, 
        strategy: Dict, 
        phase1_results: List[Dict],
        data_dict: Dict[str, pd.DataFrame],
        min_roi: float = 5.0
    ) -> List[Dict]:
        """Phase 2: Re-test on tokens with >min_roi% ROI from Phase 1."""
        
        # Filter profitable tokens
        profitable_tokens = [
            r['symbol'] for r in phase1_results 
            if r.get('total_roi_pct', 0) > min_roi
        ]
        
        print(f"\n📊 Phase 2: Re-testing {strategy['name']} on {len(profitable_tokens)} profitable tokens (>{min_roi}% ROI)...")
        
        if not profitable_tokens:
            print(f"⚠️ No profitable tokens found for {strategy['name']}")
            return []
        
        results = []
        for idx, symbol in enumerate(profitable_tokens, 1):
            if idx % 20 == 0:
                print(f"   Progress: {idx}/{len(profitable_tokens)} tokens...")
            
            metrics = await self.run_backtest_for_symbol(strategy, symbol, data_dict)
            if metrics:
                results.append(metrics)
        
        print(f"✅ Completed Phase 2: {len(results)} results")
        return results
    
    def save_results(
        self, 
        strategy: Dict, 
        phase1_results: List[Dict], 
        phase2_results: List[Dict]
    ):
        """Save test results to JSON files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        strategy_name = strategy['name']
        
        # Save Phase 1 (all tokens)
        phase1_file = self.backtest_results_dir / f"{strategy_name}_all338_detailed_{timestamp}.json"
        with open(phase1_file, 'w') as f:
            json.dump(phase1_results, f, indent=2)
        
        # Save Phase 1 summary
        phase1_summary = self.calculate_summary(phase1_results, strategy)
        phase1_summary_file = self.backtest_results_dir / f"{strategy_name}_all338_summary_{timestamp}.json"
        with open(phase1_summary_file, 'w') as f:
            json.dump(phase1_summary, f, indent=2)
        
        # Save Phase 2 (filtered tokens)
        if phase2_results:
            phase2_file = self.backtest_results_dir / f"{strategy_name}_5pct_plus_detailed_{timestamp}.json"
            with open(phase2_file, 'w') as f:
                json.dump(phase2_results, f, indent=2)
            
            # Save Phase 2 summary
            phase2_summary = self.calculate_summary(phase2_results, strategy)
            phase2_summary_file = self.backtest_results_dir / f"{strategy_name}_5pct_plus_summary_{timestamp}.json"
            with open(phase2_summary_file, 'w') as f:
                json.dump(phase2_summary, f, indent=2)
        
        print(f"💾 Saved results for {strategy_name}")
    
    def calculate_summary(self, results: List[Dict], strategy: Dict) -> Dict:
        """Calculate summary statistics for a set of results."""
        if not results:
            return {}
        
        total_tokens = len(results)
        avg_roi = sum(r['total_roi_pct'] for r in results) / total_tokens
        avg_win_rate = sum(r['win_rate_pct'] for r in results) / total_tokens
        total_trades = sum(r['total_trades'] for r in results)
        avg_trades_per_day = sum(r['trades_per_day'] for r in results) / total_tokens
        
        # Calculate portfolio ROI
        initial_capital_per_token = 50.0
        total_initial = initial_capital_per_token * total_tokens
        total_final = sum(r['final_capital'] for r in results)
        portfolio_roi = ((total_final - total_initial) / total_initial * 100) if total_initial > 0 else 0
        
        # Count profitable tokens
        profitable_tokens = sum(1 for r in results if r['total_roi_pct'] > 0)
        
        return {
            'strategy_id': strategy['id'],
            'strategy_name': strategy['name'],
            'leverage': strategy['leverage'],
            'total_tokens_tested': total_tokens,
            'profitable_tokens': profitable_tokens,
            'profitable_pct': (profitable_tokens / total_tokens * 100) if total_tokens > 0 else 0,
            'portfolio_roi_pct': portfolio_roi,
            'avg_roi_per_token_pct': avg_roi,
            'avg_win_rate_pct': avg_win_rate,
            'total_trades': total_trades,
            'avg_trades_per_day': avg_trades_per_day,
            'total_capital_invested': total_initial,
            'total_final_capital': total_final,
            'total_profit': total_final - total_initial
        }
    
    async def test_all_strategies(self):
        """Test all 30 strategies through both phases."""
        
        print("="*100)
        print("🚀 LEVERAGE STRATEGY TESTING PIPELINE")
        print("="*100)
        print()
        
        # Load strategies
        strategies = self.load_strategies(60, 89)
        print(f"📋 Loaded {len(strategies)} strategies (IDs 60-89)")
        print()
        
        # Load all token symbols
        symbols_file = Path("/Users/macbookpro13/bitgettrading/all_bitget_symbols.txt")
        with open(symbols_file, 'r') as f:
            all_symbols = [line.strip() for line in f if line.strip()]
        
        print(f"📊 Testing on {len(all_symbols)} tokens")
        print()
        
        # Load cached data once
        data_dict = await self.load_cached_data(all_symbols)
        print()
        
        # Test each strategy
        all_summaries = []
        
        for idx, strategy in enumerate(strategies, 1):
            print("="*100)
            print(f"Strategy {idx}/{len(strategies)}: {strategy['name']} (Leverage: {strategy['leverage']}x)")
            print("="*100)
            
            start_time = time.time()
            
            # Phase 1: All tokens
            phase1_results = await self.test_strategy_phase1(strategy, data_dict)
            
            # Phase 2: Filtered tokens
            phase2_results = await self.test_strategy_phase2(strategy, phase1_results, data_dict, min_roi=5.0)
            
            # Save results
            self.save_results(strategy, phase1_results, phase2_results)
            
            # Calculate summaries
            phase1_summary = self.calculate_summary(phase1_results, strategy)
            phase2_summary = self.calculate_summary(phase2_results, strategy) if phase2_results else {}
            
            elapsed = time.time() - start_time
            
            print(f"\n⏱️ Completed in {elapsed:.1f}s")
            print(f"📈 Phase 1: {phase1_summary.get('portfolio_roi_pct', 0):.2f}% ROI on {len(phase1_results)} tokens")
            if phase2_results:
                print(f"📈 Phase 2: {phase2_summary.get('portfolio_roi_pct', 0):.2f}% ROI on {len(phase2_results)} tokens")
            print()
            
            all_summaries.append({
                'strategy': strategy['name'],
                'leverage': strategy['leverage'],
                'phase1': phase1_summary,
                'phase2': phase2_summary
            })
        
        # Generate final comparison report
        self.generate_final_report(all_summaries)
        
        print("="*100)
        print("✅ ALL TESTING COMPLETE!")
        print("="*100)
    
    def generate_final_report(self, summaries: List[Dict]):
        """Generate comprehensive final report comparing all strategies."""
        
        report = """# Leverage Strategy Testing Report

## 📊 Overview

Tested 30 strategies (10 base strategies x 3 leverage levels: 25x, 50x, 100x) on 338 tokens.

**Testing Protocol:**
1. **Phase 1**: Test all strategies on all 338 tokens
2. **Phase 2**: Re-test on tokens with >5% ROI from Phase 1

---

## 🏆 Top Performers by Portfolio ROI (Phase 2)

"""
        
        # Sort by Phase 2 portfolio ROI
        phase2_sorted = sorted(
            [s for s in summaries if s['phase2']],
            key=lambda x: x['phase2'].get('portfolio_roi_pct', 0),
            reverse=True
        )
        
        report += "| Rank | Strategy | Leverage | ROI % | Win Rate % | Tokens | Trades/Day |\n"
        report += "|------|----------|----------|-------|------------|--------|------------|\n"
        
        for idx, s in enumerate(phase2_sorted[:15], 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            name = s['strategy'][:30]
            leverage = s['leverage']
            roi = s['phase2'].get('portfolio_roi_pct', 0)
            win_rate = s['phase2'].get('avg_win_rate_pct', 0)
            tokens = s['phase2'].get('total_tokens_tested', 0)
            trades_day = s['phase2'].get('avg_trades_per_day', 0)
            
            report += f"| {medal} | {name} | {leverage}x | {roi:.2f}% | {win_rate:.2f}% | {tokens} | {trades_day:.2f} |\n"
        
        report += "\n---\n\n## 📈 Leverage Comparison\n\n"
        
        # Group by base strategy name
        leverage_comparison = {}
        for s in summaries:
            base_name = s['strategy'].rsplit('_', 1)[0]
            if base_name not in leverage_comparison:
                leverage_comparison[base_name] = {}
            leverage_comparison[base_name][s['leverage']] = s['phase2']
        
        report += "### Portfolio ROI by Leverage\n\n"
        report += "| Base Strategy | 25x ROI % | 50x ROI % | 100x ROI % | Best Leverage |\n"
        report += "|---------------|-----------|-----------|------------|---------------|\n"
        
        for base_name, leverage_data in leverage_comparison.items():
            roi_25x = leverage_data.get(25, {}).get('portfolio_roi_pct', 0)
            roi_50x = leverage_data.get(50, {}).get('portfolio_roi_pct', 0)
            roi_100x = leverage_data.get(100, {}).get('portfolio_roi_pct', 0)
            
            best_leverage = max(
                [(25, roi_25x), (50, roi_50x), (100, roi_100x)],
                key=lambda x: x[1]
            )[0]
            
            report += f"| {base_name[:25]} | {roi_25x:.2f}% | {roi_50x:.2f}% | {roi_100x:.2f}% | **{best_leverage}x** |\n"
        
        report += f"\n---\n\n## 💡 Key Insights\n\n"
        
        # Calculate insights
        if phase2_sorted:
            best_strategy = phase2_sorted[0]
            report += f"1. **Best Overall**: {best_strategy['strategy']} achieved {best_strategy['phase2']['portfolio_roi_pct']:.2f}% ROI\n"
            report += f"2. **Win Rate**: Top strategy has {best_strategy['phase2']['avg_win_rate_pct']:.2f}% win rate\n"
            report += f"3. **Profitable Tokens**: {best_strategy['phase2']['profitable_tokens']} out of {best_strategy['phase2']['total_tokens_tested']} tokens\n"
        
        report += "\n---\n\n## ⚠️ Risk Analysis\n\n"
        report += "**Liquidation Risk by Leverage:**\n"
        report += "- **25x**: ~3.5% distance to liquidation (MEDIUM risk)\n"
        report += "- **50x**: ~1.0% distance to liquidation (EXTREME risk)\n"
        report += "- **100x**: ~1.0% distance to liquidation (EXTREME risk)\n\n"
        report += "**Recommendation**: Start with 25x leverage. Higher leverage may offer higher returns but carries significantly higher liquidation risk.\n"
        
        report += f"\n---\n\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # Save report
        report_file = self.backtest_results_dir / f"LEVERAGE_COMPARISON_REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"📄 Final report saved: {report_file.name}")


async def main():
    """Run the leverage strategy tester."""
    tester = LeverageStrategyTester()
    await tester.test_all_strategies()


if __name__ == "__main__":
    asyncio.run(main())

