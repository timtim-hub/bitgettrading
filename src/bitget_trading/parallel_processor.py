"""Parallel processing for fast multi-symbol feature computation."""

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable

import numpy as np

from src.bitget_trading.logger import get_logger

logger = get_logger()


class ParallelProcessor:
    """
    Parallel processor for computing features across multiple symbols.
    
    Uses all available CPU cores to speed up computation by 8-10x.
    """
    
    def __init__(self, max_workers: int | None = None) -> None:
        """
        Initialize parallel processor.
        
        Args:
            max_workers: Max number of worker processes (None = use all cores)
        """
        self.max_workers = max_workers or mp.cpu_count()
        logger.info(f"🚀 Parallel processor initialized with {self.max_workers} workers")
    
    def compute_features_parallel(
        self,
        symbols: list[str],
        compute_func: Callable[[str], dict[str, float]],
        timeout: float = 5.0,
    ) -> dict[str, dict[str, float]]:
        """
        Compute features for multiple symbols in parallel.
        
        Args:
            symbols: List of symbol names
            compute_func: Function that takes symbol and returns features
            timeout: Timeout per symbol in seconds
        
        Returns:
            Dict of {symbol: features}
        """
        if len(symbols) == 0:
            return {}
        
        # For small number of symbols, just run sequentially (overhead not worth it)
        if len(symbols) < 4:
            return {symbol: compute_func(symbol) for symbol in symbols}
        
        results = {}
        
        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_symbol = {
                    executor.submit(compute_func, symbol): symbol
                    for symbol in symbols
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_symbol, timeout=timeout * len(symbols)):
                    symbol = future_to_symbol[future]
                    try:
                        features = future.result(timeout=timeout)
                        results[symbol] = features
                    except Exception as e:
                        logger.warning(f"Failed to compute features for {symbol}: {e}")
                        results[symbol] = {}
        
        except Exception as e:
            logger.error(f"Parallel processing failed: {e}")
            # Fallback to sequential
            results = {symbol: compute_func(symbol) for symbol in symbols}
        
        return results
    
    def rank_symbols_parallel(
        self,
        symbols: list[str],
        rank_func: Callable[[str], tuple[float, str]],
        timeout: float = 2.0,
    ) -> list[tuple[str, float, str]]:
        """
        Rank multiple symbols in parallel.
        
        Args:
            symbols: List of symbol names
            rank_func: Function that takes symbol and returns (score, side)
            timeout: Timeout per symbol in seconds
        
        Returns:
            List of (symbol, score, side) sorted by score (descending)
        """
        if len(symbols) == 0:
            return []
        
        # For small number, run sequentially
        if len(symbols) < 4:
            results = [(symbol, *rank_func(symbol)) for symbol in symbols]
            return sorted(results, key=lambda x: x[1], reverse=True)
        
        results = []
        
        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_symbol = {
                    executor.submit(rank_func, symbol): symbol
                    for symbol in symbols
                }
                
                for future in as_completed(future_to_symbol, timeout=timeout * len(symbols)):
                    symbol = future_to_symbol[future]
                    try:
                        score, side = future.result(timeout=timeout)
                        results.append((symbol, score, side))
                    except Exception as e:
                        logger.warning(f"Failed to rank {symbol}: {e}")
        
        except Exception as e:
            logger.error(f"Parallel ranking failed: {e}")
            # Fallback to sequential
            results = [(symbol, *rank_func(symbol)) for symbol in symbols]
        
        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results


# Singleton instance
_parallel_processor: ParallelProcessor | None = None


def get_parallel_processor() -> ParallelProcessor:
    """Get singleton parallel processor instance."""
    global _parallel_processor
    if _parallel_processor is None:
        _parallel_processor = ParallelProcessor()
    return _parallel_processor


def compute_features_batch(
    symbols: list[str],
    compute_func: Callable[[str], dict[str, float]],
) -> dict[str, dict[str, float]]:
    """
    Convenience function to compute features for multiple symbols in parallel.
    
    Args:
        symbols: List of symbol names
        compute_func: Function that takes symbol and returns features
    
    Returns:
        Dict of {symbol: features}
    """
    processor = get_parallel_processor()
    return processor.compute_features_parallel(symbols, compute_func)


def rank_symbols_batch(
    symbols: list[str],
    rank_func: Callable[[str], tuple[float, str]],
) -> list[tuple[str, float, str]]:
    """
    Convenience function to rank multiple symbols in parallel.
    
    Args:
        symbols: List of symbol names
        rank_func: Function that takes symbol and returns (score, side)
    
    Returns:
        List of (symbol, score, side) sorted by score
    """
    processor = get_parallel_processor()
    return processor.rank_symbols_parallel(symbols, rank_func)

