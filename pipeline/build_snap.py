"""
pipeline/build_snap.py
======================
Prepares the USDA SNAP retailer file the app ships. Stamps an `is_urban`
flag onto each retailer (via a point-in-tract spatial join against the 2020
tract boundaries + the USDA Food Atlas urban_tract flag) so the app can draw
coverage rings at the USDA convention: 1 mile urban, 10 miles rural.

The Food Atlas is used here as an OFFLINE input only — it is NOT shipped.

Input:  data/raw/snap_retailers.csv, boundaries_tracts.parquet, usda_food_atlas.csv
Output: data/processed/snap_retailers.csv

Run:  python pipeline/build_snap.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.constants import COUNTY_NAMES  # noqa: E402

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

# USDA fields only — no derived rollups. `store_type_raw` is USDA's own
# "Store Type" value, carried through unchanged.
KEEP = ["name", "address", "county", "state", "zip", "lat", "lon",
        "store_type_raw", "authorization_date"]


def main():
    s = pd.read_csv(RAW / "snap_retailers.csv")
    s = s.dropna(subset=["lat", "lon"]).copy()

    # keep only the 11-county region (all rows already are, but be explicit)
    region = {c.replace(" County", "").upper() for c in COUNTY_NAMES}
    s["_cty"] = s["county"].astype(str).str.upper().str.strip()
    s = s[s["_cty"].isin(region)].copy()

    # ── Spatial joins: retailer point -> tract GEOID and ZCTA ─────────────
    tracts = gpd.read_parquet(RAW / "boundaries_tracts.parquet")
    zctas = gpd.read_parquet(RAW / "boundaries_zctas.parquet")
    base = gpd.GeoDataFrame(
        s.reset_index(drop=True),
        geometry=gpd.points_from_xy(s["lon"], s["lat"]), crs=tracts.crs
    )

    def _assign(poly_gdf, col):
        j = gpd.sjoin(base[["geometry"]], poly_gdf[[col, "geometry"]],
                      how="left", predicate="within")
        # a point on a shared edge can match >1 polygon — keep the first
        j = j[~j.index.duplicated(keep="first")]
        return j[col].values

    base["GEOID"] = _assign(tracts, "GEOID")          # 11-digit tract
    base["zcta"] = _assign(zctas, "ZCTA5CE20")        # 5-digit ZCTA

    # ── Urban flag from USDA atlas (keyed on 11-digit tract_geoid) ─────────
    atlas = pd.read_csv(RAW / "usda_food_atlas.csv", dtype={"tract_geoid": str})
    urban = atlas.set_index("tract_geoid")["urban_tract"].to_dict()
    base["is_urban"] = base["GEOID"].map(urban)
    # Unknown tract (e.g. point just outside a boundary): default to urban,
    # the more conservative 1-mile ring, so coverage gaps are not overstated.
    n_missing = int(base["is_urban"].isna().sum())
    base["is_urban"] = base["is_urban"].fillna(1).astype(int).astype(bool)

    out = base[KEEP + ["GEOID", "zcta", "is_urban"]].copy()
    PROC.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROC / "snap_retailers.csv", index=False)

    print(f"[OK] snap_retailers.csv — {len(out)} retailers "
          f"({int(out['is_urban'].sum())} urban / {int((~out['is_urban']).sum())} rural; "
          f"{n_missing} defaulted to urban)")
    print("     store types:", out["store_type_raw"].nunique(), "USDA types")


if __name__ == "__main__":
    main()
