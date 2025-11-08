"""
Professional Strategy Generator
Creates 40 well-reasoned strategies based on actual trading principles.
Each strategy has a clear rationale and is designed to exploit specific market conditions.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


# === STRATEGY DEFINITIONS WITH RATIONALES ===

PROFESSIONAL_STRATEGIES = [
    # === SCALPING STRATEGIES (1-8) ===
    {
        "id": 1,
        "name": "Scalper_HighFreq_TightStop",
        "category": "Scalping",
        "rationale": "Exploit small price movements with high frequency. Tight stops protect capital, tight TPs lock in micro-profits before reversals.",
        "entry_threshold": 1.0,  # Very low - many entries
        "stop_loss_pct": 0.25,  # 25% capital - TIGHT stop
        "take_profit_pct": 0.08,  # 8% capital - TIGHT TP
        "trailing_callback": 0.015,  # 1.5% - very tight trailing
        "volume_ratio": 1.5,  # Lower requirement
        "confluence_required": 3,  # Lower requirement
        "position_size_pct": 0.08,  # Smaller positions for safety
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 2,
        "name": "Scalper_MomentumRider",
        "category": "Scalping",
        "rationale": "Ride short-term momentum bursts. Requires stronger volume confirmation to avoid fakeouts.",
        "entry_threshold": 1.2,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.10,
        "trailing_callback": 0.02,
        "volume_ratio": 2.5,  # HIGH volume required
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 3,
        "name": "Scalper_VolumeSpike",
        "category": "Scalping",
        "rationale": "Enter on volume spikes which often precede price moves. Quick TP to capture the initial surge.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.12,
        "trailing_callback": 0.02,
        "volume_ratio": 3.0,  # VERY HIGH volume requirement
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 4,
        "name": "Scalper_QuickFlip",
        "category": "Scalping",
        "rationale": "Ultra-fast entries/exits. Wider stop for noise tolerance, but tight TP to flip positions quickly.",
        "entry_threshold": 0.8,  # Ultra-low threshold
        "stop_loss_pct": 0.35,
        "take_profit_pct": 0.08,
        "trailing_callback": 0.01,  # 1% - extremely tight
        "volume_ratio": 1.5,
        "confluence_required": 3,
        "position_size_pct": 0.08,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 5,
        "name": "Scalper_BreakoutSniper",
        "category": "Scalping",
        "rationale": "Wait for strong confluence before entering, then scalp the breakout. Medium TP to capture full move.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.14,
        "trailing_callback": 0.02,
        "volume_ratio": 2.5,
        "confluence_required": 4,  # Higher confluence for quality
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 6,
        "name": "Scalper_RangeTrader",
        "category": "Scalping",
        "rationale": "Exploit range-bound markets. Tight stops/TPs for quick profits in consolidation zones.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.25,
        "take_profit_pct": 0.10,
        "trailing_callback": 0.015,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 7,
        "name": "Scalper_NewsFader",
        "category": "Scalping",
        "rationale": "Fade initial overreactions. Lower threshold to catch reversals, medium stops for volatility.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.40,  # Wider for volatility
        "take_profit_pct": 0.12,
        "trailing_callback": 0.025,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 8,
        "name": "Scalper_MeanReversion",
        "category": "Scalping",
        "rationale": "Buy dips/sell rips expecting mean reversion. Quick TP before trend resumes.",
        "entry_threshold": 1.2,
        "stop_loss_pct": 0.35,
        "take_profit_pct": 0.10,
        "trailing_callback": 0.02,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    
    # === SWING TRADING STRATEGIES (9-16) ===
    {
        "id": 9,
        "name": "Swing_TrendFollower",
        "category": "Swing",
        "rationale": "Follow established trends with medium-term holds. Higher TP/trailing to capture larger moves.",
        "entry_threshold": 1.8,  # Wait for strong trend confirmation
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,  # Higher TP for swing trades
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 10,
        "name": "Swing_Breakout",
        "category": "Swing",
        "rationale": "Enter on confirmed breakouts from consolidation. Wide stops to avoid stop hunts, high TP for full move.",
        "entry_threshold": 2.0,  # Strong breakout signal required
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.25,  # Very high TP
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 5,  # High confluence for breakout confirmation
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 11,
        "name": "Swing_PullbackEntry",
        "category": "Swing",
        "rationale": "Enter on pullbacks in uptrends. Lower threshold to catch dips, but requires trend confirmation.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 12,
        "name": "Swing_PatientTrader",
        "category": "Swing",
        "rationale": "Wait for perfect setups with very high confluence. Lower frequency but higher quality trades.",
        "entry_threshold": 2.5,  # Very selective
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.22,
        "trailing_callback": 0.035,
        "volume_ratio": 2.5,
        "confluence_required": 5,  # Very high confluence
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 13,
        "name": "Swing_MomentumSurfer",
        "category": "Swing",
        "rationale": "Ride momentum waves. Medium entry threshold, wide trailing to let winners run.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.04,  # Wider trailing for momentum
        "volume_ratio": 2.2,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 14,
        "name": "Swing_VolatilityExpansion",
        "category": "Swing",
        "rationale": "Enter when volatility expands (Bollinger squeeze breakouts). Wide stops for volatility.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.55,  # Wide stop for volatility
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 15,
        "name": "Swing_SupportResistance",
        "category": "Swing",
        "rationale": "Trade bounces from key S/R levels. Medium stops, medium TPs for S/R range.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 16,
        "name": "Swing_TrendReversal",
        "category": "Swing",
        "rationale": "Catch early trend reversals. Higher threshold for confirmation, wide TP to capture new trend.",
        "entry_threshold": 2.2,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.26,
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 5,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    
    # === BALANCED STRATEGIES (17-24) ===
    {
        "id": 17,
        "name": "Balanced_AllRounder",
        "category": "Balanced",
        "rationale": "Balanced approach for all market conditions. Medium everything for consistent performance.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 18,
        "name": "Balanced_RiskManaged",
        "category": "Balanced",
        "rationale": "Focus on capital preservation. Tighter stops, moderate TPs, high confluence for quality.",
        "entry_threshold": 2.0,
        "stop_loss_pct": 0.40,  # Tighter stop
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.2,
        "confluence_required": 5,  # Higher confluence
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 19,
        "name": "Balanced_GoldenRatio",
        "category": "Balanced",
        "rationale": "Uses optimal risk/reward ratios (2:1). Balanced stops/TPs for consistent profitability.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.18,  # 2:1 ratio (adjusted for leverage)
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 20,
        "name": "Balanced_VolumePrice",
        "category": "Balanced",
        "rationale": "Combines volume and price analysis. Requires strong volume confirmation for entries.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.5,  # High volume requirement
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 21,
        "name": "Balanced_AdaptiveTrader",
        "category": "Balanced",
        "rationale": "Adapts to market conditions. Medium flexibility in all parameters.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 22,
        "name": "Balanced_QualityOverQuantity",
        "category": "Balanced",
        "rationale": "Prioritizes trade quality. Higher threshold and confluence, moderate frequency.",
        "entry_threshold": 2.0,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.2,
        "confluence_required": 5,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 23,
        "name": "Balanced_SteadyEddie",
        "category": "Balanced",
        "rationale": "Consistent, steady profits. Avoids extremes, targets reliable 1-2% per day.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 24,
        "name": "Balanced_SmartMoney",
        "category": "Balanced",
        "rationale": "Follows 'smart money' - requires high volume + strong confluence to confirm institutional flow.",
        "entry_threshold": 1.9,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.8,  # Very high volume = smart money
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    
    # === AGGRESSIVE STRATEGIES (25-32) ===
    {
        "id": 25,
        "name": "Aggressive_HighRisk_HighReward",
        "category": "Aggressive",
        "rationale": "Maximum risk for maximum reward. Wide stops to weather volatility, very high TPs for big wins.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.60,  # Wide stop
        "take_profit_pct": 0.30,  # Very high TP
        "trailing_callback": 0.05,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 26,
        "name": "Aggressive_MomentumChaser",
        "category": "Aggressive",
        "rationale": "Chase strong momentum. Lower threshold for quick entries, wide trailing to ride trends.",
        "entry_threshold": 1.3,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.05,  # Wide trailing
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 27,
        "name": "Aggressive_VolatilityHunter",
        "category": "Aggressive",
        "rationale": "Seeks high volatility for explosive moves. Very wide stops for wild swings, huge TPs.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.65,  # Very wide
        "take_profit_pct": 0.32,  # Huge TP
        "trailing_callback": 0.06,
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 28,
        "name": "Aggressive_BreakoutBlitz",
        "category": "Aggressive",
        "rationale": "Aggressive breakout entries with lower threshold. Wide stops/TPs for full breakout capture.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.26,
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 29,
        "name": "Aggressive_TrendExplosion",
        "category": "Aggressive",
        "rationale": "Enter early in trend formations. Medium threshold, wide TPs to capture full trend.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.28,
        "trailing_callback": 0.05,
        "volume_ratio": 2.2,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 30,
        "name": "Aggressive_PumpCatcher",
        "category": "Aggressive",
        "rationale": "Catch pump beginnings with low threshold + high volume. Quick TP before dump.",
        "entry_threshold": 1.2,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.22,
        "trailing_callback": 0.03,
        "volume_ratio": 3.0,  # Very high volume = pump detection
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 31,
        "name": "Aggressive_ParabolicRider",
        "category": "Aggressive",
        "rationale": "Ride parabolic moves. Lower threshold for early entry, very wide trailing to stay in.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.28,
        "trailing_callback": 0.06,  # Very wide trailing
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 32,
        "name": "Aggressive_AllIn",
        "category": "Aggressive",
        "rationale": "Go all-in on strong signals. High confluence requirement, but massive TPs when right.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.60,
        "take_profit_pct": 0.35,  # Massive TP
        "trailing_callback": 0.05,
        "volume_ratio": 2.5,
        "confluence_required": 5,  # Need strong confirmation
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    
    # === CONTRARIAN STRATEGIES (33-40) ===
    {
        "id": 33,
        "name": "Contrarian_OverboughtFader",
        "category": "Contrarian",
        "rationale": "Fade overbought conditions (RSI >70). Counter-trend, needs wide stops for extended moves.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 1.8,
        "confluence_required": 4,
        "position_size_pct": 0.09,  # Smaller size for counter-trend
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 34,
        "name": "Contrarian_PanicBuyer",
        "category": "Contrarian",
        "rationale": "Buy panic selloffs. Wide stops for continued panic, medium TP for bounce.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.5,  # High volume = panic
        "confluence_required": 4,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 35,
        "name": "Contrarian_ExhaustionTrader",
        "category": "Contrarian",
        "rationale": "Trade trend exhaustion signals. High confluence for reversal confirmation.",
        "entry_threshold": 2.0,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.035,
        "volume_ratio": 2.2,
        "confluence_required": 5,  # Need strong reversal signals
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 36,
        "name": "Contrarian_DivergenceHunter",
        "category": "Contrarian",
        "rationale": "Trade RSI/MACD divergences. Medium threshold, wide stops for divergence resolution.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 37,
        "name": "Contrarian_VolumeAnomaly",
        "category": "Contrarian",
        "rationale": "Fade volume anomalies (unusual volume without price move = trap). Quick TPs.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.14,
        "trailing_callback": 0.025,
        "volume_ratio": 3.0,  # Very high volume = anomaly
        "confluence_required": 3,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 38,
        "name": "Contrarian_SqueezeBreaker",
        "category": "Contrarian",
        "rationale": "Fade false breakouts from squeezes. Medium stops, quick TPs before re-squeeze.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.14,
        "trailing_callback": 0.02,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 39,
        "name": "Contrarian_SentimentFader",
        "category": "Contrarian",
        "rationale": "Fade extreme sentiment. When everyone is bullish, short (and vice versa).",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.55,  # Wide for sentiment extremes
        "take_profit_pct": 0.20,
        "trailing_callback": 0.04,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
    {
        "id": 40,
        "name": "Contrarian_MeanReversionExtreme",
        "category": "Contrarian",
        "rationale": "Trade extreme deviations from mean (>2 std dev). Expect snapback, wide stops for more deviation.",
        "entry_threshold": 1.9,
        "stop_loss_pct": 0.60,  # Very wide for extreme moves
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.09,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
    },
]


def generate_and_save_strategies():
    """Generate strategy JSON files and summary."""
    strategies_dir = Path("strategies")
    strategies_dir.mkdir(exist_ok=True)
    
    print("="*80)
    print("PROFESSIONAL STRATEGY GENERATOR")
    print("="*80)
    print(f"Generating {len(PROFESSIONAL_STRATEGIES)} well-reasoned strategies...\n")
    
    # Save individual strategy files
    for strategy in PROFESSIONAL_STRATEGIES:
        filename = strategies_dir / f"strategy_{strategy['id']:03d}.json"
        with open(filename, 'w') as f:
            json.dump(strategy, f, indent=2)
    
    # Save summary
    summary_file = strategies_dir / "strategies_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(PROFESSIONAL_STRATEGIES, f, indent=2)
    
    # Save rationales document
    rationales_file = strategies_dir / "STRATEGY_RATIONALES.md"
    with open(rationales_file, 'w') as f:
        f.write("# Strategy Rationales\n\n")
        f.write("Each strategy has a specific purpose and market condition it excels in.\n\n")
        f.write("---\n\n")
        
        # Group by category
        categories = {}
        for s in PROFESSIONAL_STRATEGIES:
            cat = s['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(s)
        
        for category, strategies in categories.items():
            f.write(f"## {category} Strategies\n\n")
            for s in strategies:
                f.write(f"### {s['id']}. {s['name']}\n\n")
                f.write(f"**Rationale:** {s['rationale']}\n\n")
                f.write(f"**Parameters:**\n")
                f.write(f"- Entry Threshold: {s['entry_threshold']}\n")
                f.write(f"- Stop Loss: {s['stop_loss_pct']*100:.0f}% capital\n")
                f.write(f"- Take Profit: {s['take_profit_pct']*100:.0f}% capital\n")
                f.write(f"- Trailing: {s['trailing_callback']*100:.1f}%\n")
                f.write(f"- Volume Ratio: {s['volume_ratio']}x\n")
                f.write(f"- Confluence: {s['confluence_required']}/9 indicators\n")
                f.write(f"\n---\n\n")
    
    print(f"✅ Generated {len(PROFESSIONAL_STRATEGIES)} strategy files")
    print(f"✅ Created summary: {summary_file}")
    print(f"✅ Created rationales: {rationales_file}")
    
    # Print category summary
    print("\n" + "="*80)
    print("STRATEGY BREAKDOWN")
    print("="*80)
    for category, strategies in categories.items():
        print(f"\n{category}: {len(strategies)} strategies")
        for s in strategies:
            print(f"  {s['id']:2d}. {s['name']}")
    print("\n" + "="*80)


if __name__ == "__main__":
    generate_and_save_strategies()

