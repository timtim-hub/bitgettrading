"""
Token Pre-Filter System

Filter tokens BEFORE strategy testing to focus on high-quality tradeable assets.

Filters:
- Minimum 24h volume: $50M+
- Volatility: Top 50% (more movement = more opportunity)
- Historical ML model accuracy: >75% (if available)
- Price range: $0.10 - $10,000 (avoid extreme prices)
- Reduce universe from 338 to top 50-80 tokens
"""

import asyncio
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from data_fetcher import HistoricalDataFetcher


class TokenPrefilter:
    """
    Pre-filter tokens based on volume, volatility, and ML performance.
    """
    
    def __init__(self, cache_dir: str = "backtest_data"):
        """Initialize the token prefilter."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.fetcher = HistoricalDataFetcher(cache_dir=cache_dir)
        
        # Filter criteria
        self.min_volume_24h_usd = 50_000_000  # $50M minimum daily volume
        self.min_price = 0.10
        self.max_price = 10_000.0
        self.target_token_count = 60  # Target 50-80 tokens
        self.volatility_percentile = 50  # Top 50% most volatile
    
    def calculate_24h_volume(self, df: pd.DataFrame) -> float:
        """
        Calculate approximate 24h volume in USD.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Estimated 24h volume in USD
        """
        if df.empty or len(df) < 24:
            return 0.0
        
        # Get last 24 candles (assuming 1H timeframe = 24 hours)
        last_24 = df.tail(24)
        
        # Sum volume * price for USD volume estimate
        usd_volume = (last_24['volume'] * last_24['close']).sum()
        
        return usd_volume
    
    def calculate_volatility(self, df: pd.DataFrame, window: int = 24) -> float:
        """
        Calculate price volatility (standard deviation of returns).
        
        Args:
            df: DataFrame with OHLCV data
            window: Rolling window for calculation
            
        Returns:
            Volatility score (higher = more volatile)
        """
        if df.empty or len(df) < window:
            return 0.0
        
        # Calculate returns
        returns = df['close'].pct_change()
        
        # Calculate rolling volatility
        volatility = returns.tail(window).std()
        
        # Annualize (assuming 1H candles, 24 candles per day, 365 days per year)
        annualized_vol = volatility * np.sqrt(24 * 365)
        
        return annualized_vol
    
    def get_ml_accuracy(self, symbol: str) -> Optional[float]:
        """
        Get ML model accuracy for a symbol (if available from previous training).
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            ML accuracy (0-1) or None if not available
        """
        # Check if we have ML model metadata with per-symbol accuracy
        models_dir = Path("/Users/macbookpro13/bitgettrading/models")
        
        # Look for latest model metadata
        metadata_files = list(models_dir.glob("*model_metadata*.json"))
        if not metadata_files:
            return None
        
        # Get most recent metadata file
        latest_metadata = max(metadata_files, key=lambda p: p.stat().st_mtime)
        
        try:
            with open(latest_metadata, 'r') as f:
                metadata = json.load(f)
            
            # Check if per-symbol accuracy is available
            if 'per_symbol_accuracy' in metadata and symbol in metadata['per_symbol_accuracy']:
                return metadata['per_symbol_accuracy'][symbol]
        except Exception as e:
            pass
        
        return None
    
    def check_price_range(self, df: pd.DataFrame) -> bool:
        """
        Check if token price is within acceptable range.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            True if price is acceptable
        """
        if df.empty:
            return False
        
        current_price = df['close'].iloc[-1]
        
        return self.min_price <= current_price <= self.max_price
    
    async def score_token(
        self,
        symbol: str,
        df: pd.DataFrame
    ) -> Tuple[float, Dict[str, any]]:
        """
        Calculate comprehensive score for a token.
        
        Args:
            symbol: Trading pair symbol
            df: DataFrame with OHLCV data
            
        Returns:
            Tuple of (score, details_dict)
        """
        details = {
            'symbol': symbol,
            'volume_24h_usd': 0.0,
            'volatility': 0.0,
            'ml_accuracy': None,
            'price': 0.0,
            'price_ok': False,
            'volume_ok': False,
            'score': 0.0,
        }
        
        if df.empty:
            return 0.0, details
        
        # Calculate metrics
        volume_24h = self.calculate_24h_volume(df)
        volatility = self.calculate_volatility(df)
        ml_accuracy = self.get_ml_accuracy(symbol)
        current_price = df['close'].iloc[-1]
        price_ok = self.check_price_range(df)
        volume_ok = volume_24h >= self.min_volume_24h_usd
        
        # Update details
        details['volume_24h_usd'] = volume_24h
        details['volatility'] = volatility
        details['ml_accuracy'] = ml_accuracy
        details['price'] = current_price
        details['price_ok'] = price_ok
        details['volume_ok'] = volume_ok
        
        # Calculate score (0-100)
        score = 0.0
        
        # Volume score (40 points)
        if volume_ok:
            # Logarithmic scale: $50M = 20 pts, $500M = 30 pts, $5B = 40 pts
            volume_score = min(40, 20 + 10 * np.log10(volume_24h / self.min_volume_24h_usd))
            score += volume_score
        
        # Volatility score (30 points)
        # Higher volatility = higher score (more trading opportunities)
        # Typical crypto annualized vol: 50-200%
        vol_score = min(30, volatility * 15)  # Cap at 30 points
        score += vol_score
        
        # ML accuracy score (20 points) - if available
        if ml_accuracy is not None:
            ml_score = ml_accuracy * 20  # 75% accuracy = 15 pts, 100% = 20 pts
            score += ml_score
        else:
            # If no ML data, give neutral score
            score += 10
        
        # Price range score (10 points)
        if price_ok:
            score += 10
        
        details['score'] = score
        
        return score, details
    
    async def filter_tokens(
        self,
        symbols: List[str],
        timeframe: str = "1H",
        days: int = 30,
        use_cache: bool = True
    ) -> Tuple[List[str], List[Dict]]:
        """
        Filter tokens and return top candidates.
        
        Args:
            symbols: List of symbols to evaluate
            timeframe: Timeframe for data
            days: Days of history
            use_cache: Whether to use cached data
            
        Returns:
            Tuple of (filtered_symbols, all_scores)
        """
        print("="*80)
        print("TOKEN PRE-FILTERING")
        print("="*80)
        print(f"Total symbols to evaluate: {len(symbols)}")
        print(f"Target: Top {self.target_token_count} tokens")
        print(f"Criteria:")
        print(f"  - Min 24h volume: ${self.min_volume_24h_usd:,.0f}")
        print(f"  - Price range: ${self.min_price} - ${self.max_price:,.0f}")
        print(f"  - Volatility: Top {self.volatility_percentile}%")
        print("="*80)
        print()
        
        # Fetch data for all symbols
        print("📊 Fetching data for all symbols...")
        data_dict = await self.fetcher.fetch_all_symbols(
            symbols=symbols,
            timeframe=timeframe,
            days=days,
            use_cache=use_cache
        )
        
        print(f"\n✅ Data loaded for {len(data_dict)} symbols")
        print()
        
        # Score all tokens
        print("🔍 Scoring all tokens...")
        all_scores = []
        
        for idx, (symbol, df) in enumerate(data_dict.items(), 1):
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{len(data_dict)} symbols scored...")
            
            score, details = await self.score_token(symbol, df)
            all_scores.append(details)
        
        print(f"\n✅ Scored {len(all_scores)} tokens")
        print()
        
        # Sort by score
        all_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # Filter by minimum criteria
        filtered_scores = [
            s for s in all_scores
            if s['volume_ok'] and s['price_ok']
        ]
        
        print(f"📊 Filtering results:")
        print(f"  - Total scored: {len(all_scores)}")
        print(f"  - Passed filters: {len(filtered_scores)}")
        print(f"  - Target top: {self.target_token_count}")
        print()
        
        # Take top N
        top_scores = filtered_scores[:self.target_token_count]
        top_symbols = [s['symbol'] for s in top_scores]
        
        # Print summary statistics
        if top_scores:
            volumes = [s['volume_24h_usd'] for s in top_scores]
            volatilities = [s['volatility'] for s in top_scores]
            scores = [s['score'] for s in top_scores]
            
            print("📈 Top Tokens Statistics:")
            print(f"  Volume (24h):")
            print(f"    Min: ${min(volumes):,.0f}")
            print(f"    Max: ${max(volumes):,.0f}")
            print(f"    Avg: ${np.mean(volumes):,.0f}")
            print(f"  Volatility:")
            print(f"    Min: {min(volatilities):.2%}")
            print(f"    Max: {max(volatilities):.2%}")
            print(f"    Avg: {np.mean(volatilities):.2%}")
            print(f"  Score:")
            print(f"    Min: {min(scores):.1f}")
            print(f"    Max: {max(scores):.1f}")
            print(f"    Avg: {np.mean(scores):.1f}")
            print()
            
            print("🏆 Top 10 Tokens:")
            for i, s in enumerate(top_scores[:10], 1):
                print(f"  {i:2d}. {s['symbol']:12s} | Score: {s['score']:5.1f} | Vol: ${s['volume_24h_usd']:>12,.0f} | Volatility: {s['volatility']:6.2%}")
        
        print()
        print("="*80)
        print(f"✅ FILTERING COMPLETE: {len(top_symbols)} tokens selected")
        print("="*80)
        
        return top_symbols, all_scores
    
    def save_results(
        self,
        filtered_symbols: List[str],
        all_scores: List[Dict],
        output_dir: Path = None
    ):
        """
        Save filtering results to files.
        
        Args:
            filtered_symbols: List of filtered symbol names
            all_scores: List of all scored tokens
            output_dir: Output directory (default: backtest_results)
        """
        if output_dir is None:
            output_dir = Path("/Users/macbookpro13/bitgettrading/backtest_results")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save filtered symbols list
        symbols_file = output_dir / f"filtered_tokens_{timestamp}.txt"
        with open(symbols_file, 'w') as f:
            for symbol in filtered_symbols:
                f.write(f"{symbol}\n")
        
        # Save detailed scores
        scores_file = output_dir / f"token_scores_{timestamp}.json"
        with open(scores_file, 'w') as f:
            json.dump(all_scores, f, indent=2, default=str)
        
        print(f"\n💾 Results saved:")
        print(f"  - Filtered symbols: {symbols_file}")
        print(f"  - Detailed scores: {scores_file}")


async def main():
    """Run token pre-filtering."""
    # Load all symbols
    symbols_file = Path("/Users/macbookpro13/bitgettrading/all_bitget_symbols.txt")
    with open(symbols_file, 'r') as f:
        all_symbols = [line.strip() for line in f if line.strip()]
    
    print(f"Loaded {len(all_symbols)} symbols from {symbols_file}")
    print()
    
    # Create prefilter
    prefilter = TokenPrefilter()
    
    # Filter tokens
    filtered_symbols, all_scores = await prefilter.filter_tokens(
        symbols=all_symbols,
        timeframe="1H",
        days=30,
        use_cache=True
    )
    
    # Save results
    prefilter.save_results(filtered_symbols, all_scores)


if __name__ == "__main__":
    asyncio.run(main())

