"""
Ultimate Strategy Generator
Creates 40 RADICALLY DIFFERENT strategies to find the best one in the world.
Each strategy uses completely different approaches, indicators, and methodologies.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


ULTIMATE_STRATEGIES = [
    # === KEEP THE WINNER (Strategy 1) ===
    {
        "id": 1,
        "name": "WINNER_Aggressive_HighRisk_HighReward",
        "category": "Proven Winner",
        "rationale": "The proven winner from previous backtest - 303% ROI on FILUSDT with fees!",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.60,
        "take_profit_pct": 0.30,
        "trailing_callback": 0.05,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        # Strategy-specific parameters
        "primary_indicator": "momentum",
        "entry_method": "high_risk_breakout",
        "exit_method": "wide_tp_sl",
        "risk_style": "aggressive",
    },
    
    # === 39 RADICALLY DIFFERENT STRATEGIES ===
    
    # 2. RSI OVERSOLD/OVERBOUGHT PURE
    {
        "id": 2,
        "name": "RSI_Extremes_Reversal",
        "category": "Mean Reversion",
        "rationale": "Buy when RSI <30 (oversold), sell when RSI >70 (overbought). Pure mean reversion.",
        "entry_threshold": 0.5,  # Lower - RSI does the filtering
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.12,
        "trailing_callback": 0.02,
        "volume_ratio": 1.5,
        "confluence_required": 2,  # RSI + 1 other
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "rsi",
        "entry_method": "rsi_extremes",
        "exit_method": "quick_reversal",
        "risk_style": "conservative",
        "rsi_oversold": 30,
        "rsi_overbought": 70,
    },
    
    # 3. MACD HISTOGRAM DIVERGENCE
    {
        "id": 3,
        "name": "MACD_Divergence_Hunter",
        "category": "Divergence",
        "rationale": "Trade MACD divergences - price makes new high but MACD doesn't = reversal.",
        "entry_threshold": 1.8,  # Need strong divergence
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "macd",
        "entry_method": "divergence_detection",
        "exit_method": "divergence_completion",
        "risk_style": "balanced",
    },
    
    # 4. BOLLINGER BAND SQUEEZE BREAKOUT
    {
        "id": 4,
        "name": "Bollinger_Squeeze_Explosion",
        "category": "Volatility Breakout",
        "rationale": "Enter when Bollinger Bands squeeze (low volatility) then break out explosively.",
        "entry_threshold": 2.0,  # Wait for confirmed breakout
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.28,
        "trailing_callback": 0.04,
        "volume_ratio": 3.0,  # Need massive volume on breakout
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "bollinger",
        "entry_method": "squeeze_breakout",
        "exit_method": "expansion_complete",
        "risk_style": "aggressive",
    },
    
    # 5. EMA CROSSOVER GOLDEN/DEATH CROSS
    {
        "id": 5,
        "name": "EMA_Golden_Death_Cross",
        "category": "Trend Following",
        "rationale": "Golden Cross (EMA20>EMA50) = long, Death Cross (EMA20<EMA50) = short.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.22,
        "trailing_callback": 0.035,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ema",
        "entry_method": "crossover",
        "exit_method": "opposite_cross",
        "risk_style": "balanced",
    },
    
    # 6. VWAP DEVIATION TRADE
    {
        "id": 6,
        "name": "VWAP_Mean_Reversion",
        "category": "Mean Reversion",
        "rationale": "Buy when price is >1.5% below VWAP, sell when >1.5% above. Institutional levels.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.35,
        "take_profit_pct": 0.15,
        "trailing_callback": 0.02,
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "vwap",
        "entry_method": "deviation_from_vwap",
        "exit_method": "return_to_vwap",
        "risk_style": "conservative",
    },
    
    # 7. ADX TREND STRENGTH FILTER
    {
        "id": 7,
        "name": "ADX_Strong_Trend_Only",
        "category": "Trend Following",
        "rationale": "Only trade when ADX >25 (strong trend). Follow the trend direction.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.25,
        "trailing_callback": 0.04,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "adx",
        "entry_method": "strong_trend_confirmation",
        "exit_method": "trend_weakening",
        "risk_style": "balanced",
        "adx_threshold": 25,
    },
    
    # 8. STOCHASTIC RSI OVERBOUGHT/OVERSOLD
    {
        "id": 8,
        "name": "StochRSI_Fast_Scalper",
        "category": "Scalping",
        "rationale": "Use Stochastic RSI for ultra-fast entries. <20 = oversold, >80 = overbought.",
        "entry_threshold": 0.8,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.08,
        "trailing_callback": 0.015,
        "volume_ratio": 1.5,
        "confluence_required": 2,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "stoch_rsi",
        "entry_method": "stoch_extremes",
        "exit_method": "quick_scalp",
        "risk_style": "aggressive",
    },
    
    # 9. ATR VOLATILITY BREAKOUT
    {
        "id": 9,
        "name": "ATR_Volatility_Expansion",
        "category": "Volatility",
        "rationale": "Enter when ATR expands significantly - volatility breakout imminent.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.60,
        "take_profit_pct": 0.30,
        "trailing_callback": 0.05,
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "atr",
        "entry_method": "volatility_spike",
        "exit_method": "volatility_contraction",
        "risk_style": "aggressive",
    },
    
    # 10. VOLUME PROFILE HIGH VOLUME NODE
    {
        "id": 10,
        "name": "Volume_Profile_Support_Resistance",
        "category": "Support/Resistance",
        "rationale": "Trade bounces from high-volume nodes (support/resistance).",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.8,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "volume_profile",
        "entry_method": "bounce_from_hvn",
        "exit_method": "reach_next_hvn",
        "risk_style": "balanced",
    },
    
    # 11. MOMENTUM ACCELERATION (Rate of Change)
    {
        "id": 11,
        "name": "ROC_Momentum_Acceleration",
        "category": "Momentum",
        "rationale": "Enter when Rate of Change is accelerating - momentum building.",
        "entry_threshold": 1.3,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.2,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "roc",
        "entry_method": "acceleration",
        "exit_method": "deceleration",
        "risk_style": "aggressive",
    },
    
    # 12. ICHIMOKU CLOUD BREAKOUT
    {
        "id": 12,
        "name": "Ichimoku_Cloud_Kumo_Breakout",
        "category": "Trend Following",
        "rationale": "Enter when price breaks through Ichimoku cloud - strong trend signal.",
        "entry_threshold": 2.0,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.26,
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ichimoku",
        "entry_method": "cloud_breakout",
        "exit_method": "return_to_cloud",
        "risk_style": "balanced",
    },
    
    # 13. PARABOLIC SAR TREND FOLLOWER
    {
        "id": 13,
        "name": "PSAR_Trend_Dots",
        "category": "Trend Following",
        "rationale": "Follow Parabolic SAR dots - flip when dots change sides.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.48,
        "take_profit_pct": 0.22,
        "trailing_callback": 0.035,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "psar",
        "entry_method": "dot_flip",
        "exit_method": "opposite_dot_flip",
        "risk_style": "balanced",
    },
    
    # 14. FIBONACCI RETRACEMENT ZONES
    {
        "id": 14,
        "name": "Fibonacci_Golden_Ratio_Entries",
        "category": "Retracement",
        "rationale": "Enter at Fib levels (0.382, 0.5, 0.618) - golden ratio support/resistance.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "fibonacci",
        "entry_method": "fib_level_bounce",
        "exit_method": "next_fib_level",
        "risk_style": "conservative",
    },
    
    # 15. CANDLESTICK PATTERN RECOGNITION
    {
        "id": 15,
        "name": "Candlestick_Pattern_Master",
        "category": "Pattern Recognition",
        "rationale": "Trade Japanese candlestick patterns - doji, hammer, engulfing, etc.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.2,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "candlestick",
        "entry_method": "pattern_recognition",
        "exit_method": "pattern_completion",
        "risk_style": "balanced",
    },
    
    # 16. SUPPORT/RESISTANCE BREAKOUT
    {
        "id": 16,
        "name": "SR_Breakout_Retest",
        "category": "Breakout",
        "rationale": "Trade breakouts of key S/R levels, wait for retest confirmation.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.8,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "support_resistance",
        "entry_method": "breakout_retest",
        "exit_method": "next_sr_level",
        "risk_style": "balanced",
    },
    
    # 17. TRIPLE EMA CONFLUENCE
    {
        "id": 17,
        "name": "Triple_EMA_Confluence_9_21_55",
        "category": "Trend Following",
        "rationale": "All 3 EMAs (9,21,55) must align - ultra-strong trend confirmation.",
        "entry_threshold": 2.2,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.28,
        "trailing_callback": 0.045,
        "volume_ratio": 2.0,
        "confluence_required": 5,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "triple_ema",
        "entry_method": "three_ema_stack",
        "exit_method": "ema_cross",
        "risk_style": "conservative",
    },
    
    # 18. ORDER FLOW IMBALANCE
    {
        "id": 18,
        "name": "OrderFlow_BuyPressure_Detector",
        "category": "Market Microstructure",
        "rationale": "Detect order flow imbalances - heavy buy/sell pressure from orderbook.",
        "entry_threshold": 1.2,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 3.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "orderflow",
        "entry_method": "imbalance_detection",
        "exit_method": "balance_restored",
        "risk_style": "aggressive",
    },
    
    # 19. WILLIAM %R EXTREME REVERSAL
    {
        "id": 19,
        "name": "Williams_R_Extreme_Bounce",
        "category": "Mean Reversion",
        "rationale": "Williams %R <-80 = oversold bounce, >-20 = overbought drop.",
        "entry_threshold": 0.9,
        "stop_loss_pct": 0.35,
        "take_profit_pct": 0.14,
        "trailing_callback": 0.02,
        "volume_ratio": 1.8,
        "confluence_required": 2,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "williams_r",
        "entry_method": "extreme_levels",
        "exit_method": "return_to_middle",
        "risk_style": "conservative",
    },
    
    # 20. CCI COMMODITY CHANNEL INDEX
    {
        "id": 20,
        "name": "CCI_Overbought_Oversold",
        "category": "Mean Reversion",
        "rationale": "CCI >+100 = overbought fade, <-100 = oversold buy.",
        "entry_threshold": 1.0,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "cci",
        "entry_method": "extreme_cci",
        "exit_method": "cci_normalization",
        "risk_style": "balanced",
    },
    
    # 21. KELTNER CHANNEL BREAKOUT
    {
        "id": 21,
        "name": "Keltner_Channel_Expansion",
        "category": "Volatility Breakout",
        "rationale": "Enter when price breaks Keltner channels - volatility expansion.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.52,
        "take_profit_pct": 0.26,
        "trailing_callback": 0.04,
        "volume_ratio": 2.5,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "keltner",
        "entry_method": "channel_breakout",
        "exit_method": "return_to_channel",
        "risk_style": "balanced",
    },
    
    # 22. DONCHIAN CHANNEL BREAKOUT (Turtle Trading)
    {
        "id": 22,
        "name": "Donchian_Turtle_Trading_System",
        "category": "Trend Following",
        "rationale": "Classic Turtle Trading - buy 20-day high, sell 20-day low.",
        "entry_threshold": 1.9,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.25,
        "trailing_callback": 0.04,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "donchian",
        "entry_method": "20_day_breakout",
        "exit_method": "10_day_exit",
        "risk_style": "balanced",
    },
    
    # 23. SUPER TREND INDICATOR
    {
        "id": 23,
        "name": "SuperTrend_Follow_The_Line",
        "category": "Trend Following",
        "rationale": "Follow SuperTrend line - flip when price crosses the line.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.48,
        "take_profit_pct": 0.23,
        "trailing_callback": 0.035,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "supertrend",
        "entry_method": "line_cross",
        "exit_method": "opposite_cross",
        "risk_style": "balanced",
    },
    
    # 24. ACCUMULATION/DISTRIBUTION LINE
    {
        "id": 24,
        "name": "AD_Line_Smart_Money",
        "category": "Volume Analysis",
        "rationale": "Follow Accumulation/Distribution - smart money flow indicator.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ad_line",
        "entry_method": "ad_divergence",
        "exit_method": "ad_convergence",
        "risk_style": "balanced",
    },
    
    # 25. ON-BALANCE VOLUME (OBV)
    {
        "id": 25,
        "name": "OBV_Volume_Precedes_Price",
        "category": "Volume Analysis",
        "rationale": "OBV shows volume flow - leads price. Trade OBV divergences.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.8,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "obv",
        "entry_method": "obv_divergence",
        "exit_method": "obv_confirmation",
        "risk_style": "balanced",
    },
    
    # 26. CHAIKIN MONEY FLOW
    {
        "id": 26,
        "name": "CMF_Buying_Selling_Pressure",
        "category": "Volume Analysis",
        "rationale": "CMF >0 = buying pressure, <0 = selling. Trade the pressure shifts.",
        "entry_threshold": 1.3,
        "stop_loss_pct": 0.42,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.3,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "cmf",
        "entry_method": "pressure_shift",
        "exit_method": "pressure_reversal",
        "risk_style": "balanced",
    },
    
    # 27. MONEY FLOW INDEX (MFI)
    {
        "id": 27,
        "name": "MFI_Volume_Weighted_RSI",
        "category": "Volume + Momentum",
        "rationale": "MFI combines volume + RSI. <20 oversold, >80 overbought.",
        "entry_threshold": 1.1,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 2.5,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "mfi",
        "entry_method": "mfi_extremes",
        "exit_method": "mfi_middle",
        "risk_style": "balanced",
    },
    
    # 28. AROON INDICATOR
    {
        "id": 28,
        "name": "Aroon_Trend_Strength",
        "category": "Trend Following",
        "rationale": "Aroon Up >70 & Aroon Down <30 = strong uptrend.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "aroon",
        "entry_method": "aroon_crossover",
        "exit_method": "aroon_weakening",
        "risk_style": "balanced",
    },
    
    # 29. ELDER RAY (BULL/BEAR POWER)
    {
        "id": 29,
        "name": "Elder_Ray_Bull_Bear_Power",
        "category": "Momentum",
        "rationale": "Bull Power >0 & rising = buy. Bear Power <0 & falling = sell.",
        "entry_threshold": 1.4,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "elder_ray",
        "entry_method": "power_surge",
        "exit_method": "power_fade",
        "risk_style": "balanced",
    },
    
    # 30. PIVOT POINTS (CLASSIC)
    {
        "id": 30,
        "name": "Pivot_Points_Intraday_SR",
        "category": "Support/Resistance",
        "rationale": "Trade bounces from daily pivot points - S1, S2, R1, R2.",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.18,
        "trailing_callback": 0.03,
        "volume_ratio": 2.2,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "pivot_points",
        "entry_method": "pivot_bounce",
        "exit_method": "next_pivot",
        "risk_style": "conservative",
    },
    
    # 31. PRICE ACTION PURE (NO INDICATORS)
    {
        "id": 31,
        "name": "Pure_Price_Action_Naked_Chart",
        "category": "Price Action",
        "rationale": "No indicators! Read pure price action - swing highs/lows, structure.",
        "entry_threshold": 1.6,
        "stop_loss_pct": 0.48,
        "take_profit_pct": 0.22,
        "trailing_callback": 0.035,
        "volume_ratio": 2.0,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "none",
        "entry_method": "structure_break",
        "exit_method": "opposite_structure",
        "risk_style": "balanced",
    },
    
    # 32. HARMONIC PATTERNS (GARTLEY, BUTTERFLY)
    {
        "id": 32,
        "name": "Harmonic_Patterns_Gartley_Butterfly",
        "category": "Pattern Recognition",
        "rationale": "Trade harmonic patterns - precise Fibonacci-based reversals.",
        "entry_threshold": 2.0,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 5,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "harmonic",
        "entry_method": "pattern_completion",
        "exit_method": "target_zones",
        "risk_style": "conservative",
    },
    
    # 33. WYCKOFF ACCUMULATION/DISTRIBUTION
    {
        "id": 33,
        "name": "Wyckoff_Smart_Money_Phases",
        "category": "Market Structure",
        "rationale": "Trade Wyckoff phases - accumulation spring, distribution upthrust.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.8,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "wyckoff",
        "entry_method": "spring_upthrust",
        "exit_method": "phase_complete",
        "risk_style": "balanced",
    },
    
    # 34. ELLIOTT WAVE THEORY
    {
        "id": 34,
        "name": "Elliott_Wave_5_3_Pattern",
        "category": "Wave Theory",
        "rationale": "Trade Elliott Wave structure - enter wave 3, exit before wave 5.",
        "entry_threshold": 2.2,
        "stop_loss_pct": 0.55,
        "take_profit_pct": 0.28,
        "trailing_callback": 0.045,
        "volume_ratio": 2.0,
        "confluence_required": 5,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "elliott_wave",
        "entry_method": "wave_3_impulse",
        "exit_method": "wave_5_top",
        "risk_style": "conservative",
    },
    
    # 35. MARTINGALE AGGRESSIVE
    {
        "id": 35,
        "name": "Martingale_Double_Down",
        "category": "Position Sizing",
        "rationale": "Double position size after losses - recover with one win (HIGH RISK!).",
        "entry_threshold": 1.2,
        "stop_loss_pct": 0.35,
        "take_profit_pct": 0.15,
        "trailing_callback": 0.025,
        "volume_ratio": 1.8,
        "confluence_required": 3,
        "position_size_pct": 0.05,  # Start smaller for doubling
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "momentum",
        "entry_method": "martingale_system",
        "exit_method": "quick_recovery",
        "risk_style": "ultra_aggressive",
        "martingale_multiplier": 2.0,
    },
    
    # 36. ANTI-MARTINGALE (PYRAMID)
    {
        "id": 36,
        "name": "Anti_Martingale_Pyramid_Winners",
        "category": "Position Sizing",
        "rationale": "Add to winning positions - let winners run big!",
        "entry_threshold": 1.5,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.25,
        "trailing_callback": 0.05,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.08,  # Start smaller
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "momentum",
        "entry_method": "pyramid_on_profit",
        "exit_method": "trailing_all",
        "risk_style": "aggressive",
        "pyramid_levels": 3,
    },
    
    # 37. TIME-BASED EXIT (HOLD 2 HOURS MAX)
    {
        "id": 37,
        "name": "Time_Based_2Hour_Exit",
        "category": "Time Management",
        "rationale": "Exit all positions after 2 hours regardless - no overnight holds.",
        "entry_threshold": 1.3,
        "stop_loss_pct": 0.45,
        "take_profit_pct": 0.20,
        "trailing_callback": 0.03,
        "volume_ratio": 2.0,
        "confluence_required": 3,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "momentum",
        "entry_method": "intraday_momentum",
        "exit_method": "time_based_2h",
        "risk_style": "balanced",
        "max_hold_hours": 2,
    },
    
    # 38. CORRELATION PAIRS TRADING
    {
        "id": 38,
        "name": "Correlation_Pairs_Mean_Reversion",
        "category": "Statistical Arbitrage",
        "rationale": "Trade correlated pairs - when divergence exceeds threshold, revert.",
        "entry_threshold": 1.7,
        "stop_loss_pct": 0.40,
        "take_profit_pct": 0.16,
        "trailing_callback": 0.025,
        "volume_ratio": 1.5,
        "confluence_required": 4,
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "correlation",
        "entry_method": "divergence_threshold",
        "exit_method": "convergence",
        "risk_style": "conservative",
    },
    
    # 39. NEWS-DRIVEN MOMENTUM
    {
        "id": 39,
        "name": "News_Event_Volatility_Trader",
        "category": "Event Trading",
        "rationale": "Trade volatility spikes during news events - fast in, fast out.",
        "entry_threshold": 1.0,  # Lower - news provides signal
        "stop_loss_pct": 0.50,  # Wider for volatility
        "take_profit_pct": 0.22,
        "trailing_callback": 0.04,
        "volume_ratio": 4.0,  # Massive volume on news
        "confluence_required": 2,
        "position_size_pct": 0.08,  # Smaller for high risk
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "volatility",
        "entry_method": "spike_detection",
        "exit_method": "quick_scalp",
        "risk_style": "ultra_aggressive",
    },
    
    # 40. MACHINE LEARNING HYBRID
    {
        "id": 40,
        "name": "ML_Hybrid_Multi_Indicator_Ensemble",
        "category": "Machine Learning",
        "rationale": "Combine ALL indicators with weighted ensemble - ML-style decision making.",
        "entry_threshold": 1.8,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 0.24,
        "trailing_callback": 0.04,
        "volume_ratio": 2.2,
        "confluence_required": 6,  # Need many indicators to agree
        "position_size_pct": 0.10,
        "leverage": 25,
        "max_positions": 15,
        "min_liquidity": 100000,
        "primary_indicator": "ensemble",
        "entry_method": "weighted_consensus",
        "exit_method": "ensemble_flip",
        "risk_style": "balanced",
        "indicator_weights": {
            "rsi": 0.12,
            "macd": 0.15,
            "bollinger": 0.10,
            "ema": 0.12,
            "vwap": 0.15,
            "volume": 0.10,
            "momentum": 0.13,
            "volatility": 0.08,
            "trend": 0.05,
        },
    },
]


def generate_and_save_strategies():
    """Generate and save all 40 ultimate strategies."""
    strategies_dir = Path("strategies")
    strategies_dir.mkdir(exist_ok=True)
    
    print("="*100)
    print("ULTIMATE STRATEGY GENERATOR - Finding the Best Strategy in the World")
    print("="*100)
    print(f"Generating {len(ULTIMATE_STRATEGIES)} RADICALLY DIFFERENT strategies...\n")
    
    # Save individual strategy files
    for strategy in ULTIMATE_STRATEGIES:
        filename = strategies_dir / f"strategy_{strategy['id']:03d}.json"
        with open(filename, 'w') as f:
            json.dump(strategy, f, indent=2)
    
    # Save summary
    summary_file = strategies_dir / "strategies_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(ULTIMATE_STRATEGIES, f, indent=2)
    
    # Save detailed rationales
    rationales_file = strategies_dir / "ULTIMATE_STRATEGY_RATIONALES.md"
    with open(rationales_file, 'w') as f:
        f.write("# 🏆 ULTIMATE STRATEGY RATIONALES\n\n")
        f.write("## 40 RADICALLY DIFFERENT Strategies to Find the Best in the World\n\n")
        f.write("Each strategy uses completely different approaches:\n")
        f.write("- Different indicators (RSI, MACD, Bollinger, ADX, etc.)\n")
        f.write("- Different methods (trend following, mean reversion, breakouts)\n")
        f.write("- Different patterns (harmonic, Elliott Wave, Wyckoff)\n")
        f.write("- Different risk management (martingale, pyramid, time-based)\n\n")
        f.write("---\n\n")
        
        # Group by category
        categories = {}
        for s in ULTIMATE_STRATEGIES:
            cat = s['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(s)
        
        for category, strategies in sorted(categories.items()):
            f.write(f"## {category} ({len(strategies)} strategies)\n\n")
            for s in strategies:
                f.write(f"### {s['id']}. {s['name']}\n\n")
                f.write(f"**Rationale:** {s['rationale']}\n\n")
                f.write(f"**Primary Indicator:** {s['primary_indicator']}\n")
                f.write(f"**Entry Method:** {s['entry_method']}\n")
                f.write(f"**Exit Method:** {s['exit_method']}\n")
                f.write(f"**Risk Style:** {s['risk_style']}\n\n")
                f.write(f"**Parameters:**\n")
                f.write(f"- Entry Threshold: {s['entry_threshold']}\n")
                f.write(f"- Stop Loss: {s['stop_loss_pct']*100:.0f}% capital\n")
                f.write(f"- Take Profit: {s['take_profit_pct']*100:.0f}% capital\n")
                f.write(f"- Trailing: {s['trailing_callback']*100:.1f}%\n")
                f.write(f"- Volume Ratio: {s['volume_ratio']}x\n")
                f.write(f"- Confluence: {s['confluence_required']}/9 indicators\n")
                f.write(f"\n---\n\n")
    
    print(f"✅ Generated {len(ULTIMATE_STRATEGIES)} strategy files")
    print(f"✅ Created summary: {summary_file}")
    print(f"✅ Created rationales: {rationales_file}")
    
    # Print category breakdown
    print("\n" + "="*100)
    print("STRATEGY CATEGORIES")
    print("="*100)
    for category, strategies in sorted(categories.items()):
        print(f"\n{category}: {len(strategies)} strategies")
        for s in strategies:
            print(f"  {s['id']:2d}. {s['name']:<45s} [{s['primary_indicator']}]")
    print("\n" + "="*100)
    print("\n🔥 These strategies are RADICALLY DIFFERENT!")
    print("   - Different indicators, methods, patterns, risk management")
    print("   - Ready to find the BEST strategy in the world!")
    print("   - Run backtest to discover the winner!")


if __name__ == "__main__":
    generate_and_save_strategies()

