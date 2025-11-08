"""
Test ALL ML-Inspired Strategies
Follows mandatory 2-step process: ALL 338 tokens → 5%+ ROI filter
"""

import asyncio
import json
from pathlib import Path
from filtered_backtest_pipeline import run_filtered_backtest, identify_profitable_tokens

async def main():
    """Test all 4 ML-inspired strategies."""
    
    strategies_to_test = [
        ("strategies/strategy_046.json", "ML_ADX_Trend", 46),
        ("strategies/strategy_047.json", "ML_MFI_Volume", 47),
        ("strategies/strategy_048.json", "ML_Ensemble", 48),
        ("strategies/strategy_049.json", "ML_ATR_Volatility", 49),
    ]
    
    # Load all symbols
    with open("all_bitget_symbols.txt", "r") as f:
        all_symbols = [line.strip() for line in f if line.strip()]
    
    print("\n" + "="*80)
    print("🧠 TESTING 4 ML-INSPIRED STRATEGIES")
    print("="*80)
    print(f"Based on LightGBM model (82% accuracy, 0.864 AUC)")
    print(f"Trained on ALL 338 tokens, 64,595 samples")
    print(f"\nTesting Protocol:")
    print(f"  1️⃣ Test on ALL 338 tokens")
    print(f"  2️⃣ Filter to 5%+ ROI tokens")
    print(f"  3️⃣ Re-test on filtered subset")
    print("="*80 + "\n")
    
    all_results = {}
    
    for strategy_path, strategy_name, strategy_id in strategies_to_test:
        print(f"\n{'='*80}")
        print(f"🚀 TESTING: {strategy_name}")
        print(f"{'='*80}\n")
        
        # STEP 1: Test on ALL 338 tokens
        print(f"📍 STEP 1: Testing {strategy_name} on ALL 338 tokens")
        print("-" * 80)
        
        step1_result = await run_filtered_backtest(
            strategy_path,
            all_symbols,
            f"{strategy_name}_all338"
        )
        
        if not step1_result or not step1_result.get('results'):
            print(f"⚠️ No results for {strategy_name}, skipping...")
            continue
        
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
            all_results[strategy_name] = {
                'step1': step1_result['summary'],
                'step2': None
            }
            continue
        
        # STEP 3: Re-test on filtered subset
        print(f"\n📍 STEP 3: Re-testing {strategy_name} on {len(profitable_tokens_5pct)} filtered tokens")
        print("-" * 80)
        
        step2_result = await run_filtered_backtest(
            strategy_path,
            profitable_tokens_5pct,
            f"{strategy_name}_5pct_plus"
        )
        
        all_results[strategy_name] = {
            'step1': step1_result['summary'],
            'step2': step2_result['summary'] if step2_result else None
        }
    
    # Generate comparison report
    generate_comparison_report(all_results)
    
    print("\n" + "="*80)
    print("🎉 ALL ML STRATEGIES TESTED!")
    print("="*80)
    print(f"\n📁 Results saved to:")
    print(f"   - backtest_results/*_all338_*.json")
    print(f"   - backtest_results/*_5pct_plus_*.json")
    print(f"   - ML_STRATEGIES_COMPARISON.md")
    print("="*80 + "\n")

def generate_comparison_report(results: dict):
    """Generate markdown comparison report."""
    
    output = []
    output.append("# 🧠 ML-INSPIRED STRATEGIES COMPARISON REPORT\n")
    output.append(f"**Date:** {Path('backtest_results').stat().st_mtime}\n")
    output.append(f"**Model:** LightGBM v1 (82% accuracy, 0.864 AUC)\n")
    output.append(f"**Training Data:** ALL 338 tokens, 64,595 samples\n\n")
    output.append("---\n\n")
    
    output.append("## 📊 RESULTS SUMMARY\n\n")
    output.append("| Strategy | ALL 338 Tokens ROI | 5%+ Filtered ROI | Improvement | Filtered Tokens |\n")
    output.append("|----------|-------------------|------------------|-------------|------------------|\n")
    
    for name, data in results.items():
        step1 = data['step1']
        step2 = data['step2']
        
        if step2:
            improvement = step2['portfolio_roi_pct'] - step1['portfolio_roi_pct']
            output.append(f"| {name} | {step1['portfolio_roi_pct']:.2f}% | {step2['portfolio_roi_pct']:.2f}% | +{improvement:.2f}% | {step2['total_tokens']} |\n")
        else:
            output.append(f"| {name} | {step1['portfolio_roi_pct']:.2f}% | N/A | N/A | 0 |\n")
    
    output.append("\n---\n\n")
    
    # Detailed breakdown
    output.append("## 📋 DETAILED BREAKDOWN\n\n")
    
    for name, data in results.items():
        output.append(f"### {name}\n\n")
        
        step1 = data['step1']
        output.append(f"**Test on ALL 338 Tokens:**\n")
        output.append(f"- Portfolio ROI: {step1['portfolio_roi_pct']:.2f}%\n")
        output.append(f"- Profit/Loss: ${step1['portfolio_profit_usd']:.2f}\n")
        output.append(f"- Profitable Tokens: {step1['profitable_tokens']}/{step1['total_tokens']}\n")
        output.append(f"- Total Trades: {step1['total_trades']}\n")
        output.append(f"- Best Token: {step1['best_token']} ({step1['best_roi_pct']:.2f}%)\n\n")
        
        if data['step2']:
            step2 = data['step2']
            output.append(f"**Test on 5%+ ROI Tokens ({step2['total_tokens']} tokens):**\n")
            output.append(f"- Portfolio ROI: {step2['portfolio_roi_pct']:.2f}%\n")
            output.append(f"- Profit/Loss: ${step2['portfolio_profit_usd']:.2f}\n")
            output.append(f"- Profitable Tokens: {step2['profitable_tokens']}/{step2['total_tokens']}\n")
            output.append(f"- Total Trades: {step2['total_trades']}\n")
            output.append(f"- Best Token: {step2['best_token']} ({step2['best_roi_pct']:.2f}%)\n\n")
        else:
            output.append(f"**No tokens met 5%+ ROI threshold**\n\n")
        
        output.append("---\n\n")
    
    # Save report
    report_path = Path("ML_STRATEGIES_COMPARISON.md")
    with open(report_path, 'w') as f:
        f.write(''.join(output))
    
    print(f"\n✅ Comparison report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())

