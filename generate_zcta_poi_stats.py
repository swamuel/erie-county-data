"""
generate_zcta_poi_stats.py
Aggregates erie_pois.csv to ZIP Code (ZCTA) level — counts per category
and nearest-distance metrics from each ZCTA centroid.

Mirrors the logic in process_pois.py but joins to ZCTA boundaries instead
of census tract boundaries.

Run with:  python generate_zcta_poi_stats.py
Output:    data/processed/zcta_poi_stats.csv
"""

import pandas as pd
import geopandas as gpd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

CRS_METRIC = "EPSG:32617"
CRS_GEO    = "EPSG:4326"
POI_PATH   = "data/raw/erie_pois.csv"
OUT_PATH   = "data/processed/zcta_poi_stats.csv"

# Load ZCTA list from cache produced by fetch_zcta_data.py
from pathlib import Path
import pandas as _zcta_pd
_zcta_cache = Path("data/raw/region_zctas.csv")
if _zcta_cache.exists():
    ZCTA_LIST = _zcta_pd.read_csv(_zcta_cache, dtype={"zcta": str})["zcta"].str.zfill(5).tolist()
    print(f"Using {len(ZCTA_LIST)} ZCTAs from cache")
else:
    # Fallback: Erie+Crawford only until fetch_zcta_data.py has been run
    ZCTA_LIST = [str(z).zfill(5) for z in [
    16110, 16111, 16131, 16134, 16314, 16316, 16327, 16328, 16335,
    16354, 16360, 16403, 16404, 16406, 16422, 16424, 16432, 16433,
    16434, 16435, 16440, 16401, 16407, 16410, 16411, 16412, 16413,
    16415, 16417, 16421, 16423, 16426, 16427, 16428, 16430, 16438,
    16441, 16442, 16443, 16501, 16502, 16503, 16504, 16505, 16506,
    16507, 16508, 16509, 16510, 16511, 16563
]]

METRIC_CATEGORIES = {
    "grocery_supermarket":  ("Food & Grocery", "Supermarket"),
    "grocery_large":        ("Food & Grocery", "Large Grocery Store"),
    "grocery_medium":       ("Food & Grocery", "Medium Grocery Store"),
    "grocery_small":        ("Food & Grocery", "Small Grocery Store"),
    "grocery_combination":  ("Food & Grocery", "Combination Grocery/Other"),
    "grocery_specialty":    ("Food & Grocery", "Specialty Food Store"),
    "farmers_market":       ("Food & Grocery", "Farmers' Market"),
    "convenience":          ("Food & Grocery", "Convenience Store"),
    "pharmacy":             ("Health",           "Pharmacy"),
    "hospital":             ("Health",           "Hospital"),
    "clinic":               ("Health",           "Clinic"),
    "library":              ("Education & Civic","Library"),
    "school":               ("Education & Civic","School"),
    "community_center":     ("Civic & Social",   "Community Center"),
    "social_services":      ("Civic & Social",   "Social Services"),
}

FULL_SERVICE_TYPES = {
    "Supermarket", "Large Grocery Store", "Medium Grocery Store",
    "Small Grocery Store", "Combination Grocery/Other", "Specialty Food Store"
}

NEAREST_CATS = {
    "pharmacy":         ("Health",           "Pharmacy"),
    "hospital":         ("Health",           "Hospital"),
    "clinic":           ("Health",           "Clinic"),
    "library":          ("Education & Civic","Library"),
    "community_center": ("Civic & Social",   "Community Center"),
    "social_services":  ("Civic & Social",   "Social Services"),
}

# ── Load POIs ─────────────────────────────────────────────────────────────────
print("Loading POI data...")
df = pd.read_csv(POI_PATH)
df = df.dropna(subset=["lat", "lon"])
print(f"  {len(df):,} POIs loaded")

gdf_pois = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GEO)
gdf_pois = gdf_pois.to_crs(CRS_METRIC)

# ── Load ZCTA boundaries ──────────────────────────────────────────────────────
print("Loading ZCTA boundaries...")
zcta_url = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
gdf_zctas = gpd.read_file(zcta_url)
gdf_zctas = gdf_zctas[gdf_zctas["ZCTA5CE20"].isin(ZCTA_LIST)].copy()
gdf_zctas = gdf_zctas.to_crs(CRS_METRIC)
print(f"  {len(gdf_zctas)} ZCTAs loaded")

# ── Spatial join: POIs → ZCTAs ────────────────────────────────────────────────
print("Joining POIs to ZCTAs...")
joined = gpd.sjoin(gdf_pois, gdf_zctas[["ZCTA5CE20", "geometry"]], how="left", predicate="within")
df["ZCTA5CE20"] = joined["ZCTA5CE20"].values
print(f"  {df['ZCTA5CE20'].notna().sum():,} POIs matched to a ZCTA")
print(f"  {df['ZCTA5CE20'].isna().sum():,} POIs outside ZCTA boundaries")

# ── ZCTA-level counts ─────────────────────────────────────────────────────────
print("Computing counts per ZCTA...")
zcta_ids = gdf_zctas["ZCTA5CE20"].unique()
stats = pd.DataFrame({"ZCTA5CE20": zcta_ids})

count_df = (
    df.groupby(["ZCTA5CE20", "primary_category", "type"], dropna=False)
    .size().reset_index(name="n")
)
for key, (pcat, ptype) in METRIC_CATEGORIES.items():
    mask = (count_df["primary_category"] == pcat) & (count_df["type"] == ptype)
    sub = count_df[mask][["ZCTA5CE20", "n"]].rename(columns={"n": f"count_{key}"})
    stats = stats.merge(sub, on="ZCTA5CE20", how="left")
    stats[f"count_{key}"] = stats[f"count_{key}"].fillna(0).astype(int)

food_df = df[df["primary_category"] == "Food & Grocery"]
full_service_counts = (
    food_df[food_df["type"].isin(FULL_SERVICE_TYPES)]
    .groupby("ZCTA5CE20").size().rename("count_grocery_any")
)
snap_counts = df[df["snap_eligible"].astype(bool)].groupby("ZCTA5CE20").size().rename("count_snap_retailers")
civic_counts = (
    df[~df["type"].isin(["Place of Worship", "Emergency Services"])]
    .groupby("ZCTA5CE20").size().rename("count_total_civic")
)
stats = (stats
    .merge(full_service_counts.reset_index(), on="ZCTA5CE20", how="left")
    .merge(snap_counts.reset_index(), on="ZCTA5CE20", how="left")
    .merge(civic_counts.reset_index(), on="ZCTA5CE20", how="left")
)
for col in ["count_grocery_any", "count_snap_retailers", "count_total_civic"]:
    stats[col] = stats[col].fillna(0).astype(int)

# ── Nearest distances from ZCTA centroid ─────────────────────────────────────
print("Computing nearest distances from ZCTA centroids...")
zcta_centroids = gdf_zctas[["ZCTA5CE20", "geometry"]].copy()
zcta_centroids = zcta_centroids.set_geometry(zcta_centroids.geometry.centroid)

# Nearest full-service grocery
fs_pois = gdf_pois[
    (gdf_pois["primary_category"] == "Food & Grocery") &
    (gdf_pois["type"].isin(FULL_SERVICE_TYPES))
][["geometry"]].copy()

if len(fs_pois) > 0:
    nearest = gpd.sjoin_nearest(
        zcta_centroids, fs_pois, how="left", distance_col="nearest_grocery_full_m"
    )[["ZCTA5CE20", "nearest_grocery_full_m"]].drop_duplicates("ZCTA5CE20")
else:
    nearest = zcta_centroids[["ZCTA5CE20"]].copy()
    nearest["nearest_grocery_full_m"] = np.nan

nearest["nearest_grocery_full_miles"] = (nearest["nearest_grocery_full_m"] / 1609.34).round(2)
stats = stats.merge(nearest, on="ZCTA5CE20", how="left")
print(f"  nearest grocery: max {nearest['nearest_grocery_full_miles'].max():.1f} mi")

for key, (pcat, ptype) in NEAREST_CATS.items():
    cat_pois = gdf_pois[
        (gdf_pois["primary_category"] == pcat) &
        (gdf_pois["type"] == ptype)
    ][["geometry"]].copy()

    col_m  = f"nearest_{key}_m"
    col_mi = f"nearest_{key}_miles"

    if len(cat_pois) == 0:
        stats[col_m]  = np.nan
        stats[col_mi] = np.nan
        continue

    d = gpd.sjoin_nearest(
        zcta_centroids, cat_pois, how="left", distance_col=col_m
    )[["ZCTA5CE20", col_m]].drop_duplicates("ZCTA5CE20")
    d[col_mi] = (d[col_m] / 1609.34).round(2)
    stats = stats.merge(d, on="ZCTA5CE20", how="left")
    print(f"  nearest {key}: max {d[col_mi].max():.1f} mi")

# ── Save ──────────────────────────────────────────────────────────────────────
stats.to_csv(OUT_PATH, index=False)
print(f"\nSaved: {OUT_PATH} ({len(stats)} ZCTAs x {len(stats.columns)} columns)")
print("\nTop ZCTAs by grocery count:")
print(stats[["ZCTA5CE20", "count_grocery_any", "nearest_grocery_full_miles"]]
      .sort_values("count_grocery_any", ascending=False).head(10).to_string(index=False))
print("\nDone.")
