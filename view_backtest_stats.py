#!/usr/bin/env python3
"""View backtest statistics file."""

import sys
from pathlib import Path

def main() -> None:
    """Display backtest statistics."""
    stats_file = Path("data/symbol_performance_stats.txt")
    
    if not stats_file.exists():
        print("❌ Stats file not found!")
        print(f"   Expected location: {stats_file.absolute()}")
        print("\n   The backtest system needs to run first.")
        print("   Stats will be generated after the initial backtest completes.")
        sys.exit(1)
    
    # Read and display file
    with open(stats_file, "r") as f:
        content = f.read()
    
    print(content)
    
    # Also show file location
    print("\n" + "=" * 80)
    print(f"📄 Stats file location: {stats_file.absolute()}")
    print("=" * 80)

if __name__ == "__main__":
    main()

