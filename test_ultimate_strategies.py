"""
Test ALL 10 World-Class Strategies
Complete 2-step protocol: ALL 338 tokens → 5%+ ROI filter
Includes TRADES PER DAY in all reports!
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from filtered_backtest_pipeline import run_filtered_backtest

async def main():
    """Test all 10 ultimate strategies."""
    
    strategies_to_test = [
        (50, "Pure_LightGBM_ML_Only"),
        (51, "LightGBM_Adaptive_Thresholds"),
        (52, "MultiTimeframe_LightGBM_Ensemble"),
        (53, "LightGBM_OrderFlow_Imbalance"),
        (54, "Volatility_Adaptive_LightGBM"),
        (55, "LightGBM_Market_Regime_Adaptive"),
        (56, "LightGBM_Smart_Money_Concepts"),
        (57, "Triple_Model_LightGBM_Voting"),
        (58, "LightGBM_Mean_Reversion_Hybrid"),
        (59, "LightGBM_Breakout_Confirmation"),
    ]
    
    # Load all symbols
    with open("all_bitget_symbols.txt", "r") as f:
        all_symbols = [line.strip() for line in f if line.strip()]
    
    print("\n" + "="*80)
    print("🚀 TESTING 10 WORLD-CLASS STRATEGIES")
    print("="*80)
    print(f"Strategies: {len(strategies_to_test)}")
    print(f"Tokens: {len(all_symbols)}")
    print(f"Total Backtests: {len(strategies_to_test) * len(all_symbols) * 2} (2-step process)")
    print(f"\nProtocol:")
    print(f"  1️⃣ Test on ALL 338 tokens")
    print(f"  2️⃣ Filter to 5%+ ROI tokens")
    print(f"  3️⃣ Re-test on filtered subset")
    print(f"  4️⃣ Include TRADES PER DAY in reports")
    print("="*80 + "\n")
    
    all_results = []
    backtest_days = 8.29  # From our data
    
    for idx, (strategy_id, strategy_name) in enumerate(strategies_to_test, 1):
        strategy_path = f"strategies/strategy_{strategy_id:03d}.json"
        
        print(f"\n{'='*80}")
        print(f"🎯 STRATEGY {idx}/10: {strategy_name}")
        print(f"{'='*80}\n")
        
        # STEP 1: Test on ALL 338 tokens
        print(f"📍 STEP 1: Testing on ALL 338 tokens")
        print("-" * 80)
        
        step1_result = await run_filtered_backtest(
            strategy_path,
            all_symbols,
            f"{strategy_name}_all338"
        )
        
        if not step1_result or not step1_result.get('results'):
            print(f"⚠️ No results for {strategy_name}, skipping...")
            continue
        
        # Calculate trades per day for step 1
        step1_summary = step1_result['summary']
        step1_trades_per_day = step1_summary['total_trades'] / backtest_days
        
        print(f"\n📊 STEP 1 RESULTS:")
        print(f"   Portfolio ROI: {step1_summary['portfolio_roi_pct']:.2f}%")
        print(f"   Total Trades: {step1_summary['total_trades']}")
        print(f"   Trades per Day: {step1_trades_per_day:.1f} (across all tokens)")
        print(f"   Profitable Tokens: {step1_summary['profitable_tokens']}/{step1_summary['total_tokens']}")
        
        # STEP 2: Filter to 5%+ ROI tokens
        print(f"\n📍 STEP 2: Filtering to 5%+ ROI tokens")
        print("-" * 80)
        
        profitable_tokens_5pct = [
            r['symbol'] 
            for r in step1_result['results'] 
            if r['total_roi_pct'] >= 5.0
        ]
        
        print(f"✅ Found {len(profitable_tokens_5pct)} tokens with 5%+ ROI")
        
        if len(profitable_tokens_5pct) == 0:
            print(f"⚠️ No profitable tokens for {strategy_name}")
            all_results.append({
                'strategy_id': strategy_id,
                'strategy_name': strategy_name,
                'step1': step1_summary,
                'step1_trades_per_day': step1_trades_per_day,
                'step2': None
            })
            continue
        
        # STEP 3: Re-test on filtered subset
        print(f"\n📍 STEP 3: Re-testing on {len(profitable_tokens_5pct)} filtered tokens")
        print("-" * 80)
        
        step2_result = await run_filtered_backtest(
            strategy_path,
            profitable_tokens_5pct,
            f"{strategy_name}_5pct_plus"
        )
        
        if step2_result and step2_result.get('summary'):
            step2_summary = step2_result['summary']
            step2_trades_per_day = step2_summary['total_trades'] / backtest_days
            
            print(f"\n📊 STEP 2 RESULTS:")
            print(f"   Portfolio ROI: {step2_summary['portfolio_roi_pct']:.2f}%")
            print(f"   Total Trades: {step2_summary['total_trades']}")
            print(f"   Trades per Day: {step2_trades_per_day:.1f}")
            print(f"   Profitable Tokens: {step2_summary['profitable_tokens']}/{step2_summary['total_tokens']}")
            print(f"   Improvement: +{step2_summary['portfolio_roi_pct'] - step1_summary['portfolio_roi_pct']:.2f}%")
            
            all_results.append({
                'strategy_id': strategy_id,
                'strategy_name': strategy_name,
                'step1': step1_summary,
                'step1_trades_per_day': step1_trades_per_day,
                'step2': step2_summary,
                'step2_trades_per_day': step2_trades_per_day
            })
        else:
            all_results.append({
                'strategy_id': strategy_id,
                'strategy_name': strategy_name,
                'step1': step1_summary,
                'step1_trades_per_day': step1_trades_per_day,
                'step2': None
            })
        
        # Progress update
        print(f"\n{'='*80}")
        print(f"✅ Completed {idx}/10 strategies")
        print(f"{'='*80}\n")
    
    # Generate comprehensive report
    generate_ultimate_report(all_results, backtest_days)
    
    print("\n" + "="*80)
    print("🎉 ALL 10 STRATEGIES TESTED!")
    print("="*80)
    print(f"\n📁 Results saved to:")
    print(f"   - backtest_results/*_all338_*.json (10 files)")
    print(f"   - backtest_results/*_5pct_plus_*.json (up to 10 files)")
    print(f"   - ULTIMATE_STRATEGIES_REPORT.md (comprehensive)")
    print("="*80 + "\n")

def generate_ultimate_report(results: list, backtest_days: float):
    """Generate comprehensive markdown report with TRADES PER DAY."""
    
    output = []
    output.append("# 🏆 ULTIMATE STRATEGIES COMPARISON REPORT\n\n")
    output.append(f"**Date:** {datetime.now().strftime('%B %d, %Y')}\n")
    output.append(f"**Test Duration:** {backtest_days:.2f} days\n")
    output.append(f"**Strategies Tested:** 10\n")
    output.append(f"**Tokens Tested:** 338 (FULL universe)\n")
    output.append(f"**Testing Protocol:** 2-step (ALL → 5%+ filter)\n\n")
    output.append("---\n\n")
    
    # Sort by step2 ROI (filtered performance)
    results_sorted = sorted(
        [r for r in results if r.get('step2')],
        key=lambda x: x['step2']['portfolio_roi_pct'],
        reverse=True
    )
    
    if results_sorted:
        best = results_sorted[0]
        output.append("## 🥇 WINNING STRATEGY\n\n")
        output.append(f"### {best['strategy_name']}\n\n")
        output.append(f"**ID:** {best['strategy_id']}\n\n")
        
        output.append(f"**Performance (5%+ Filtered Tokens):**\n")
        step2 = best['step2']
        output.append(f"- Portfolio ROI: **{step2['portfolio_roi_pct']:.2f}%**\n")
        output.append(f"- Profit/Loss: **${step2['portfolio_profit_usd']:.2f}**\n")
        output.append(f"- Profitable Tokens: {step2['profitable_tokens']}/{step2['total_tokens']} ({step2['profitable_tokens']/step2['total_tokens']*100:.1f}%)\n")
        output.append(f"- Total Trades: {step2['total_trades']}\n")
        output.append(f"- **Trades per Day: {best['step2_trades_per_day']:.1f}** (across all filtered tokens)\n")
        output.append(f"- Trades per Token per Day: {best['step2_trades_per_day']/step2['total_tokens']:.2f}\n")
        output.append(f"- Best Token: {step2['best_token']} ({step2['best_roi_pct']:.2f}%)\n\n")
        
        # Time-based projections
        if step2['portfolio_roi_pct'] > -90:
            daily_mult = (1 + step2['portfolio_roi_pct']/100) ** (1/backtest_days)
            output.append(f"**Projected Returns (Compounded):**\n")
            output.append(f"- Daily ROI: {(daily_mult - 1)*100:.2f}%\n")
            output.append(f"- Weekly ROI: {(daily_mult**7 - 1)*100:.2f}%\n")
            output.append(f"- Monthly ROI: {(daily_mult**30 - 1)*100:.2f}%\n\n")
        
        output.append("---\n\n")
    
    # Full comparison table
    output.append("## 📊 COMPLETE RESULTS (All 10 Strategies)\n\n")
    output.append("| Rank | Strategy | ALL 338 ROI | Filtered ROI | Improvement | Trades/Day | Filtered Tokens |\n")
    output.append("|------|----------|-------------|--------------|-------------|------------|------------------|\n")
    
    for i, result in enumerate(results_sorted, 1):
        step1 = result['step1']
        step2 = result['step2']
        improvement = step2['portfolio_roi_pct'] - step1['portfolio_roi_pct']
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        
        output.append(f"| {i} {emoji} | {result['strategy_name'][:30]} | {step1['portfolio_roi_pct']:.2f}% | **{step2['portfolio_roi_pct']:.2f}%** | +{improvement:.2f}% | {result['step2_trades_per_day']:.1f} | {step2['total_tokens']} |\n")
    
    # Add strategies with no profitable tokens
    no_profit_strategies = [r for r in results if not r.get('step2')]
    for result in no_profit_strategies:
        step1 = result['step1']
        output.append(f"| - | {result['strategy_name'][:30]} | {step1['portfolio_roi_pct']:.2f}% | N/A | N/A | {result['step1_trades_per_day']:.1f} | 0 |\n")
    
    output.append("\n---\n\n")
    
    # Detailed breakdown
    output.append("## 📋 DETAILED BREAKDOWN\n\n")
    
    for i, result in enumerate(results_sorted, 1):
        output.append(f"### {i}. {result['strategy_name']}\n\n")
        output.append(f"**Strategy ID:** {result['strategy_id']}\n\n")
        
        step1 = result['step1']
        output.append(f"**Test on ALL 338 Tokens:**\n")
        output.append(f"- Portfolio ROI: {step1['portfolio_roi_pct']:.2f}%\n")
        output.append(f"- Total Trades: {step1['total_trades']}\n")
        output.append(f"- Trades per Day: {result['step1_trades_per_day']:.1f}\n")
        output.append(f"- Profitable Tokens: {step1['profitable_tokens']}/{step1['total_tokens']}\n")
        output.append(f"- Best Token: {step1['best_token']} ({step1['best_roi_pct']:.2f}%)\n\n")
        
        step2 = result['step2']
        output.append(f"**Test on 5%+ ROI Tokens ({step2['total_tokens']} tokens):**\n")
        output.append(f"- Portfolio ROI: {step2['portfolio_roi_pct']:.2f}%\n")
        output.append(f"- Total Trades: {step2['total_trades']}\n")
        output.append(f"- Trades per Day: {result['step2_trades_per_day']:.1f}\n")
        output.append(f"- Trades per Token per Day: {result['step2_trades_per_day']/step2['total_tokens']:.2f}\n")
        output.append(f"- Profitable Tokens: {step2['profitable_tokens']}/{step2['total_tokens']} ({step2['profitable_tokens']/step2['total_tokens']*100:.1f}%)\n")
        output.append(f"- Improvement: +{step2['portfolio_roi_pct'] - step1['portfolio_roi_pct']:.2f}%\n\n")
        
        output.append("---\n\n")
    
    # Save report
    report_path = Path("ULTIMATE_STRATEGIES_REPORT.md")
    with open(report_path, 'w') as f:
        f.write(''.join(output))
    
    print(f"\n✅ Ultimate report saved to: {report_path}")
    
    # Also save JSON for programmatic access
    json_path = Path("backtest_results/ultimate_strategies_summary.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ JSON summary saved to: {json_path}")

if __name__ == "__main__":
    asyncio.run(main())

