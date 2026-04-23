"""
generate_zcta_access_stats.py
Builds zcta_access_stats.csv for the Desert Analysis tab.

Extends zcta_poi_stats with:
  - nearest_pantry_miles  (from pantry_locations.csv, Food Pantry type only)
  - nearest_snap_miles    (from erie_pois.csv where snap_eligible == True)
  - ACS rate variables from zcta_data (most recent year)
  - no_insurance_rate from cdc_places_zcta
  - area_name, county_name, total_population

Run:    python generate_zcta_access_stats.py
Prereq: python process_agency_list.py  (to generate pantry_locations.csv)
Output: data/processed/zcta_access_stats.csv
"""
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

CRS_METRIC = "EPSG:32617"
CRS_GEO    = "EPSG:4326"

ZCTA_POI_PATH   = "data/processed/zcta_poi_stats.csv"
PANTRY_PATH     = "data/processed/pantry_locations.csv"
POI_PATH        = "data/raw/erie_pois.csv"
ZCTA_DATA_PATH  = "data/raw/zcta_data.csv"
CDC_ZCTA_PATH   = "data/raw/cdc_places_zcta.csv"
BOUNDARIES_PATH = "data/raw/boundaries_zctas.parquet"
OUT_PATH        = "data/processed/zcta_access_stats.csv"


def add_nearest_distance(zcta_centroids, gdf_points, col_miles, stats):
    """Compute nearest distance from each ZCTA centroid to any point in gdf_points."""
    col_m = col_miles.replace("_miles", "_m")
    if len(gdf_points) == 0:
        stats[col_miles] = np.nan
        return stats
    d = gpd.sjoin_nearest(
        zcta_centroids,
        gdf_points[["geometry"]],
        how="left",
        distance_col=col_m,
    )[["ZCTA5CE20", col_m]].drop_duplicates("ZCTA5CE20")
    d[col_miles] = (d[col_m] / 1609.34).round(2)
    stats = stats.merge(d[["ZCTA5CE20", col_miles]], on="ZCTA5CE20", how="left")
    print(f"  {col_miles}: max {d[col_miles].max():.1f} mi")
    return stats


def main():
    # ── Base: zcta_poi_stats ──────────────────────────────────
    print("Loading zcta_poi_stats...")
    stats = pd.read_csv(ZCTA_POI_PATH, dtype={"ZCTA5CE20": str})
    stats["ZCTA5CE20"] = stats["ZCTA5CE20"].str.zfill(5)
    if "nearest_grocery_full_miles" in stats.columns:
        stats = stats.rename(columns={"nearest_grocery_full_miles": "nearest_grocery_miles"})
    if "nearest_grocery_full_m" in stats.columns:
        stats = stats.drop(columns=["nearest_grocery_full_m"])
    print(f"  {len(stats)} ZCTAs, {len(stats.columns)} base columns")

    # ── ZCTA centroids from boundary parquet ──────────────────
    print("Loading ZCTA boundaries...")
    gdf_zctas = gpd.read_parquet(BOUNDARIES_PATH)
    gdf_zctas = gdf_zctas.to_crs(CRS_METRIC)
    zcta_centroids = gdf_zctas[["ZCTA5CE20", "geometry"]].copy()
    zcta_centroids = zcta_centroids.set_geometry(zcta_centroids.geometry.centroid)
    zcta_centroids = zcta_centroids[zcta_centroids["ZCTA5CE20"].isin(stats["ZCTA5CE20"])]
    print(f"  {len(zcta_centroids)} ZCTA centroids")

    # ── Nearest food pantry ───────────────────────────────────
    print("Computing nearest_pantry_miles...")
    if Path(PANTRY_PATH).exists():
        pantries = pd.read_csv(PANTRY_PATH)
        food_pantries = pantries[
            pantries["program_type"] == "Food Pantry"
        ].dropna(subset=["lat", "lon"])
        print(f"  {len(food_pantries)} Food Pantry locations with coordinates")
        gdf_p = gpd.GeoDataFrame(
            food_pantries,
            geometry=gpd.points_from_xy(food_pantries["lon"], food_pantries["lat"]),
            crs=CRS_GEO,
        ).to_crs(CRS_METRIC)
        stats = add_nearest_distance(zcta_centroids, gdf_p, "nearest_pantry_miles", stats)
    else:
        print("  pantry_locations.csv not found — run process_agency_list.py first")
        stats["nearest_pantry_miles"] = np.nan

    # ── Nearest SNAP-eligible store ───────────────────────────
    print("Computing nearest_snap_miles...")
    if Path(POI_PATH).exists():
        pois = pd.read_csv(POI_PATH)
        if "snap_eligible" in pois.columns:
            snap_mask = pois["snap_eligible"].astype(str).str.lower() == "true"
        else:
            snap_mask = pois.get("geocode_source", pd.Series(dtype=str)) == "usda_snap"
        snap_pois = pois[snap_mask].dropna(subset=["lat", "lon"])
        print(f"  {len(snap_pois)} SNAP-eligible locations with coordinates")
        gdf_s = gpd.GeoDataFrame(
            snap_pois,
            geometry=gpd.points_from_xy(snap_pois["lon"], snap_pois["lat"]),
            crs=CRS_GEO,
        ).to_crs(CRS_METRIC)
        stats = add_nearest_distance(zcta_centroids, gdf_s, "nearest_snap_miles", stats)
    else:
        print("  erie_pois.csv not found — skipping SNAP distances")
        stats["nearest_snap_miles"] = np.nan

    # ── ACS rate variables (most recent year) ─────────────────
    print("Joining ACS rate variables...")
    zcta_df = pd.read_csv(ZCTA_DATA_PATH, dtype={"zcta": str})
    zcta_df["zcta"] = zcta_df["zcta"].str.zfill(5)
    most_recent = zcta_df["year"].max()
    zcta_recent = zcta_df[zcta_df["year"] == most_recent].copy()
    print(f"  Using ACS year: {most_recent}")

    acs_cols = [c for c in [
        "no_vehicle_rate", "poverty_rate", "median_household_income",
        "total_population", "area_name", "county_name", "unemployment_rate",
    ] if c in zcta_recent.columns]

    stats = stats.merge(
        zcta_recent[["zcta"] + acs_cols].rename(columns={"zcta": "ZCTA5CE20"}),
        on="ZCTA5CE20", how="left",
    )
    print(f"  Joined: {acs_cols}")

    # ── no_insurance_rate from CDC PLACES ZCTA ────────────────
    if Path(CDC_ZCTA_PATH).exists():
        cdc = pd.read_csv(CDC_ZCTA_PATH, dtype={"zcta": str})
        cdc["zcta"] = cdc["zcta"].str.zfill(5)
        if "no_insurance_rate" in cdc.columns:
            stats = stats.merge(
                cdc[["zcta", "no_insurance_rate"]].rename(columns={"zcta": "ZCTA5CE20"}),
                on="ZCTA5CE20", how="left",
            )
            print("  Joined no_insurance_rate from CDC PLACES ZCTA")
    if "no_insurance_rate" not in stats.columns:
        stats["no_insurance_rate"] = np.nan

    # ── Save ──────────────────────────────────────────────────
    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH}")
    print(f"  {len(stats)} ZCTAs × {len(stats.columns)} columns")

    key_cols = [
        "ZCTA5CE20", "area_name", "county_name", "total_population",
        "nearest_pantry_miles", "nearest_snap_miles", "nearest_grocery_miles",
        "nearest_clinic_miles", "nearest_hospital_miles", "nearest_pharmacy_miles",
        "no_vehicle_rate", "poverty_rate", "no_insurance_rate", "median_household_income",
    ]
    present = [c for c in key_cols if c in stats.columns]
    missing = [c for c in key_cols if c not in stats.columns]
    print(f"  Key columns present: {present}")
    if missing:
        print(f"  Missing columns: {missing}")


if __name__ == "__main__":
    main()
