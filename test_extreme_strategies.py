"""
Test Extreme ROI Strategies with Three-Phase Protocol

Phase 1: Test on filtered 60 tokens
Phase 2: Re-test on >10% ROI tokens
Phase 3: Re-test on >20% ROI tokens

ALWAYS includes ROI for 24h/7d/30d + all metrics.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List
import time
from datetime import datetime
import pandas as pd

from backtest_engine_multi import MultiPositionBacktestEngine
from metrics_calculator import MetricsCalculator


class ExtremeStrategiesTester:
    """Test extreme ROI strategies with three-phase protocol."""
    
    def __init__(self):
        self.results_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        self.results_dir.mkdir(exist_ok=True)
        self.strategies_dir = Path("/Users/macbookpro13/bitgettrading/strategies")
        self.cache_dir = Path("/Users/macbookpro13/bitgettrading/backtest_data")
    
    def load_strategies(self, start_id: int = 110, end_id: int = 159) -> List[Dict]:
        """Load strategies 110-159."""
        strategies = []
        for strategy_id in range(start_id, end_id + 1):
            filepath = self.strategies_dir / f"strategy_{strategy_id:03d}.json"
            if filepath.exists():
                with open(filepath, 'r') as f:
                    strategies.append(json.load(f))
        return strategies
    
    def load_all_tokens(self) -> List[str]:
        """Load ALL 338 tokens for Phase 1 testing."""
        print("📋 Loading ALL 338 tokens for Phase 1 testing...")
        with open("/Users/macbookpro13/bitgettrading/all_bitget_symbols.txt", 'r') as f:
            tokens = [line.strip() for line in f if line.strip()]
        print(f"✅ Loaded {len(tokens)} tokens\n")
        return tokens
    
    async def load_cached_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Load cached data for symbols."""
        data_dict = {}
        
        print(f"📂 Loading cached data for {len(symbols)} symbols...")
        
        for symbol in symbols:
            cache_patterns = [
                self.cache_dir / f"{symbol}_1H_30d.pkl",
                self.cache_dir / f"{symbol}_1m_200.pkl",
                self.cache_dir / f"{symbol}_1H.pkl",
            ]
            
            for cache_file in cache_patterns:
                if cache_file.exists():
                    try:
                        df = pd.read_pickle(cache_file)
                        data_dict[symbol] = df
                        break
                    except Exception:
                        continue
        
        print(f"✅ Loaded data for {len(data_dict)} symbols\n")
        return data_dict
    
    def run_backtest(
        self,
        strategy: Dict,
        symbol: str,
        df: pd.DataFrame
    ) -> Dict:
        """Run backtest for one strategy on one symbol."""
        try:
            engine = MultiPositionBacktestEngine(strategy)
            result = engine.run_backtest(df, symbol, initial_capital=50.0)
            
            metrics = MetricsCalculator.calculate_all_metrics(result)
            
            return {
                'symbol': symbol,
                'strategy_id': strategy['id'],
                'total_roi_pct': metrics.total_roi_pct,
                'roi_per_day_pct': metrics.roi_per_day_pct,
                'roi_per_week_pct': metrics.roi_per_week_pct,
                'roi_per_month_pct': metrics.roi_per_month_pct,
                'win_rate_pct': metrics.win_rate_pct,
                'total_trades': metrics.total_trades,
                'trades_per_day': metrics.trades_per_day,
                'sharpe_ratio': metrics.sharpe_ratio,
                'max_drawdown_pct': metrics.max_drawdown_pct,
                'profit_factor': metrics.profit_factor,
                'final_capital': metrics.final_capital,
                'capital_24h': metrics.capital_24h,
                'capital_1week': metrics.capital_1week,
                'max_concurrent_positions': result.max_concurrent_positions,
                'correlation_violations': result.correlation_violations,
                'total_slippage_cost': result.total_slippage_cost,
            }
        except Exception as e:
            print(f"❌ Error: {symbol} - {e}")
            return None
    
    async def test_strategy_phase(
        self,
        strategy: Dict,
        symbols: List[str],
        data_dict: Dict[str, pd.DataFrame],
        phase_name: str
    ) -> List[Dict]:
        """Test strategy on given symbols."""
        print(f"\n📊 {phase_name}: Testing {strategy['name']} on {len(symbols)} tokens...")
        
        results = []
        for idx, symbol in enumerate(symbols, 1):
            if idx % 20 == 0:
                print(f"   Progress: {idx}/{len(symbols)}")
            
            if symbol in data_dict:
                metrics = self.run_backtest(strategy, symbol, data_dict[symbol])
                if metrics:
                    results.append(metrics)
        
        print(f"✅ Completed {phase_name}: {len(results)} results")
        return results
    
    async def test_strategy_three_phases(
        self,
        strategy: Dict,
        data_dict: Dict[str, pd.DataFrame],
        all_symbols: List[str]
    ) -> Dict:
        """Test strategy through all three phases."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Phase 1: ALL 338 tokens (MANDATORY!)
        phase1_symbols = [s for s in all_symbols if s in data_dict]
        phase1_results = await self.test_strategy_phase(
            strategy, phase1_symbols, data_dict, "Phase 1 (ALL 338 Tokens)"
        )
        
        # Save Phase 1
        phase1_file = self.results_dir / f"{strategy['name']}_phase1_{timestamp}.json"
        with open(phase1_file, 'w') as f:
            json.dump(phase1_results, f, indent=2)
        
        # Phase 2: ALL 5%+ ROI tokens (MANDATORY - keep all profitable!)
        phase2_symbols = [
            r['symbol'] for r in phase1_results
            if r['total_roi_pct'] >= 5.0
        ]
        
        if phase2_symbols:
            phase2_results = await self.test_strategy_phase(
                strategy, phase2_symbols, data_dict, "Phase 2 (ALL 5%+ ROI)"
            )
            
            phase2_file = self.results_dir / f"{strategy['name']}_phase2_5pct_plus_{timestamp}.json"
            with open(phase2_file, 'w') as f:
                json.dump(phase2_results, f, indent=2)
        else:
            print(f"⚠️ No tokens passed 5% ROI threshold for Phase 2")
            phase2_results = []
        
        # Phase 3: >20% ROI tokens (top performers from Phase 2)
        phase3_symbols = [
            r['symbol'] for r in phase2_results
            if r['total_roi_pct'] > 20.0
        ]
        
        if phase3_symbols:
            phase3_results = await self.test_strategy_phase(
                strategy, phase3_symbols, data_dict, "Phase 3 (>20% ROI)"
            )
            
            phase3_file = self.results_dir / f"{strategy['name']}_phase3_{timestamp}.json"
            with open(phase3_file, 'w') as f:
                json.dump(phase3_results, f, indent=2)
        else:
            print(f"⚠️ No tokens passed 20% ROI threshold for Phase 3")
            phase3_results = []
        
        return {
            'strategy': strategy['name'],
            'strategy_id': strategy['id'],
            'leverage': strategy['leverage'],
            'phase1': self.calculate_summary(phase1_results),
            'phase2': self.calculate_summary(phase2_results),
            'phase3': self.calculate_summary(phase3_results),
        }
    
    def calculate_summary(self, results: List[Dict]) -> Dict:
        """Calculate summary statistics."""
        if not results:
            return {}
        
        total_tokens = len(results)
        
        return {
            'total_tokens': total_tokens,
            'avg_roi_pct': sum(r['total_roi_pct'] for r in results) / total_tokens,
            'avg_roi_per_day_pct': sum(r['roi_per_day_pct'] for r in results) / total_tokens,
            'avg_roi_per_week_pct': sum(r['roi_per_week_pct'] for r in results) / total_tokens,
            'avg_roi_per_month_pct': sum(r['roi_per_month_pct'] for r in results) / total_tokens,
            'avg_win_rate_pct': sum(r['win_rate_pct'] for r in results) / total_tokens,
            'total_trades': sum(r['total_trades'] for r in results),
            'avg_trades_per_day': sum(r['trades_per_day'] for r in results) / total_tokens,
            'avg_sharpe_ratio': sum(r['sharpe_ratio'] for r in results) / total_tokens,
            'profitable_tokens': sum(1 for r in results if r['total_roi_pct'] > 0),
        }
    
    def generate_report(self, all_summaries: List[Dict]):
        """Generate comprehensive report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report = f"""# Extreme ROI Strategies Test Report

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Strategies Tested**: {len(all_summaries)}
**Protocol**: Three-Phase (ALL 338 Tokens → ALL 5%+ ROI → >20% ROI)

---

## 🏆 Top Performers (Phase 2: ALL 5%+ ROI)

**This is the KEY phase - all profitable tokens!**

| Rank | Strategy | Leverage | Avg ROI | ROI/Day | ROI/Week | ROI/Month | Win Rate | Tokens |
|------|----------|----------|---------|---------|----------|-----------|----------|--------|
"""
        
        # Sort by Phase 2 avg ROI (5%+ ROI tokens - ALL profitable!)
        phase2_sorted = sorted(
            [s for s in all_summaries if s.get('phase2') and s['phase2'].get('total_tokens', 0) > 0],
            key=lambda x: x['phase2'].get('avg_roi_pct', 0),
            reverse=True
        )
        
        for idx, s in enumerate(phase2_sorted[:20], 1):
            p2 = s['phase2']
            report += f"| {idx} | {s['strategy'][:30]} | {s['leverage']}x | {p2['avg_roi_pct']:.2f}% | {p2['avg_roi_per_day_pct']:.2f}% | {p2['avg_roi_per_week_pct']:.2f}% | {p2['avg_roi_per_month_pct']:.2f}% | {p2['avg_win_rate_pct']:.2f}% | {p2['total_tokens']} |\n"
        
        report += "\n---\n\n## 🏆 Top Performers (Phase 3: >20% ROI)\n\n"
        
        # Sort by Phase 3 avg ROI
        phase3_sorted = sorted(
            [s for s in all_summaries if s.get('phase3') and s['phase3'].get('total_tokens', 0) > 0],
            key=lambda x: x['phase3'].get('avg_roi_pct', 0),
            reverse=True
        )
        
        report += "| Rank | Strategy | Leverage | Avg ROI | ROI/Day | ROI/Week | ROI/Month | Win Rate | Tokens |\n"
        report += "|------|----------|----------|---------|---------|----------|-----------|----------|--------|\n"
        
        for idx, s in enumerate(phase3_sorted[:20], 1):
            p3 = s['phase3']
            report += f"| {idx} | {s['strategy'][:30]} | {s['leverage']}x | {p3['avg_roi_pct']:.2f}% | {p3['avg_roi_per_day_pct']:.2f}% | {p3['avg_roi_per_week_pct']:.2f}% | {p3['avg_roi_per_month_pct']:.2f}% | {p3['avg_win_rate_pct']:.2f}% | {p3['total_tokens']} |\n"
        
        report += "\n---\n\n## 📊 All Strategies Summary\n\n"
        
        for s in sorted(all_summaries, key=lambda x: x['strategy_id']):
            report += f"### Strategy {s['strategy_id']}: {s['strategy']}\n\n"
            report += f"**Leverage**: {s['leverage']}x\n\n"
            
            for phase_name, phase_data in [('Phase 1', s.get('phase1', {})), ('Phase 2 (5%+ ROI)', s.get('phase2', {})), ('Phase 3 (>20% ROI)', s.get('phase3', {}))]:
                if phase_data and phase_data.get('total_tokens', 0) > 0:
                    report += f"**{phase_name}**:\n"
                    report += f"- Tokens: {phase_data['total_tokens']}\n"
                    report += f"- Avg ROI: {phase_data['avg_roi_pct']:.2f}%\n"
                    report += f"- ROI/Day: {phase_data['avg_roi_per_day_pct']:.2f}%\n"
                    report += f"- ROI/Week: {phase_data['avg_roi_per_week_pct']:.2f}%\n"
                    report += f"- ROI/Month: {phase_data['avg_roi_per_month_pct']:.2f}%\n"
                    report += f"- Win Rate: {phase_data['avg_win_rate_pct']:.2f}%\n"
                    report += f"- Total Trades: {phase_data['total_trades']}\n\n"
            
            report += "---\n\n"
        
        report_file = self.results_dir / f"EXTREME_STRATEGIES_REPORT_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\n📄 Report saved: {report_file.name}")
    
    async def test_all_strategies(self):
        """Test all 50 extreme strategies."""
        print("="*100)
        print("🚀 EXTREME ROI STRATEGIES TESTING")
        print("="*100)
        print()
        
        # Load strategies
        strategies = self.load_strategies(110, 159)
        print(f"📋 Loaded {len(strategies)} strategies (IDs 110-159)\n")
        
        # Load ALL 338 tokens (MANDATORY for Phase 1!)
        all_tokens = self.load_all_tokens()
        
        # Load data for ALL tokens
        data_dict = await self.load_cached_data(all_tokens)
        
        # Test each strategy
        all_summaries = []
        
        for idx, strategy in enumerate(strategies, 1):
            print(f"\n{'='*100}")
            print(f"Strategy {idx}/{len(strategies)}: {strategy['name']} (ID: {strategy['id']}, Leverage: {strategy['leverage']}x)")
            print(f"{'='*100}")
            
            start_time = time.time()
            
            summary = await self.test_strategy_three_phases(strategy, data_dict, all_tokens)
            all_summaries.append(summary)
            
            elapsed = time.time() - start_time
            print(f"\n⏱️ Completed in {elapsed:.1f}s")
            
            if summary['phase2'] and summary['phase2'].get('total_tokens', 0) > 0:
                p2 = summary['phase2']
                print(f"📈 Phase 2 (5%+ ROI): {p2['avg_roi_pct']:.2f}% ROI ({p2['total_tokens']} tokens)")
                print(f"⭐ Daily: {p2['avg_roi_per_day_pct']:.2f}% | Weekly: {p2['avg_roi_per_week_pct']:.2f}% | Monthly: {p2['avg_roi_per_month_pct']:.2f}%")
            
            if summary.get('phase3') and summary['phase3'].get('total_tokens', 0) > 0:
                p3 = summary['phase3']
                print(f"📈 Phase 3 (>20% ROI): {p3['avg_roi_pct']:.2f}% ROI ({p3['total_tokens']} tokens)")
        
        # Generate report
        self.generate_report(all_summaries)
        
        print(f"\n{'='*100}")
        print("✅ ALL TESTING COMPLETE!")
        print(f"{'='*100}")


async def main():
    """Run extreme strategies tester."""
    tester = ExtremeStrategiesTester()
    await tester.test_all_strategies()


if __name__ == "__main__":
    asyncio.run(main())

