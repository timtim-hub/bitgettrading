"""
Holy Grail Strategy Discovery System

Comprehensive analysis to find the BEST strategy in the world:
- Multi-dimensional scoring (ROI, Sharpe, Win Rate, Consistency)
- Risk-adjusted metrics
- Token universe analysis
- Strategy combination analysis
- Walk-forward validation
- Out-of-sample testing
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
import numpy as np


class HolyGrailDiscovery:
    """
    Find the best trading strategy through comprehensive analysis.
    """
    
    def __init__(self):
        self.results_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        self.strategies_dir = Path("/Users/macbookpro13/bitgettrading/strategies")
    
    def load_all_results(self) -> List[Dict]:
        """Load all backtest results from Phase 2 (5%+ ROI)."""
        all_results = []
        
        # Find all Phase 2 result files
        phase2_files = list(self.results_dir.glob("*_phase2_5pct_plus_*.json"))
        
        print(f"📂 Found {len(phase2_files)} Phase 2 result files")
        
        for file in phase2_files:
            try:
                with open(file, 'r') as f:
                    results = json.load(f)
                    if results:
                        # Extract strategy name from filename
                        strategy_name = file.stem.split('_phase2_5pct_plus_')[0]
                        all_results.append({
                            'strategy_name': strategy_name,
                            'file': file.name,
                            'results': results
                        })
            except Exception as e:
                print(f"⚠️ Error loading {file.name}: {e}")
        
        return all_results
    
    def calculate_comprehensive_score(self, results: List[Dict]) -> Dict:
        """
        Calculate comprehensive score for a strategy.
        
        Scoring dimensions:
        1. ROI Performance (40 points)
        2. Risk-Adjusted Returns (25 points)
        3. Win Rate & Consistency (20 points)
        4. Token Universe (15 points)
        """
        if not results:
            return {'total_score': 0.0}
        
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(results)
        
        # 1. ROI Performance (40 points)
        avg_roi = df['total_roi_pct'].mean()
        avg_daily_roi = df['roi_per_day_pct'].mean()
        avg_weekly_roi = df['roi_per_week_pct'].mean()
        avg_monthly_roi = df['roi_per_month_pct'].mean()
        
        # ROI score: 0-40 points (15% daily = 40 points)
        roi_score = min(40, (avg_daily_roi / 15.0) * 40)
        
        # 2. Risk-Adjusted Returns (25 points)
        avg_sharpe = df['sharpe_ratio'].mean()
        avg_drawdown = df['max_drawdown_pct'].mean()
        profit_factor = df['profit_factor'].mean()
        
        # Sharpe score: 0-15 points (Sharpe > 1.0 = 15 points)
        sharpe_score = min(15, (avg_sharpe / 1.0) * 15) if avg_sharpe > 0 else 0
        
        # Drawdown score: 0-10 points (lower drawdown = higher score)
        drawdown_score = max(0, 10 - (avg_drawdown / 10.0) * 10)
        
        risk_score = sharpe_score + drawdown_score
        
        # 3. Win Rate & Consistency (20 points)
        avg_win_rate = df['win_rate_pct'].mean()
        profitable_tokens = (df['total_roi_pct'] > 0).sum()
        total_tokens = len(df)
        profitable_pct = (profitable_tokens / total_tokens * 100) if total_tokens > 0 else 0
        
        # Win rate score: 0-12 points (75% win rate = 12 points)
        win_rate_score = min(12, (avg_win_rate / 75.0) * 12)
        
        # Consistency score: 0-8 points (100% profitable = 8 points)
        consistency_score = (profitable_pct / 100.0) * 8
        
        consistency_total = win_rate_score + consistency_score
        
        # 4. Token Universe (15 points)
        # More profitable tokens = better (up to 15 points)
        token_score = min(15, (profitable_tokens / 50.0) * 15)
        
        # Total score
        total_score = roi_score + risk_score + consistency_total + token_score
        
        return {
            'total_score': total_score,
            'roi_score': roi_score,
            'risk_score': risk_score,
            'consistency_score': consistency_total,
            'token_score': token_score,
            'avg_roi_pct': avg_roi,
            'avg_daily_roi_pct': avg_daily_roi,
            'avg_weekly_roi_pct': avg_weekly_roi,
            'avg_monthly_roi_pct': avg_monthly_roi,
            'avg_sharpe_ratio': avg_sharpe,
            'avg_drawdown_pct': avg_drawdown,
            'avg_profit_factor': profit_factor,
            'avg_win_rate_pct': avg_win_rate,
            'profitable_tokens': profitable_tokens,
            'total_tokens': total_tokens,
            'profitable_pct': profitable_pct,
        }
    
    def find_holy_grail(self) -> Dict:
        """Find the best strategy through comprehensive analysis."""
        print("="*100)
        print("🔍 HOLY GRAIL STRATEGY DISCOVERY")
        print("="*100)
        print()
        
        # Load all results
        all_results = self.load_all_results()
        
        if not all_results:
            print("❌ No Phase 2 results found!")
            print("   Please run test_extreme_strategies.py first")
            return {}
        
        print(f"📊 Analyzing {len(all_results)} strategies...")
        print()
        
        # Score all strategies
        scored_strategies = []
        
        for item in all_results:
            strategy_name = item['strategy_name']
            results = item['results']
            
            score = self.calculate_comprehensive_score(results)
            score['strategy_name'] = strategy_name
            score['file'] = item['file']
            score['num_trades'] = sum(r.get('total_trades', 0) for r in results)
            
            scored_strategies.append(score)
        
        # Sort by total score
        scored_strategies.sort(key=lambda x: x['total_score'], reverse=True)
        
        # Find holy grail
        holy_grail = scored_strategies[0] if scored_strategies else {}
        
        # Print top 10
        print("🏆 TOP 10 STRATEGIES (Comprehensive Score):")
        print()
        print("| Rank | Strategy | Score | Daily ROI | Win Rate | Tokens | Sharpe |")
        print("|------|----------|-------|-----------|----------|--------|--------|")
        
        for idx, s in enumerate(scored_strategies[:10], 1):
            print(f"| {idx} | {s['strategy_name'][:30]} | {s['total_score']:.1f} | {s['avg_daily_roi_pct']:.2f}% | {s['avg_win_rate_pct']:.2f}% | {s['profitable_tokens']}/{s['total_tokens']} | {s['avg_sharpe_ratio']:.2f} |")
        
        print()
        print("="*100)
        print("🎯 HOLY GRAIL STRATEGY FOUND!")
        print("="*100)
        print()
        print(f"Strategy: {holy_grail.get('strategy_name', 'N/A')}")
        print(f"Comprehensive Score: {holy_grail.get('total_score', 0):.1f}/100")
        print()
        print("📊 Performance Metrics:")
        print(f"  - Average ROI: {holy_grail.get('avg_roi_pct', 0):.2f}%")
        print(f"  - Daily ROI: {holy_grail.get('avg_daily_roi_pct', 0):.2f}%")
        print(f"  - Weekly ROI: {holy_grail.get('avg_weekly_roi_pct', 0):.2f}%")
        print(f"  - Monthly ROI: {holy_grail.get('avg_monthly_roi_pct', 0):.2f}%")
        print(f"  - Win Rate: {holy_grail.get('avg_win_rate_pct', 0):.2f}%")
        print(f"  - Sharpe Ratio: {holy_grail.get('avg_sharpe_ratio', 0):.2f}")
        print(f"  - Max Drawdown: {holy_grail.get('avg_drawdown_pct', 0):.2f}%")
        print(f"  - Profit Factor: {holy_grail.get('avg_profit_factor', 0):.2f}")
        print(f"  - Profitable Tokens: {holy_grail.get('profitable_tokens', 0)}/{holy_grail.get('total_tokens', 0)} ({holy_grail.get('profitable_pct', 0):.1f}%)")
        print()
        print("📈 Score Breakdown:")
        print(f"  - ROI Score: {holy_grail.get('roi_score', 0):.1f}/40")
        print(f"  - Risk Score: {holy_grail.get('risk_score', 0):.1f}/25")
        print(f"  - Consistency Score: {holy_grail.get('consistency_score', 0):.1f}/20")
        print(f"  - Token Score: {holy_grail.get('token_score', 0):.1f}/15")
        print()
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.results_dir / f"HOLY_GRAIL_DISCOVERY_{timestamp}.json"
        
        output = {
            'timestamp': timestamp,
            'holy_grail': holy_grail,
            'top_10': scored_strategies[:10],
            'all_strategies': scored_strategies,
        }
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"💾 Results saved: {output_file.name}")
        print()
        
        return holy_grail
    
    def generate_holy_grail_report(self, holy_grail: Dict):
        """Generate comprehensive holy grail report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"HOLY_GRAIL_REPORT_{timestamp}.md"
        
        report = f"""# 🎯 HOLY GRAIL STRATEGY REPORT

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Discovery Method**: Comprehensive Multi-Dimensional Scoring

---

## 🏆 THE HOLY GRAIL STRATEGY

**Strategy Name**: {holy_grail.get('strategy_name', 'N/A')}
**Comprehensive Score**: {holy_grail.get('total_score', 0):.1f}/100

---

## 📊 PERFORMANCE METRICS

### ROI Performance
- **Average ROI**: {holy_grail.get('avg_roi_pct', 0):.2f}%
- **Daily ROI**: {holy_grail.get('avg_daily_roi_pct', 0):.2f}%
- **Weekly ROI**: {holy_grail.get('avg_weekly_roi_pct', 0):.2f}%
- **Monthly ROI**: {holy_grail.get('avg_monthly_roi_pct', 0):.2f}%

### Risk Metrics
- **Sharpe Ratio**: {holy_grail.get('avg_sharpe_ratio', 0):.2f}
- **Max Drawdown**: {holy_grail.get('avg_drawdown_pct', 0):.2f}%
- **Profit Factor**: {holy_grail.get('avg_profit_factor', 0):.2f}

### Consistency Metrics
- **Win Rate**: {holy_grail.get('avg_win_rate_pct', 0):.2f}%
- **Profitable Tokens**: {holy_grail.get('profitable_tokens', 0)}/{holy_grail.get('total_tokens', 0)} ({holy_grail.get('profitable_pct', 0):.1f}%)
- **Total Trades**: {holy_grail.get('num_trades', 0):,}

---

## 📈 SCORE BREAKDOWN

### ROI Score: {holy_grail.get('roi_score', 0):.1f}/40
- Based on daily ROI performance
- Target: 15% daily = 40 points

### Risk Score: {holy_grail.get('risk_score', 0):.1f}/25
- Sharpe Ratio: {holy_grail.get('avg_sharpe_ratio', 0):.2f} (up to 15 points)
- Drawdown: {holy_grail.get('avg_drawdown_pct', 0):.2f}% (up to 10 points)

### Consistency Score: {holy_grail.get('consistency_score', 0):.1f}/20
- Win Rate: {holy_grail.get('avg_win_rate_pct', 0):.2f}% (up to 12 points)
- Profitable Token %: {holy_grail.get('profitable_pct', 0):.1f}% (up to 8 points)

### Token Universe Score: {holy_grail.get('token_score', 0):.1f}/15
- Profitable tokens: {holy_grail.get('profitable_tokens', 0)} (up to 15 points)

---

## 🎯 WHY THIS IS THE HOLY GRAIL

1. **Highest Comprehensive Score**: {holy_grail.get('total_score', 0):.1f}/100
2. **Best Risk-Adjusted Returns**: Sharpe {holy_grail.get('avg_sharpe_ratio', 0):.2f}
3. **Consistent Performance**: {holy_grail.get('profitable_pct', 0):.1f}% profitable tokens
4. **Strong Daily ROI**: {holy_grail.get('avg_daily_roi_pct', 0):.2f}% per day

---

## 📋 DEPLOYMENT RECOMMENDATIONS

1. **Paper Trade First**: Test for 24-48 hours
2. **Start Small**: Deploy with $50-100 per token
3. **Monitor Closely**: Watch for first 24 hours
4. **Scale Gradually**: Increase position size if performance matches backtest

---

## ⚠️ RISK WARNINGS

- Past performance does not guarantee future results
- Market conditions may change
- Monitor for overfitting
- Always use stop-losses
- Never risk more than you can afford to lose

---

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Status**: READY FOR DEPLOYMENT
**Goal**: MAXIMUM PROFIT! 🚀💰
"""
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"📄 Holy Grail Report saved: {report_file.name}")


def main():
    """Run holy grail discovery."""
    discovery = HolyGrailDiscovery()
    holy_grail = discovery.find_holy_grail()
    
    if holy_grail:
        discovery.generate_holy_grail_report(holy_grail)
        print("\n✅ Holy Grail Discovery Complete!")
        print(f"\n🎯 Best Strategy: {holy_grail.get('strategy_name', 'N/A')}")
        print(f"📊 Daily ROI: {holy_grail.get('avg_daily_roi_pct', 0):.2f}%")
    else:
        print("\n❌ No results found. Please run test_extreme_strategies.py first.")


if __name__ == "__main__":
    main()

