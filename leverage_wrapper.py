"""Quick wrapper to add leverage-aware calculations to existing strategies."""

from institutional_leverage import LeverageManager
from typing import Optional
from dataclasses import dataclass
import asyncio


@dataclass
class LeverageAdjustedPrices:
    """Container for leverage-adjusted TP/SL prices."""
    tp_price: float
    sl_price: float
    leverage: int
    tp_roi_pct: float
    sl_roi_pct: float


async def adjust_tp_sl_for_leverage(
    leverage_manager: LeverageManager,
    symbol: str,
    side: str,
    entry_price: float,
    tp_price_base: float,  # Original TP from strategy
    sl_price_base: float,  # Original SL from strategy
    atr: float = 0,
) -> LeverageAdjustedPrices:
    """
    Adjust TP/SL prices to account for leverage.
    
    Strategy gives us prices based on % moves, but we need to adjust for ROI.
    
    Args:
        leverage_manager: LeverageManager instance
        symbol: Trading symbol
        side: "long" or "short"
        entry_price: Entry price
        tp_price_base: Original TP price from strategy
        sl_price_base: Original SL price from strategy
        atr: ATR value for ATR-based calculations
    
    Returns:
        LeverageAdjustedPrices with corrected prices
    """
    # Get leverage for symbol
    leverage = await leverage_manager.get_symbol_leverage(symbol)
    
    # Target ROI (2.5% profit, 2% loss)
    target_tp_roi = 0.025  # 2.5%
    max_sl_loss = 0.02     # 2%
    
    # Calculate leverage-adjusted TP
    tp_price = await leverage_manager.calculate_tp_price(
        symbol=symbol,
        entry_price=entry_price,
        side=side,
        target_roi_pct=target_tp_roi,
        atr=atr,
        atr_multiplier=2.5,
    )
    
    # Calculate leverage-adjusted SL
    sl_price = await leverage_manager.calculate_sl_price(
        symbol=symbol,
        entry_price=entry_price,
        side=side,
        max_loss_roi_pct=max_sl_loss,
        atr=atr,
        atr_multiplier=1.5,
    )
    
    # Calculate actual ROI percentages
    if side == 'long':
        tp_roi_pct = ((tp_price - entry_price) / entry_price) * leverage * 100
        sl_roi_pct = ((sl_price - entry_price) / entry_price) * leverage * 100
    else:  # short
        tp_roi_pct = ((entry_price - tp_price) / entry_price) * leverage * 100
        sl_roi_pct = ((entry_price - sl_price) / entry_price) * leverage * 100
    
    return LeverageAdjustedPrices(
        tp_price=tp_price,
        sl_price=sl_price,
        leverage=leverage,
        tp_roi_pct=tp_roi_pct,
        sl_roi_pct=abs(sl_roi_pct),
    )

