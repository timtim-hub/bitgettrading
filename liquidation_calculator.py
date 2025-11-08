"""
Liquidation Price and Risk Calculator for Multiple Leverage Levels

Calculates liquidation prices, margin requirements, and risk metrics for 25x, 50x, and 100x leverage.
"""

from typing import Dict, Tuple
from dataclasses import dataclass


@dataclass
class LiquidationRisk:
    """Risk metrics for a leveraged position."""
    leverage: int
    entry_price: float
    liquidation_price_long: float
    liquidation_price_short: float
    maintenance_margin_rate: float
    initial_margin_rate: float
    liquidation_distance_long_pct: float
    liquidation_distance_short_pct: float
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "EXTREME"
    max_position_size_pct: float  # % of capital to use for this leverage
    recommended_sl_pct: float  # Recommended stop-loss % (capital)
    recommended_tp_pct: float  # Recommended take-profit % (capital)


class LiquidationCalculator:
    """
    Calculate liquidation prices and risk metrics for futures trading.
    
    Based on Bitget's liquidation formula:
    For LONG: Liquidation Price = Entry Price * (1 - 1/Leverage + MMR)
    For SHORT: Liquidation Price = Entry Price * (1 + 1/Leverage - MMR)
    
    Where MMR = Maintenance Margin Rate (varies by position size)
    """
    
    # Bitget USDT-M Futures Maintenance Margin Rates (approximate)
    MAINTENANCE_MARGIN_RATES = {
        25: 0.005,   # 0.5% for 25x
        50: 0.010,   # 1.0% for 50x
        100: 0.020,  # 2.0% for 100x
    }
    
    def __init__(self):
        """Initialize liquidation calculator."""
        pass
    
    def calculate_liquidation_price(
        self, 
        entry_price: float, 
        leverage: int, 
        side: str = "long"
    ) -> float:
        """
        Calculate liquidation price for a position.
        
        Args:
            entry_price: Entry price for the position
            leverage: Leverage multiplier (25, 50, or 100)
            side: "long" or "short"
            
        Returns:
            Liquidation price
        """
        mmr = self.MAINTENANCE_MARGIN_RATES.get(leverage, 0.01)
        
        if side == "long":
            # Long liquidation: price drops by (1/leverage - MMR)
            liq_price = entry_price * (1 - (1/leverage) + mmr)
        else:
            # Short liquidation: price rises by (1/leverage - MMR)
            liq_price = entry_price * (1 + (1/leverage) - mmr)
        
        return liq_price
    
    def calculate_liquidation_distance(
        self, 
        entry_price: float, 
        liq_price: float, 
        side: str = "long"
    ) -> float:
        """
        Calculate distance to liquidation as a percentage.
        
        Returns:
            Distance to liquidation in % (positive number)
        """
        if side == "long":
            distance_pct = ((entry_price - liq_price) / entry_price) * 100
        else:
            distance_pct = ((liq_price - entry_price) / entry_price) * 100
        
        return abs(distance_pct)
    
    def assess_risk_level(self, liquidation_distance_pct: float) -> str:
        """
        Assess risk level based on liquidation distance.
        
        Returns:
            "LOW", "MEDIUM", "HIGH", or "EXTREME"
        """
        if liquidation_distance_pct > 5.0:
            return "LOW"
        elif liquidation_distance_pct > 3.0:
            return "MEDIUM"
        elif liquidation_distance_pct > 1.5:
            return "HIGH"
        else:
            return "EXTREME"
    
    def calculate_adaptive_parameters(self, leverage: int) -> Tuple[float, float, float]:
        """
        Calculate adaptive TP/SL/trailing parameters based on leverage.
        
        Higher leverage = tighter stops, smaller position size.
        
        Returns:
            (position_size_pct, stop_loss_capital_pct, take_profit_capital_pct)
        """
        if leverage == 25:
            # Conservative parameters for 25x
            position_size_pct = 0.12  # 12% of capital per position
            stop_loss_capital_pct = 0.50  # 50% capital stop
            take_profit_capital_pct = 0.20  # 20% capital target
        elif leverage == 50:
            # More conservative for 50x
            position_size_pct = 0.08  # 8% of capital per position
            stop_loss_capital_pct = 0.35  # 35% capital stop (tighter)
            take_profit_capital_pct = 0.15  # 15% capital target
        elif leverage == 100:
            # Very conservative for 100x
            position_size_pct = 0.05  # 5% of capital per position
            stop_loss_capital_pct = 0.25  # 25% capital stop (very tight)
            take_profit_capital_pct = 0.10  # 10% capital target
        else:
            # Default fallback
            position_size_pct = 0.10
            stop_loss_capital_pct = 0.40
            take_profit_capital_pct = 0.15
        
        return position_size_pct, stop_loss_capital_pct, take_profit_capital_pct
    
    def calculate_risk_metrics(
        self, 
        entry_price: float, 
        leverage: int
    ) -> LiquidationRisk:
        """
        Calculate comprehensive risk metrics for a position.
        
        Args:
            entry_price: Entry price for the position
            leverage: Leverage multiplier (25, 50, or 100)
            
        Returns:
            LiquidationRisk object with all risk metrics
        """
        # Calculate liquidation prices
        liq_price_long = self.calculate_liquidation_price(entry_price, leverage, "long")
        liq_price_short = self.calculate_liquidation_price(entry_price, leverage, "short")
        
        # Calculate distances
        liq_distance_long = self.calculate_liquidation_distance(entry_price, liq_price_long, "long")
        liq_distance_short = self.calculate_liquidation_distance(entry_price, liq_price_short, "short")
        
        # Use the smaller distance for risk assessment (more conservative)
        min_liq_distance = min(liq_distance_long, liq_distance_short)
        risk_level = self.assess_risk_level(min_liq_distance)
        
        # Get maintenance margin rate
        mmr = self.MAINTENANCE_MARGIN_RATES.get(leverage, 0.01)
        initial_margin_rate = 1.0 / leverage
        
        # Get adaptive parameters
        pos_size_pct, sl_pct, tp_pct = self.calculate_adaptive_parameters(leverage)
        
        return LiquidationRisk(
            leverage=leverage,
            entry_price=entry_price,
            liquidation_price_long=liq_price_long,
            liquidation_price_short=liq_price_short,
            maintenance_margin_rate=mmr,
            initial_margin_rate=initial_margin_rate,
            liquidation_distance_long_pct=liq_distance_long,
            liquidation_distance_short_pct=liq_distance_short,
            risk_level=risk_level,
            max_position_size_pct=pos_size_pct,
            recommended_sl_pct=sl_pct,
            recommended_tp_pct=tp_pct
        )
    
    def compare_leverage_levels(self, entry_price: float) -> Dict[int, LiquidationRisk]:
        """
        Compare risk metrics across all leverage levels.
        
        Args:
            entry_price: Entry price for comparison
            
        Returns:
            Dictionary mapping leverage to LiquidationRisk
        """
        results = {}
        for leverage in [25, 50, 100]:
            results[leverage] = self.calculate_risk_metrics(entry_price, leverage)
        return results
    
    def print_risk_comparison(self, entry_price: float):
        """
        Print a formatted comparison of risk metrics across leverage levels.
        """
        print("="*100)
        print(f"LIQUIDATION RISK ANALYSIS @ Entry Price: ${entry_price:.4f}")
        print("="*100)
        print()
        
        results = self.compare_leverage_levels(entry_price)
        
        print(f"{'Leverage':<10} {'Liq (Long)':<15} {'Liq (Short)':<15} {'Distance %':<12} {'Risk':<10} {'Pos Size %':<12} {'SL %':<8} {'TP %':<8}")
        print("-"*100)
        
        for leverage in [25, 50, 100]:
            risk = results[leverage]
            min_distance = min(risk.liquidation_distance_long_pct, risk.liquidation_distance_short_pct)
            
            print(f"{leverage}x{' ':<7} "
                  f"${risk.liquidation_price_long:<14.4f} "
                  f"${risk.liquidation_price_short:<14.4f} "
                  f"{min_distance:<11.2f}% "
                  f"{risk.risk_level:<10} "
                  f"{risk.max_position_size_pct*100:<11.1f}% "
                  f"{risk.recommended_sl_pct*100:<7.0f}% "
                  f"{risk.recommended_tp_pct*100:<7.0f}%")
        
        print()
        print("="*100)
        print("RISK LEVEL GUIDE:")
        print("  LOW (>5% distance)     : Safe for most market conditions")
        print("  MEDIUM (3-5% distance) : Use with caution, tight stops recommended")
        print("  HIGH (1.5-3% distance) : High risk, only for experienced traders")
        print("  EXTREME (<1.5% distance): Very high liquidation risk, not recommended")
        print("="*100)
        print()
        
        return results


def main():
    """Example usage and demonstration."""
    calc = LiquidationCalculator()
    
    # Example 1: Bitcoin entry at $65,000
    print("\n📊 Example 1: BTCUSDT @ $65,000")
    calc.print_risk_comparison(65000.0)
    
    # Example 2: ETH entry at $3,500
    print("\n📊 Example 2: ETHUSDT @ $3,500")
    calc.print_risk_comparison(3500.0)
    
    # Example 3: Altcoin entry at $1.234
    print("\n📊 Example 3: Generic Token @ $1.234")
    calc.print_risk_comparison(1.234)
    
    # Detailed breakdown for 25x vs 50x vs 100x
    print("\n"+"="*100)
    print("📈 DETAILED COMPARISON: Impact of Leverage on Position Parameters")
    print("="*100)
    print()
    
    price = 100.0
    results = calc.compare_leverage_levels(price)
    
    for leverage in [25, 50, 100]:
        risk = results[leverage]
        print(f"\n{'='*80}")
        print(f"  {leverage}x LEVERAGE - Risk Level: {risk.risk_level}")
        print(f"{'='*80}")
        print(f"  Entry Price:              ${risk.entry_price:.4f}")
        print(f"  Liquidation (Long):       ${risk.liquidation_price_long:.4f} ({risk.liquidation_distance_long_pct:.2f}% away)")
        print(f"  Liquidation (Short):      ${risk.liquidation_price_short:.4f} ({risk.liquidation_distance_short_pct:.2f}% away)")
        print(f"  Initial Margin Rate:      {risk.initial_margin_rate*100:.2f}%")
        print(f"  Maintenance Margin Rate:  {risk.maintenance_margin_rate*100:.2f}%")
        print(f"  Recommended Position Size: {risk.max_position_size_pct*100:.1f}% of capital")
        print(f"  Recommended Stop Loss:    {risk.recommended_sl_pct*100:.0f}% of capital")
        print(f"  Recommended Take Profit:  {risk.recommended_tp_pct*100:.0f}% of capital")
        
        # Convert to price percentages
        sl_price_pct = (risk.recommended_sl_pct / leverage) * 100
        tp_price_pct = (risk.recommended_tp_pct / leverage) * 100
        
        print(f"  Stop Loss (price %):      {sl_price_pct:.2f}%")
        print(f"  Take Profit (price %):    {tp_price_pct:.2f}%")
    
    print("\n"+"="*100)
    print("✅ Liquidation calculator ready!")
    print("="*100)


if __name__ == "__main__":
    main()

