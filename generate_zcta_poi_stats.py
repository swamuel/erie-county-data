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
from shapely.geometry import Point
import warnings
warnings.filterwarnings("ignore")

CRS_METRIC = "EPSG:32617"
CRS_GEO    = "EPSG:4326"
POI_PATH   = "data/raw/erie_pois.csv"
OUT_PATH   = "data/processed/zcta_poi_stats.csv"

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

geometry = [Point(row.lon, row.lat) for _, row in df.iterrows()]
gdf_pois = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=CRS_GEO)
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
rows = []
for zcta in gdf_zctas["ZCTA5CE20"].unique():
    row = {"ZCTA5CE20": zcta}
    zcta_pois = df[df["ZCTA5CE20"] == zcta]

    for key, (pcat, ptype) in METRIC_CATEGORIES.items():
        subset = zcta_pois[
            (zcta_pois["primary_category"] == pcat) &
            (zcta_pois["type"] == ptype)
        ]
        row[f"count_{key}"] = len(subset)

    food = zcta_pois[zcta_pois["primary_category"] == "Food & Grocery"]
    row["count_grocery_any"]    = len(food[food["type"].isin(FULL_SERVICE_TYPES)])
    row["count_snap_retailers"] = int(zcta_pois["snap_eligible"].sum())
    row["count_total_civic"]    = len(zcta_pois[
        ~zcta_pois["type"].isin(["Place of Worship", "Emergency Services"])
    ])
    rows.append(row)

stats = pd.DataFrame(rows)

# ── Nearest distances from ZCTA centroid ─────────────────────────────────────
print("Computing nearest distances from ZCTA centroids...")
zctas_c = gdf_zctas[["ZCTA5CE20", "geometry"]].copy()
zctas_c["centroid"] = zctas_c.geometry.centroid

# Nearest full-service grocery
fs_pois = gdf_pois[
    (gdf_pois["primary_category"] == "Food & Grocery") &
    (gdf_pois["type"].isin(FULL_SERVICE_TYPES))
].copy()

distances = []
for _, z in zctas_c.iterrows():
    ct = z["centroid"]
    if ct is None or ct.is_empty or len(fs_pois) == 0:
        distances.append(np.nan)
    else:
        distances.append(fs_pois.geometry.distance(ct).min())

dist_df = pd.DataFrame({
    "ZCTA5CE20": zctas_c["ZCTA5CE20"].values,
    "nearest_grocery_full_m": distances
})
dist_df["nearest_grocery_full_miles"] = (dist_df["nearest_grocery_full_m"] / 1609.34).round(2)
stats = stats.merge(dist_df, on="ZCTA5CE20", how="left")
print(f"  nearest grocery: max {dist_df['nearest_grocery_full_miles'].max():.1f} mi")

for key, (pcat, ptype) in NEAREST_CATS.items():
    cat_pois = gdf_pois[
        (gdf_pois["primary_category"] == pcat) &
        (gdf_pois["type"] == ptype)
    ].copy()

    col_m  = f"nearest_{key}_m"
    col_mi = f"nearest_{key}_miles"

    if len(cat_pois) == 0:
        stats[col_m]  = np.nan
        stats[col_mi] = np.nan
        continue

    distances = []
    for _, z in zctas_c.iterrows():
        ct = z["centroid"]
        distances.append(cat_pois.geometry.distance(ct).min() if ct and not ct.is_empty else np.nan)

    d = pd.DataFrame({"ZCTA5CE20": zctas_c["ZCTA5CE20"].values, col_m: distances})
    d[col_mi] = (d[col_m] / 1609.34).round(2)
    stats = stats.merge(d, on="ZCTA5CE20", how="left")
    print(f"  nearest {key}: max {d[col_mi].max():.1f} mi")

# ── Save ──────────────────────────────────────────────────────────────────────
stats.to_csv(OUT_PATH, index=False)
print(f"\nSaved → {OUT_PATH} ({len(stats)} ZCTAs × {len(stats.columns)} columns)")
print("\nTop ZCTAs by grocery count:")
print(stats[["ZCTA5CE20", "count_grocery_any", "nearest_grocery_full_miles"]]
      .sort_values("count_grocery_any", ascending=False).head(10).to_string(index=False))
print("\nDone.")
