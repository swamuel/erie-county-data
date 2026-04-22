"""
process_pois.py — Build the unified erie_pois.csv and tract_poi_stats.csv.

Data sources:
  Food & Grocery  → USDA SNAP retailer data (data/raw/snap_retailers.csv)
  All other POIs  → OpenStreetMap data (data/raw/osm_pois_raw.csv)

Cleaning rules applied to OSM:
  - Exclude out-of-state (lat > 42.27)
  - Exclude all Food & Grocery records (replaced by SNAP)
  - Remove department stores
  - Fix Lions Eye Bank classification

Run with: python process_pois.py
Outputs:  data/raw/erie_pois.csv
          data/processed/tract_poi_stats.csv
"""

import pandas as pd
import geopandas as gpd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── CONSTANTS ─────────────────────────────────────────────
PA_LAT_MAX  = 42.27
from lib.constants import FIPS_LIST
ERIE_FIPS   = FIPS_LIST  # All 11 NW PA counties
TIGER_URL   = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
CRS_METRIC  = "EPSG:32617"
CRS_GEO     = "EPSG:4326"

DEPT_STORE_EXCLUDE = {
    "boscov's", "marshalls", "tj maxx", "jcpenney", "macy's", "kohl's", "burlington", "ross"
}

# Categories for tract-level metric computation
METRIC_CATEGORIES = {
    "grocery_supermarket":  ("Food & Grocery", "Supermarket"),
    "grocery_large":        ("Food & Grocery", "Large Grocery Store"),
    "grocery_medium":       ("Food & Grocery", "Medium Grocery Store"),
    "grocery_small":        ("Food & Grocery", "Small Grocery Store"),
    "grocery_combination":  ("Food & Grocery", "Combination Grocery/Other"),
    "grocery_specialty":    ("Food & Grocery", "Specialty Food Store"),
    "farmers_market":       ("Food & Grocery", "Farmers' Market"),
    "convenience":          ("Food & Grocery", "Convenience Store"),
    "pharmacy":             ("Health",         "Pharmacy"),
    "hospital":             ("Health",         "Hospital"),
    "clinic":               ("Health",         "Clinic"),
    "library":              ("Education & Civic", "Library"),
    "school":               ("Education & Civic", "School"),
    "community_center":     ("Civic & Social", "Community Center"),
    "social_services":      ("Civic & Social", "Social Services"),
}

# Convenience grouping — any full-service store (supermarket through combination)
FULL_SERVICE_TYPES = {
    "Supermarket", "Large Grocery Store", "Medium Grocery Store",
    "Small Grocery Store", "Combination Grocery/Other", "Specialty Food Store"
}

# ── STEP 1: LOAD AND CLEAN OSM (non-food only) ────────────
print("=" * 55)
print("STEP 1 — OSM data (non-food categories)")
print("=" * 55)
osm = pd.read_csv("data/raw/osm_pois_raw.csv")
print(f"  {len(osm)} raw OSM records")

osm = osm.dropna(subset=["lat", "lon"])

# Exclude out-of-state
before = len(osm)
osm = osm[osm["lat"] <= PA_LAT_MAX].copy()
print(f"  Removed {before - len(osm)} out-of-state records")

# Drop ALL Food & Grocery — replaced by SNAP
before = len(osm)
osm = osm[osm["primary_category"] != "Food & Grocery"].copy()
print(f"  Removed {before - len(osm)} Food & Grocery records (using SNAP instead)")

# Drop department stores (any remaining)
dept_mask = (
    (osm["type"] == "Big Box") &
    (osm["name"].str.lower().str.strip().isin(DEPT_STORE_EXCLUDE))
)
before = len(osm)
osm = osm[~dept_mask].copy()
if before - len(osm) > 0:
    print(f"  Removed {before - len(osm)} department stores")

# Fix Lions Eye Bank
lions_mask = osm["name"].str.lower().str.contains("lions eye", na=False)
if lions_mask.sum() > 0:
    osm.loc[lions_mask, "primary_category"] = "Health"
    osm.loc[lions_mask, "type"]             = "Clinic"
    osm.loc[lions_mask, "subtype"]          = "Medical Office"
    print(f"  Reclassified {lions_mask.sum()} Lions Eye Bank record(s)")

# Standardize columns
osm["snap_eligible"]    = False
osm["geocode_source"]   = osm["geocode_source"].fillna("openstreetmap")
osm["store_type"]       = osm["subtype"].fillna("")  # OSM uses subtype as the type label

# Keep only needed columns
osm_cols = [
    "name", "address", "primary_category", "type", "subtype",
    "store_type", "lat", "lon", "snap_eligible", "geocode_source"
]
osm = osm[[c for c in osm_cols if c in osm.columns]].copy()
osm = osm.reset_index(drop=True)

print(f"  {len(osm)} clean OSM records")
print("\n  By category:")
for cat, count in osm.groupby("primary_category").size().sort_values(ascending=False).items():
    print(f"    {cat}: {count}")

# ── STEP 2: LOAD AND CLEAN SNAP (food only) ───────────────
print("\n" + "=" * 55)
print("STEP 2 — USDA SNAP data (food & grocery)")
print("=" * 55)
snap = pd.read_csv("data/raw/snap_retailers.csv")
print(f"  {len(snap)} SNAP records")

snap = snap.dropna(subset=["lat", "lon"])
snap = snap[snap["lat"] != 0].copy()

# Standardize columns to match OSM schema
snap["primary_category"] = "Food & Grocery"
_snap_type               = snap.get("store_type", snap.get("store_type_raw", "")).fillna("")
snap["type"]             = _snap_type
snap["subtype"]          = _snap_type
snap["store_type"]       = _snap_type
snap["snap_eligible"]    = True
snap["geocode_source"]   = "usda_snap"

# Verify snap columns
print(f"  SNAP CSV columns: {list(snap.columns)}")
snap_cols = [
    "name", "address", "primary_category", "type", "subtype",
    "store_type", "lat", "lon", "snap_eligible", "geocode_source"
]
snap = snap[[c for c in snap_cols if c in snap.columns]].copy()
print(f"  SNAP kept columns: {list(snap.columns)}")
snap = snap.reset_index(drop=True)

print(f"  {len(snap)} clean SNAP records")
print("\n  By store type:")
for t, count in snap["type"].value_counts().items():
    print(f"    {t}: {count}")

# ── STEP 3: COMBINE ───────────────────────────────────────
print("\n" + "=" * 55)
print("STEP 3 — Combining OSM + SNAP")
print("=" * 55)
df = pd.concat([snap, osm], ignore_index=True)
print(f"  {len(df)} total records")
print(f"  SNAP (food): {snap['snap_eligible'].sum()}")
print(f"  OSM (non-food): {len(osm)}")

# ── STEP 4: SPATIAL JOIN ──────────────────────────────────
print("\n" + "=" * 55)
print("STEP 4 — Spatial join to tracts")
print("=" * 55)
tracts = gpd.read_file(TIGER_URL)
tracts = tracts[
    tracts["COUNTYFP"].isin(ERIE_FIPS) &
    (tracts["TRACTCE"] != "990000")
].copy()
tracts = tracts.to_crs(CRS_METRIC)
print(f"  {len(tracts)} tracts loaded")

gdf_pois = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_GEO)
gdf_pois = gdf_pois.to_crs(CRS_METRIC)

joined = gpd.sjoin(gdf_pois, tracts[["TRACTCE", "geometry"]], how="left", predicate="within")
df["TRACTCE"] = joined["TRACTCE"].values
print(f"  {df['TRACTCE'].notna().sum()} POIs matched to a tract")
print(f"  {df['TRACTCE'].isna().sum()} outside tract boundaries")

# ── STEP 5: SAVE CLEAN POI FILE ───────────────────────────
out_pois = "data/raw/erie_pois.csv"
df.to_csv(out_pois, index=False)
print(f"\nSaved: {out_pois} ({len(df)} records)")

# ── STEP 6: TRACT-LEVEL COUNTS ────────────────────────────
print("\n" + "=" * 55)
print("STEP 5 — Tract-level metrics")
print("=" * 55)
tract_ids = tracts["TRACTCE"].unique()
stats = pd.DataFrame({"TRACTCE": tract_ids})

# Count by (TRACTCE, primary_category, type) in one pass
count_df = (
    df.groupby(["TRACTCE", "primary_category", "type"], dropna=False)
    .size().reset_index(name="n")
)
for key, (pcat, ptype) in METRIC_CATEGORIES.items():
    mask = (count_df["primary_category"] == pcat) & (count_df["type"] == ptype)
    sub = count_df[mask][["TRACTCE", "n"]].rename(columns={"n": f"count_{key}"})
    stats = stats.merge(sub, on="TRACTCE", how="left")
    stats[f"count_{key}"] = stats[f"count_{key}"].fillna(0).astype(int)

# Aggregate counts
food_df = df[df["primary_category"] == "Food & Grocery"]
full_service_counts = (
    food_df[food_df["type"].isin(FULL_SERVICE_TYPES)]
    .groupby("TRACTCE").size().rename("count_grocery_any")
)
snap_counts = df[df["snap_eligible"].astype(bool)].groupby("TRACTCE").size().rename("count_snap_retailers")
civic_counts = (
    df[~df["type"].isin(["Place of Worship", "Emergency Services"])]
    .groupby("TRACTCE").size().rename("count_total_civic")
)
stats = (stats
    .merge(full_service_counts.reset_index(), on="TRACTCE", how="left")
    .merge(snap_counts.reset_index(), on="TRACTCE", how="left")
    .merge(civic_counts.reset_index(), on="TRACTCE", how="left")
)
for col in ["count_grocery_any", "count_snap_retailers", "count_total_civic"]:
    stats[col] = stats[col].fillna(0).astype(int)

# ── STEP 7: NEAREST DISTANCES ─────────────────────────────
print("Computing nearest distances...")
tract_centroids = tracts[["TRACTCE", "geometry"]].copy()
tract_centroids = tract_centroids.set_geometry(tract_centroids.geometry.centroid)

# Nearest full-service grocery (any SNAP full-service type)
fs_pois = gdf_pois[
    (gdf_pois["primary_category"] == "Food & Grocery") &
    (gdf_pois["type"].isin(FULL_SERVICE_TYPES))
][["geometry"]].copy()

if len(fs_pois) > 0:
    nearest = gpd.sjoin_nearest(
        tract_centroids, fs_pois, how="left", distance_col="nearest_grocery_full_m"
    )[["TRACTCE", "nearest_grocery_full_m"]].drop_duplicates("TRACTCE")
else:
    nearest = tract_centroids[["TRACTCE"]].copy()
    nearest["nearest_grocery_full_m"] = np.nan

nearest["nearest_grocery_full_miles"] = (nearest["nearest_grocery_full_m"] / 1609.34).round(2)
stats = stats.merge(nearest, on="TRACTCE", how="left")
print(f"  nearest grocery: max {nearest['nearest_grocery_full_miles'].max():.1f} mi")

# Nearest for other key categories
other_cats = {
    "pharmacy":         ("Health",         "Pharmacy"),
    "hospital":         ("Health",         "Hospital"),
    "clinic":           ("Health",         "Clinic"),
    "library":          ("Education & Civic", "Library"),
    "community_center": ("Civic & Social", "Community Center"),
    "social_services":  ("Civic & Social", "Social Services"),
}

for key, (pcat, ptype) in other_cats.items():
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
        tract_centroids, cat_pois, how="left", distance_col=col_m
    )[["TRACTCE", col_m]].drop_duplicates("TRACTCE")
    d[col_mi] = (d[col_m] / 1609.34).round(2)
    stats = stats.merge(d, on="TRACTCE", how="left")
    print(f"  nearest {key}: max {d[col_mi].max():.1f} mi")

# ── STEP 8: SAVE STATS ────────────────────────────────────
out_stats = "data/processed/tract_poi_stats.csv"
stats.to_csv(out_stats, index=False)
print(f"\nSaved: {out_stats} ({len(stats)} tracts x {len(stats.columns)} columns)")

# Preview
print("\nFarthest tracts from nearest full-service grocery:")
preview = stats[["TRACTCE", "count_grocery_any", "nearest_grocery_full_miles"]].dropna()
preview = preview.sort_values("nearest_grocery_full_miles", ascending=False).head(10)
print(preview.to_string(index=False))

print("\nDone.")