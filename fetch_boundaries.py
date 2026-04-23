"""
One-time script to download Census TIGER shapefiles and save filtered
subsets for the 11-county NW PA region as local GeoParquet files.

Run this locally before deploying:
    python fetch_boundaries.py
"""

import geopandas as gpd
import pandas as pd
from pathlib import Path

from lib.constants import FIPS_LIST, STATE_FIPS

OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("Downloading PA tract shapefile...")
tracts = gpd.read_file(
    "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
)
tracts = tracts[tracts["COUNTYFP"].isin(FIPS_LIST)]
tracts = tracts[tracts["TRACTCE"] != "990000"]
tracts.to_parquet(OUT_DIR / "boundaries_tracts.parquet", index=False)
print(f"  Saved {len(tracts)} tracts")

print("Downloading US county shapefile...")
counties = gpd.read_file(
    "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
)
counties = counties[
    (counties["COUNTYFP"].isin(FIPS_LIST)) &
    (counties["STATEFP"] == STATE_FIPS)
]
counties.to_parquet(OUT_DIR / "boundaries_counties.parquet", index=False)
print(f"  Saved {len(counties)} counties")

print("Downloading US ZCTA shapefile (large — may take a minute)...")
zcta_cache = OUT_DIR / "region_zctas.csv"
if zcta_cache.exists():
    zcta_list = pd.read_csv(zcta_cache, dtype={"zcta": str})["zcta"].str.zfill(5).tolist()
else:
    raise FileNotFoundError("data/raw/region_zctas.csv not found — run fetch_zcta_data.py first")

zctas = gpd.read_file(
    "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
)
zctas = zctas[zctas["ZCTA5CE20"].isin(zcta_list)]
zctas["ZCTA5CE20"] = zctas["ZCTA5CE20"].astype(str).str.zfill(5)
zctas.to_parquet(OUT_DIR / "boundaries_zctas.parquet", index=False)
print(f"  Saved {len(zctas)} ZCTAs")

print("Done. Boundary files saved to data/raw/")
