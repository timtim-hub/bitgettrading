"""
Liquidation Guards and Position Sizing
25x leverage-aware risk management
"""

import math
from typing import Tuple, Optional, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Position sizing result"""
    contracts: float  # Final contract quantity
    notional_usd: float  # Position notional value
    margin_usd: float  # Margin required
    leverage: float  # Effective leverage
    liq_price: float  # Estimated liquidation price
    stop_price: float  # Stop loss price
    passed_liq_guards: bool  # Whether liq guards passed
    reduction_factor: float  # Factor by which position was reduced (1.0 = no reduction)
    reason: str  # Reason for sizing decision


@dataclass
class LiquidationGuards:
    """Liquidation guard parameters"""
    max_stop_pct: float  # Max stop distance as % of price (0.028 = 2.8%)
    min_abs_buffer_pct: float  # Min absolute buffer to liq (0.012 = 1.2%)
    min_fraction_of_liq_distance: float  # Min fraction of liq distance (0.30 = 30%)


class RiskManager:
    """Manage position sizing with liquidation guards for 25x leverage"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.leverage = config.get('leverage', 25)
        self.margin_fraction = config.get('margin_fraction_per_trade', 0.10)
        
        liq_config = config.get('liq_guards', {})
        self.liq_guards = LiquidationGuards(
            max_stop_pct=liq_config.get('max_stop_pct', 0.028),
            min_abs_buffer_pct=liq_config.get('min_abs_buffer_pct', 0.012),
            min_fraction_of_liq_distance=liq_config.get('min_fraction_of_liq_distance', 0.30)
        )
        
        logger.info(
            f"✅ RiskManager initialized | "
            f"Leverage={self.leverage}x | "
            f"Margin/trade={self.margin_fraction*100:.0f}% | "
            f"Max stop={self.liq_guards.max_stop_pct*100:.1f}% | "
            f"Min liq buffer={self.liq_guards.min_abs_buffer_pct*100:.1f}%"
        )
    
    def get_maintenance_margin_rate(self, symbol: str, notional_usd: float) -> float:
        """
        Get maintenance margin rate for Bitget USDT-M futures
        
        This is a simplified version. In production, fetch from exchange API.
        Bitget uses tiered maintenance margin based on position size.
        
        Typical tiers (example for BTCUSDT):
        0-50k: 0.4%
        50k-250k: 0.5%
        250k-1M: 1.0%
        1M-7.5M: 2.5%
        7.5M+: 5.0%
        """
        # Simplified conservative estimate
        if notional_usd < 50_000:
            return 0.004  # 0.4%
        elif notional_usd < 250_000:
            return 0.005  # 0.5%
        elif notional_usd < 1_000_000:
            return 0.010  # 1.0%
        elif notional_usd < 7_500_000:
            return 0.025  # 2.5%
        else:
            return 0.050  # 5.0%
    
    def calculate_liquidation_price(self, side: str, entry_price: float, 
                                     leverage: float, maintenance_margin_rate: float) -> float:
        """
        Calculate liquidation price for isolated margin
        
        Formula (long):
        Liq Price = Entry Price * (1 - 1/Leverage + MMR)
        
        Formula (short):
        Liq Price = Entry Price * (1 + 1/Leverage - MMR)
        
        Where MMR = maintenance margin rate
        """
        if side == "long":
            liq_price = entry_price * (1 - 1/leverage + maintenance_margin_rate)
        else:  # short
            liq_price = entry_price * (1 + 1/leverage - maintenance_margin_rate)
        
        return liq_price
    
    def check_liq_guards(self, side: str, entry_price: float, stop_price: float, 
                         liq_price: float) -> Tuple[bool, str]:
        """
        Check if position passes liquidation safety guards
        
        Must satisfy:
        1. Hard guard: |P - S| / P <= max_stop_pct (e.g., 0.028 = 2.8%)
        2. Liq buffer: |S - LiqPrice| / P >= min_abs_buffer_pct (e.g., 0.012 = 1.2%)
        3. Liq buffer: |S - LiqPrice| >= min_fraction * |P - LiqPrice| (e.g., 0.30 = 30%)
        
        Returns:
            (passes, reason)
        """
        # Calculate distances
        stop_distance_pct = abs(entry_price - stop_price) / entry_price
        liq_distance_pct = abs(entry_price - liq_price) / entry_price
        stop_to_liq_distance_pct = abs(stop_price - liq_price) / entry_price
        
        # Guard 1: Hard stop distance limit
        if stop_distance_pct > self.liq_guards.max_stop_pct:
            return False, f"stop distance {stop_distance_pct*100:.2f}% > {self.liq_guards.max_stop_pct*100:.1f}% max"
        
        # Guard 2: Minimum absolute buffer to liquidation
        if stop_to_liq_distance_pct < self.liq_guards.min_abs_buffer_pct:
            return False, f"stop-to-liq buffer {stop_to_liq_distance_pct*100:.2f}% < {self.liq_guards.min_abs_buffer_pct*100:.1f}% min"
        
        # Guard 3: Minimum fraction of liquidation distance
        min_buffer = self.liq_guards.min_fraction_of_liq_distance * liq_distance_pct
        if stop_to_liq_distance_pct < min_buffer:
            return False, f"stop-to-liq buffer {stop_to_liq_distance_pct*100:.2f}% < {min_buffer*100:.1f}% (30% of liq distance)"
        
        return True, "passed"
    
    def floor_to_lot_size(self, quantity: float, lot_size: float, min_qty: float) -> float:
        """
        Floor quantity to lot size and ensure >= minimum
        
        Args:
            quantity: Raw quantity
            lot_size: Lot size (e.g., 0.001 for BTC)
            min_qty: Minimum order quantity
        
        Returns:
            Floored quantity or 0 if below minimum
        """
        if lot_size <= 0:
            lot_size = 0.001  # Default
        
        floored = math.floor(quantity / lot_size) * lot_size
        
        if floored < min_qty:
            return 0.0
        
        return floored
    
    def calculate_position_size(self, symbol: str, side: str, entry_price: float, 
                                 stop_price: float, equity_usdt: float,
                                 lot_size: float = 0.001, min_qty: float = 0.001) -> PositionSize:
        """
        Calculate position size with liquidation guards
        
        Process:
        1. Calculate target notional: N_target = (margin_fraction * equity) * leverage
        2. Calculate raw quantity: Q_raw = floor_to_lot(N_target / entry_price)
        3. Calculate liquidation price
        4. Check liquidation guards
        5. If fails, reduce Q proportionally until it passes
        6. If still failing at min_qty, return 0
        
        Args:
            symbol: Trading symbol
            side: 'long' or 'short'
            entry_price: Entry price
            stop_price: Stop loss price
            equity_usdt: Total wallet equity in USDT
            lot_size: Lot size for symbol
            min_qty: Minimum order quantity
        
        Returns:
            PositionSize object
        """
        # Calculate target margin and notional
        margin_target = self.margin_fraction * equity_usdt
        notional_target = margin_target * self.leverage
        
        # Calculate raw quantity
        q_raw = notional_target / entry_price
        q_floored = self.floor_to_lot_size(q_raw, lot_size, min_qty)
        
        if q_floored == 0:
            return PositionSize(
                contracts=0,
                notional_usd=0,
                margin_usd=0,
                leverage=0,
                liq_price=0,
                stop_price=stop_price,
                passed_liq_guards=False,
                reduction_factor=0,
                reason="quantity below minimum after lot sizing"
            )
        
        # Calculate notional with floored quantity
        notional = q_floored * entry_price
        margin = notional / self.leverage
        
        # Get maintenance margin rate and calculate liquidation price
        mmr = self.get_maintenance_margin_rate(symbol, notional)
        liq_price = self.calculate_liquidation_price(side, entry_price, self.leverage, mmr)
        
        # Check liquidation guards
        passes, reason = self.check_liq_guards(side, entry_price, stop_price, liq_price)
        
        if passes:
            logger.debug(
                f"✅ Position sizing PASSED | "
                f"{symbol} {side} | "
                f"Q={q_floored:.4f} | "
                f"Notional=${notional:.2f} | "
                f"Entry=${entry_price:.4f} | "
                f"Stop=${stop_price:.4f} | "
                f"Liq=${liq_price:.4f}"
            )
            
            return PositionSize(
                contracts=q_floored,
                notional_usd=notional,
                margin_usd=margin,
                leverage=self.leverage,
                liq_price=liq_price,
                stop_price=stop_price,
                passed_liq_guards=True,
                reduction_factor=1.0,
                reason="passed"
            )
        
        # Failed guards - try to reduce position
        logger.warning(
            f"⚠️ Position sizing FAILED liq guards | "
            f"{symbol} {side} | "
            f"Reason: {reason} | "
            f"Attempting to reduce position..."
        )
        
        # Try reducing position in 10% increments
        for reduction_factor in [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]:
            q_reduced = q_floored * reduction_factor
            q_reduced_floored = self.floor_to_lot_size(q_reduced, lot_size, min_qty)
            
            if q_reduced_floored == 0:
                continue
            
            notional_reduced = q_reduced_floored * entry_price
            margin_reduced = notional_reduced / self.leverage
            
            mmr_reduced = self.get_maintenance_margin_rate(symbol, notional_reduced)
            liq_price_reduced = self.calculate_liquidation_price(side, entry_price, self.leverage, mmr_reduced)
            
            passes_reduced, reason_reduced = self.check_liq_guards(side, entry_price, stop_price, liq_price_reduced)
            
            if passes_reduced:
                logger.info(
                    f"✅ Position reduced to pass liq guards | "
                    f"{symbol} {side} | "
                    f"Reduction={reduction_factor*100:.0f}% | "
                    f"Q={q_reduced_floored:.4f} (was {q_floored:.4f}) | "
                    f"Notional=${notional_reduced:.2f} (was ${notional:.2f})"
                )
                
                return PositionSize(
                    contracts=q_reduced_floored,
                    notional_usd=notional_reduced,
                    margin_usd=margin_reduced,
                    leverage=self.leverage,
                    liq_price=liq_price_reduced,
                    stop_price=stop_price,
                    passed_liq_guards=True,
                    reduction_factor=reduction_factor,
                    reason=f"reduced to {reduction_factor*100:.0f}% to pass guards"
                )
        
        # Could not reduce to pass guards
        logger.error(
            f"❌ Could not reduce position to pass liq guards | "
            f"{symbol} {side} | "
            f"Entry=${entry_price:.4f} | "
            f"Stop=${stop_price:.4f} | "
            f"Reason: {reason}"
        )
        
        return PositionSize(
            contracts=0,
            notional_usd=0,
            margin_usd=0,
            leverage=0,
            liq_price=liq_price,
            stop_price=stop_price,
            passed_liq_guards=False,
            reduction_factor=0,
            reason=f"could not reduce to pass guards: {reason}"
        )
    
    def calculate_stop_loss(self, side: str, entry_price: float, atr: float, 
                            atr_multiplier: float) -> float:
        """
        Calculate stop loss price
        
        Args:
            side: 'long' or 'short'
            entry_price: Entry price
            atr: Current ATR value
            atr_multiplier: ATR multiplier (e.g., 1.2 for majors)
        
        Returns:
            Stop loss price
        """
        stop_distance = atr * atr_multiplier
        
        if side == "long":
            stop_price = entry_price - stop_distance
        else:  # short
            stop_price = entry_price + stop_distance
        
        return stop_price

