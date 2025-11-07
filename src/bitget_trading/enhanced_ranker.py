"""Enhanced cross-sectional ranking with multi-timeframe confluence and smart sizing."""

import numpy as np

from bitget_trading.logger import get_logger
from bitget_trading.multi_symbol_state import MultiSymbolStateManager, SymbolState
from bitget_trading.pro_trader_indicators import ProTraderIndicators, is_near_level
from bitget_trading.regime_detector import RegimeDetector
from bitget_trading.technical_indicators import TechnicalIndicators

logger = get_logger()


class EnhancedRanker:
    """
    Enhanced ranking system with:
    - Multi-timeframe confluence
    - Smart position sizing
    - Volume filtering
    - Funding rate bias
    - Correlation awareness
    """

    def __init__(
        self,
        momentum_weight: float = 0.4,
        imbalance_weight: float = 0.3,
        volatility_weight: float = 0.2,
        liquidity_weight: float = 0.1,
        bandit_alpha: float = 0.5,
        ucb_exploration: float = 2.0,
    ) -> None:
        """Initialize enhanced ranker."""
        self.momentum_weight = momentum_weight
        self.imbalance_weight = imbalance_weight
        self.volatility_weight = volatility_weight
        self.liquidity_weight = liquidity_weight
        self.bandit_alpha = bandit_alpha
        self.ucb_exploration = ucb_exploration

        # NEW: Regime detector
        self.regime_detector = RegimeDetector()

        # NEW: PRO TRADER indicators (S/R, market structure, trade grading)
        self.pro_indicators = ProTraderIndicators()

        # NEW: TECHNICAL INDICATORS (RSI, MACD, Bollinger, EMA, VWAP)
        self.technical_indicators = TechnicalIndicators()

        # NEW: BTC correlation tracking (for diversification)
        self.btc_correlations: dict[str, float] = {}

    def check_multi_timeframe_confluence(
        self, features: dict[str, float], regime: str = "ranging"
    ) -> tuple[bool, str, float, dict]:
        """
        ADVANCED confluence check with 6 layers of validation:
        1. Weighted Timeframe Confluence (longer = stronger)
        2. Volume-Confirmed Confluence (institutional signal)
        3. Orderbook-Confirmed Confluence (smart money)
        4. Adaptive Confluence Window (regime-aware)
        5. Cross-Validate with Technical Indicators (in compute_enhanced_score)
        6. Momentum Acceleration Check (catching rockets 🚀)

        Uses 1s, 3s, 5s, 10s, 15s, 30s, 1min for fast signal detection.

        Returns:
            (has_confluence, direction, strength, metadata)
        """
        # 🔥 LAYER 1: WEIGHTED TIMEFRAME CONFLUENCE
        # Longer timeframes = higher weight (institutional signal)
        timeframe_weights = {
            "1s": 0.5,  # Noise-prone, lowest weight
            "3s": 0.7,
            "5s": 1.0,  # Baseline
            "10s": 1.3,
            "15s": 1.5,
            "30s": 2.0,  # Strong signal
            "1min": 2.5,  # Strongest signal (institutional)
        }

        # Get ultra-short-term returns
        timeframe_data = [
            ("1s", features.get("return_1s")),
            ("3s", features.get("return_3s")),
            ("5s", features.get("return_5s")),
            ("10s", features.get("return_10s")),
            ("15s", features.get("return_15s")),
            ("30s", features.get("return_30s")),
            ("1min", features.get("return_1min")),
        ]

        # Filter to available returns
        available_timeframes = []
        for name, ret in timeframe_data:
            if ret is not None and ret != 0:
                available_timeframes.append(
                    (name, ret, timeframe_weights.get(name, 1.0))
                )

        if len(available_timeframes) == 0:
            return False, "neutral", 0.0, {"reason": "no_data"}

        # 🔥 LAYER 2: VOLUME-CONFIRMED CONFLUENCE
        # Require volume surge when timeframes align (institutional activity)
        volume_ratio = features.get("volume_ratio", 1.0)
        volume_confirmed = volume_ratio >= 1.5  # At least 150% of average volume

        if not volume_confirmed:
            return (
                False,
                "neutral",
                0.0,
                {"reason": "no_volume_confirmation", "volume_ratio": volume_ratio},
            )

        # 🔥 LAYER 3: ORDERBOOK-CONFIRMED CONFLUENCE
        # Use bid/ask imbalance to confirm direction (smart money)
        ob_imbalance = features.get("ob_imbalance", 0.0)
        orderbook_threshold = 0.05  # 5% imbalance minimum

        # Weighted timeframe analysis
        weighted_sum_bullish = 0.0
        weighted_sum_bearish = 0.0
        total_weight = 0.0

        bullish_timeframes = []
        bearish_timeframes = []

        for name, ret, weight in available_timeframes:
            total_weight += weight
            if ret > 0:
                weighted_sum_bullish += ret * weight
                bullish_timeframes.append((name, ret))
            else:
                weighted_sum_bearish += abs(ret) * weight
                bearish_timeframes.append((name, ret))

        # Calculate weighted average returns
        if weighted_sum_bullish > 0:
            weighted_avg_bullish = weighted_sum_bullish / total_weight
        else:
            weighted_avg_bullish = 0.0

        if weighted_sum_bearish > 0:
            weighted_avg_bearish = weighted_sum_bearish / total_weight
        else:
            weighted_avg_bearish = 0.0

        # 🔥 LAYER 4: ADAPTIVE CONFLUENCE WINDOW (Regime-Aware)
        # Different requirements per regime
        total_timeframes = len(available_timeframes)
        bullish_count = len(bullish_timeframes)
        bearish_count = len(bearish_timeframes)

        if regime == "trending":
            # Stricter: avoid chop
            required_agreement_pct = 0.75  # 75% agreement
        elif regime == "breakout":
            # More lenient: capture fast moves
            required_agreement_pct = 0.60  # 60% agreement
        elif regime == "volatile":
            # Strictest: maximum safety
            required_agreement_pct = 0.85  # 85% agreement
        else:  # ranging
            # Balanced
            required_agreement_pct = 0.70  # 70% agreement

        required_agreement = max(2, int(total_timeframes * required_agreement_pct))

        # 🔥 LAYER 6: MOMENTUM ACCELERATION CHECK
        # Track if confluence is strengthening (catching rockets 🚀)
        momentum_accelerating = False
        if len(available_timeframes) >= 3:
            # Check if longer timeframes show stronger momentum
            short_term_avg = (
                sum(abs(ret) for name, ret, _ in available_timeframes[:2]) / 2
            )
            long_term_avg = (
                sum(abs(ret) for name, ret, _ in available_timeframes[-2:]) / 2
            )

            if long_term_avg > short_term_avg * 1.2:  # 20% acceleration
                momentum_accelerating = True

        # Determine direction with orderbook confirmation
        direction = "neutral"
        strength = 0.0
        metadata = {
            "volume_ratio": volume_ratio,
            "ob_imbalance": ob_imbalance,
            "momentum_accelerating": momentum_accelerating,
            "regime": regime,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "total_timeframes": total_timeframes,
            "required_agreement": required_agreement,
        }

        if bullish_count >= required_agreement:
            # Bullish confluence detected
            # LAYER 3: Confirm with orderbook
            if ob_imbalance < -orderbook_threshold:
                # Orderbook shows bid pressure (bullish confirmation)
                direction = "long"
                strength = weighted_avg_bullish

                # Boost strength if momentum accelerating
                if momentum_accelerating:
                    strength *= 1.3  # 30% boost for accelerating momentum
                    metadata["momentum_boost"] = True

                metadata["orderbook_confirmed"] = True
            else:
                # Orderbook doesn't confirm (potential trap)
                return (
                    False,
                    "neutral",
                    0.0,
                    {**metadata, "reason": "orderbook_conflict"},
                )

        elif bearish_count >= required_agreement:
            # Bearish confluence detected
            # LAYER 3: Confirm with orderbook
            if ob_imbalance > orderbook_threshold:
                # Orderbook shows ask pressure (bearish confirmation)
                direction = "short"
                strength = weighted_avg_bearish

                # Boost strength if momentum accelerating
                if momentum_accelerating:
                    strength *= 1.3  # 30% boost for accelerating momentum
                    metadata["momentum_boost"] = True

                metadata["orderbook_confirmed"] = True
            else:
                # Orderbook doesn't confirm (potential trap)
                return (
                    False,
                    "neutral",
                    0.0,
                    {**metadata, "reason": "orderbook_conflict"},
                )

        if direction == "neutral":
            return (
                False,
                "neutral",
                0.0,
                {**metadata, "reason": "insufficient_agreement"},
            )

        return True, direction, strength, metadata

    def compute_enhanced_score(
        self, state: SymbolState, features: dict[str, float], btc_return: float = 0.0
    ) -> tuple[float, str, dict]:
        """
        Compute enhanced score with all improvements.

        STRICT FILTERS: Only trade high-quality setups!

        NEW: 6-Layer Confluence Validation with Adaptive Thresholds

        Returns:
            (score, predicted_side, metadata)
        """
        # 🔥 STEP 1: Detect market regime FIRST (needed for adaptive confluence)
        price_history = list(state.price_history)
        volatility = features.get("volatility_60s", 0.01)
        volume_ratio = features.get("volume_ratio", 1.0)
        regime = self.regime_detector.detect_regime(
            price_history, volatility * 100, volume_ratio
        )

        # 🔥 STEP 2: Multi-timeframe confluence with 6-layer validation
        (
            has_confluence,
            direction,
            confluence_strength,
            confluence_metadata,
        ) = self.check_multi_timeframe_confluence(features, regime=regime)

        if not has_confluence:
            # No confluence = skip this symbol
            reason = confluence_metadata.get("reason", "no_confluence")
            logger.info(
                f"🚫 [CONFLUENCE FAILED] {state.symbol} | Reason: {reason} | "
                f"Regime: {regime} | "
                f"Volume: {confluence_metadata.get('volume_ratio', 0):.2f}x | "
                f"OB: {confluence_metadata.get('ob_imbalance', 0):.3f} | "
                f"Bullish: {confluence_metadata.get('bullish_count', 0)}/{confluence_metadata.get('total_timeframes', 0)} | "
                f"Bearish: {confluence_metadata.get('bearish_count', 0)}/{confluence_metadata.get('total_timeframes', 0)}"
            )
            return (
                0.0,
                "neutral",
                {"reason": reason, "confluence_metadata": confluence_metadata},
            )

        # 🔥 STEP 3: ADAPTIVE confluence strength threshold (regime-aware)
        # Different regimes require different signal quality
        if regime == "trending":
            # Higher threshold for trending (avoid false breakouts)
            min_confluence_strength = 0.0010  # 0.10% = 2.5% capital @ 25x
        elif regime == "breakout":
            # Lower threshold for breakout (capture fast moves)
            min_confluence_strength = 0.0006  # 0.06% = 1.5% capital @ 25x
        elif regime == "volatile":
            # Highest threshold for volatile (maximum safety)
            min_confluence_strength = 0.0015  # 0.15% = 3.75% capital @ 25x
        else:  # ranging
            # Balanced threshold
            min_confluence_strength = 0.0008  # 0.08% = 2.0% capital @ 25x

        if confluence_strength < min_confluence_strength:
            return (
                0.0,
                "neutral",
                {
                    "reason": "weak_confluence_for_regime",
                    "regime": regime,
                    "strength": confluence_strength,
                    "required": min_confluence_strength,
                },
            )

        # 🔥 STEP 4: FEE-ADJUSTED FILTER (adaptive per regime)
        leverage = 25  # From env
        expected_capital_return = confluence_strength * leverage
        fee_cost = 0.0004  # 0.04% round-trip maker fees

        # Adaptive fee multiplier per regime
        if regime == "breakout":
            min_fee_multiplier = 1.5  # Lower bar for fast moves
        elif regime == "volatile":
            min_fee_multiplier = 3.0  # Higher bar for safety
        else:
            min_fee_multiplier = 2.0  # Standard: 2x fees

        min_expected_return = fee_cost * min_fee_multiplier

        if expected_capital_return < min_expected_return:
            return (
                0.0,
                "neutral",
                {
                    "reason": "profit_below_fees",
                    "regime": regime,
                    "expected": expected_capital_return,
                    "required": min_expected_return,
                },
            )

        # 🔥 STEP 5: Volume already validated in confluence check (Layer 2)
        # Just extract for metadata
        volume_ratio = confluence_metadata.get("volume_ratio", 1.0)

        # 4. Base momentum score (Sharpe-like)
        return_15s = features.get("return_15s", 0.0)
        volatility_60s = features.get("volatility_60s", 1.0)

        momentum_score = return_15s / volatility_60s if volatility_60s > 1e-6 else 0.0

        # 5. Order book imbalance
        ob_imbalance = features.get("ob_imbalance", 0.0)

        # 6. Volatility factor (ULTRA-SHORT-TERM optimized)
        # For scalping, we want slightly lower volatility (easier to capture small moves)
        volatility_30s = features.get("volatility_30s", 0.0)
        optimal_vol = 0.0015  # 0.15% volatility = sweet spot for scalping
        if volatility_30s > 0:
            vol_ratio = min(volatility_30s / optimal_vol, optimal_vol / volatility_30s)
            volatility_score = vol_ratio
        else:
            volatility_score = 0.0

        # 7. Liquidity score (STRICT: Need tight spreads for quality)
        spread_bps = features.get("spread_bps", 100.0)
        if spread_bps > 30.0:  # Skip if spread > 30 bps (want tighter spreads!)
            return 0.0, "neutral", {"reason": "wide_spread"}
        spread_score = max(0, 1 - spread_bps / 30.0)

        # 8. Momentum threshold (STRICT: Need strong momentum!)
        # For quality trades, need meaningful price movement
        return_5s = features.get("return_5s", 0.0)
        if (
            abs(return_5s) < 0.0012 and abs(return_15s) < 0.0018
        ):  # STRICTER: Need even stronger momentum!
            return 0.0, "neutral", {"reason": "weak_momentum"}

        # 9. Funding rate bias (EXPLOIT FUNDING!)
        funding_rate = features.get("funding_rate", 0.0)
        funding_bias = 0.0
        if direction == "long" and funding_rate < 0:  # Longs get paid
            funding_bias = 0.2  # Boost long score
        elif direction == "short" and funding_rate > 0:  # Shorts get paid
            funding_bias = 0.2  # Boost short score

        # 10. TECHNICAL INDICATORS (RSI, MACD, Bollinger, EMA, VWAP)
        prices = (
            np.array([p for _, p in state.price_history])
            if state.price_history
            else np.array([])
        )
        indicator_scores = {}
        indicator_confluence = []

        if len(prices) >= 20:
            # Calculate RSI
            rsi = self.technical_indicators.calculate_rsi(prices, period=14)
            if direction == "long":
                rsi_score = (
                    1.0 if rsi < 30 else (0.5 if rsi < 50 else 0.0)
                )  # Oversold = bullish
            else:  # short
                rsi_score = (
                    1.0 if rsi > 70 else (0.5 if rsi > 50 else 0.0)
                )  # Overbought = bearish
            indicator_scores["rsi"] = rsi_score
            if rsi_score > 0.5:
                indicator_confluence.append("rsi")

            # Calculate MACD
            macd_data = self.technical_indicators.calculate_macd(
                prices, fast_period=3, slow_period=7, signal_period=2
            )
            if direction == "long":
                macd_score = 1.0 if macd_data["is_bullish"] else 0.0
            else:  # short
                macd_score = 1.0 if macd_data["is_bearish"] else 0.0
            indicator_scores["macd"] = macd_score
            if macd_score > 0.5:
                indicator_confluence.append("macd")

            # Calculate Bollinger Bands
            bb_data = self.technical_indicators.calculate_bollinger_bands(
                prices, period=20, std_dev=2.0
            )
            current_price = state.last_price
            if direction == "long":
                # Buy when price touches lower band (oversold)
                bb_score = (
                    1.0
                    if current_price <= bb_data["lower_band"] * 1.001
                    else (0.5 if current_price < bb_data["middle_band"] else 0.0)
                )
            else:  # short
                # Sell when price touches upper band (overbought)
                bb_score = (
                    1.0
                    if current_price >= bb_data["upper_band"] * 0.999
                    else (0.5 if current_price > bb_data["middle_band"] else 0.0)
                )
            indicator_scores["bollinger"] = bb_score
            if bb_score > 0.5:
                indicator_confluence.append("bollinger")

            # Calculate EMA Crossovers
            ema_data = self.technical_indicators.calculate_ema_crossovers(
                prices, fast_period=3, slow_period=7
            )
            if direction == "long":
                ema_score = 1.0 if ema_data["is_bullish"] else 0.0
            else:  # short
                ema_score = 1.0 if ema_data["is_bearish"] else 0.0
            indicator_scores["ema"] = ema_score
            if ema_score > 0.5:
                indicator_confluence.append("ema")

            # Calculate VWAP
            vwap_data = self.technical_indicators.calculate_vwap(prices, period=20)
            if direction == "long":
                vwap_score = (
                    1.0 if vwap_data["is_above"] else 0.0
                )  # Price above VWAP = bullish
            else:  # short
                vwap_score = (
                    1.0 if vwap_data["is_below"] else 0.0
                )  # Price below VWAP = bearish
            indicator_scores["vwap"] = vwap_score
            if vwap_score > 0.5:
                indicator_confluence.append("vwap")
        else:
            # Not enough data for technical indicators
            indicator_scores = {
                "rsi": 0.0,
                "macd": 0.0,
                "bollinger": 0.0,
                "ema": 0.0,
                "vwap": 0.0,
            }

        # 11. Multi-Indicator Confluence Check
        # Require at least 4 out of 6 indicators to agree (momentum + 5 technical indicators)
        momentum_agrees = (
            (momentum_score > 0) if direction == "long" else (momentum_score < 0)
        )
        if momentum_agrees:
            indicator_confluence.append("momentum")

        total_indicators = 6  # momentum + 5 technical indicators
        confluence_count = len(indicator_confluence)
        required_confluence = 3  # At least 3 out of 6 must agree (more trades)

        if confluence_count < required_confluence:
            logger.debug(
                "trade_rejected_insufficient_confluence",
                symbol=state.symbol,
                confluence_count=confluence_count,
                required=required_confluence,
                indicators=indicator_confluence,
            )
            return (
                0.0,
                "neutral",
                {
                    "reason": "insufficient_indicator_confluence",
                    "confluence_count": confluence_count,
                },
            )

        # Combine all scores with new technical indicators
        composite_score = (
            self.momentum_weight * momentum_score * 0.20
            + indicator_scores.get("rsi", 0.0) * 0.15
            + indicator_scores.get("macd", 0.0) * 0.15
            + indicator_scores.get("bollinger", 0.0) * 0.10
            + indicator_scores.get("ema", 0.0) * 0.10
            + indicator_scores.get("vwap", 0.0) * 0.10
            + self.imbalance_weight * ob_imbalance * 0.15
            + self.volatility_weight * volatility_score * 0.05
            + self.liquidity_weight * spread_score * 0.05
            + funding_bias * 0.05
        )

        # Normalize composite score to 0-100 range
        composite_score_normalized = np.clip(composite_score * 100, 0, 100)

        # Combine all scores (legacy base_score for backward compatibility)
        base_score = (
            self.momentum_weight * momentum_score
            + self.imbalance_weight * ob_imbalance
            + self.volatility_weight * volatility_score
            + self.liquidity_weight * spread_score
            + funding_bias
        )

        # 12. Boost by confluence strength
        base_score *= 1 + confluence_strength * 100  # AMPLIFY confluence impact!

        # 13. Boost by volume ratio
        base_score *= 1 + (volume_ratio - 1) * 0.5  # 50% of excess volume

        # 14. Boost by technical indicator confluence
        if len(prices) >= 20:
            indicator_confluence_bonus = (
                confluence_count / total_indicators
            ) * 0.5  # Up to 50% bonus
            base_score *= 1 + indicator_confluence_bonus

        # 15. UCB bandit overlay
        bandit_score = state.get_ucb_score(1000, c=self.ucb_exploration)
        if np.isfinite(bandit_score):
            bandit_norm = np.clip(bandit_score, -100, 100) / 100.0
        else:
            bandit_norm = 1.0

        # Combined final score (use composite score if available, otherwise base_score)
        if len(prices) >= 20:
            # Use composite score with technical indicators
            final_score = (
                self.bandit_alpha * (composite_score_normalized / 100.0)
                + (1 - self.bandit_alpha) * bandit_norm
            )
        else:
            # Fallback to base_score if not enough data
            final_score = (
                self.bandit_alpha * np.clip(base_score, -5, 5) / 5.0
                + (1 - self.bandit_alpha) * bandit_norm
            )

        # PRO TRADER QUALITY CHECK: Analyze market structure and trade quality

        if len(prices) >= 30:
            # 1. Detect support/resistance
            (
                support_levels,
                resistance_levels,
            ) = self.pro_indicators.detect_support_resistance(prices)
            current_price = state.last_price

            # Check if near S/R
            near_sr = is_near_level(current_price, support_levels + resistance_levels)

            # 2. Analyze market structure
            market_structure = self.pro_indicators.analyze_market_structure(prices)

            # 3. Calculate expected R:R (simplified - use TP/SL from position manager)
            # For 50x leverage: 8% capital stop = 0.16% price, 20% capital TP = 0.4% price
            if direction == "long":
                estimated_stop = current_price * 0.9984  # 0.16% below
                estimated_tp = current_price * 1.004  # 0.4% above
            else:  # short
                estimated_stop = current_price * 1.0016
                estimated_tp = current_price * 0.996

            rr_calc = self.pro_indicators.calculate_risk_reward(
                current_price, estimated_stop, estimated_tp, direction
            )

            # 4. Add technical indicator data to features for trade grading
            enhanced_features = features.copy()
            if len(prices) >= 20:
                rsi = self.technical_indicators.calculate_rsi(prices, period=14)
                macd_data = self.technical_indicators.calculate_macd(
                    prices, fast_period=3, slow_period=7, signal_period=2
                )
                bb_data = self.technical_indicators.calculate_bollinger_bands(
                    prices, period=20, std_dev=2.0
                )
                ema_data = self.technical_indicators.calculate_ema_crossovers(
                    prices, fast_period=3, slow_period=7
                )
                vwap_data = self.technical_indicators.calculate_vwap(prices, period=20)

                enhanced_features.update(
                    {
                        "rsi": rsi,
                        "macd_bullish": macd_data["is_bullish"],
                        "macd_bearish": macd_data["is_bearish"],
                        "bb_extreme": (current_price <= bb_data["lower_band"] * 1.001)
                        or (current_price >= bb_data["upper_band"] * 0.999),
                        "ema_aligned": (direction == "long" and ema_data["is_bullish"])
                        or (direction == "short" and ema_data["is_bearish"]),
                        "vwap_favorable": (
                            direction == "long" and vwap_data["is_above"]
                        )
                        or (direction == "short" and vwap_data["is_below"]),
                    }
                )

            # 5. Grade the trade (A/B/C/D/F) - now with 10 factors (5+ required for A-grade)
            trade_grade = self.pro_indicators.grade_trade_quality(
                enhanced_features,
                direction,
                rr_calc["risk_reward_ratio"],
                market_structure,
                near_sr,
            )

            # 🚨 LOGGING: Log all indicator values for debugging
            if len(prices) >= 20:
                logger.debug(
                    f"📊 [INDICATORS] {state.symbol} | "
                    f"RSI: {enhanced_features.get('rsi', 50):.1f} | "
                    f"MACD: {'bullish' if enhanced_features.get('macd_bullish') else 'bearish' if enhanced_features.get('macd_bearish') else 'neutral'} | "
                    f"BB: {'extreme' if enhanced_features.get('bb_extreme') else 'normal'} | "
                    f"EMA: {'aligned' if enhanced_features.get('ema_aligned') else 'not aligned'} | "
                    f"VWAP: {'favorable' if enhanced_features.get('vwap_favorable') else 'not favorable'} | "
                    f"Confluence: {confluence_count}/{total_indicators} indicators agree"
                )

            # 🚨 CRITICAL: Check if trading AGAINST market structure - INSTANT REJECTION!
            # This is the #1 cause of losses - NEVER trade against the trend!
            if (
                direction == "long" and market_structure["structure"] == "downtrend"
            ) or (direction == "short" and market_structure["structure"] == "uptrend"):
                logger.debug(
                    "trade_rejected_against_structure",
                    symbol=state.symbol,
                    direction=direction,
                    structure=market_structure["structure"],
                    reason="NEVER trade against market structure!",
                )
                return (
                    0.0,
                    "neutral",
                    {
                        "reason": "against_structure",
                        "structure": market_structure["structure"],
                    },
                )

            # PRO RULE: ONLY A-grade trades! (5+ factors required out of 10)
            # B-grade and below are causing too many losses!
            if trade_grade["grade"] != "A":
                logger.debug(
                    "trade_rejected_not_A_grade",
                    symbol=state.symbol,
                    grade=trade_grade["grade"],
                    factors=trade_grade["factors_met"],
                    reasons=trade_grade["reasons"],
                )
                return (
                    0.0,
                    "neutral",
                    {"reason": "not_A_grade", "grade": trade_grade["grade"]},
                )

            # A-grade ONLY = maximum win rate!
            final_score *= 2.0  # 100% bonus for A-grade setups!

            logger.debug(
                "trade_quality_check",
                symbol=state.symbol,
                grade=trade_grade["grade"],
                score=trade_grade["score"],
                structure=market_structure["structure"],
                near_sr=near_sr,
                rr=f"{rr_calc['risk_reward_ratio']:.1f}:1",
            )

        # ULTRA-STRICT: Only take PERFECT signals (A-grade + very high score)
        if (
            final_score < 1.5
        ):  # STRICTER: Even higher quality bar for 80%+ win rate (25% stricter)
            return 0.0, "neutral", {"reason": "low_score"}

        # Build metadata with trade quality info for loss tracking
        metadata = {
            "regime": regime,
            "confluence": confluence_strength,
            "volume_ratio": volume_ratio,
            "funding_rate": funding_rate,
        }

        # Add pro trader metadata if available
        if len(prices) >= 30:
            metadata.update(
                {
                    "grade": trade_grade["grade"],
                    "market_structure": market_structure["structure"],
                    "near_sr": near_sr,
                    "rr_ratio": rr_calc["risk_reward_ratio"],
                }
            )
        else:
            # Fallback if not enough data
            metadata.update(
                {
                    "grade": "C",  # Default to C grade
                    "market_structure": "unknown",
                    "near_sr": False,
                    "rr_ratio": 2.5,  # Default R:R
                }
            )

        return final_score, direction, metadata

    def calculate_smart_position_size(
        self,
        base_size: float,
        signal_strength: float,
        regime: str,
        volatility: float,
    ) -> float:
        """
        Calculate position size based on signal quality and market regime.

        Args:
            base_size: Base position size (10% of capital)
            signal_strength: Signal strength (0-1)
            regime: Market regime
            volatility: Current volatility

        Returns:
            Adjusted position size
        """
        # Start with base size
        size = base_size

        # 1. Scale by signal strength
        if signal_strength > 0.8:
            size *= 1.3  # 30% larger for very strong signals
        elif signal_strength > 0.7:
            size *= 1.15  # 15% larger for strong signals
        elif signal_strength < 0.6:
            size *= 0.7  # 30% smaller for weak signals

        # 2. Adjust for regime
        regime_params = self.regime_detector.get_regime_parameters(regime)
        size *= regime_params["position_size_multiplier"]

        # 3. Reduce in high volatility (risk management)
        if volatility > 0.03:  # > 3% volatility
            size *= 0.7
        elif volatility > 0.05:  # > 5% volatility
            size *= 0.5

        # Cap at 15% max, 3% min
        size = np.clip(size, base_size * 0.3, base_size * 1.5)

        return size

    def rank_symbols_enhanced(
        self,
        state_manager: MultiSymbolStateManager,
        top_k: int = 10,
    ) -> list[dict]:
        """
        Enhanced ranking with all improvements.

        Returns:
            List of dicts with symbol, score, side, metadata, position_size_multiplier
        """
        all_features = state_manager.get_all_features()

        logger.debug(f"🔍 Analyzing {len(all_features)} symbols for ranking")

        # Get BTC return for correlation check
        btc_features = all_features.get("BTCUSDT", {})
        btc_return = btc_features.get("return_5min", 0.0)

        scored_symbols = []
        skip_reasons = {
            # OLD reasons (legacy)
            "no_confluence": 0,
            "weak_confluence": 0,
            "low_volume": 0,
            "wide_spread": 0,
            "weak_momentum": 0,
            "low_score": 0,
            # NEW confluence validation reasons (6-layer system)
            "no_volume_confirmation": 0,
            "orderbook_conflict": 0,
            "insufficient_agreement": 0,
            "weak_confluence_for_regime": 0,
            "profit_below_fees": 0,
            "insufficient_indicator_confluence": 0,
            "against_structure": 0,
            "not_A_grade": 0,
        }

        for symbol, features in all_features.items():
            state = state_manager.get_state(symbol)
            if not state:
                continue

            # Compute enhanced score
            score, direction, metadata = self.compute_enhanced_score(
                state, features, btc_return
            )

            if score <= 0:
                # Track why symbols are being skipped
                reason = metadata.get("reason", "low_score")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                continue

            # Calculate position size multiplier
            volatility = features.get("volatility_60s", 0.01)
            size_multiplier = self.calculate_smart_position_size(
                base_size=1.0,  # Will be multiplied by actual capital later
                signal_strength=score,
                regime=metadata["regime"],
                volatility=volatility,
            )

            scored_symbols.append(
                {
                    "symbol": symbol,
                    "score": score,
                    "predicted_side": direction,
                    "position_size_multiplier": size_multiplier,
                    "regime": metadata["regime"],
                    "confluence": metadata["confluence"],
                    "volume_ratio": metadata["volume_ratio"],
                    "funding_rate": metadata["funding_rate"],
                    "volatility": volatility,
                    # Pro trader metadata for loss tracking
                    "grade": metadata.get("grade", "C"),
                    "market_structure": metadata.get("market_structure", "unknown"),
                    "near_sr": metadata.get("near_sr", False),
                    "rr_ratio": metadata.get("rr_ratio", 2.5),
                }
            )

        # Sort by score
        scored_symbols.sort(key=lambda x: x["score"], reverse=True)

        # Correlation filter: Limit BTC-correlated positions
        # But rank ALL symbols first, then filter (not just top_k)
        if btc_return != 0:
            # Apply correlation filter but keep all symbols ranked
            filtered = self._apply_correlation_filter(
                scored_symbols, all_features, len(scored_symbols)
            )
        else:
            filtered = scored_symbols  # Return ALL ranked symbols, not just top_k

        # Return top_k only at the end (after ranking all)
        return filtered[:top_k] if top_k < len(filtered) else filtered

        logger.info(
            "enhanced_ranking_complete",
            total_analyzed=len(all_features),
            scored=len(scored_symbols),
            after_filters=len(filtered),
            skip_reasons=skip_reasons,
        )

        # Return top_k (but we ranked ALL symbols first)
        result = filtered[:top_k] if top_k < len(filtered) else filtered

        if result:
            logger.info(
                "top_ranked",
                total_ranked=len(scored_symbols),
                returned=len(result),
                top_3=[
                    (s["symbol"], f"{s['score']:.3f}", s["regime"]) for s in result[:3]
                ],
            )

        return result

    def _apply_correlation_filter(
        self,
        scored_symbols: list[dict],
        all_features: dict,
        top_k: int,
    ) -> list[dict]:
        """
        Apply correlation filter to ensure diversification.

        Limits highly BTC-correlated positions.
        """
        btc_return_5min = all_features.get("BTCUSDT", {}).get("return_5min", 0)

        selected = []
        btc_correlated_count = 0
        max_btc_correlated = top_k // 2  # Max 50% BTC-correlated

        for candidate in scored_symbols:
            if len(selected) >= top_k:
                break

            symbol = candidate["symbol"]

            # Check BTC correlation
            symbol_return = all_features.get(symbol, {}).get("return_5min", 0)

            if btc_return_5min != 0 and symbol_return != 0:
                # Simple correlation: same direction?
                is_correlated = (btc_return_5min * symbol_return) > 0

                if is_correlated and symbol != "BTCUSDT":
                    if btc_correlated_count >= max_btc_correlated:
                        logger.debug(
                            f"Skipping {symbol} - too many BTC-correlated positions"
                        )
                        continue
                    btc_correlated_count += 1

            selected.append(candidate)

        return selected
