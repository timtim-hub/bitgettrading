#!/usr/bin/env python3
"""Paper trading with multi-symbol cross-sectional ranking."""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime

from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.universe import UniverseManager

logger = setup_logging()


@dataclass
class Position:
    """Paper trading position."""
    
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    size: float
    entry_time: datetime
    capital_allocated: float


class PaperTrader:
    """
    Paper trading engine for multi-symbol cross-sectional strategy.
    
    Uses live Bitget market data but simulates order execution.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_symbols: int = 10,
        rebalance_interval_sec: int = 30,
        leverage: float = 3.0,
    ) -> None:
        """
        Initialize paper trader.
        
        Args:
            initial_capital: Starting capital in USDT
            max_symbols: Maximum number of concurrent positions
            rebalance_interval_sec: How often to rebalance (seconds)
            leverage: Leverage to use
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_symbols = max_symbols
        self.rebalance_interval_sec = rebalance_interval_sec
        self.leverage = leverage
        
        # Positions
        self.positions: dict[str, Position] = {}
        
        # Performance tracking
        self.equity_curve: list[tuple[datetime, float]] = []
        self.trades: list[dict] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        self.total_fees = 0.0
        
        # Components
        self.universe = UniverseManager(min_volume_24h=500_000, max_spread_bps=100)
        self.state_manager = MultiSymbolStateManager()
        self.ranker = CrossSectionalRanker(
            momentum_weight=0.4,
            imbalance_weight=0.3,
            volatility_weight=0.2,
            liquidity_weight=0.1,
            bandit_alpha=0.5,
            ucb_exploration=2.0,
        )
        
        self.start_time = datetime.now()
        self.last_rebalance = time.time()

    async def initialize(self) -> None:
        """Initialize universe and state."""
        logger.info("initializing_paper_trader", capital=self.capital)
        
        # Fetch tradeable universe
        symbols = await self.universe.get_tradeable_universe()
        logger.info(f"found_{len(symbols)}_tradeable_symbols")
        
        # Initialize state for top 100 symbols (for speed)
        for symbol in symbols[:100]:
            self.state_manager.add_symbol(symbol)
        
        logger.info("initialization_complete")

    async def update_market_data(self) -> None:
        """Fetch latest market data for all symbols."""
        tickers = await self.universe.fetch_tickers()
        
        if not tickers:
            logger.warning("no_ticker_data")
            return
        
        # Update state manager
        for symbol, ticker in tickers.items():
            if symbol in self.state_manager.symbols:
                self.state_manager.update_ticker(symbol, ticker)
                
                # Simulate order book (since we don't have real-time WS)
                mid = ticker.get("last_price", 0)
                if mid > 0:
                    spread = mid * 0.0005  # 5 bps estimate
                    self.state_manager.update_orderbook(symbol, {
                        "bids": [[mid - spread/2, 1000], [mid - spread, 500]],
                        "asks": [[mid + spread/2, 1000], [mid + spread, 500]],
                    })

    def calculate_position_pnl(self, position: Position, current_price: float) -> float:
        """Calculate current PnL for a position."""
        if position.side == "long":
            price_change = current_price - position.entry_price
        else:  # short
            price_change = position.entry_price - current_price
        
        pnl = (price_change / position.entry_price) * position.capital_allocated * self.leverage
        return pnl

    def get_current_equity(self) -> float:
        """Calculate current equity including unrealized PnL."""
        equity = self.capital
        
        for symbol, position in self.positions.items():
            state = self.state_manager.get_state(symbol)
            if state and state.mid_price > 0:
                pnl = self.calculate_position_pnl(position, state.mid_price)
                equity += pnl
        
        return equity

    async def rebalance(self) -> None:
        """Execute rebalancing based on cross-sectional ranking."""
        logger.info("rebalancing_portfolio")
        
        # Get current equity
        current_equity = self.get_current_equity()
        
        # Rank symbols
        top_symbols = self.ranker.rank_symbols(
            self.state_manager,
            top_k=self.max_symbols,
            min_spread_bps=50.0,
            min_depth=100.0,
        )
        
        if not top_symbols:
            logger.warning("no_symbols_ranked")
            return
        
        logger.info(f"top_ranked_symbols", symbols=[s[0] for s in top_symbols[:5]])
        
        # Allocate capital
        allocations = self.ranker.allocate_capital(
            top_symbols,
            total_capital=current_equity,
            max_per_symbol_pct=0.15,
        )
        
        # Close positions not in new allocation
        to_close = [s for s in self.positions.keys() if s not in allocations]
        for symbol in to_close:
            await self.close_position(symbol)
        
        # Open/adjust positions in allocation
        for symbol, allocated_capital in allocations.items():
            state = self.state_manager.get_state(symbol)
            if not state or state.mid_price <= 0:
                continue
            
            # Determine side based on signal
            features = state.compute_features()
            momentum = features.get("return_15s", 0)
            imbalance = features.get("ob_imbalance", 0)
            
            # Simple signal: positive momentum + imbalance = long
            if momentum > 0 or imbalance > 0.1:
                side = "long"
            elif momentum < 0 or imbalance < -0.1:
                side = "short"
            else:
                continue  # Skip neutral
            
            # Check if we already have this position
            if symbol in self.positions:
                # For simplicity, keep existing position
                continue
            
            # Open new position
            await self.open_position(symbol, side, allocated_capital, state.mid_price)

    async def open_position(self, symbol: str, side: str, capital: float, price: float) -> None:
        """Open a new position."""
        # Calculate size
        size = (capital * self.leverage) / price
        
        # Fee (0.06% taker)
        fee = capital * self.leverage * 0.0006
        self.capital -= fee
        self.total_fees += fee
        
        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            size=size,
            entry_time=datetime.now(),
            capital_allocated=capital,
        )
        
        self.positions[symbol] = position
        
        logger.info(
            "position_opened",
            symbol=symbol,
            side=side,
            price=f"{price:.4f}",
            capital=f"${capital:.2f}",
        )

    async def close_position(self, symbol: str) -> None:
        """Close an existing position."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        state = self.state_manager.get_state(symbol)
        
        if not state or state.mid_price <= 0:
            # Can't close without price
            del self.positions[symbol]
            return
        
        # Calculate PnL
        pnl = self.calculate_position_pnl(position, state.mid_price)
        
        # Fee
        exit_value = position.capital_allocated * self.leverage
        fee = exit_value * 0.0006
        self.capital -= fee
        self.total_fees += fee
        
        # Net PnL
        net_pnl = pnl - fee
        self.capital += net_pnl
        self.total_pnl += net_pnl
        
        # Track trade
        self.total_trades += 1
        if net_pnl > 0:
            self.winning_trades += 1
        
        # Record for bandit
        return_pct = (net_pnl / position.capital_allocated) * 100
        self.state_manager.record_trade(symbol, net_pnl, return_pct)
        
        # Store trade
        duration = (datetime.now() - position.entry_time).total_seconds()
        self.trades.append({
            "symbol": symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": state.mid_price,
            "pnl": net_pnl,
            "duration_sec": duration,
        })
        
        logger.info(
            "position_closed",
            symbol=symbol,
            pnl=f"${net_pnl:.2f}",
            duration=f"{duration:.0f}s",
        )
        
        # Remove position
        del self.positions[symbol]

    async def run(self, duration_minutes: int = 5) -> None:
        """
        Run paper trading for specified duration.
        
        Args:
            duration_minutes: How long to run
        """
        logger.info(f"starting_paper_trading for {duration_minutes} minutes")
        
        await self.initialize()
        
        end_time = time.time() + (duration_minutes * 60)
        
        while time.time() < end_time:
            try:
                # Update market data
                await self.update_market_data()
                
                # Track equity
                equity = self.get_current_equity()
                self.equity_curve.append((datetime.now(), equity))
                
                # Rebalance if needed
                if time.time() - self.last_rebalance >= self.rebalance_interval_sec:
                    await self.rebalance()
                    self.last_rebalance = time.time()
                
                # Log status
                pnl_pct = ((equity - self.initial_capital) / self.initial_capital) * 100
                logger.info(
                    "status",
                    equity=f"${equity:.2f}",
                    pnl=f"{pnl_pct:+.2f}%",
                    positions=len(self.positions),
                    trades=self.total_trades,
                )
                
                # Wait before next iteration
                await asyncio.sleep(10)  # Update every 10 seconds
                
            except Exception as e:
                logger.error("error_in_trading_loop", error=str(e))
        
        # Close all positions at end
        logger.info("closing_all_positions")
        for symbol in list(self.positions.keys()):
            await self.close_position(symbol)
        
        # Final report
        self.print_results()

    def print_results(self) -> None:
        """Print final trading results."""
        final_equity = self.capital
        total_return = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        logger.info("\n" + "="*60)
        logger.info("PAPER TRADING RESULTS")
        logger.info("="*60)
        logger.info(f"Duration: {(datetime.now() - self.start_time).total_seconds():.0f} seconds")
        logger.info(f"Initial Capital: ${self.initial_capital:.2f}")
        logger.info(f"Final Equity: ${final_equity:.2f}")
        logger.info(f"Total Return: {total_return:+.2f}%")
        logger.info(f"Total PnL: ${self.total_pnl:.2f}")
        logger.info(f"Total Fees: ${self.total_fees:.2f}")
        logger.info(f"Net PnL: ${self.total_pnl - self.total_fees:.2f}")
        logger.info(f"Total Trades: {self.total_trades}")
        
        if self.total_trades > 0:
            win_rate = (self.winning_trades / self.total_trades) * 100
            logger.info(f"Winning Trades: {self.winning_trades}")
            logger.info(f"Win Rate: {win_rate:.1f}%")
            
            avg_pnl = self.total_pnl / self.total_trades
            logger.info(f"Avg PnL per Trade: ${avg_pnl:.2f}")
        
        logger.info("="*60)
        
        # Show recent trades
        if self.trades:
            logger.info("\nRecent Trades:")
            for trade in self.trades[-10:]:
                logger.info(
                    f"  {trade['symbol']}: {trade['side']} | "
                    f"${trade['pnl']:.2f} | {trade['duration_sec']:.0f}s"
                )


async def main() -> None:
    """Run paper trading."""
    trader = PaperTrader(
        initial_capital=10000.0,
        max_symbols=10,
        rebalance_interval_sec=30,
        leverage=3.0,
    )
    
    # Run for 5 minutes
    await trader.run(duration_minutes=5)


if __name__ == "__main__":
    asyncio.run(main())

