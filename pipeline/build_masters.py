"""
pipeline/build_masters.py
=========================
Builds the FLAT master files the app reads — one per geography — so the app
does exactly ONE join at runtime (attributes -> boundary), with no
cross-dataset merges and no tract-code collisions.

Why this exists
---------------
The old app merged 5+ datasets at runtime keyed on a 6-digit tract code.
But a 6-digit tract code is only unique WITHIN a county — nine codes recur
across the 11-county region (e.g. 950100 in both Elk and Jefferson). Joining
on that alone exploded rows and mis-assigned data. The masters are keyed on
the full 11-digit GEOID (state+county+tract), which is globally unique.

All heavy lifting (dtype cleaning, zero-padding, water-tract removal,
sentinel scrubbing, derived-column math) happens here, once, offline —
never in the app.

Inputs  (data/raw, data/processed)
Outputs (data/processed):
    master_tract.csv    GEOID + year  ->  economic + demographic attributes
    master_zcta.csv     ZCTA5CE20 + year
    master_county.csv   GEOID + year  (economic benchmarks, 11 region counties)

Run:  python pipeline/build_masters.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.constants import COUNTY_FIPS, FIPS_TO_NAME, STATE_FIPS  # noqa: E402

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
SUPPRESSED = -666666666
WATER_SUFFIX = "990000"

# Boundaries are 2020 TIGER vintage. ACS 2019 uses 2010-vintage tract codes;
# the 2020 redistricting renumbered 11 tracts in the region, so 2019 tract data
# cannot be cleanly placed on the 2020 polygons. We ship 2020-2023 only, so
# every tract renders correctly in every year. (2020-2023 match boundaries 1:1.)
MIN_YEAR = 2020

# The economic variables shown in the app — all ACS-verified by pipeline/verify.py.
ECON_COLS = ["median_household_income", "poverty_rate", "bachelors_rate",
             "rent_burden_rate", "no_vehicle_rate"]
# Demographic variables shown in the app.
DEMO_PCT = ["pct_white_non_hispanic", "pct_black", "pct_hispanic", "pct_asian", "pct_other"]
DEMO_RAW = ["white_non_hispanic", "black_alone", "hispanic_latino", "asian_alone",
            "other_race", "race_total"]
DEMO_MISC = ["total_population", "median_age"]


def _geoid(county_fips: pd.Series, tract_code: pd.Series) -> pd.Series:
    return STATE_FIPS + county_fips.str.zfill(3) + tract_code.str.zfill(6)


def build_tract() -> pd.DataFrame:
    # ── Economic ──────────────────────────────────────────────────────────
    econ = pd.read_csv(RAW / "erie_tract_data.csv",
                       dtype={"tract_code": str, "county_fips": str})
    econ["tract_code"] = econ["tract_code"].str.zfill(6)
    econ["county_fips"] = econ["county_fips"].str.zfill(3)
    econ["GEOID"] = _geoid(econ["county_fips"], econ["tract_code"])
    econ = econ[~econ["tract_code"].str.endswith(WATER_SUFFIX)]
    econ = econ[econ["year"] >= MIN_YEAR]
    econ = econ[["GEOID", "county_fips", "county_name", "tract_code", "tract_name",
                 "year"] + ECON_COLS]

    # ── Demographic ───────────────────────────────────────────────────────
    demo = pd.read_csv(RAW / "tract_demographics.csv",
                       dtype={"tract_code": str, "county_fips": str})
    demo["tract_code"] = demo["tract_code"].str.zfill(6)
    demo["county_fips"] = demo["county_fips"].str.zfill(3)
    demo["GEOID"] = _geoid(demo["county_fips"], demo["tract_code"])
    demo = demo[~demo["tract_code"].str.endswith(WATER_SUFFIX)]

    # scrub the ACS suppression sentinel wherever it survived into the raw file
    for c in demo.columns:
        if demo[c].dtype.kind in "if":
            demo[c] = demo[c].replace(SUPPRESSED, pd.NA)

    # derive other_race as the residual raw count (chart uses it); clip >= 0
    for c in ["white_non_hispanic", "black_alone", "hispanic_latino",
              "asian_alone", "race_total"]:
        demo[c] = pd.to_numeric(demo[c], errors="coerce")
    demo["other_race"] = (
        demo["race_total"]
        - demo[["white_non_hispanic", "black_alone", "hispanic_latino", "asian_alone"]].sum(axis=1)
    ).clip(lower=0)

    demo_keep = ["GEOID", "year"] + DEMO_MISC + DEMO_PCT + DEMO_RAW
    demo_keep = [c for c in demo_keep if c in demo.columns]
    demo = demo[demo_keep]

    # ── Single pipeline-time join on the collision-safe key ───────────────
    master = econ.merge(demo, on=["GEOID", "year"], how="left")

    # SNAP participation (ACS B19058) — optional context layer for the SNAP tab
    snap_path = RAW / "snap_participation_tract.csv"
    if snap_path.exists():
        sp = pd.read_csv(snap_path, dtype={"GEOID": str})
        sp = sp[sp["year"] >= MIN_YEAR]
        master = master.merge(sp, on=["GEOID", "year"], how="left")

    _validate_key(master, ["GEOID", "year"], "master_tract")
    _validate_against_boundary(master, "boundaries_tracts.parquet", "GEOID", "master_tract")
    return master.sort_values(["year", "GEOID"]).reset_index(drop=True)


def build_zcta() -> pd.DataFrame:
    # zcta_data.csv is already flat per (zcta, year); just clean and standardise.
    z = pd.read_csv(RAW / "zcta_data.csv", dtype={"zcta": str})
    z["ZCTA5CE20"] = z["zcta"].str.zfill(5)
    z = z[z["year"] >= MIN_YEAR]
    for c in z.columns:
        if z[c].dtype.kind in "if":
            z[c] = z[c].replace(SUPPRESSED, pd.NA)

    # SNAP participation (ACS B19058); national file, merge filters to region
    snap_path = RAW / "snap_participation_zcta.csv"
    if snap_path.exists():
        sp = pd.read_csv(snap_path, dtype={"ZCTA5CE20": str})
        z = z.merge(sp, on=["ZCTA5CE20", "year"], how="left")

    front = ["ZCTA5CE20", "zcta", "year", "area_name", "county_name"]
    z = z[[c for c in front if c in z.columns]
          + [c for c in z.columns if c not in front]]
    _validate_key(z, ["ZCTA5CE20", "year"], "master_zcta")
    return z.sort_values(["year", "ZCTA5CE20"]).reset_index(drop=True)


def build_county() -> pd.DataFrame:
    c = pd.read_csv(RAW / "benchmarks_pa_counties.csv", dtype={"county_fips": str})
    c["county_fips"] = c["county_fips"].str.zfill(3)
    c = c[c["county_fips"].isin(COUNTY_FIPS.values())].copy()
    c = c[c["year"] >= MIN_YEAR]
    c["GEOID"] = STATE_FIPS + c["county_fips"]
    c["county_name"] = c["county_fips"].map(FIPS_TO_NAME)
    keep = ["GEOID", "county_fips", "county_name", "name", "year"] + ECON_COLS
    c = c[[col for col in keep if col in c.columns]]
    _validate_key(c, ["GEOID", "year"], "master_county")
    _validate_against_boundary(c, "boundaries_counties.parquet", "GEOID", "master_county")
    return c.sort_values(["year", "GEOID"]).reset_index(drop=True)


# ── Validation helpers (fail the build, don't ship bad data) ──────────────
def _validate_key(df: pd.DataFrame, keys: list[str], name: str):
    dups = int(df.duplicated(subset=keys).sum())
    if dups:
        raise SystemExit(f"[{name}] {dups} duplicate rows on key {keys} — aborting.")


def _validate_against_boundary(df: pd.DataFrame, parquet: str, key: str, name: str):
    import geopandas as gpd
    gdf = gpd.read_parquet(RAW / parquet)
    bkey = "GEOID"
    boundary_ids = set(gdf[bkey].astype(str))
    master_ids = set(df[key].astype(str))
    orphans = master_ids - boundary_ids
    if orphans:
        sample = list(orphans)[:5]
        raise SystemExit(
            f"[{name}] {len(orphans)} {key}(s) have no matching boundary "
            f"(e.g. {sample}) — aborting.")
    # simulate the app's runtime join for ONE year: must not explode
    yr = sorted(df["year"].unique())[-1]
    one = df[df["year"] == yr]
    joined = gdf.merge(one, left_on=bkey, right_on=key, how="left")
    if len(joined) != len(gdf):
        raise SystemExit(
            f"[{name}] runtime join explodes {len(gdf)} boundaries -> "
            f"{len(joined)} rows for {yr} — key not unique.")


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    print("Building flat master files (collision-safe, single-join)...\n")

    for name, builder in [("master_tract", build_tract),
                          ("master_zcta", build_zcta),
                          ("master_county", build_county)]:
        df = builder()
        out = PROC / f"{name}.csv"
        df.to_csv(out, index=False)
        print(f"  [OK] {name}.csv  —  {len(df):,} rows, {len(df.columns)} cols, "
              f"years {df['year'].min()}-{df['year'].max()}")

    print("\nAll masters built and validated (keys unique, boundaries matched, "
          "no join explosion).")


if __name__ == "__main__":
    main()
