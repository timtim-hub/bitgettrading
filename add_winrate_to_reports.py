"""
Add Win Rate to All Strategy Reports
Regenerates summaries with win rate included
"""

import json
from pathlib import Path

def calculate_avg_win_rate(detailed_results):
    """Calculate average win rate from detailed results."""
    if not detailed_results:
        return 0.0
    
    win_rates = [r['win_rate_pct'] for r in detailed_results]
    return sum(win_rates) / len(win_rates)

def main():
    """Add win rates to all strategies."""
    
    print("\n" + "="*80)
    print("📊 ADDING WIN RATES TO ALL STRATEGY REPORTS")
    print("="*80 + "\n")
    
    # Find all detailed result files
    results_dir = Path("backtest_results")
    detailed_files = list(results_dir.glob("*_5pct_plus_detailed_*.json"))
    
    all_strategies = {}
    
    for file in detailed_files:
        # Extract strategy name
        strategy_name = file.stem.replace("_5pct_plus_detailed", "").rsplit("_", 1)[0]
        
        # Load results
        with open(file, 'r') as f:
            data = json.load(f)
        
        # Calculate average win rate
        avg_win_rate = calculate_avg_win_rate(data)
        
        # Get summary data
        total_trades = sum(r['total_trades'] for r in data)
        total_roi = sum(r['total_roi_pct'] for r in data) / len(data)
        
        all_strategies[strategy_name] = {
            'avg_win_rate': avg_win_rate,
            'total_trades': total_trades,
            'avg_roi': total_roi,
            'num_tokens': len(data),
            'file': file.name
        }
        
        print(f"✅ {strategy_name}")
        print(f"   Win Rate: {avg_win_rate:.2f}%")
        print(f"   ROI: {total_roi:.2f}%")
        print(f"   Trades: {total_trades}")
        print()
    
    # Sort by ROI
    sorted_strategies = sorted(all_strategies.items(), key=lambda x: x[1]['avg_roi'], reverse=True)
    
    # Generate summary table
    print("="*80)
    print("📊 ALL STRATEGIES WITH WIN RATES")
    print("="*80 + "\n")
    print(f"{'Rank':<6} {'Strategy':<35} {'ROI %':<10} {'Win Rate %':<12} {'Trades':<8}")
    print("-"*80)
    
    for i, (name, data) in enumerate(sorted_strategies, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        print(f"{i:<2} {emoji:<4} {name[:35]:<35} {data['avg_roi']:>7.2f}%   {data['avg_win_rate']:>9.2f}%    {data['total_trades']:<8}")
    
    print("\n" + "="*80 + "\n")
    
    # Save to file
    output_file = Path("WIN_RATES_SUMMARY.txt")
    with open(output_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("📊 ALL STRATEGIES WITH WIN RATES\n")
        f.write("="*80 + "\n\n")
        f.write(f"{'Rank':<6} {'Strategy':<35} {'ROI %':<10} {'Win Rate %':<12} {'Trades':<8}\n")
        f.write("-"*80 + "\n")
        
        for i, (name, data) in enumerate(sorted_strategies, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
            f.write(f"{i:<2} {emoji:<4} {name[:35]:<35} {data['avg_roi']:>7.2f}%   {data['avg_win_rate']:>9.2f}%    {data['total_trades']:<8}\n")
    
    print(f"✅ Saved win rates summary to: {output_file}\n")

if __name__ == "__main__":
    main()

