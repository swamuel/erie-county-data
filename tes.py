import pandas as pd
df = pd.read_csv("data/processed/tract_poi_stats.csv")
print(df.columns.tolist())
print(df.head(3).to_string())