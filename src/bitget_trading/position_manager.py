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
    """Trading position with trailing stop."""
    
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
    trailing_stop_pct: float = 0.03  # 3% trailing from peak
    
    # Risk management (OPTIMIZED for fee reduction)
    stop_loss_pct: float = 0.02   # 2% hard stop-loss
    take_profit_pct: float = 0.10  # 10% take-profit (was 5% - let winners run!)
    
    # Performance tracking
    unrealized_pnl: float = 0.0
    peak_pnl_pct: float = 0.0  # Track peak profit


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
    ) -> None:
        """Add a new position."""
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
        )
        
        self.positions[symbol] = position
        self.save_positions()
        
        logger.info(
            "position_added",
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
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
        
        Returns:
            (should_close, reason)
        """
        if symbol not in self.positions:
            return False, ""
        
        position = self.positions[symbol]
        
        # Calculate current PnL %
        if position.side == "long":
            pnl_pct = ((current_price - position.entry_price) / position.entry_price)
        else:
            pnl_pct = ((position.entry_price - current_price) / position.entry_price)
        
        # 1. Hard stop-loss
        if pnl_pct < -position.stop_loss_pct:
            return True, f"STOP-LOSS ({pnl_pct*100:.2f}%)"
        
        # 2. Take-profit
        if pnl_pct > position.take_profit_pct:
            return True, f"TAKE-PROFIT ({pnl_pct*100:.2f}%)"
        
        # 3. Trailing stop (only if in profit)
        if pnl_pct > 0.01:  # Only activate trailing if up 1%+
            if position.side == "long":
                # Trail from highest price
                trailing_stop_price = position.highest_price * (1 - position.trailing_stop_pct)
                if current_price < trailing_stop_price:
                    return True, f"TRAILING-STOP from peak ${position.highest_price:.4f}"
            else:  # short
                # Trail from lowest price
                trailing_stop_price = position.lowest_price * (1 + position.trailing_stop_pct)
                if current_price > trailing_stop_price:
                    return True, f"TRAILING-STOP from low ${position.lowest_price:.4f}"
        
        return False, ""

    def get_position(self, symbol: str) -> Position | None:
        """Get position for a symbol."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """Get all positions."""
        return self.positions.copy()

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

