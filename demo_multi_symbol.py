#!/usr/bin/env python3
"""Demo multi-symbol cross-sectional ranking system."""

import asyncio

from src.bitget_trading.cross_sectional_ranker import CrossSectionalRanker
from src.bitget_trading.logger import setup_logging
from src.bitget_trading.multi_symbol_state import MultiSymbolStateManager
from src.bitget_trading.universe import UniverseManager

logger = setup_logging()


async def demo() -> None:
    """Demonstrate multi-symbol ranking system."""
    
    logger.info("=== MULTI-SYMBOL CROSS-SECTIONAL DEMO ===")
    
    # 1. Fetch universe of tradeable symbols
    logger.info("Step 1: Fetching all USDT-M futures contracts...")
    universe = UniverseManager(min_volume_24h=500_000, max_spread_bps=100)
    
    symbols = await universe.get_tradeable_universe()
    logger.info(f"Found {len(symbols)} tradeable symbols")
    logger.info(f"Top 20 symbols: {symbols[:20]}")
    
    # 2. Initialize multi-symbol state manager
    logger.info("\nStep 2: Initializing state manager...")
    state_manager = MultiSymbolStateManager()
    
    for symbol in symbols[:50]:  # Demo with top 50 for speed
        state_manager.add_symbol(symbol)
    
    # 3. Fetch current market data for all symbols
    logger.info("\nStep 3: Fetching current market data...")
    tickers = await universe.fetch_tickers()
    
    # Update state with ticker data
    for symbol in state_manager.symbols.keys():
        if symbol in tickers:
            ticker = tickers[symbol]
            state_manager.update_ticker(symbol, ticker)
            
            # Simulate some order book data
            mid = ticker["last_price"]
            spread = mid * 0.0005  # 5 bps
            state_manager.update_orderbook(symbol, {
                "bids": [[mid - spread/2, 1000], [mid - spread, 500]],
                "asks": [[mid + spread/2, 1000], [mid + spread, 500]],
            })
    
    # 4. Simulate some trade history for bandit
    logger.info("\nStep 4: Simulating trade history for bandit...")
    import random
    
    for symbol in list(state_manager.symbols.keys())[:20]:
        # Simulate 5-10 trades per symbol
        n_trades = random.randint(5, 10)
        for _ in range(n_trades):
            pnl = random.gauss(0.5, 5.0)  # Slightly positive expected
            return_pct = random.gauss(0.1, 2.0)
            state_manager.record_trade(symbol, pnl, return_pct)
    
    # 5. Rank symbols cross-sectionally
    logger.info("\nStep 5: Ranking symbols cross-sectionally...")
    ranker = CrossSectionalRanker(
        momentum_weight=0.4,
        imbalance_weight=0.3,
        volatility_weight=0.2,
        liquidity_weight=0.1,
        bandit_alpha=0.5,  # 50% rules, 50% bandit
        ucb_exploration=2.0,
    )
    
    top_symbols = ranker.rank_symbols(
        state_manager,
        top_k=15,
        min_spread_bps=50.0,
        min_depth=100.0,
    )
    
    logger.info(f"\n=== TOP 15 RANKED SYMBOLS ===")
    for i, (symbol, score) in enumerate(top_symbols, 1):
        state = state_manager.get_state(symbol)
        if state:
            logger.info(
                f"{i}. {symbol}: score={score:.4f} | "
                f"spread={state.spread_bps:.2f}bps | "
                f"imbalance={state.ob_imbalance:.3f} | "
                f"trades={state.n_trades} | "
                f"win_rate={state.get_win_rate():.2%}"
            )
    
    # 6. Allocate capital
    logger.info("\n=== CAPITAL ALLOCATION ===")
    allocations = ranker.allocate_capital(
        top_symbols,
        total_capital=10000.0,
        max_per_symbol_pct=0.15,
    )
    
    for symbol, capital in list(allocations.items())[:10]:
        logger.info(f"{symbol}: ${capital:.2f} ({capital/10000*100:.1f}%)")
    
    logger.info("\n=== DEMO COMPLETE ===")
    logger.info("\nKey features demonstrated:")
    logger.info("✓ Fetched all USDT-M futures contracts")
    logger.info("✓ Multi-symbol state management")
    logger.info("✓ Online trade statistics (no batch training)")
    logger.info("✓ Rule-based cross-sectional scoring")
    logger.info("✓ UCB bandit overlay for online learning")
    logger.info("✓ Capital allocation to top-ranked symbols")


if __name__ == "__main__":
    asyncio.run(demo())

