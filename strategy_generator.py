"""
Strategy Configuration Generator
Generates 40 systematic strategy variations for comprehensive backtesting.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any
import itertools


def generate_strategy_variations() -> list[Dict[str, Any]]:
    """
    Generate 40 systematic strategy variations.
    
    We'll vary key parameters that impact performance:
    - Entry threshold multipliers
    - Stop-loss percentages (capital-based)
    - Take-profit percentages (capital-based)
    - Trailing TP callback rates
    - Volume ratio thresholds
    - Indicator confluence requirements
    - Position size percentages
    """
    
    # Define parameter ranges (will be combined systematically)
    parameter_sets = [
        # Conservative strategies (1-10): Tight stops, lower targets
        {
            "name": "Conservative",
            "variations": [
                {"entry_threshold": 2.5, "stop_loss_pct": 0.30, "take_profit_pct": 0.10, "trailing_callback": 0.02, "volume_ratio": 2.5, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.30, "take_profit_pct": 0.12, "trailing_callback": 0.02, "volume_ratio": 2.5, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.35, "take_profit_pct": 0.10, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.35, "take_profit_pct": 0.12, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.40, "take_profit_pct": 0.10, "trailing_callback": 0.02, "volume_ratio": 2.5, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.40, "take_profit_pct": 0.12, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.5, "stop_loss_pct": 0.40, "take_profit_pct": 0.14, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 3.0, "stop_loss_pct": 0.30, "take_profit_pct": 0.10, "trailing_callback": 0.02, "volume_ratio": 3.0, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 3.0, "stop_loss_pct": 0.35, "take_profit_pct": 0.12, "trailing_callback": 0.02, "volume_ratio": 2.5, "confluence_required": 5, "position_size_pct": 0.10},
                {"entry_threshold": 3.0, "stop_loss_pct": 0.40, "take_profit_pct": 0.14, "trailing_callback": 0.03, "volume_ratio": 2.5, "confluence_required": 5, "position_size_pct": 0.10},
            ]
        },
        # Balanced strategies (11-20): Medium risk/reward
        {
            "name": "Balanced",
            "variations": [
                {"entry_threshold": 2.0, "stop_loss_pct": 0.40, "take_profit_pct": 0.14, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.40, "take_profit_pct": 0.16, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.45, "take_profit_pct": 0.14, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.45, "take_profit_pct": 0.16, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.50, "take_profit_pct": 0.16, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.50, "take_profit_pct": 0.18, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.50, "take_profit_pct": 0.16, "trailing_callback": 0.02, "volume_ratio": 2.5, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 2.0, "stop_loss_pct": 0.50, "take_profit_pct": 0.18, "trailing_callback": 0.03, "volume_ratio": 2.5, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 1.8, "stop_loss_pct": 0.45, "take_profit_pct": 0.16, "trailing_callback": 0.02, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 1.8, "stop_loss_pct": 0.50, "take_profit_pct": 0.18, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
            ]
        },
        # Aggressive strategies (21-30): Wider stops, higher targets, more trades
        {
            "name": "Aggressive",
            "variations": [
                {"entry_threshold": 1.5, "stop_loss_pct": 0.50, "take_profit_pct": 0.18, "trailing_callback": 0.02, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.50, "take_profit_pct": 0.20, "trailing_callback": 0.03, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.55, "take_profit_pct": 0.20, "trailing_callback": 0.03, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.60, "take_profit_pct": 0.20, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.60, "take_profit_pct": 0.22, "trailing_callback": 0.04, "volume_ratio": 2.0, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.7, "stop_loss_pct": 0.50, "take_profit_pct": 0.18, "trailing_callback": 0.02, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.7, "stop_loss_pct": 0.50, "take_profit_pct": 0.20, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.7, "stop_loss_pct": 0.55, "take_profit_pct": 0.20, "trailing_callback": 0.03, "volume_ratio": 2.0, "confluence_required": 4, "position_size_pct": 0.10},
                {"entry_threshold": 1.7, "stop_loss_pct": 0.60, "take_profit_pct": 0.22, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.7, "stop_loss_pct": 0.60, "take_profit_pct": 0.24, "trailing_callback": 0.04, "volume_ratio": 2.0, "confluence_required": 3, "position_size_pct": 0.10},
            ]
        },
        # Ultra-Aggressive strategies (31-40): Maximum risk/reward
        {
            "name": "UltraAggressive",
            "variations": [
                {"entry_threshold": 1.2, "stop_loss_pct": 0.60, "take_profit_pct": 0.24, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.2, "stop_loss_pct": 0.60, "take_profit_pct": 0.26, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.2, "stop_loss_pct": 0.65, "take_profit_pct": 0.26, "trailing_callback": 0.05, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.0, "stop_loss_pct": 0.60, "take_profit_pct": 0.24, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.0, "stop_loss_pct": 0.65, "take_profit_pct": 0.26, "trailing_callback": 0.05, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.0, "stop_loss_pct": 0.70, "take_profit_pct": 0.28, "trailing_callback": 0.05, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.65, "take_profit_pct": 0.24, "trailing_callback": 0.04, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.5, "stop_loss_pct": 0.65, "take_profit_pct": 0.26, "trailing_callback": 0.05, "volume_ratio": 2.0, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.3, "stop_loss_pct": 0.65, "take_profit_pct": 0.26, "trailing_callback": 0.05, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
                {"entry_threshold": 1.3, "stop_loss_pct": 0.70, "take_profit_pct": 0.28, "trailing_callback": 0.05, "volume_ratio": 1.5, "confluence_required": 3, "position_size_pct": 0.10},
            ]
        }
    ]
    
    strategies = []
    strategy_id = 1
    
    for param_set in parameter_sets:
        for variation in param_set["variations"]:
            strategy = {
                "id": strategy_id,
                "name": f"{param_set['name']}_{strategy_id:03d}",
                "description": f"{param_set['name']} strategy variation {strategy_id}",
                **variation,
                # Additional settings
                "leverage": 25,
                "max_positions": 15,
                "min_liquidity": 100000,
            }
            strategies.append(strategy)
            strategy_id += 1
    
    return strategies


def save_strategies(strategies: list[Dict[str, Any]], output_dir: str = "strategies"):
    """Save strategies as individual JSON files."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    for strategy in strategies:
        filename = output_path / f"strategy_{strategy['id']:03d}.json"
        with open(filename, 'w') as f:
            json.dump(strategy, f, indent=2)
    
    print(f"✅ Generated {len(strategies)} strategy files in {output_dir}/")
    
    # Also create a summary file
    summary_path = output_path / "strategies_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(strategies, f, indent=2)
    print(f"✅ Created summary file: {summary_path}")


def print_strategy_summary(strategies: list[Dict[str, Any]]):
    """Print a summary of generated strategies."""
    print("\n" + "="*80)
    print("STRATEGY GENERATION SUMMARY")
    print("="*80)
    print(f"Total strategies: {len(strategies)}")
    print()
    
    # Group by category
    categories = {}
    for s in strategies:
        category = s['name'].split('_')[0]
        if category not in categories:
            categories[category] = []
        categories[category].append(s)
    
    for category, strats in categories.items():
        print(f"\n{category}: {len(strats)} strategies")
        print(f"  Entry threshold range: {min(s['entry_threshold'] for s in strats):.1f} - {max(s['entry_threshold'] for s in strats):.1f}")
        print(f"  Stop-loss range: {min(s['stop_loss_pct'] for s in strats)*100:.0f}% - {max(s['stop_loss_pct'] for s in strats)*100:.0f}% capital")
        print(f"  Take-profit range: {min(s['take_profit_pct'] for s in strats)*100:.0f}% - {max(s['take_profit_pct'] for s in strats)*100:.0f}% capital")
        print(f"  Trailing callback range: {min(s['trailing_callback'] for s in strats)*100:.0f}% - {max(s['trailing_callback'] for s in strats)*100:.0f}%")
    
    print("\n" + "="*80)


def main():
    """Generate all strategy configurations."""
    print("🚀 Generating 40 strategy variations...")
    
    strategies = generate_strategy_variations()
    print_strategy_summary(strategies)
    save_strategies(strategies)
    
    print("\n✅ Strategy generation complete!")
    print(f"Next step: Run backtests with these strategies")


if __name__ == "__main__":
    main()

