#!/usr/bin/env python3
"""Check number of features generated."""

import pandas as pd
from src.bitget_trading.features import calculate_features, get_feature_columns

# Load data
df = pd.read_csv("data/SOL_USDT:USDT_30d.csv")

# Calculate features
df_features = calculate_features(df)
df_features = df_features.ffill().bfill().dropna()

# Get feature columns
feature_cols = get_feature_columns(df_features)

print(f"Total features: {len(feature_cols)}")
print(f"\nFeature columns:")
for i, col in enumerate(feature_cols, 1):
    print(f"{i}. {col}")

