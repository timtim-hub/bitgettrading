"""
Create 3 ML-Inspired Strategies Based on LightGBM Feature Importance
Uses top features identified by the trained model.
"""

import json
from pathlib import Path

# Top features from LightGBM training (82% accuracy, 0.864 AUC)
# 1. ADX (trend strength)
# 2. SMA_200_distance 
# 3. SMA_50_distance
# 4. MFI (money flow index)
# 5. ATR_pct (volatility)
# 6. RSI_21
# 7. Volume indicators
# 8. OBV (on-balance volume)

def create_strategy_046():
    """
    Strategy 046: ML_Feature_ADX_Trend_Focus
    Focus on ADX (top feature) + trend indicators
    """
    return {
        "id": 46,
        "name": "ML_Feature_ADX_Trend_Focus",
        "category": "ML-Inspired Trend Following",
        "rationale": "Uses ADX (top ML feature, 1198 importance) as primary signal. ADX >25 indicates strong trend. Confirmed by SMA distances (2nd & 3rd top features). Conservative entries, aggressive exits.",
        "entry_threshold": 0.9,  # Lower = easier entry
        "stop_loss_pct": 0.45,  # 45% capital = 1.8% price @ 25x
        "take_profit_pct": 0.22,  # 22% capital = 0.88% price @ 25x
        "trailing_callback": 0.035,  # 3.5% trailing
        "volume_ratio": 1.4,  # Volume 40% above average
        "confluence_required": 3,  # Need 3 confirmations
        "position_size_pct": 0.13,  # 13% per position
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "adx",  # TOP ML FEATURE!
        "entry_method": "adx_strong_trend",
        "exit_method": "trailing_tp_aggressive",
        "risk_style": "ml_conservative"
    }

def create_strategy_047():
    """
    Strategy 047: ML_Feature_MFI_Volume_Flow
    Focus on MFI (4th feature) + volume indicators
    """
    return {
        "id": 47,
        "name": "ML_Feature_MFI_Volume_Flow",
        "category": "ML-Inspired Volume Analysis",
        "rationale": "Uses MFI (974 importance) + volume indicators (top ML features). MFI <20 = oversold with money flowing in. Volume confirmation prevents fake signals. High win rate focus.",
        "entry_threshold": 0.85,
        "stop_loss_pct": 0.50,  # 50% capital = 2% price @ 25x
        "take_profit_pct": 0.18,  # 18% capital = 0.72% price @ 25x
        "trailing_callback": 0.03,  # Tight 3% trailing
        "volume_ratio": 1.6,  # Strong volume requirement (top feature!)
        "confluence_required": 2,  # MFI + volume
        "position_size_pct": 0.12,  # 12% per position
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "mfi",  # 4TH TOP ML FEATURE!
        "entry_method": "mfi_oversold_reversal",
        "exit_method": "quick_tp",
        "risk_style": "ml_balanced"
    }

def create_strategy_048():
    """
    Strategy 048: ML_Feature_Multi_Indicator_Ensemble
    Combines top 5 ML features with weighted scoring
    """
    return {
        "id": 48,
        "name": "ML_Feature_Multi_Indicator_Ensemble",
        "category": "ML-Inspired Ensemble",
        "rationale": "Ensemble approach using ALL top 5 ML features: ADX (1198), SMA distances (1173, 1078), MFI (974), ATR (900). Weighted scoring system mimics ML decision tree. Only trades when ensemble score >70%.",
        "entry_threshold": 0.75,  # Lower threshold, ensemble decides
        "stop_loss_pct": 0.48,  # 48% capital = 1.92% price @ 25x
        "take_profit_pct": 0.20,  # 20% capital = 0.8% price @ 25x
        "trailing_callback": 0.04,  # 4% trailing
        "volume_ratio": 1.5,  # Medium volume requirement
        "confluence_required": 4,  # Need 4/5 top features aligned
        "position_size_pct": 0.14,  # 14% per position (aggressive sizing)
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ml_ensemble",  # USES ALL TOP 5!
        "entry_method": "ensemble_score",
        "exit_method": "adaptive_tp",
        "risk_style": "ml_aggressive"
    }

def create_strategy_049():
    """
    Strategy 049: ML_Feature_ATR_Volatility_Breakout
    Focus on ATR_pct (5th feature) + volatility expansion
    """
    return {
        "id": 49,
        "name": "ML_Feature_ATR_Volatility_Breakout",
        "category": "ML-Inspired Volatility Breakout",
        "rationale": "Uses ATR_pct (900 importance) to identify volatility expansion. ML model learned that high ATR predicts directional moves. Trades breakouts during volatility spikes. Fast in/out.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.40,  # Tight 40% capital = 1.6% price @ 25x
        "take_profit_pct": 0.25,  # Aggressive 25% capital = 1% price @ 25x
        "trailing_callback": 0.02,  # Very tight 2% trailing
        "volume_ratio": 2.0,  # High volume breakouts only
        "confluence_required": 2,  # ATR + momentum
        "position_size_pct": 0.10,  # Smaller 10% per position (volatility risk)
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "atr",  # 5TH TOP ML FEATURE!
        "entry_method": "volatility_expansion",
        "exit_method": "fast_exit",
        "risk_style": "ml_volatility_trader"
    }

def main():
    """Generate all ML-inspired strategies."""
    strategies_dir = Path("strategies")
    strategies_dir.mkdir(exist_ok=True)
    
    strategies = [
        create_strategy_046(),
        create_strategy_047(),
        create_strategy_048(),
        create_strategy_049()
    ]
    
    print("\n" + "="*80)
    print("🧠 CREATING ML-INSPIRED STRATEGIES (Based on 82% Accurate Model)")
    print("="*80 + "\n")
    
    for strategy in strategies:
        filename = strategies_dir / f"strategy_{strategy['id']:03d}.json"
        
        # Save strategy
        with open(filename, 'w') as f:
            json.dump(strategy, f, indent=2)
        
        print(f"✅ Created: {filename}")
        print(f"   Name: {strategy['name']}")
        print(f"   Primary: {strategy['primary_indicator']}")
        print(f"   Rationale: {strategy['rationale'][:80]}...")
        print()
    
    print("="*80)
    print("🎉 4 ML-INSPIRED STRATEGIES CREATED!")
    print("="*80)
    print("\nBased on LightGBM Feature Importance (82% accuracy, 0.864 AUC):")
    print("  1. ADX (trend strength) - 1198 importance")
    print("  2. SMA_200_distance - 1173")
    print("  3. SMA_50_distance - 1078")
    print("  4. MFI (money flow) - 974")
    print("  5. ATR_pct (volatility) - 900")
    print("\nReady for backtesting! 🚀")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()

