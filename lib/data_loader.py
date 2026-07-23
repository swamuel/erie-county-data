"""
lib/data_loader.py
==================
Slim data access for the app. Reads the flat, pre-validated master files built
by pipeline/build_masters.py and does exactly ONE join per geography
(attributes -> boundary) on the collision-safe 11-digit GEOID.

No cross-dataset merges happen here — all of that is done offline in the
pipeline. See pipeline/verify.py for the accuracy guarantee on this data.
"""

from pathlib import Path

import streamlit as st
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"


# ── Flat masters ──────────────────────────────────────────────────────────
@st.cache_data
def load_masters():
    tract = pd.read_csv(
        PROC / "master_tract.csv",
        dtype={"GEOID": str, "county_fips": str, "tract_code": str},
    )
    zcta = pd.read_csv(
        PROC / "master_zcta.csv", dtype={"ZCTA5CE20": str, "zcta": str}
    )
    county = pd.read_csv(
        PROC / "master_county.csv", dtype={"GEOID": str, "county_fips": str}
    )
    return tract, zcta, county


@st.cache_resource
def load_boundaries():
    tracts = gpd.read_parquet(RAW / "boundaries_tracts.parquet")
    counties = gpd.read_parquet(RAW / "boundaries_counties.parquet")
    zctas = gpd.read_parquet(RAW / "boundaries_zctas.parquet")
    return tracts, counties, zctas


@st.cache_data
def load_snap():
    return pd.read_csv(
        PROC / "snap_retailers.csv", dtype={"GEOID": str, "zip": str, "zcta": str}
    )


@st.cache_data
def load_benchmarks():
    nat = pd.read_csv(RAW / "benchmarks_national.csv")
    pa = pd.read_csv(RAW / "benchmarks_pennsylvania.csv")
    erie = pd.read_csv(RAW / "benchmarks_erie.csv")
    counties = pd.read_csv(RAW / "benchmarks_pa_counties.csv")
    return nat, pa, erie, counties


@st.cache_data
def load_stratification():
    return pd.read_csv(PROC / "income_stratification.csv")


# ── The one and only runtime join ─────────────────────────────────────────
@st.cache_resource
def build_geo(geography, year):
    """Attach master attributes for `year` to the matching boundary polygons.

    Exactly one merge on the globally-unique GEOID (or ZCTA), so no tract-code
    collisions and no row explosion.
    """
    tract, zcta, _ = load_masters()
    gdf_t, _, gdf_z = load_boundaries()

    if geography == "Tract":
        m = tract[tract["year"] == year]
        merged = gdf_t.merge(m, on="GEOID", how="left")
        merged["display_name"] = (
            merged["NAMELSAD"].fillna("Tract " + merged["GEOID"])
            + " — " + merged["county_name"].fillna("").astype(str).str.replace(" County", "", regex=False)
        )

    else:  # Zip Code
        m = zcta[zcta["year"] == year]
        merged = gdf_z.merge(m, on="ZCTA5CE20", how="left")
        name = merged["area_name"].fillna(merged["ZCTA5CE20"]).astype(str)
        merged["display_name"] = name + " (" + merged["ZCTA5CE20"] + ")"

    return merged
