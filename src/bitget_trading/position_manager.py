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
    # With 50x leverage + 0.04% round-trip fees
    trailing_stop_pct: float = 0.04  # 4% trailing from peak (0.08% price @ 50x)
    stop_loss_pct: float = 0.08   # 8% hard stop-loss (0.16% price @ 50x) - wider for volatility
    take_profit_pct: float = 0.20  # 20% take-profit (0.4% price @ 50x) - let winners run!
    
    # Regime info
    regime: str = "ranging"  # Market regime at entry
    
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
        regime: str = "ranging",
        stop_loss_pct: float = 0.08,  # 8% capital (0.16% price @ 50x) - wider for volatility
        take_profit_pct: float = 0.20,  # 20% capital (0.4% price @ 50x) - let winners run!
        trailing_stop_pct: float = 0.04,  # 4% capital (0.08% price @ 50x) - tighter trailing
    ) -> None:
        """Add a new position with regime-based parameters."""
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
        
        # Calculate current price change % (currency move)
        if position.side == "long":
            price_change_pct = ((current_price - position.entry_price) / position.entry_price)
        else:
            price_change_pct = ((position.entry_price - current_price) / position.entry_price)
        
        # Apply leverage to get return on CAPITAL
        return_on_capital_pct = price_change_pct * position.leverage
        
        # CRITICAL: Targets are based on CAPITAL return, not price move!
        # With 50x leverage:
        # - 10% capital return = 0.2% price move
        # - 2% capital loss = 0.04% price move
        
        target_price_move_for_stop = position.stop_loss_pct / position.leverage  # e.g., 2% / 50 = 0.04%
        target_price_move_for_tp = position.take_profit_pct / position.leverage  # e.g., 10% / 50 = 0.2%
        target_price_move_for_trail = position.trailing_stop_pct / position.leverage  # e.g., 3% / 50 = 0.06%
        
        # 1. Hard stop-loss (on capital, not price) - ALWAYS HONOR
        if price_change_pct < -target_price_move_for_stop:
            return True, f"STOP-LOSS (Capital: {return_on_capital_pct*100:.2f}%, Price: {price_change_pct*100:.4f}%)"
        
        # 2. QUICK PROFIT EXIT: Take profit after 3-5 minutes if above minimum threshold
        # This prevents giving back profits in choppy markets
        from datetime import datetime, timedelta
        try:
            entry_dt = datetime.fromisoformat(position.entry_time)
            time_in_position = (datetime.now() - entry_dt).total_seconds()
            
            # After 3 minutes, take any profit > 2% capital (covers fees + profit)
            if time_in_position > 180 and return_on_capital_pct > 0.02:
                return True, f"QUICK-PROFIT after {time_in_position/60:.1f}min (Capital: {return_on_capital_pct*100:.2f}%)"
            
            # After 5 minutes, take any profit > 1.5% capital (marginal profit)
            if time_in_position > 300 and return_on_capital_pct > 0.015:
                return True, f"TIME-EXIT after {time_in_position/60:.1f}min (Capital: {return_on_capital_pct*100:.2f}%)"
            
            # After 10 minutes, exit even at breakeven (free up capital)
            if time_in_position > 600 and return_on_capital_pct > -0.005:
                return True, f"MAX-TIME-EXIT after {time_in_position/60:.1f}min (Capital: {return_on_capital_pct*100:.2f}%)"
        except:
            pass  # If datetime parsing fails, skip time-based exits
        
        # 3. MINIMUM PROFIT LOCK: Don't close small winners/losers (avoid fee erosion)
        # Between -1% and +1.5% capital return, hold position (fees cost ~0.04%)
        if -0.01 < return_on_capital_pct < 0.015:
            # Too small to justify closing - would lose to fees
            return False, ""
        
        # 4. Take-profit (on capital, not price)
        if price_change_pct > target_price_move_for_tp:
            return True, f"TAKE-PROFIT (Capital: {return_on_capital_pct*100:.2f}%, Price: {price_change_pct*100:.4f}%)"
        
        # 4. Trailing stop (only if in profit on capital basis)
        min_profit_for_trailing = 0.01 / position.leverage  # 1% capital return = 0.02% price move @ 50x
        if price_change_pct > min_profit_for_trailing:
            if position.side == "long":
                # Trail from highest price
                trailing_stop_price = position.highest_price * (1 - target_price_move_for_trail)
                if current_price < trailing_stop_price:
                    return True, f"TRAILING-STOP from peak ${position.highest_price:.4f} (Capital PnL: {return_on_capital_pct*100:.2f}%)"
            else:  # short
                # Trail from lowest price
                trailing_stop_price = position.lowest_price * (1 + target_price_move_for_trail)
                if current_price > trailing_stop_price:
                    return True, f"TRAILING-STOP from low ${position.lowest_price:.4f} (Capital PnL: {return_on_capital_pct*100:.2f}%)"
        
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

