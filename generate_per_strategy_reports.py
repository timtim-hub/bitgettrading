"""
Generate detailed per-strategy reports showing all tokens with >5% ROI
"""

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime


def load_strategy_results(backtest_dir: Path) -> Dict[str, List[Dict]]:
    """Load all 5pct_plus detailed results grouped by strategy."""
    strategy_results = {}
    
    # Find all *_5pct_plus_detailed_*.json files
    for file in backtest_dir.glob("*_5pct_plus_detailed_*.json"):
        # Extract strategy name from filename
        strategy_name = file.stem.replace("_5pct_plus_detailed", "").rsplit("_", 1)[0]
        
        with open(file, 'r') as f:
            results = json.load(f)
        
        # Filter tokens with >5% ROI
        filtered_results = [r for r in results if r.get('total_roi_pct', 0) > 5.0]
        
        if filtered_results:
            strategy_results[strategy_name] = filtered_results
    
    return strategy_results


def generate_strategy_report(strategy_name: str, tokens: List[Dict], output_dir: Path):
    """Generate a detailed markdown report for a single strategy."""
    
    # Sort tokens by ROI descending
    tokens_sorted = sorted(tokens, key=lambda x: x.get('total_roi_pct', 0), reverse=True)
    
    # Calculate aggregate stats
    total_tokens = len(tokens_sorted)
    avg_roi = sum(t['total_roi_pct'] for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_win_rate = sum(t['win_rate_pct'] for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    total_trades = sum(t['total_trades'] for t in tokens_sorted)
    avg_trades_per_day = sum(t['trades_per_day'] for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    
    # Calculate capital metrics
    initial_capital_per_token = 50.0
    total_initial_capital = initial_capital_per_token * total_tokens
    total_final_capital = sum(t['final_capital'] for t in tokens_sorted)
    portfolio_roi = ((total_final_capital - total_initial_capital) / total_initial_capital * 100) if total_initial_capital > 0 else 0
    
    # Calculate time-based ROI (using first token's metrics as reference)
    avg_roi_per_day = sum(t.get('roi_per_day_pct', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_roi_per_week = sum(t.get('roi_per_week_pct', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_roi_per_month = sum(t.get('roi_per_month_pct', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    
    # Calculate risk metrics
    avg_sharpe = sum(t.get('sharpe_ratio', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_sortino = sum(t.get('sortino_ratio', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_max_dd = sum(t.get('max_drawdown_pct', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    avg_profit_factor = sum(t.get('profit_factor', 0) for t in tokens_sorted) / total_tokens if total_tokens > 0 else 0
    
    # Generate markdown report
    report = f"""# Strategy Report: {strategy_name}

## 📊 Portfolio Overview

**Test Period:** 30 days historical data  
**Leverage:** 25x (default)  
**Initial Capital per Token:** $50 USD  
**Tokens Tested:** {total_tokens} tokens with >5% ROI

---

## 🏆 Key Performance Metrics

| Metric | Value |
|--------|-------|
| **Portfolio ROI** | **{portfolio_roi:.2f}%** |
| **Total Capital** | ${total_initial_capital:.2f} → ${total_final_capital:.2f} |
| **Profit** | ${total_final_capital - total_initial_capital:.2f} |
| **Average ROI per Token** | {avg_roi:.2f}% |
| **Win Rate** | {avg_win_rate:.2f}% |
| **Total Trades** | {total_trades} |
| **Trades per Day (avg)** | {avg_trades_per_day:.2f} |

---

## 📈 Time-Based ROI

| Period | ROI % |
|--------|-------|
| **Daily ROI (avg)** | {avg_roi_per_day:.2f}% |
| **Weekly ROI (avg)** | {avg_roi_per_week:.2f}% |
| **Monthly ROI (avg)** | {avg_roi_per_month:.2f}% |

---

## ⚖️ Risk Metrics

| Metric | Value |
|--------|-------|
| **Sharpe Ratio (avg)** | {avg_sharpe:.4f} |
| **Sortino Ratio (avg)** | {avg_sortino:.4f} |
| **Max Drawdown (avg)** | {avg_max_dd:.2f}% |
| **Profit Factor (avg)** | {avg_profit_factor:.2f} |

---

## 💰 Top 10 Performing Tokens

| Rank | Token | ROI % | Win Rate % | Trades | Final Capital |
|------|-------|-------|------------|--------|---------------|
"""
    
    # Add top 10 tokens
    for idx, token in enumerate(tokens_sorted[:10], 1):
        symbol = token['symbol']
        roi = token['total_roi_pct']
        win_rate = token['win_rate_pct']
        trades = token['total_trades']
        final_cap = token['final_capital']
        
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}"
        report += f"| {medal} | {symbol} | {roi:.2f}% | {win_rate:.2f}% | {trades} | ${final_cap:.2f} |\n"
    
    # Add all tokens section
    report += f"""

---

## 📋 All Tokens Performance (>{5}% ROI)

| # | Token | ROI % | Win Rate % | Trades | Trades/Day | Final Capital | Sharpe | Max DD % |
|---|-------|-------|------------|--------|------------|---------------|--------|----------|
"""
    
    for idx, token in enumerate(tokens_sorted, 1):
        symbol = token['symbol']
        roi = token['total_roi_pct']
        win_rate = token['win_rate_pct']
        trades = token['total_trades']
        trades_per_day = token['trades_per_day']
        final_cap = token['final_capital']
        sharpe = token.get('sharpe_ratio', 0)
        max_dd = token.get('max_drawdown_pct', 0)
        
        report += f"| {idx} | {symbol} | {roi:.2f}% | {win_rate:.2f}% | {trades} | {trades_per_day:.2f} | ${final_cap:.2f} | {sharpe:.4f} | {max_dd:.2f}% |\n"
    
    # Add detailed per-token breakdown
    report += f"""

---

## 📊 Detailed Token Analysis

"""
    
    for idx, token in enumerate(tokens_sorted, 1):
        symbol = token['symbol']
        roi = token['total_roi_pct']
        win_rate = token['win_rate_pct']
        trades = token['total_trades']
        trades_per_day = token['trades_per_day']
        trades_per_hour = token.get('trades_per_hour', 0)
        final_cap = token['final_capital']
        profit = final_cap - initial_capital_per_token
        
        roi_day = token.get('roi_per_day_pct', 0)
        roi_week = token.get('roi_per_week_pct', 0)
        roi_month = token.get('roi_per_month_pct', 0)
        
        sharpe = token.get('sharpe_ratio', 0)
        sortino = token.get('sortino_ratio', 0)
        max_dd = token.get('max_drawdown_pct', 0)
        profit_factor = token.get('profit_factor', 0)
        
        report += f"""### {idx}. {symbol}

**Performance:**
- Total ROI: **{roi:.2f}%**
- Win Rate: {win_rate:.2f}%
- Capital: $50.00 → ${final_cap:.2f} (+${profit:.2f})

**Trading Activity:**
- Total Trades: {trades}
- Trades per Day: {trades_per_day:.2f}
- Trades per Hour: {trades_per_hour:.4f}

**Time-Based Returns:**
- Daily ROI: {roi_day:.2f}%
- Weekly ROI: {roi_week:.2f}%
- Monthly ROI: {roi_month:.2f}%

**Risk Metrics:**
- Sharpe Ratio: {sharpe:.4f}
- Sortino Ratio: {sortino:.4f}
- Max Drawdown: {max_dd:.2f}%
- Profit Factor: {profit_factor:.4f}

---

"""
    
    # Add footer
    report += f"""

---

## 📝 Notes

- **Fees Included:** All results include Bitget taker fees (0.06% per side, 0.12% round trip)
- **Test Duration:** 30 days of 1H candle data
- **Leverage:** 25x (default)
- **Initial Capital:** $50 per token
- **Total Portfolio:** ${total_initial_capital:.2f} invested across {total_tokens} tokens
- **Net Profit:** ${total_final_capital - total_initial_capital:.2f}
- **Portfolio ROI:** {portfolio_roi:.2f}%

**Strategy ID:** {tokens_sorted[0].get('strategy_id', 'N/A') if tokens_sorted else 'N/A'}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## ⚠️ Important

This strategy shows positive ROI across {total_tokens} tokens. All tokens listed achieved >5% ROI during the backtest period.

**Next Steps:**
1. Verify results with paper trading
2. Test with different leverage levels (50x, 100x)
3. Calculate liquidation risks
4. Implement adaptive parameters
5. Consider combining with other strategies

"""
    
    # Write report to file
    output_file = output_dir / f"STRATEGY_REPORT_{strategy_name}.md"
    with open(output_file, 'w') as f:
        f.write(report)
    
    print(f"✅ Generated report: {output_file.name}")
    print(f"   - Tokens: {total_tokens}")
    print(f"   - Portfolio ROI: {portfolio_roi:.2f}%")
    print(f"   - Avg Win Rate: {avg_win_rate:.2f}%")
    print()
    
    return {
        'strategy_name': strategy_name,
        'total_tokens': total_tokens,
        'portfolio_roi': portfolio_roi,
        'avg_win_rate': avg_win_rate,
        'total_trades': total_trades
    }


def main():
    """Generate per-strategy reports for all strategies."""
    backtest_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
    output_dir = Path("/Users/macbookpro13/bitgettrading/strategy_reports")
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    print("="*80)
    print("🔍 GENERATING PER-STRATEGY REPORTS")
    print("="*80)
    print()
    
    # Load all strategy results
    print("📂 Loading backtest results...")
    strategy_results = load_strategy_results(backtest_dir)
    print(f"✅ Found {len(strategy_results)} strategies with >5% ROI tokens")
    print()
    
    # Generate report for each strategy
    print("📝 Generating reports...")
    print()
    
    summary = []
    for strategy_name, tokens in strategy_results.items():
        stats = generate_strategy_report(strategy_name, tokens, output_dir)
        summary.append(stats)
    
    # Generate summary report
    print("="*80)
    print("📊 SUMMARY OF ALL STRATEGIES")
    print("="*80)
    print()
    
    # Sort by portfolio ROI
    summary_sorted = sorted(summary, key=lambda x: x['portfolio_roi'], reverse=True)
    
    print(f"{'Rank':<6} {'Strategy':<40} {'Tokens':<8} {'ROI %':<12} {'Win Rate %':<12} {'Trades':<10}")
    print("-"*95)
    
    for idx, stats in enumerate(summary_sorted, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        name = stats['strategy_name'][:38]
        tokens = stats['total_tokens']
        roi = stats['portfolio_roi']
        win_rate = stats['avg_win_rate']
        trades = stats['total_trades']
        
        print(f"{medal:<6} {name:<40} {tokens:<8} {roi:<12.2f} {win_rate:<12.2f} {trades:<10}")
    
    print()
    print("="*80)
    print(f"✅ Generated {len(strategy_results)} strategy reports in: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    main()

