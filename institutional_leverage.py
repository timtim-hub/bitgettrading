"""Leverage-aware TP/SL/Trailing calculation module."""

from typing import Dict, Tuple
import asyncio
from structlog import get_logger

logger = get_logger()


class LeverageManager:
    """
    Manages leverage-aware TP/SL calculations.
    
    Key Principle:
    - With N×leverage, a 1% price move = N% ROI on equity
    - To get X% ROI, we need X/N% price move
    - Example: 25× leverage, 2.5% ROI target → 0.1% price move needed
    """
    
    def __init__(self, rest_client, default_leverage: int = 25):
        """
        Initialize LeverageManager.
        
        Args:
            rest_client: Bitget REST API client
            default_leverage: Default leverage if unable to fetch (default: 25)
        """
        self.rest_client = rest_client
        self.default_leverage = default_leverage
        self.leverage_cache: Dict[str, int] = {}  # symbol → max leverage
        logger.info(f"✅ LeverageManager initialized | Default leverage: {default_leverage}x")
    
    async def get_symbol_leverage(self, symbol: str) -> int:
        """
        Get actual max leverage for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
        
        Returns:
            Max leverage for symbol (e.g., 25 or 10)
        """
        # Check cache first
        if symbol in self.leverage_cache:
            return self.leverage_cache[symbol]
        
        try:
            # Fetch from API
            symbol_info = await self.rest_client.get_symbol_info(symbol)
            
            if symbol_info and 'maxLeverage' in symbol_info:
                max_leverage = int(symbol_info['maxLeverage'])
                self.leverage_cache[symbol] = max_leverage
                logger.debug(f"📊 {symbol}: Max leverage = {max_leverage}x")
                return max_leverage
            else:
                logger.warning(f"⚠️ Could not fetch leverage for {symbol}, using default {self.default_leverage}x")
                return self.default_leverage
        
        except Exception as e:
            logger.warning(f"⚠️ Error fetching leverage for {symbol}: {e}, using default {self.default_leverage}x")
            return self.default_leverage
    
    async def calculate_tp_price(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        target_roi_pct: float,
        atr: float = 0,
        atr_multiplier: float = 2.5,
    ) -> float:
        """
        Calculate TP price based on leverage and target ROI.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            side: "long" or "short"
            target_roi_pct: Target ROI on equity (e.g., 0.025 for 2.5%)
            atr: ATR value (optional, for ATR-based TP)
            atr_multiplier: ATR multiplier (e.g., 2.5)
        
        Returns:
            TP price
        """
        leverage = await self.get_symbol_leverage(symbol)
        
        # Calculate required price move for target ROI
        # Formula: price_move_pct = target_roi / leverage
        price_move_pct = target_roi_pct / leverage
        
        # Calculate TP based on minimum ROI
        if side == 'long':
            tp_min = entry_price * (1 + price_move_pct)
        else:  # short
            tp_min = entry_price * (1 - price_move_pct)
        
        # 🚨 CRITICAL FIX: With leverage, always use ROI-based TP for consistent 2.5% ROI
        # ATR-based TP gives inconsistent results (sometimes 67% ROI!)
        # We want MINIMUM 2.5% ROI, not maximum profit
        tp_price = tp_min
        
        # Optional: If ATR is available, ensure TP is at least min ROI but not more than ATR target
        # This prevents both under-targeting AND over-targeting
        if atr > 0:
            if side == 'long':
                tp_atr = entry_price + (atr_multiplier * atr)
                # For LONG: Use the SMALLER TP (closer to entry = min profit)
                tp_price = min(tp_atr, tp_min)
            else:  # short
                tp_atr = entry_price - (atr_multiplier * atr)
                # For SHORT: Use the LARGER TP (closer to entry = min profit)
                tp_price = max(tp_atr, tp_min)
        
        # Log calculation
        tp_roi_actual = abs((tp_price - entry_price) / entry_price) * leverage * 100
        logger.debug(
            f"📊 TP Calc | {symbol} {side.upper()} | "
            f"Leverage: {leverage}x | Target ROI: {target_roi_pct*100:.1f}% | "
            f"Price move: {price_move_pct*100:.2f}% | "
            f"Entry: ${entry_price:.4f} → TP: ${tp_price:.4f} | "
            f"Actual ROI: {tp_roi_actual:.1f}%"
        )
        
        return tp_price
    
    async def calculate_sl_price(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        max_loss_roi_pct: float,
        atr: float = 0,
        atr_multiplier: float = 1.5,
    ) -> float:
        """
        Calculate SL price based on leverage and max loss ROI.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            side: "long" or "short"
            max_loss_roi_pct: Max acceptable loss ROI (e.g., 0.02 for 2%)
            atr: ATR value (optional, for ATR-based SL)
            atr_multiplier: ATR multiplier (e.g., 1.5)
        
        Returns:
            SL price
        """
        leverage = await self.get_symbol_leverage(symbol)
        
        # Calculate required price move for max loss
        price_move_pct = max_loss_roi_pct / leverage
        
        # Calculate SL based on max loss ROI
        if side == 'long':
            sl_min = entry_price * (1 - price_move_pct)
        else:  # short
            sl_min = entry_price * (1 + price_move_pct)
        
        # 🚨 CRITICAL FIX: With leverage, always use ROI-based SL for consistent 2% loss
        # ATR-based SL gives inconsistent results
        # We want MAXIMUM 2% loss, not minimum loss
        sl_price = sl_min
        
        # Optional: If ATR is available, ensure SL is at most 2% loss but not tighter than ATR
        # This prevents both over-stopping AND under-stopping
        if atr > 0:
            if side == 'long':
                sl_atr = entry_price - (atr_multiplier * atr)
                # For LONG: Use the LARGER SL (closer to entry = tighter stop)
                sl_price = max(sl_atr, sl_min)
            else:  # short
                sl_atr = entry_price + (atr_multiplier * atr)
                # For SHORT: Use the SMALLER SL (closer to entry = tighter stop)
                sl_price = min(sl_atr, sl_min)
        
        # Log calculation
        sl_roi_actual = abs((sl_price - entry_price) / entry_price) * leverage * 100
        logger.debug(
            f"🛑 SL Calc | {symbol} {side.upper()} | "
            f"Leverage: {leverage}x | Max Loss: {max_loss_roi_pct*100:.1f}% | "
            f"Price move: {price_move_pct*100:.2f}% | "
            f"Entry: ${entry_price:.4f} → SL: ${sl_price:.4f} | "
            f"Actual Loss: {sl_roi_actual:.1f}%"
        )
        
        return sl_price
    
    async def calculate_trailing_callback(
        self,
        symbol: str,
        target_roi_pct: float = 0.01,  # 1% ROI for trailing callback
    ) -> float:
        """
        Calculate trailing stop callback percentage based on leverage.
        
        Args:
            symbol: Trading symbol
            target_roi_pct: Target ROI for trailing callback (e.g., 0.01 for 1%)
        
        Returns:
            Callback ratio (e.g., 0.0004 for 0.04% with 25x leverage)
        """
        leverage = await self.get_symbol_leverage(symbol)
        
        # Calculate price move percentage for target ROI
        callback_pct = target_roi_pct / leverage
        
        logger.debug(
            f"🔄 Trailing Calc | {symbol} | "
            f"Leverage: {leverage}x | Target ROI: {target_roi_pct*100:.1f}% | "
            f"Callback: {callback_pct*100:.2f}% price move"
        )
        
        return callback_pct


# Global leverage manager instance (initialized by live trader)
leverage_manager: LeverageManager | None = None


def get_leverage_manager() -> LeverageManager:
    """Get global leverage manager instance."""
    if leverage_manager is None:
        raise RuntimeError("LeverageManager not initialized! Call init_leverage_manager() first.")
    return leverage_manager


def init_leverage_manager(rest_client, default_leverage: int = 25):
    """Initialize global leverage manager."""
    global leverage_manager
    leverage_manager = LeverageManager(rest_client, default_leverage)
    return leverage_manager

