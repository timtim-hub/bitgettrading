"""Position management with persistence and trailing stops."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bitget_trading.logger import get_logger

logger = get_logger()


@dataclass
class Position:
    """Trading position with trailing stop and regime-based parameters."""
    
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    size: float
    entry_time: str
    capital: float
    leverage: int
    
    # Trailing stop tracking
    highest_price: float = 0.0  # For long positions
    lowest_price: float = 0.0   # For short positions
    
    # OPTIMIZED for ultra-short-term scalping with fees in mind
    # With 25x leverage + 0.04% round-trip fees (SAFER than 50x!)
    trailing_stop_pct: float = 0.01  # 1% trailing from peak (0.04% price @ 25x) - ACTIVE!
    stop_loss_pct: float = 0.25   # 25% hard stop-loss (1% price @ 25x) - Balanced risk/reward
    take_profit_pct: float = 0.06  # 6% take-profit (0.24% price @ 25x) - WITH 1% trailing protection!
    
    # Regime info
    regime: str = "ranging"  # Market regime at entry
    
    # Entry quality metadata (for loss tracking)
    metadata: dict[str, Any] = None  # Trade grade, structure, R:R, etc.
    
    # Performance tracking
    unrealized_pnl: float = 0.0
    peak_pnl_pct: float = 0.0  # Track peak profit
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.metadata is None:
            self.metadata = {}


class PositionManager:
    """Manage positions with persistence and trailing stops."""

    def __init__(self, save_path: str = "data/positions.json") -> None:
        """
        Initialize position manager.
        
        Args:
            save_path: Path to save positions
        """
        self.save_path = Path(save_path)
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        self.positions: dict[str, Position] = {}
        
        # Load existing positions on startup
        self.load_positions()

    def add_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size: float,
        capital: float,
        leverage: int,
        regime: str = "ranging",
        stop_loss_pct: float = 0.25,  # 25% capital (1% price @ 25x) - Balanced risk/reward
        take_profit_pct: float = 0.06,  # 6% capital (0.24% price @ 25x) - WITH 1% trailing!
        trailing_stop_pct: float = 0.01,  # 1% capital (0.04% price @ 25x) - ACTIVE!
        metadata: dict = None,  # Entry quality metadata for loss tracking
    ) -> None:
        """Add a new position with regime-based parameters and metadata."""
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            entry_time=datetime.now().isoformat(),
            capital=capital,
            leverage=leverage,
            highest_price=entry_price if side == "long" else 0.0,
            lowest_price=entry_price if side == "short" else float('inf'),
            regime=regime,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            metadata=metadata or {},  # Store entry metadata for loss tracking
        )
        
        self.positions[symbol] = position
        self.save_positions()
        
        logger.info(
            "position_added",
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            regime=regime,
            tp=f"{take_profit_pct*100}%",
            sl=f"{stop_loss_pct*100}%",
        )

    def remove_position(self, symbol: str) -> Position | None:
        """Remove a position."""
        position = self.positions.pop(symbol, None)
        if position:
            self.save_positions()
            logger.info("position_removed", symbol=symbol)
        return position

    def update_position_price(self, symbol: str, current_price: float) -> None:
        """Update position with current price and trailing stop."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Update trailing levels
        if position.side == "long":
            position.highest_price = max(position.highest_price, current_price)
        else:  # short
            if position.lowest_price == float('inf'):
                position.lowest_price = current_price
            else:
                position.lowest_price = min(position.lowest_price, current_price)
        
        # Calculate PnL
        if position.side == "long":
            pnl_pct = ((current_price - position.entry_price) / position.entry_price)
        else:  # short
            pnl_pct = ((position.entry_price - current_price) / position.entry_price)
        
        position.unrealized_pnl = pnl_pct * position.capital * position.leverage
        
        # Track peak PnL
        position.peak_pnl_pct = max(position.peak_pnl_pct, pnl_pct * 100)
        
        self.save_positions()

    def check_exit_conditions(
        self, symbol: str, current_price: float
    ) -> tuple[bool, str]:
        """
        Check if position should be closed.
        
        Accounts for LEVERAGE: with 50x leverage, only need 0.2% price move for 10% return!
        
        Returns:
            (should_close, reason)
        """
        if symbol not in self.positions:
            return False, ""
        
        position = self.positions[symbol]
        
        # Calculate time in position (for logging)
        from datetime import datetime
        entry_time = datetime.fromisoformat(position.entry_time.replace('Z', '+00:00'))
        time_in_position = (datetime.now(entry_time.tzinfo) - entry_time).total_seconds()
        
        # Calculate current price change % (currency move)
        if position.side == "long":
            price_change_pct = ((current_price - position.entry_price) / position.entry_price)
        else:
            price_change_pct = ((position.entry_price - current_price) / position.entry_price)
        
        # Apply leverage to get return on CAPITAL
        return_on_capital_pct = price_change_pct * position.leverage
        
        # CRITICAL: Targets are based on CAPITAL return, not price move!
        # With 25x leverage:
        # - 14% capital TP = 0.56% price move - WITH trailing protection!
        # - 50% capital SL = 2.0% price move - MAXIMUM ROOM for big moves!
        
        target_price_move_for_stop = position.stop_loss_pct / position.leverage  # e.g., 0.50 / 25 = 0.02 (2%)
        target_price_move_for_tp = position.take_profit_pct / position.leverage  # e.g., 0.14 / 25 = 0.0056 (0.56%)
        target_price_move_for_trail = position.trailing_stop_pct / position.leverage  # e.g., 0.04 / 25 = 0.0016 (0.16%)
        
        # 🚨 EXTREME DEBUG: Log EVERY detail to understand exits
        logger.info(
            f"🔍 [EXIT CHECK] {symbol} | "
            f"Entry: ${position.entry_price:.4f} → Current: ${current_price:.4f} | "
            f"Price Δ: {price_change_pct*100:.4f}% | "
            f"Capital PnL: {return_on_capital_pct*100:.2f}% | "
            f"Leverage: {position.leverage}x | "
            f"SL target: {-target_price_move_for_stop*100:.2f}% price ({-position.stop_loss_pct*100:.0f}% capital) | "
            f"TP target: {target_price_move_for_tp*100:.2f}% price ({position.take_profit_pct*100:.0f}% capital) | "
            f"Time held: {time_in_position/60:.1f}min"
        )
        
        # 1. Hard stop-loss (on capital, not price) - ALWAYS HONOR
        if price_change_pct < -target_price_move_for_stop:
            return True, f"STOP-LOSS (Capital: {return_on_capital_pct*100:.2f}%, Price: {price_change_pct*100:.4f}%)"
        
        # 2. Take-profit (on capital, not price) - CHECK THIS FIRST!
        if price_change_pct > target_price_move_for_tp:
            logger.info(
                f"🎯 TP TRIGGERED! {symbol} | "
                f"Capital: {return_on_capital_pct*100:.2f}% | "
                f"Price: {price_change_pct*100:.4f}% | "
                f"Target: {target_price_move_for_tp*100:.4f}% | "
                f"Leverage: {position.leverage}x"
            )
            return True, f"TAKE-PROFIT (Capital: {return_on_capital_pct*100:.2f}%, Price: {price_change_pct*100:.4f}%)"
        
        # 3. REMOVED: Minimum profit lock was TRAPPING positions in losses!
        # Old logic: Held positions between -0.5% to +0.5%, but this caused:
        # - Small losses to turn into BIG losses
        # - Positions stuck without exit_reason
        # - Fees accumulating while waiting
        # 
        # NEW APPROACH: Let stop-loss handle downside, let TP/trailing handle upside
        # NO artificial holds - trust our SL/TP/trailing logic!
        
        # 4. Trailing stop (only AFTER reaching TP threshold on CAPITAL basis)
        # Prevents early 4% exits; trailing becomes a post-TP profit lock
        if return_on_capital_pct >= position.take_profit_pct:
            if position.side == "long":
                # Trail from highest price
                trailing_stop_price = position.highest_price * (1 - target_price_move_for_trail)
                drop_from_peak_price_pct = (position.highest_price - current_price) / position.highest_price
                drop_from_peak_capital_pct = drop_from_peak_price_pct * position.leverage
                logger.info(
                    f"🧵 [TRAIL CHECK] {symbol} (LONG) | Peak: ${position.highest_price:.4f} | "
                    f"Drop from peak: {drop_from_peak_capital_pct*100:.2f}% capital | "
                    f"Trail width: {position.trailing_stop_pct*100:.0f}% capital"
                )
                if current_price < trailing_stop_price:
                    return True, (
                        f"TRAILING-STOP from peak ${position.highest_price:.4f} "
                        f"(Drop: {drop_from_peak_capital_pct*100:.2f}% capital)"
                    )
            else:  # short
                # Trail from lowest price
                trailing_stop_price = position.lowest_price * (1 + target_price_move_for_trail)
                drop_from_low_price_pct = (current_price - position.lowest_price) / position.lowest_price
                drop_from_low_capital_pct = drop_from_low_price_pct * position.leverage
                logger.info(
                    f"🧵 [TRAIL CHECK] {symbol} (SHORT) | Low: ${position.lowest_price:.4f} | "
                    f"Bounce from low: {drop_from_low_capital_pct*100:.2f}% capital | "
                    f"Trail width: {position.trailing_stop_pct*100:.0f}% capital"
                )
                if current_price > trailing_stop_price:
                    return True, (
                        f"TRAILING-STOP from low ${position.lowest_price:.4f} "
                        f"(Bounce: {drop_from_low_capital_pct*100:.2f}% capital)"
                    )
 
        return False, ""

    def get_position(self, symbol: str) -> Position | None:
        """Get position for a symbol."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """Get all positions."""
        return self.positions.copy()
    
    def log_all_position_settings(self) -> None:
        """Log TP/SL settings for all open positions (for debugging)."""
        if not self.positions:
            logger.info("📊 No open positions")
            return
        
        logger.info(f"📊 === OPEN POSITIONS SETTINGS ({len(self.positions)} total) ===")
        for symbol, pos in self.positions.items():
            logger.info(
                f"   {symbol}: "
                f"Side={pos.side} | "
                f"Leverage={pos.leverage}x | "
                f"SL={pos.stop_loss_pct*100:.0f}% capital ({pos.stop_loss_pct/pos.leverage*100:.2f}% price) | "
                f"TP={pos.take_profit_pct*100:.0f}% capital ({pos.take_profit_pct/pos.leverage*100:.2f}% price) | "
                f"Trailing={pos.trailing_stop_pct*100:.0f}% capital"
            )

    def save_positions(self) -> None:
        """Save positions to disk."""
        try:
            positions_data = {
                symbol: asdict(position)
                for symbol, position in self.positions.items()
            }
            
            with open(self.save_path, "w") as f:
                json.dump(positions_data, f, indent=2)
            
            logger.debug("positions_saved", count=len(self.positions))
            
        except Exception as e:
            logger.error("save_positions_error", error=str(e))

    def load_positions(self) -> None:
        """Load positions from disk."""
        if not self.save_path.exists():
            logger.info("no_saved_positions_found")
            return
        
        try:
            with open(self.save_path, "r") as f:
                positions_data = json.load(f)
            
            for symbol, data in positions_data.items():
                position = Position(**data)
                self.positions[symbol] = position
            
            logger.info(
                "positions_loaded",
                count=len(self.positions),
                symbols=list(self.positions.keys()),
            )
            
        except Exception as e:
            logger.error("load_positions_error", error=str(e))

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized PnL across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_position_summary(self) -> dict[str, Any]:
        """Get summary of all positions."""
        return {
            "total_positions": len(self.positions),
            "total_unrealized_pnl": self.get_total_unrealized_pnl(),
            "symbols": list(self.positions.keys()),
        }