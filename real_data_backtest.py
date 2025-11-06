#!/usr/bin/env python3
"""
Backtest using REAL market data from Bitget.

Uses actual price movements and cross-sectional ranking.
"""

import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.bitget_trading.logger import setup_logging

logger = setup_logging()


@dataclass
class MarketSnapshot:
    """Market data at a specific time."""
    
    timestamp: datetime
    snapshot: int
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    spread_pct: float
    return_pct: float
    volatility_pct: float
    volume_24h: float
    quote_volume_24h: float


@dataclass
class Position:
    """Trading position."""
    
    symbol: str
    side: str
    entry_price: float
    size: float
    capital: float
    entry_snapshot: int


class RealDataBacktester:
    """Backtest on real market data."""

    def __init__(
        self,
        initial_capital: float = 50.0,
        leverage: float = 50.0,
        position_size_pct: float = 0.10,
        max_positions: int = 10,
    ) -> None:
        """Initialize backtester."""
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.leverage = leverage
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        
        # State
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[tuple[int, float]] = []

    def load_data(self, filename: str) -> dict[int, list[MarketSnapshot]]:
        """
        Load real market data from CSV.
        
        Returns:
            Dict mapping snapshot_num -> list of MarketSnapshots
        """
        logger.info(f"Loading data from: {filename}")
        
        snapshots: dict[int, list[MarketSnapshot]] = defaultdict(list)
        
        with open(filename, "r") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                snapshot = MarketSnapshot(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    snapshot=int(row["snapshot"]),
                    symbol=row["symbol"],
                    last_price=float(row["last_price"]),
                    bid_price=float(row["bid_price"]),
                    ask_price=float(row["ask_price"]),
                    spread_pct=float(row["spread_pct"]),
                    return_pct=float(row["return_pct"]),
                    volatility_pct=float(row["volatility_pct"]),
                    volume_24h=float(row["volume_24h"]),
                    quote_volume_24h=float(row["quote_volume_24h"]),
                )
                
                snapshots[snapshot.snapshot].append(snapshot)
        
        logger.info(f"✅ Loaded {len(snapshots)} snapshots")
        logger.info(f"✅ Total symbols: {len(set(s.symbol for snaps in snapshots.values() for s in snaps))}")
        logger.info(f"✅ Data points per snapshot: ~{len(snapshots[0])}")
        
        return snapshots

    def calculate_signal(self, snapshot: MarketSnapshot, prev_snapshot: MarketSnapshot | None) -> tuple[str | None, float]:
        """
        Calculate trading signal based on real data.
        
        Uses:
        - Momentum: return_pct
        - Volatility: volatility_pct
        - Spread: spread_pct
        """
        # Filter: Skip if spread too wide
        if snapshot.spread_pct > 0.10:  # 0.1% max spread
            return None, 0.0
        
        # Filter: Skip low volume
        if snapshot.quote_volume_24h < 500_000:  # $500k min volume
            return None, 0.0
        
        # Calculate momentum score
        momentum = snapshot.return_pct
        
        # Adjust by volatility (prefer moderate volatility)
        volatility_factor = 1.0
        if snapshot.volatility_pct < 1.0:  # Too calm
            volatility_factor = 0.5
        elif snapshot.volatility_pct > 10.0:  # Too wild
            volatility_factor = 0.5
        else:  # Sweet spot
            volatility_factor = 1.0 + (snapshot.volatility_pct / 20.0)
        
        # Combined score
        score = abs(momentum) * volatility_factor
        
        # Need strong signal
        if score < 0.5:  # Min threshold
            return None, 0.0
        
        # Determine side
        if momentum > 0:
            side = "long"
        else:
            side = "short"
        
        return side, score

    def rank_symbols(self, snapshots: list[MarketSnapshot], prev_snapshots: dict[str, MarketSnapshot]) -> list[tuple[str, str, float]]:
        """
        Rank all symbols cross-sectionally.
        
        Returns:
            List of (symbol, side, score) sorted by score descending
        """
        signals = []
        
        for snapshot in snapshots:
            prev = prev_snapshots.get(snapshot.symbol)
            side, score = self.calculate_signal(snapshot, prev)
            
            if side and score > 0:
                signals.append((snapshot.symbol, side, score))
        
        # Sort by score descending
        signals.sort(key=lambda x: x[2], reverse=True)
        
        return signals

    def open_position(self, symbol: str, side: str, entry_price: float, snapshot_num: int) -> None:
        """Open a new position."""
        capital = self.capital * self.position_size_pct
        
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=(capital * self.leverage) / entry_price,
            capital=capital,
            entry_snapshot=snapshot_num,
        )
        
        self.positions[symbol] = position
        
        # Fee
        fee = capital * self.leverage * 0.0006
        self.capital -= fee

    def close_position(self, symbol: str, exit_price: float, snapshot_num: int) -> None:
        """Close an existing position."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Calculate PnL
        if position.side == "long":
            price_change_pct = (exit_price - position.entry_price) / position.entry_price
        else:
            price_change_pct = (position.entry_price - exit_price) / position.entry_price
        
        pnl_pct = price_change_pct * self.leverage
        pnl = position.capital * pnl_pct
        
        # Fee
        fee = position.capital * self.leverage * 0.0006
        pnl -= fee
        
        # Update capital
        self.capital += pnl
        
        # Record trade
        self.trades.append({
            "symbol": symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct * 100,
            "duration": snapshot_num - position.entry_snapshot,
        })
        
        # Remove position
        del self.positions[symbol]

    def run_backtest(self, data_file: str) -> None:
        """Run backtest on real data."""
        logger.info("="*70)
        logger.info("BACKTESTING ON REAL BITGET DATA")
        logger.info("="*70)
        logger.info(f"Initial Capital: ${self.initial_capital:.2f}")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Position Size: {self.position_size_pct*100}% per trade")
        logger.info(f"Max Positions: {self.max_positions}")
        logger.info("="*70 + "\n")
        
        # Load data
        snapshots = self.load_data(data_file)
        
        if not snapshots:
            logger.error("No data loaded!")
            return
        
        # Process each snapshot
        prev_snapshots: dict[str, MarketSnapshot] = {}
        
        for snapshot_num in sorted(snapshots.keys()):
            snapshot_data = snapshots[snapshot_num]
            
            # Rank symbols
            ranked = self.rank_symbols(snapshot_data, prev_snapshots)
            
            # Close positions not in top ranked
            top_symbols = {s[0] for s in ranked[:self.max_positions]}
            to_close = [sym for sym in self.positions.keys() if sym not in top_symbols]
            
            for symbol in to_close:
                # Find current price
                snap = next((s for s in snapshot_data if s.symbol == symbol), None)
                if snap:
                    self.close_position(symbol, snap.last_price, snapshot_num)
            
            # Open new positions
            for symbol, side, score in ranked[:self.max_positions]:
                if symbol in self.positions:
                    continue  # Already have position
                
                if len(self.positions) >= self.max_positions:
                    break  # Max positions reached
                
                # Find snapshot for this symbol
                snap = next((s for s in snapshot_data if s.symbol == symbol), None)
                if snap:
                    self.open_position(symbol, side, snap.last_price, snapshot_num)
            
            # Update equity curve
            equity = self.get_equity(snapshot_data)
            self.equity_curve.append((snapshot_num, equity))
            
            # Log progress
            if snapshot_num % 5 == 0:
                pnl_pct = ((equity - self.initial_capital) / self.initial_capital) * 100
                logger.info(
                    f"[Snapshot {snapshot_num:02d}] "
                    f"Equity: ${equity:.2f} ({pnl_pct:+.2f}%) | "
                    f"Positions: {len(self.positions)} | "
                    f"Trades: {len(self.trades)}"
                )
            
            # Update prev snapshots
            for snap in snapshot_data:
                prev_snapshots[snap.symbol] = snap
        
        # Close all remaining positions
        final_snapshot_data = snapshots[max(snapshots.keys())]
        for symbol in list(self.positions.keys()):
            snap = next((s for s in final_snapshot_data if s.symbol == symbol), None)
            if snap:
                self.close_position(symbol, snap.last_price, max(snapshots.keys()))
        
        # Print results
        self.print_results()

    def get_equity(self, snapshot_data: list[MarketSnapshot]) -> float:
        """Calculate current equity including unrealized PnL."""
        equity = self.capital
        
        for symbol, position in self.positions.items():
            snap = next((s for s in snapshot_data if s.symbol == symbol), None)
            if not snap:
                continue
            
            # Calculate unrealized PnL
            if position.side == "long":
                price_change_pct = (snap.last_price - position.entry_price) / position.entry_price
            else:
                price_change_pct = (position.entry_price - snap.last_price) / position.entry_price
            
            pnl_pct = price_change_pct * self.leverage
            pnl = position.capital * pnl_pct
            
            equity += pnl
        
        return equity

    def print_results(self) -> None:
        """Print backtest results."""
        logger.info("\n" + "="*70)
        logger.info("BACKTEST RESULTS")
        logger.info("="*70)
        
        final_capital = self.capital
        total_return = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        logger.info(f"Initial Capital:     ${self.initial_capital:.2f}")
        logger.info(f"Final Capital:       ${final_capital:.2f}")
        logger.info(f"Total Return:        {total_return:+.2f}%")
        logger.info(f"Total PnL:           ${final_capital - self.initial_capital:+.2f}")
        
        if not self.trades:
            logger.info("\nNo trades executed.")
            return
        
        logger.info(f"\nTotal Trades:        {len(self.trades)}")
        
        winners = [t for t in self.trades if t["pnl"] > 0]
        losers = [t for t in self.trades if t["pnl"] <= 0]
        
        logger.info(f"Winning Trades:      {len(winners)}")
        logger.info(f"Losing Trades:       {len(losers)}")
        
        if self.trades:
            win_rate = (len(winners) / len(self.trades)) * 100
            logger.info(f"Win Rate:            {win_rate:.1f}%")
        
        if winners:
            avg_win = sum(t["pnl"] for t in winners) / len(winners)
            logger.info(f"Average Win:         ${avg_win:.2f}")
        
        if losers:
            avg_loss = sum(t["pnl"] for t in losers) / len(losers)
            logger.info(f"Average Loss:        ${avg_loss:.2f}")
        
        # Top trades
        logger.info("\n" + "="*70)
        logger.info("TOP 10 TRADES")
        logger.info("="*70)
        
        top_trades = sorted(self.trades, key=lambda t: t["pnl"], reverse=True)[:10]
        for i, trade in enumerate(top_trades, 1):
            logger.info(
                f"{i:2d}. {trade['symbol']:12s} {trade['side']:5s} | "
                f"${trade['pnl']:+7.2f} ({trade['pnl_pct']:+6.1f}%) | "
                f"{trade['duration']} snapshots"
            )
        
        logger.info("="*70)


def main() -> None:
    """Run backtest on real data."""
    if len(sys.argv) < 2:
        logger.error("Usage: python real_data_backtest.py <data_file.csv>")
        logger.info("\nRun data collection first:")
        logger.info("  poetry run python collect_all_symbols_data.py")
        sys.exit(1)
    
    data_file = sys.argv[1]
    
    if not Path(data_file).exists():
        logger.error(f"Data file not found: {data_file}")
        sys.exit(1)
    
    backtester = RealDataBacktester(
        initial_capital=50.0,
        leverage=50.0,
        position_size_pct=0.10,
        max_positions=10,
    )
    
    backtester.run_backtest(data_file)


if __name__ == "__main__":
    main()

