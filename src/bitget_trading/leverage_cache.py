"""Leverage cache to avoid redundant API calls on startup."""

import json
import time
from pathlib import Path
from typing import Any

from structlog import get_logger

logger = get_logger()


class LeverageCache:
    """
    Cache for tracking which symbols have leverage set.
    
    Since Bitget persists leverage settings on the exchange side,
    we don't need to set them every time. This cache tracks what
    we've already set to avoid ~600 API calls on every startup.
    """

    def __init__(self, cache_file: str = "leverage_cache.json", cache_expiry_hours: int = 24):
        """
        Initialize leverage cache.
        
        Args:
            cache_file: Path to cache file
            cache_expiry_hours: How long to trust cache entries (default: 24 hours)
        """
        self.cache_file = Path(cache_file)
        self.cache_expiry_seconds = cache_expiry_hours * 3600
        self.cache: dict[str, dict[str, Any]] = self._load_cache()
    
    def _load_cache(self) -> dict[str, dict[str, Any]]:
        """Load cache from disk."""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, "r") as f:
                cache = json.load(f)
                logger.info(
                    f"📂 [LEVERAGE CACHE] Loaded cache with {len(cache)} symbols from {self.cache_file}"
                )
                return cache
        except Exception as e:
            logger.warning(f"⚠️ [LEVERAGE CACHE] Failed to load cache: {e}")
            return {}
    
    def _save_cache(self) -> None:
        """Save cache to disk."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"❌ [LEVERAGE CACHE] Failed to save cache: {e}")
    
    def is_set(self, symbol: str, leverage: int, hold_side: str) -> bool:
        """
        Check if leverage is already set for this symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Desired leverage
            hold_side: "long" or "short"
        
        Returns:
            True if leverage is set and cache is fresh
        """
        cache_key = f"{symbol}_{hold_side}"
        
        if cache_key not in self.cache:
            return False
        
        entry = self.cache[cache_key]
        
        # Check if cache is expired
        age = time.time() - entry["timestamp"]
        if age > self.cache_expiry_seconds:
            logger.debug(
                f"⏰ [LEVERAGE CACHE] {symbol} {hold_side}: Cache expired (age: {age/3600:.1f}h)"
            )
            return False
        
        # Check if leverage matches
        if entry["leverage"] != leverage:
            logger.debug(
                f"🔄 [LEVERAGE CACHE] {symbol} {hold_side}: Leverage mismatch "
                f"(cached: {entry['leverage']}x, desired: {leverage}x)"
            )
            return False
        
        return True
    
    def mark_set(self, symbol: str, leverage: int, hold_side: str) -> None:
        """
        Mark leverage as set for this symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage value
            hold_side: "long" or "short"
        """
        cache_key = f"{symbol}_{hold_side}"
        
        self.cache[cache_key] = {
            "leverage": leverage,
            "timestamp": time.time(),
        }
        
        # Save to disk periodically (every 50 symbols)
        if len(self.cache) % 50 == 0:
            self._save_cache()
    
    def clear(self) -> None:
        """Clear entire cache."""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
        logger.info("🗑️ [LEVERAGE CACHE] Cache cleared")
    
    def save(self) -> None:
        """Explicitly save cache to disk."""
        self._save_cache()
        logger.info(f"💾 [LEVERAGE CACHE] Saved {len(self.cache)} entries to {self.cache_file}")

