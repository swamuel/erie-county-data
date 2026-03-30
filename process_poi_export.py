import pandas as pd
import geopandas as gpd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
POI_IN  = Path("data/raw/erie_pois.csv")
OUT     = Path("data/processed/erie_crawford_pois_clean.csv")
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Load POIs ─────────────────────────────────────────────────────────────────
pois = pd.read_csv(POI_IN)
print(f"Loaded {len(pois):,} POIs")
print(f"Columns: {pois.columns.tolist()}")

# Drop rows missing coordinates
pois = pois.dropna(subset=["lat", "lon"]).copy()
print(f"After dropping missing coords: {len(pois):,} POIs")

# Convert to GeoDataFrame
gdf_pois = gpd.GeoDataFrame(
    pois,
    geometry=gpd.points_from_xy(pois["lon"], pois["lat"]),
    crs="EPSG:4326"
)

# ── Load tract boundaries ─────────────────────────────────────────────────────
print("Loading tract boundaries from Census TIGER...")
tract_url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
tracts = gpd.read_file(tract_url)
tracts = tracts[tracts["COUNTYFP"].isin(["049", "039"])]
tracts = tracts[tracts["TRACTCE"] != "990000"]
print(f"Loaded {len(tracts):,} tracts")

# Ensure same CRS
gdf_pois = gdf_pois.to_crs(tracts.crs)

# ── Spatial join — assign tract to each POI ───────────────────────────────────
joined = gpd.sjoin(gdf_pois, tracts[["GEOID", "TRACTCE", "NAMELSAD", "COUNTYFP", "geometry"]],
                   how="left", predicate="within")

# Some POIs may fall outside tract boundaries (e.g. on water) — flag them
outside = joined["GEOID"].isna().sum()
if outside > 0:
    print(f"  ⚠ {outside} POIs did not fall within any tract (may be on boundaries/water)")

# ── Add county name ───────────────────────────────────────────────────────────
joined["county"] = joined["COUNTYFP"].map({"049": "Erie", "039": "Crawford"})

# ── Clean snap_eligible ───────────────────────────────────────────────────────
if "snap_eligible" in joined.columns:
    joined["snap_eligible"] = joined["snap_eligible"].astype(str).str.lower() == "true"
else:
    joined["snap_eligible"] = joined.get("geocode_source", "") == "usda_snap"

joined["snap_eligible"] = joined["snap_eligible"].map({True: "Yes", False: "No"}).fillna("No")

# ── Select and rename export columns ─────────────────────────────────────────
export_cols = [
    "GEOID", "TRACTCE", "NAMELSAD", "county",
    "name", "address", "lat", "lon",
    "primary_category", "type", "subtype",
    "snap_eligible",
]

# Only keep columns that exist
export_cols = [c for c in export_cols if c in joined.columns]
out_df = joined[export_cols].copy()

out_df = out_df.rename(columns={
    "GEOID":    "tract_geoid",
    "TRACTCE":  "tract_code",
    "NAMELSAD": "tract_name",
})

out_df = out_df.sort_values(["county", "tract_geoid", "primary_category", "name"]).reset_index(drop=True)

# ── Save ──────────────────────────────────────────────────────────────────────
out_df.to_csv(OUT, index=False)

print(f"\n✓ Saved {len(out_df):,} POIs → {OUT}")
print()
print("By county:")
print(out_df["county"].value_counts().to_string())
print()
print("By category:")
print(out_df["primary_category"].value_counts().to_string())
print()
print("SNAP-eligible stores:")
print(out_df["snap_eligible"].value_counts().to_string())
print()
print("POIs with tract assigned:", out_df["tract_geoid"].notna().sum())
print("POIs without tract:      ", out_df["tract_geoid"].isna().sum())