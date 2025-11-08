# Strategy Rationales

Each strategy has a specific purpose and market condition it excels in.

---

## Scalping Strategies

### 1. Scalper_HighFreq_TightStop

**Rationale:** Exploit small price movements with high frequency. Tight stops protect capital, tight TPs lock in micro-profits before reversals.

**Parameters:**
- Entry Threshold: 1.0
- Stop Loss: 25% capital
- Take Profit: 8% capital
- Trailing: 1.5%
- Volume Ratio: 1.5x
- Confluence: 3/9 indicators

---

### 2. Scalper_MomentumRider

**Rationale:** Ride short-term momentum bursts. Requires stronger volume confirmation to avoid fakeouts.

**Parameters:**
- Entry Threshold: 1.2
- Stop Loss: 30% capital
- Take Profit: 10% capital
- Trailing: 2.0%
- Volume Ratio: 2.5x
- Confluence: 3/9 indicators

---

### 3. Scalper_VolumeSpike

**Rationale:** Enter on volume spikes which often precede price moves. Quick TP to capture the initial surge.

**Parameters:**
- Entry Threshold: 1.0
- Stop Loss: 30% capital
- Take Profit: 12% capital
- Trailing: 2.0%
- Volume Ratio: 3.0x
- Confluence: 3/9 indicators

---

### 4. Scalper_QuickFlip

**Rationale:** Ultra-fast entries/exits. Wider stop for noise tolerance, but tight TP to flip positions quickly.

**Parameters:**
- Entry Threshold: 0.8
- Stop Loss: 35% capital
- Take Profit: 8% capital
- Trailing: 1.0%
- Volume Ratio: 1.5x
- Confluence: 3/9 indicators

---

### 5. Scalper_BreakoutSniper

**Rationale:** Wait for strong confluence before entering, then scalp the breakout. Medium TP to capture full move.

**Parameters:**
- Entry Threshold: 1.5
- Stop Loss: 30% capital
- Take Profit: 14% capital
- Trailing: 2.0%
- Volume Ratio: 2.5x
- Confluence: 4/9 indicators

---

### 6. Scalper_RangeTrader

**Rationale:** Exploit range-bound markets. Tight stops/TPs for quick profits in consolidation zones.

**Parameters:**
- Entry Threshold: 1.0
- Stop Loss: 25% capital
- Take Profit: 10% capital
- Trailing: 1.5%
- Volume Ratio: 1.8x
- Confluence: 3/9 indicators

---

### 7. Scalper_NewsFader

**Rationale:** Fade initial overreactions. Lower threshold to catch reversals, medium stops for volatility.

**Parameters:**
- Entry Threshold: 1.0
- Stop Loss: 40% capital
- Take Profit: 12% capital
- Trailing: 2.5%
- Volume Ratio: 2.0x
- Confluence: 3/9 indicators

---

### 8. Scalper_MeanReversion

**Rationale:** Buy dips/sell rips expecting mean reversion. Quick TP before trend resumes.

**Parameters:**
- Entry Threshold: 1.2
- Stop Loss: 35% capital
- Take Profit: 10% capital
- Trailing: 2.0%
- Volume Ratio: 1.8x
- Confluence: 3/9 indicators

---

## Swing Strategies

### 9. Swing_TrendFollower

**Rationale:** Follow established trends with medium-term holds. Higher TP/trailing to capture larger moves.

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 45% capital
- Take Profit: 20% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 10. Swing_Breakout

**Rationale:** Enter on confirmed breakouts from consolidation. Wide stops to avoid stop hunts, high TP for full move.

**Parameters:**
- Entry Threshold: 2.0
- Stop Loss: 50% capital
- Take Profit: 25% capital
- Trailing: 4.0%
- Volume Ratio: 2.5x
- Confluence: 5/9 indicators

---

### 11. Swing_PullbackEntry

**Rationale:** Enter on pullbacks in uptrends. Lower threshold to catch dips, but requires trend confirmation.

**Parameters:**
- Entry Threshold: 1.5
- Stop Loss: 45% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 12. Swing_PatientTrader

**Rationale:** Wait for perfect setups with very high confluence. Lower frequency but higher quality trades.

**Parameters:**
- Entry Threshold: 2.5
- Stop Loss: 50% capital
- Take Profit: 22% capital
- Trailing: 3.5%
- Volume Ratio: 2.5x
- Confluence: 5/9 indicators

---

### 13. Swing_MomentumSurfer

**Rationale:** Ride momentum waves. Medium entry threshold, wide trailing to let winners run.

**Parameters:**
- Entry Threshold: 1.7
- Stop Loss: 45% capital
- Take Profit: 20% capital
- Trailing: 4.0%
- Volume Ratio: 2.2x
- Confluence: 4/9 indicators

---

### 14. Swing_VolatilityExpansion

**Rationale:** Enter when volatility expands (Bollinger squeeze breakouts). Wide stops for volatility.

**Parameters:**
- Entry Threshold: 1.6
- Stop Loss: 55% capital
- Take Profit: 24% capital
- Trailing: 4.0%
- Volume Ratio: 2.5x
- Confluence: 4/9 indicators

---

### 15. Swing_SupportResistance

**Rationale:** Trade bounces from key S/R levels. Medium stops, medium TPs for S/R range.

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 45% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 16. Swing_TrendReversal

**Rationale:** Catch early trend reversals. Higher threshold for confirmation, wide TP to capture new trend.

**Parameters:**
- Entry Threshold: 2.2
- Stop Loss: 50% capital
- Take Profit: 26% capital
- Trailing: 4.0%
- Volume Ratio: 2.5x
- Confluence: 5/9 indicators

---

## Balanced Strategies

### 17. Balanced_AllRounder

**Rationale:** Balanced approach for all market conditions. Medium everything for consistent performance.

**Parameters:**
- Entry Threshold: 1.7
- Stop Loss: 45% capital
- Take Profit: 16% capital
- Trailing: 2.5%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 18. Balanced_RiskManaged

**Rationale:** Focus on capital preservation. Tighter stops, moderate TPs, high confluence for quality.

**Parameters:**
- Entry Threshold: 2.0
- Stop Loss: 40% capital
- Take Profit: 16% capital
- Trailing: 2.5%
- Volume Ratio: 2.2x
- Confluence: 5/9 indicators

---

### 19. Balanced_GoldenRatio

**Rationale:** Uses optimal risk/reward ratios (2:1). Balanced stops/TPs for consistent profitability.

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 40% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 20. Balanced_VolumePrice

**Rationale:** Combines volume and price analysis. Requires strong volume confirmation for entries.

**Parameters:**
- Entry Threshold: 1.7
- Stop Loss: 45% capital
- Take Profit: 16% capital
- Trailing: 2.5%
- Volume Ratio: 2.5x
- Confluence: 4/9 indicators

---

### 21. Balanced_AdaptiveTrader

**Rationale:** Adapts to market conditions. Medium flexibility in all parameters.

**Parameters:**
- Entry Threshold: 1.6
- Stop Loss: 45% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 22. Balanced_QualityOverQuantity

**Rationale:** Prioritizes trade quality. Higher threshold and confluence, moderate frequency.

**Parameters:**
- Entry Threshold: 2.0
- Stop Loss: 45% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.2x
- Confluence: 5/9 indicators

---

### 23. Balanced_SteadyEddie

**Rationale:** Consistent, steady profits. Avoids extremes, targets reliable 1-2% per day.

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 45% capital
- Take Profit: 16% capital
- Trailing: 2.5%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 24. Balanced_SmartMoney

**Rationale:** Follows 'smart money' - requires high volume + strong confluence to confirm institutional flow.

**Parameters:**
- Entry Threshold: 1.9
- Stop Loss: 45% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.8x
- Confluence: 4/9 indicators

---

## Aggressive Strategies

### 25. Aggressive_HighRisk_HighReward

**Rationale:** Maximum risk for maximum reward. Wide stops to weather volatility, very high TPs for big wins.

**Parameters:**
- Entry Threshold: 1.4
- Stop Loss: 60% capital
- Take Profit: 30% capital
- Trailing: 5.0%
- Volume Ratio: 1.8x
- Confluence: 3/9 indicators

---

### 26. Aggressive_MomentumChaser

**Rationale:** Chase strong momentum. Lower threshold for quick entries, wide trailing to ride trends.

**Parameters:**
- Entry Threshold: 1.3
- Stop Loss: 50% capital
- Take Profit: 24% capital
- Trailing: 5.0%
- Volume Ratio: 2.0x
- Confluence: 3/9 indicators

---

### 27. Aggressive_VolatilityHunter

**Rationale:** Seeks high volatility for explosive moves. Very wide stops for wild swings, huge TPs.

**Parameters:**
- Entry Threshold: 1.5
- Stop Loss: 65% capital
- Take Profit: 32% capital
- Trailing: 6.0%
- Volume Ratio: 2.5x
- Confluence: 3/9 indicators

---

### 28. Aggressive_BreakoutBlitz

**Rationale:** Aggressive breakout entries with lower threshold. Wide stops/TPs for full breakout capture.

**Parameters:**
- Entry Threshold: 1.4
- Stop Loss: 55% capital
- Take Profit: 26% capital
- Trailing: 4.0%
- Volume Ratio: 2.5x
- Confluence: 4/9 indicators

---

### 29. Aggressive_TrendExplosion

**Rationale:** Enter early in trend formations. Medium threshold, wide TPs to capture full trend.

**Parameters:**
- Entry Threshold: 1.6
- Stop Loss: 50% capital
- Take Profit: 28% capital
- Trailing: 5.0%
- Volume Ratio: 2.2x
- Confluence: 4/9 indicators

---

### 30. Aggressive_PumpCatcher

**Rationale:** Catch pump beginnings with low threshold + high volume. Quick TP before dump.

**Parameters:**
- Entry Threshold: 1.2
- Stop Loss: 45% capital
- Take Profit: 22% capital
- Trailing: 3.0%
- Volume Ratio: 3.0x
- Confluence: 3/9 indicators

---

### 31. Aggressive_ParabolicRider

**Rationale:** Ride parabolic moves. Lower threshold for early entry, very wide trailing to stay in.

**Parameters:**
- Entry Threshold: 1.4
- Stop Loss: 55% capital
- Take Profit: 28% capital
- Trailing: 6.0%
- Volume Ratio: 2.5x
- Confluence: 3/9 indicators

---

### 32. Aggressive_AllIn

**Rationale:** Go all-in on strong signals. High confluence requirement, but massive TPs when right.

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 60% capital
- Take Profit: 35% capital
- Trailing: 5.0%
- Volume Ratio: 2.5x
- Confluence: 5/9 indicators

---

## Contrarian Strategies

### 33. Contrarian_OverboughtFader

**Rationale:** Fade overbought conditions (RSI >70). Counter-trend, needs wide stops for extended moves.

**Parameters:**
- Entry Threshold: 1.6
- Stop Loss: 50% capital
- Take Profit: 16% capital
- Trailing: 2.5%
- Volume Ratio: 1.8x
- Confluence: 4/9 indicators

---

### 34. Contrarian_PanicBuyer

**Rationale:** Buy panic selloffs. Wide stops for continued panic, medium TP for bounce.

**Parameters:**
- Entry Threshold: 1.5
- Stop Loss: 55% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.5x
- Confluence: 4/9 indicators

---

### 35. Contrarian_ExhaustionTrader

**Rationale:** Trade trend exhaustion signals. High confluence for reversal confirmation.

**Parameters:**
- Entry Threshold: 2.0
- Stop Loss: 50% capital
- Take Profit: 20% capital
- Trailing: 3.5%
- Volume Ratio: 2.2x
- Confluence: 5/9 indicators

---

### 36. Contrarian_DivergenceHunter

**Rationale:** Trade RSI/MACD divergences. Medium threshold, wide stops for divergence resolution.

**Parameters:**
- Entry Threshold: 1.7
- Stop Loss: 50% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 37. Contrarian_VolumeAnomaly

**Rationale:** Fade volume anomalies (unusual volume without price move = trap). Quick TPs.

**Parameters:**
- Entry Threshold: 1.4
- Stop Loss: 45% capital
- Take Profit: 14% capital
- Trailing: 2.5%
- Volume Ratio: 3.0x
- Confluence: 3/9 indicators

---

### 38. Contrarian_SqueezeBreaker

**Rationale:** Fade false breakouts from squeezes. Medium stops, quick TPs before re-squeeze.

**Parameters:**
- Entry Threshold: 1.6
- Stop Loss: 45% capital
- Take Profit: 14% capital
- Trailing: 2.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 39. Contrarian_SentimentFader

**Rationale:** Fade extreme sentiment. When everyone is bullish, short (and vice versa).

**Parameters:**
- Entry Threshold: 1.8
- Stop Loss: 55% capital
- Take Profit: 20% capital
- Trailing: 4.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

### 40. Contrarian_MeanReversionExtreme

**Rationale:** Trade extreme deviations from mean (>2 std dev). Expect snapback, wide stops for more deviation.

**Parameters:**
- Entry Threshold: 1.9
- Stop Loss: 60% capital
- Take Profit: 18% capital
- Trailing: 3.0%
- Volume Ratio: 2.0x
- Confluence: 4/9 indicators

---

