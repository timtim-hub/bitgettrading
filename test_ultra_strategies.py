"""
Test Ultra-High ROI Strategies

ALWAYS includes:
- ROI for 24h, 7d, 30d (MANDATORY!)
- Win rate
- Trades per day
- All comprehensive metrics
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


class UltraStrategyTester:
    """Test ultra-high ROI strategies with comprehensive reporting."""
    
    def __init__(self):
        self.backtest_results_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        self.backtest_results_dir.mkdir(exist_ok=True)
        self.strategies_dir = Path("/Users/macbookpro13/bitgettrading/strategies")
        self.cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    def load_strategies(self, start_id: int = 90, end_id: int = 109) -> List[Dict]:
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
            
            # Convert to dict with ALL metrics (especially time-based ROI!)
            metrics = {
                'total_trades': perf_metrics.total_trades,
                'win_rate_pct': perf_metrics.win_rate_pct,
                'total_roi_pct': perf_metrics.total_roi_pct,
                # ⭐ CRITICAL: TIME-BASED ROI (ALWAYS INCLUDE!)
                'roi_per_day_pct': perf_metrics.roi_per_day_pct,
                'roi_per_week_pct': perf_metrics.roi_per_week_pct,
                'roi_per_month_pct': perf_metrics.roi_per_month_pct,
                # Capital at intervals
                'capital_24h': perf_metrics.capital_24h,
                'capital_1week': perf_metrics.capital_1week,
                'final_capital': perf_metrics.final_capital,
                # Risk metrics
                'sharpe_ratio': perf_metrics.sharpe_ratio,
                'sortino_ratio': perf_metrics.sortino_ratio,
                'max_drawdown_pct': perf_metrics.max_drawdown_pct,
                'profit_factor': perf_metrics.profit_factor,
                'calmar_ratio': perf_metrics.calmar_ratio,
                # Frequency
                'trades_per_day': perf_metrics.trades_per_day,
                'trades_per_hour': perf_metrics.trades_per_hour,
                # Streaks
                'win_streak': perf_metrics.win_streak,
                'loss_streak': perf_metrics.loss_streak,
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
        
        # Save Phase 1
        phase1_file = self.backtest_results_dir / f"{strategy_name}_all338_detailed_{timestamp}.json"
        with open(phase1_file, 'w') as f:
            json.dump(phase1_results, f, indent=2)
        
        # Save Phase 1 summary
        phase1_summary = self.calculate_summary(phase1_results, strategy)
        phase1_summary_file = self.backtest_results_dir / f"{strategy_name}_all338_summary_{timestamp}.json"
        with open(phase1_summary_file, 'w') as f:
            json.dump(phase1_summary, f, indent=2)
        
        # Save Phase 2
        if phase2_results:
            phase2_file = self.backtest_results_dir / f"{strategy_name}_5pct_plus_detailed_{timestamp}.json"
            with open(phase2_file, 'w') as f:
                json.dump(phase2_results, f, indent=2)
            
            phase2_summary = self.calculate_summary(phase2_results, strategy)
            phase2_summary_file = self.backtest_results_dir / f"{strategy_name}_5pct_plus_summary_{timestamp}.json"
            with open(phase2_summary_file, 'w') as f:
                json.dump(phase2_summary, f, indent=2)
        
        print(f"💾 Saved results for {strategy_name}")
    
    def calculate_summary(self, results: List[Dict], strategy: Dict) -> Dict:
        """Calculate summary statistics."""
        if not results:
            return {}
        
        total_tokens = len(results)
        
        # ⭐ CRITICAL: Calculate time-based ROI averages
        avg_roi_day = sum(r.get('roi_per_day_pct', 0) for r in results) / total_tokens
        avg_roi_week = sum(r.get('roi_per_week_pct', 0) for r in results) / total_tokens
        avg_roi_month = sum(r.get('roi_per_month_pct', 0) for r in results) / total_tokens
        
        avg_roi = sum(r['total_roi_pct'] for r in results) / total_tokens
        avg_win_rate = sum(r['win_rate_pct'] for r in results) / total_tokens
        total_trades = sum(r['total_trades'] for r in results)
        avg_trades_per_day = sum(r['trades_per_day'] for r in results) / total_tokens
        
        # Portfolio ROI
        initial_capital_per_token = 50.0
        total_initial = initial_capital_per_token * total_tokens
        total_final = sum(r['final_capital'] for r in results)
        portfolio_roi = ((total_final - total_initial) / total_initial * 100) if total_initial > 0 else 0
        
        # ⭐ Portfolio time-based ROI
        total_capital_24h = sum(r.get('capital_24h', 50.0) for r in results)
        total_capital_1week = sum(r.get('capital_1week', 50.0) for r in results)
        
        portfolio_roi_24h = ((total_capital_24h - total_initial) / total_initial * 100) if total_initial > 0 else 0
        portfolio_roi_1week = ((total_capital_1week - total_initial) / total_initial * 100) if total_initial > 0 else 0
        
        # Count profitable
        profitable_tokens = sum(1 for r in results if r['total_roi_pct'] > 0)
        
        return {
            'strategy_id': strategy['id'],
            'strategy_name': strategy['name'],
            'leverage': strategy['leverage'],
            'total_tokens_tested': total_tokens,
            'profitable_tokens': profitable_tokens,
            'profitable_pct': (profitable_tokens / total_tokens * 100) if total_tokens > 0 else 0,
            'portfolio_roi_pct': portfolio_roi,
            # ⭐ TIME-BASED ROI (ALWAYS INCLUDE!)
            'portfolio_roi_24h_pct': portfolio_roi_24h,
            'portfolio_roi_1week_pct': portfolio_roi_1week,
            'avg_roi_per_day_pct': avg_roi_day,
            'avg_roi_per_week_pct': avg_roi_week,
            'avg_roi_per_month_pct': avg_roi_month,
            # Other metrics
            'avg_roi_per_token_pct': avg_roi,
            'avg_win_rate_pct': avg_win_rate,
            'total_trades': total_trades,
            'avg_trades_per_day': avg_trades_per_day,
            'total_capital_invested': total_initial,
            'total_final_capital': total_final,
            'total_profit': total_final - total_initial,
            'total_capital_24h': total_capital_24h,
            'total_capital_1week': total_capital_1week
        }
    
    def generate_markdown_report(self, all_summaries: List[Dict], output_file: Path):
        """Generate comprehensive markdown report with TIME-BASED ROI prominently displayed."""
        
        report = f"""# Ultra-High ROI Strategies Test Report

## 📊 Overview

Tested {len(all_summaries)} ultra-optimized strategies on 338 tokens.

**Testing Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 🏆 Top Performers (Phase 2: >5% ROI Filtered)

⭐ **SORTED BY PORTFOLIO ROI** ⭐

"""
        
        # Sort by Phase 2 portfolio ROI
        phase2_sorted = sorted(
            [s for s in all_summaries if s.get('phase2')],
            key=lambda x: x['phase2'].get('portfolio_roi_pct', 0),
            reverse=True
        )
        
        report += "\n### 📈 Top 10 Strategies\n\n"
        report += "| Rank | Strategy | Leverage | Portfolio ROI | ROI/Day | ROI/Week | ROI/Month | Win Rate | Tokens |\n"
        report += "|------|----------|----------|---------------|---------|----------|-----------|----------|--------|\n"
        
        for idx, s in enumerate(phase2_sorted[:10], 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            name = s['strategy'][:25]
            leverage = s['leverage']
            p2 = s['phase2']
            
            roi = p2.get('portfolio_roi_pct', 0)
            roi_day = p2.get('avg_roi_per_day_pct', 0)
            roi_week = p2.get('avg_roi_per_week_pct', 0)
            roi_month = p2.get('avg_roi_per_month_pct', 0)
            win_rate = p2.get('avg_win_rate_pct', 0)
            tokens = p2.get('total_tokens_tested', 0)
            
            report += f"| {medal} | {name} | {leverage}x | **{roi:.2f}%** | {roi_day:.2f}% | {roi_week:.2f}% | {roi_month:.2f}% | {win_rate:.2f}% | {tokens} |\n"
        
        # Detailed section for each strategy
        report += "\n---\n\n## 📊 Detailed Results\n\n"
        
        for idx, s in enumerate(phase2_sorted, 1):
            name = s['strategy']
            leverage = s['leverage']
            p1 = s.get('phase1', {})
            p2 = s.get('phase2', {})
            
            report += f"### {idx}. {name}\n\n"
            report += f"**Leverage**: {leverage}x\n\n"
            
            # Phase 1 Results
            report += "**Phase 1 (All 338 Tokens)**:\n"
            report += f"- Portfolio ROI: {p1.get('portfolio_roi_pct', 0):.2f}%\n"
            report += f"- Profitable Tokens: {p1.get('profitable_tokens', 0)}/{p1.get('total_tokens_tested', 0)} ({p1.get('profitable_pct', 0):.1f}%)\n"
            report += f"- Total Trades: {p1.get('total_trades', 0)}\n\n"
            
            # Phase 2 Results (⭐ WITH TIME-BASED ROI!)
            if p2:
                report += "**Phase 2 (>5% ROI Tokens)**:\n"
                report += f"- **Portfolio ROI**: **{p2.get('portfolio_roi_pct', 0):.2f}%**\n"
                report += f"- **ROI per Day**: **{p2.get('avg_roi_per_day_pct', 0):.2f}%**\n"
                report += f"- **ROI per Week**: **{p2.get('avg_roi_per_week_pct', 0):.2f}%**\n"
                report += f"- **ROI per Month**: **{p2.get('avg_roi_per_month_pct', 0):.2f}%**\n"
                report += f"- Win Rate: {p2.get('avg_win_rate_pct', 0):.2f}%\n"
                report += f"- Tokens: {p2.get('total_tokens_tested', 0)}\n"
                report += f"- Total Trades: {p2.get('total_trades', 0)}\n"
                report += f"- Trades per Day: {p2.get('avg_trades_per_day', 0):.2f}\n"
                report += f"- Capital: ${p2.get('total_capital_invested', 0):.2f} → ${p2.get('total_final_capital', 0):.2f}\n"
                report += f"- Profit: ${p2.get('total_profit', 0):.2f}\n"
                
                # ⭐ Capital at intervals
                report += f"\n**Capital Growth**:\n"
                report += f"- 24h: ${p2.get('total_capital_24h', 0):.2f} ({p2.get('portfolio_roi_24h_pct', 0):.2f}%)\n"
                report += f"- 1 Week: ${p2.get('total_capital_1week', 0):.2f} ({p2.get('portfolio_roi_1week_pct', 0):.2f}%)\n"
                report += f"- 30 Days: ${p2.get('total_final_capital', 0):.2f} ({p2.get('portfolio_roi_pct', 0):.2f}%)\n"
            
            report += "\n---\n\n"
        
        # Summary
        if phase2_sorted:
            best = phase2_sorted[0]
            report += "## 🎯 Key Findings\n\n"
            report += f"1. **Best Strategy**: {best['strategy']} @ {best['leverage']}x\n"
            report += f"2. **Portfolio ROI**: {best['phase2']['portfolio_roi_pct']:.2f}%\n"
            report += f"3. **Daily ROI**: {best['phase2']['avg_roi_per_day_pct']:.2f}%\n"
            report += f"4. **Weekly ROI**: {best['phase2']['avg_roi_per_week_pct']:.2f}%\n"
            report += f"5. **Monthly ROI**: {best['phase2']['avg_roi_per_month_pct']:.2f}%\n"
            report += f"6. **Win Rate**: {best['phase2']['avg_win_rate_pct']:.2f}%\n"
            report += f"7. **Profitable Tokens**: {best['phase2']['profitable_tokens']}/{best['phase2']['total_tokens_tested']}\n"
        
        report += "\n---\n\n"
        report += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += "**Version**: V5 Ultra-High ROI Edition\n"
        
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"📄 Report saved: {output_file.name}")
    
    async def test_all_strategies(self):
        """Test all ultra-high ROI strategies."""
        
        print("="*100)
        print("🚀 ULTRA-HIGH ROI STRATEGY TESTING")
        print("="*100)
        print()
        
        # Load strategies
        strategies = self.load_strategies(90, 109)
        print(f"📋 Loaded {len(strategies)} strategies (IDs 90-109)")
        print()
        
        # Load symbols
        symbols_file = Path("/Users/macbookpro13/bitgettrading/all_bitget_symbols.txt")
        with open(symbols_file, 'r') as f:
            all_symbols = [line.strip() for line in f if line.strip()]
        
        print(f"📊 Testing on {len(all_symbols)} tokens")
        print()
        
        # Load data once
        data_dict = await self.load_cached_data(all_symbols)
        print()
        
        # Test each strategy
        all_summaries = []
        
        for idx, strategy in enumerate(strategies, 1):
            print("="*100)
            print(f"Strategy {idx}/{len(strategies)}: {strategy['name']} (Leverage: {strategy['leverage']}x)")
            print("="*100)
            
            start_time = time.time()
            
            # Phase 1
            phase1_results = await self.test_strategy_phase1(strategy, data_dict)
            
            # Phase 2
            phase2_results = await self.test_strategy_phase2(strategy, phase1_results, data_dict, min_roi=5.0)
            
            # Save
            self.save_results(strategy, phase1_results, phase2_results)
            
            # Summaries
            phase1_summary = self.calculate_summary(phase1_results, strategy)
            phase2_summary = self.calculate_summary(phase2_results, strategy) if phase2_results else {}
            
            elapsed = time.time() - start_time
            
            print(f"\n⏱️ Completed in {elapsed:.1f}s")
            print(f"📈 Phase 1: {phase1_summary.get('portfolio_roi_pct', 0):.2f}% ROI")
            if phase2_results:
                print(f"📈 Phase 2: {phase2_summary.get('portfolio_roi_pct', 0):.2f}% ROI")
                print(f"⭐ Daily: {phase2_summary.get('avg_roi_per_day_pct', 0):.2f}% | Weekly: {phase2_summary.get('avg_roi_per_week_pct', 0):.2f}% | Monthly: {phase2_summary.get('avg_roi_per_month_pct', 0):.2f}%")
            print()
            
            all_summaries.append({
                'strategy': strategy['name'],
                'leverage': strategy['leverage'],
                'phase1': phase1_summary,
                'phase2': phase2_summary
            })
        
        # Generate final report
        report_file = self.backtest_results_dir / f"ULTRA_STRATEGIES_REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        self.generate_markdown_report(all_summaries, report_file)
        
        print("="*100)
        print("✅ ALL TESTING COMPLETE!")
        print("="*100)


async def main():
    """Run the ultra strategy tester."""
    tester = UltraStrategyTester()
    await tester.test_all_strategies()


if __name__ == "__main__":
    asyncio.run(main())

