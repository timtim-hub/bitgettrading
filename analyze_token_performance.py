"""
Analyze per-token performance for the best strategy (Aggressive_HighRisk_HighReward)
"""

import json
from pathlib import Path


def analyze_best_strategy_by_token():
    """Extract and display per-token performance for best strategy."""
    
    # Load detailed results
    results_files = list(Path("backtest_results").glob("detailed_metrics_*.json"))
    if not results_files:
        print("❌ No results found!")
        return
    
    latest_results = max(results_files, key=lambda p: p.stat().st_mtime)
    print(f"📊 Loading: {latest_results.name}\n")
    
    with open(latest_results) as f:
        all_results = json.load(f)
    
    # Filter for Aggressive_HighRisk_HighReward (strategy_id 25)
    strategy_name = "Aggressive_HighRisk_HighReward"
    strategy_results = [r for r in all_results if r["strategy_name"] == strategy_name]
    
    if not strategy_results:
        print(f"❌ Strategy '{strategy_name}' not found!")
        return
    
    print(f"🏆 STRATEGY: {strategy_name}")
    print(f"📈 Strategy ID: 25")
    print(f"💰 Initial Capital: $50.00 per token")
    print(f"🎯 Leverage: 25x")
    print(f"📊 Tokens Tested: {len(strategy_results)}")
    print("\n" + "="*120)
    
    # Sort by ROI (best first)
    strategy_results.sort(key=lambda x: x["total_roi_pct"], reverse=True)
    
    # Header
    print(f"{'Rank':<6} {'Token':<18} {'ROI %':<12} {'Win%':<10} {'Trades':<10} {'Tr/Day':<10} {'Final $':<12} {'24h%':<10} {'7d%':<10} {'30d%':<10}")
    print("="*120)
    
    # Print each token
    for rank, result in enumerate(strategy_results, 1):
        symbol = result["symbol"]
        total_roi = result["total_roi_pct"]
        win_rate = result["win_rate_pct"]
        total_trades = result["total_trades"]
        trades_per_day = result["trades_per_day"]
        final_capital = result["final_capital"]
        roi_per_day = result["roi_per_day_pct"]
        roi_per_week = result["roi_per_week_pct"]
        roi_per_month = result["roi_per_month_pct"]
        
        # Color coding
        roi_color = "🟢" if total_roi > 0 else "🔴"
        
        print(f"{rank:<6} {symbol:<18} {roi_color}{total_roi:>9.2f}%  {win_rate:>6.2f}%  {total_trades:>8}  {trades_per_day:>8.2f}  ${final_capital:>9.2f}  {roi_per_day:>8.2f}%  {roi_per_week:>7.2f}%  {roi_per_month:>8.2f}%")
    
    # Summary statistics
    print("="*120)
    total_roi_avg = sum(r["total_roi_pct"] for r in strategy_results) / len(strategy_results)
    total_trades_sum = sum(r["total_trades"] for r in strategy_results)
    profitable_tokens = sum(1 for r in strategy_results if r["total_roi_pct"] > 0)
    
    print(f"\n📊 SUMMARY:")
    print(f"  Average ROI across all tokens: {total_roi_avg:.2f}%")
    print(f"  Total trades executed: {total_trades_sum:,}")
    print(f"  Profitable tokens: {profitable_tokens}/{len(strategy_results)} ({profitable_tokens/len(strategy_results)*100:.1f}%)")
    print(f"  Best token: {strategy_results[0]['symbol']} (+{strategy_results[0]['total_roi_pct']:.2f}%)")
    print(f"  Worst token: {strategy_results[-1]['symbol']} ({strategy_results[-1]['total_roi_pct']:.2f}%)")
    
    # Calculate total portfolio performance if trading all tokens with $50 each
    total_initial = len(strategy_results) * 50
    total_final = sum(r["final_capital"] for r in strategy_results)
    portfolio_roi = (total_final - total_initial) / total_initial * 100
    
    print(f"\n💼 PORTFOLIO SIMULATION:")
    print(f"  If you deployed $50 on EACH token:")
    print(f"  Initial Capital: ${total_initial:,.2f} ({len(strategy_results)} × $50)")
    print(f"  Final Capital: ${total_final:,.2f}")
    print(f"  Portfolio ROI: {portfolio_roi:.2f}%")
    print(f"  Total Profit: ${total_final - total_initial:,.2f}")
    
    print("\n" + "="*120)
    print("\n⚠️  NOTE: These results DO NOT include trading fees (0.06% per trade)")
    print("   Fees would reduce performance. Re-run backtest with fees for accurate results.")


if __name__ == "__main__":
    analyze_best_strategy_by_token()

