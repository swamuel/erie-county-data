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
from shapely.geometry import Point
import warnings
warnings.filterwarnings("ignore")

# ── CONSTANTS ─────────────────────────────────────────────
PA_LAT_MAX  = 42.27
ERIE_FIPS   = ["049", "039"]
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
snap["type"]             = snap["store_type"].fillna(snap["store_type_raw"].fillna(""))
snap["subtype"]          = snap["store_type"].fillna(snap["store_type_raw"].fillna(""))
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

geometry = [Point(row.lon, row.lat) for _, row in df.iterrows()]
gdf_pois = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=CRS_GEO)
gdf_pois = gdf_pois.to_crs(CRS_METRIC)

joined = gpd.sjoin(gdf_pois, tracts[["TRACTCE", "geometry"]], how="left", predicate="within")
df["TRACTCE"] = joined["TRACTCE"].values
print(f"  {df['TRACTCE'].notna().sum()} POIs matched to a tract")
print(f"  {df['TRACTCE'].isna().sum()} outside tract boundaries")

# ── STEP 5: SAVE CLEAN POI FILE ───────────────────────────
out_pois = "data/raw/erie_pois.csv"
df.to_csv(out_pois, index=False)
print(f"\nSaved → {out_pois} ({len(df)} records)")

# ── STEP 6: TRACT-LEVEL COUNTS ────────────────────────────
print("\n" + "=" * 55)
print("STEP 5 — Tract-level metrics")
print("=" * 55)
tract_ids = tracts["TRACTCE"].unique()
rows = []

for tractce in tract_ids:
    row = {"TRACTCE": tractce}
    tract_pois = df[df["TRACTCE"] == tractce]

    for key, (pcat, ptype) in METRIC_CATEGORIES.items():
        subset = tract_pois[
            (tract_pois["primary_category"] == pcat) &
            (tract_pois["type"] == ptype)
        ]
        row[f"count_{key}"] = len(subset)

    # Aggregate counts
    food = tract_pois[tract_pois["primary_category"] == "Food & Grocery"]
    row["count_grocery_any"]      = len(food[food["type"].isin(FULL_SERVICE_TYPES)])
    row["count_snap_retailers"]   = int(tract_pois["snap_eligible"].sum())
    row["count_total_civic"]      = len(tract_pois[
        ~tract_pois["type"].isin(["Place of Worship", "Emergency Services"])
    ])
    rows.append(row)

stats = pd.DataFrame(rows)

# ── STEP 7: NEAREST DISTANCES ─────────────────────────────
print("Computing nearest distances...")
tracts_c = tracts[["TRACTCE", "geometry"]].copy()
tracts_c["centroid"] = tracts_c.geometry.centroid

# Nearest full-service grocery (any SNAP full-service type)
fs_pois = gdf_pois[
    (gdf_pois["primary_category"] == "Food & Grocery") &
    (gdf_pois["type"].isin(FULL_SERVICE_TYPES))
].copy()

distances = []
for _, tr in tracts_c.iterrows():
    ct = tr["centroid"]
    if ct is None or ct.is_empty or len(fs_pois) == 0:
        distances.append(np.nan)
    else:
        distances.append(fs_pois.geometry.distance(ct).min())

dist_df = pd.DataFrame({
    "TRACTCE": tracts_c["TRACTCE"].values,
    "nearest_grocery_full_m": distances
})
dist_df["nearest_grocery_full_miles"] = (dist_df["nearest_grocery_full_m"] / 1609.34).round(2)
stats = stats.merge(dist_df, on="TRACTCE", how="left")
print(f"  nearest grocery: max {dist_df['nearest_grocery_full_miles'].max():.1f} mi")

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
    ].copy()

    col_m  = f"nearest_{key}_m"
    col_mi = f"nearest_{key}_miles"

    if len(cat_pois) == 0:
        stats[col_m]  = np.nan
        stats[col_mi] = np.nan
        continue

    distances = []
    for _, tr in tracts_c.iterrows():
        ct = tr["centroid"]
        if ct is None or ct.is_empty:
            distances.append(np.nan)
        else:
            distances.append(cat_pois.geometry.distance(ct).min())

    d = pd.DataFrame({"TRACTCE": tracts_c["TRACTCE"].values, col_m: distances})
    d[col_mi] = (d[col_m] / 1609.34).round(2)
    stats = stats.merge(d, on="TRACTCE", how="left")
    print(f"  nearest {key}: max {d[col_mi].max():.1f} mi")

# ── STEP 8: SAVE STATS ────────────────────────────────────
out_stats = "data/processed/tract_poi_stats.csv"
stats.to_csv(out_stats, index=False)
print(f"\nSaved → {out_stats} ({len(stats)} tracts × {len(stats.columns)} columns)")

# Preview
print("\nFarthest tracts from nearest full-service grocery:")
preview = stats[["TRACTCE", "count_grocery_any", "nearest_grocery_full_miles"]].dropna()
preview = preview.sort_values("nearest_grocery_full_miles", ascending=False).head(10)
print(preview.to_string(index=False))

print("\nDone.")