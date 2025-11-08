"""
Quick script to update data fetcher with top 100 tokens
"""

# Read top 100 symbols
with open("top_100_symbols.txt") as f:
    symbols = [line.strip() for line in f if line.strip()]

print(f"✅ Loaded {len(symbols)} symbols")
print(f"First 10: {', '.join(symbols[:10])}")
print(f"Last 10: {', '.join(symbols[-10:])}")

# Create Python list format
symbols_str = '[\n    "' + '",\n    "'.join(symbols) + '",\n]'

print("\nCopy this to data_fetcher.py:")
print("="*80)
print(f"TEST_SYMBOLS = {symbols_str}")
print("="*80)
