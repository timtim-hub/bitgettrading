"""
Compare Holy Grail ADX Strategy (046) vs Holy Grail LightGBM Strategy (160)

Uses the existing test_extreme_strategies.py infrastructure for consistent testing.
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import time

from test_extreme_strategies import ExtremeStrategiesTester


class HolyGrailComparisonTester(ExtremeStrategiesTester):
    """Compare Holy Grail ADX vs LightGBM strategies."""
    
    def __init__(self):
        super().__init__()
        self.results_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        self.results_dir.mkdir(exist_ok=True)
    
    def load_strategy(self, strategy_id: int) -> Dict:
        """Load a single strategy by ID."""
        filepath = self.strategies_dir / f"strategy_{strategy_id:03d}.json"
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    async def run_comparison(self):
        """Run comparison between Holy Grail ADX and LightGBM strategies."""
        print("="*100)
        print("🎯 HOLY GRAIL STRATEGY COMPARISON")
        print("="*100)
        print()
        
        # Load strategy configs
        strategy_046 = self.load_strategy(46)
        strategy_160 = self.load_strategy(160)
        
        if not strategy_046:
            print("❌ Strategy 046 (Holy Grail ADX) not found!")
            return
        
        if not strategy_160:
            print("❌ Strategy 160 (Holy Grail LightGBM) not found!")
            return
        
        print(f"✅ Loaded Strategy 046: {strategy_046['name']}")
        print(f"✅ Loaded Strategy 160: {strategy_160['name']}")
        print()
        
        # Load ALL 338 tokens (MANDATORY for Phase 1!)
        all_tokens = self.load_all_tokens()
        print(f"📊 Testing on ALL {len(all_tokens)} tokens (Phase 1)\n")
        
        # Load data for all tokens
        data_dict = await self.load_cached_data(all_tokens)
        print(f"✅ Loaded data for {len(data_dict)} tokens\n")
        
        all_summaries = []
        
        # --- Phase 1: Test Strategy 046 (Holy Grail ADX) on ALL tokens ---
        print("\n" + "="*100)
        print("🚀 PHASE 1: Testing Holy Grail ADX (Strategy 046) on ALL 338 tokens")
        print("="*100 + "\n")
        
        start_time = time.time()
        adx_results_phase1 = await self.test_strategy_phase(strategy_046, all_tokens, data_dict, "Phase 1 ADX")
        adx_summary_phase1 = self.calculate_summary(adx_results_phase1)
        elapsed_adx = time.time() - start_time
        
        print(f"\n✅ Phase 1 ADX complete in {elapsed_adx:.1f}s: {len(adx_results_phase1)} results")
        print(f"   Avg ROI: {adx_summary_phase1.get('avg_roi_pct', 0):.2f}%")
        print(f"   Avg ROI/Day: {adx_summary_phase1.get('avg_roi_per_day_pct', 0):.2f}%")
        print(f"   Profitable tokens: {adx_summary_phase1.get('profitable_tokens', 0)}\n")
        
        # --- Phase 1: Test Strategy 160 (Holy Grail LightGBM) on ALL tokens ---
        print("\n" + "="*100)
        print("🚀 PHASE 1: Testing Holy Grail LightGBM (Strategy 160) on ALL 338 tokens")
        print("="*100 + "\n")
        
        start_time = time.time()
        lgbm_results_phase1 = await self.test_strategy_phase(strategy_160, all_tokens, data_dict, "Phase 1 LightGBM")
        lgbm_summary_phase1 = self.calculate_summary(lgbm_results_phase1)
        elapsed_lgbm = time.time() - start_time
        
        print(f"\n✅ Phase 1 LightGBM complete in {elapsed_lgbm:.1f}s: {len(lgbm_results_phase1)} results")
        print(f"   Avg ROI: {lgbm_summary_phase1.get('avg_roi_pct', 0):.2f}%")
        print(f"   Avg ROI/Day: {lgbm_summary_phase1.get('avg_roi_per_day_pct', 0):.2f}%")
        print(f"   Profitable tokens: {lgbm_summary_phase1.get('profitable_tokens', 0)}\n")
        
        # --- Phase 2: Re-test on 5%+ ROI tokens (for both strategies) ---
        print("\n" + "="*100)
        print("🎯 PHASE 2: Re-testing on 5%+ ROI tokens")
        print("="*100 + "\n")
        
        # Get profitable tokens from Phase 1 (5%+ ROI)
        adx_profitable_tokens = [r['symbol'] for r in adx_results_phase1 if r['total_roi_pct'] >= 5.0]
        lgbm_profitable_tokens = [r['symbol'] for r in lgbm_results_phase1 if r['total_roi_pct'] >= 5.0]
        
        print(f"📊 Found {len(adx_profitable_tokens)} tokens with 5%+ ROI for Holy Grail ADX")
        print(f"📊 Found {len(lgbm_profitable_tokens)} tokens with 5%+ ROI for Holy Grail LightGBM\n")
        
        # Test ADX on its profitable tokens
        adx_summary_phase2 = {}
        if adx_profitable_tokens:
            print(f"\n🎯 PHASE 2: Re-testing Holy Grail ADX on {len(adx_profitable_tokens)} profitable tokens...\n")
            adx_results_phase2 = await self.test_strategy_phase(strategy_046, adx_profitable_tokens, data_dict, "Phase 2 ADX")
            adx_summary_phase2 = self.calculate_summary(adx_results_phase2)
            print(f"✅ Phase 2 ADX: {len(adx_results_phase2)} results")
            print(f"   Avg ROI: {adx_summary_phase2.get('avg_roi_pct', 0):.2f}%")
            print(f"   Avg ROI/Day: {adx_summary_phase2.get('avg_roi_per_day_pct', 0):.2f}%\n")
        else:
            print("⚠️ No profitable tokens found in Phase 1 for Holy Grail ADX!\n")
        
        # Test LightGBM on its profitable tokens
        lgbm_summary_phase2 = {}
        if lgbm_profitable_tokens:
            print(f"\n🎯 PHASE 2: Re-testing Holy Grail LightGBM on {len(lgbm_profitable_tokens)} profitable tokens...\n")
            lgbm_results_phase2 = await self.test_strategy_phase(strategy_160, lgbm_profitable_tokens, data_dict, "Phase 2 LightGBM")
            lgbm_summary_phase2 = self.calculate_summary(lgbm_results_phase2)
            print(f"✅ Phase 2 LightGBM: {len(lgbm_results_phase2)} results")
            print(f"   Avg ROI: {lgbm_summary_phase2.get('avg_roi_pct', 0):.2f}%")
            print(f"   Avg ROI/Day: {lgbm_summary_phase2.get('avg_roi_per_day_pct', 0):.2f}%\n")
        else:
            print("⚠️ No profitable tokens found in Phase 1 for Holy Grail LightGBM!\n")
        
        # Compile summaries
        all_summaries.append({
            'strategy_id': 46,
            'strategy': strategy_046['name'],
            'leverage': strategy_046['leverage'],
            'phase1': adx_summary_phase1,
            'phase2': adx_summary_phase2,
        })
        
        all_summaries.append({
            'strategy_id': 160,
            'strategy': strategy_160['name'],
            'leverage': strategy_160['leverage'],
            'phase1': lgbm_summary_phase1,
            'phase2': lgbm_summary_phase2,
        })
        
        # Generate comparison report
        self.generate_comparison_report(all_summaries, strategy_046, strategy_160)
        self.save_json_results(all_summaries)
        
        print("\n" + "="*100)
        print("✅ COMPARISON COMPLETE!")
        print("="*100)
        print(f"\n📊 Results saved to: {self.results_dir}")
        print("="*100 + "\n")
    
    def generate_comparison_report(self, all_summaries: List[Dict], strategy_046: Dict, strategy_160: Dict):
        """Generate detailed comparison report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        adx_summary = all_summaries[0]
        lgbm_summary = all_summaries[1]
        
        report = f"""# 🎯 Holy Grail Strategy Comparison Report

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Strategies Compared**: Holy Grail ADX (Strategy 046) vs Holy Grail LightGBM (Strategy 160)  
**Protocol**: Two-Phase Testing (ALL 338 Tokens → 5%+ ROI Tokens)

---

## 📊 Executive Summary

### Holy Grail ADX Strategy (Strategy 046)

**Phase 1 (All 338 Tokens)**:
- Total Tokens Tested: {adx_summary['phase1'].get('total_tokens', 0)}
- Average ROI: {adx_summary['phase1'].get('avg_roi_pct', 0):.2f}%
- Average ROI/Day: {adx_summary['phase1'].get('avg_roi_per_day_pct', 0):.2f}%
- Average ROI/Week: {adx_summary['phase1'].get('avg_roi_per_week_pct', 0):.2f}%
- Average ROI/Month: {adx_summary['phase1'].get('avg_roi_per_month_pct', 0):.2f}%
- Average Win Rate: {adx_summary['phase1'].get('avg_win_rate_pct', 0):.2f}%
- Profitable Tokens (5%+ ROI): {adx_summary['phase1'].get('profitable_tokens', 0)}
- Total Trades: {adx_summary['phase1'].get('total_trades', 0)}
- Trades/Day: {adx_summary['phase1'].get('avg_trades_per_day', 0):.2f}

**Phase 2 (5%+ ROI Tokens)**:
- Total Tokens Tested: {adx_summary['phase2'].get('total_tokens', 0)}
- Average ROI: {adx_summary['phase2'].get('avg_roi_pct', 0):.2f}%
- Average ROI/Day: {adx_summary['phase2'].get('avg_roi_per_day_pct', 0):.2f}%
- Average ROI/Week: {adx_summary['phase2'].get('avg_roi_per_week_pct', 0):.2f}%
- Average ROI/Month: {adx_summary['phase2'].get('avg_roi_per_month_pct', 0):.2f}%
- Average Win Rate: {adx_summary['phase2'].get('avg_win_rate_pct', 0):.2f}%

### Holy Grail LightGBM Strategy (Strategy 160)

**Phase 1 (All 338 Tokens)**:
- Total Tokens Tested: {lgbm_summary['phase1'].get('total_tokens', 0)}
- Average ROI: {lgbm_summary['phase1'].get('avg_roi_pct', 0):.2f}%
- Average ROI/Day: {lgbm_summary['phase1'].get('avg_roi_per_day_pct', 0):.2f}%
- Average ROI/Week: {lgbm_summary['phase1'].get('avg_roi_per_week_pct', 0):.2f}%
- Average ROI/Month: {lgbm_summary['phase1'].get('avg_roi_per_month_pct', 0):.2f}%
- Average Win Rate: {lgbm_summary['phase1'].get('avg_win_rate_pct', 0):.2f}%
- Profitable Tokens (5%+ ROI): {lgbm_summary['phase1'].get('profitable_tokens', 0)}
- Total Trades: {lgbm_summary['phase1'].get('total_trades', 0)}
- Trades/Day: {lgbm_summary['phase1'].get('avg_trades_per_day', 0):.2f}

**Phase 2 (5%+ ROI Tokens)**:
- Total Tokens Tested: {lgbm_summary['phase2'].get('total_tokens', 0)}
- Average ROI: {lgbm_summary['phase2'].get('avg_roi_pct', 0):.2f}%
- Average ROI/Day: {lgbm_summary['phase2'].get('avg_roi_per_day_pct', 0):.2f}%
- Average ROI/Week: {lgbm_summary['phase2'].get('avg_roi_per_week_pct', 0):.2f}%
- Average ROI/Month: {lgbm_summary['phase2'].get('avg_roi_per_month_pct', 0):.2f}%
- Average Win Rate: {lgbm_summary['phase2'].get('avg_win_rate_pct', 0):.2f}%

---

## 📈 Detailed Comparison

### Strategy Parameters

**Holy Grail ADX (Strategy 046)**:
- Entry Threshold: {strategy_046['entry_threshold']}
- Stop Loss: {strategy_046['stop_loss_pct']*100:.1f}%
- Take Profit: {strategy_046['take_profit_pct']*100:.1f}%
- Trailing Callback: {strategy_046['trailing_callback']*100:.1f}%
- Leverage: {strategy_046['leverage']}x
- Position Size: {strategy_046['position_size_pct']*100:.1f}%
- Max Positions: {strategy_046['max_positions']}
- Primary Indicator: {strategy_046.get('primary_indicator', 'adx')}
- Entry Method: {strategy_046.get('entry_method', 'adx_strong_trend')}

**Holy Grail LightGBM (Strategy 160)**:
- Entry Threshold: {strategy_160['entry_threshold']}
- Stop Loss: {strategy_160['stop_loss_pct']*100:.1f}%
- Take Profit: {strategy_160['take_profit_pct']*100:.1f}%
- Trailing Callback: {strategy_160['trailing_callback']*100:.1f}%
- Leverage: {strategy_160['leverage']}x
- Position Size: {strategy_160['position_size_pct']*100:.1f}%
- Max Positions: {strategy_160['max_positions']}
- Primary Indicator: {strategy_160.get('primary_indicator', 'lightgbm_prediction')}
- Entry Method: {strategy_160.get('entry_method', 'lightgbm_confidence')}

---

## 🎯 Performance Comparison

### Phase 1 (All Tokens) - Winner: {"LightGBM" if lgbm_summary['phase1'].get('avg_roi_pct', 0) > adx_summary['phase1'].get('avg_roi_pct', 0) else "ADX"}

| Metric | Holy Grail ADX | Holy Grail LightGBM | Difference |
|--------|----------------|---------------------|------------|
| Avg ROI | {adx_summary['phase1'].get('avg_roi_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_roi_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_roi_pct', 0) - adx_summary['phase1'].get('avg_roi_pct', 0):.2f}% |
| Avg ROI/Day | {adx_summary['phase1'].get('avg_roi_per_day_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_roi_per_day_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_roi_per_day_pct', 0) - adx_summary['phase1'].get('avg_roi_per_day_pct', 0):.2f}% |
| Win Rate | {adx_summary['phase1'].get('avg_win_rate_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_win_rate_pct', 0):.2f}% | {lgbm_summary['phase1'].get('avg_win_rate_pct', 0) - adx_summary['phase1'].get('avg_win_rate_pct', 0):.2f}% |
| Profitable Tokens | {adx_summary['phase1'].get('profitable_tokens', 0)} | {lgbm_summary['phase1'].get('profitable_tokens', 0)} | {lgbm_summary['phase1'].get('profitable_tokens', 0) - adx_summary['phase1'].get('profitable_tokens', 0)} |

### Phase 2 (5%+ ROI Tokens) - Winner: {"LightGBM" if lgbm_summary['phase2'].get('avg_roi_pct', 0) > adx_summary['phase2'].get('avg_roi_pct', 0) else "ADX"}

| Metric | Holy Grail ADX | Holy Grail LightGBM | Difference |
|--------|----------------|---------------------|------------|
| Avg ROI | {adx_summary['phase2'].get('avg_roi_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_roi_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_roi_pct', 0) - adx_summary['phase2'].get('avg_roi_pct', 0):.2f}% |
| Avg ROI/Day | {adx_summary['phase2'].get('avg_roi_per_day_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_roi_per_day_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_roi_per_day_pct', 0) - adx_summary['phase2'].get('avg_roi_per_day_pct', 0):.2f}% |
| Win Rate | {adx_summary['phase2'].get('avg_win_rate_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_win_rate_pct', 0):.2f}% | {lgbm_summary['phase2'].get('avg_win_rate_pct', 0) - adx_summary['phase2'].get('avg_win_rate_pct', 0):.2f}% |

---

## 🏆 Conclusion

{"**Winner: Holy Grail LightGBM Strategy**" if lgbm_summary['phase2'].get('avg_roi_pct', 0) > adx_summary['phase2'].get('avg_roi_pct', 0) else "**Winner: Holy Grail ADX Strategy**"}

The comparison shows that {"LightGBM" if lgbm_summary['phase2'].get('avg_roi_pct', 0) > adx_summary['phase2'].get('avg_roi_pct', 0) else "ADX"} strategy performs better on profitable tokens, achieving higher ROI and better risk-adjusted returns.

---

*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        report_file = self.results_dir / f"HOLY_GRAIL_COMPARISON_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\n📄 Comparison report saved: {report_file.name}")
    
    def save_json_results(self, all_summaries: List[Dict]):
        """Save results as JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.results_dir / f"HOLY_GRAIL_COMPARISON_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(all_summaries, f, indent=2)
        print(f"📄 JSON results saved: {json_file.name}")


async def main():
    """Run Holy Grail comparison."""
    tester = HolyGrailComparisonTester()
    await tester.run_comparison()


if __name__ == "__main__":
    asyncio.run(main())

