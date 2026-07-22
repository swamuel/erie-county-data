"""
Northwest PA Community Data — Streamlit app.

Single entry point. Reads pre-validated flat masters (pipeline/build_masters.py)
and joins each to its boundary exactly once (lib/data_loader.build_geo).
Data accuracy is verified against the live Census API by pipeline/verify.py.
"""

import streamlit as st

from lib.constants import APP_TITLE, COUNTY_NAMES
from lib.config import data_dictionary
from lib.data_loader import (
    load_masters, load_boundaries, load_snap, load_benchmarks, build_geo,
)
from lib.helpers import get_benchmark_row

import tabs.about as tab_about
import tabs.demographics as tab_demographics
import tabs.economic as tab_economic
import tabs.snap_retailers as tab_snap
import tabs.download as tab_download
import tabs.data_dictionary as tab_dict

st.set_page_config(page_title=APP_TITLE, layout="wide")

YEARS = [2023, 2022, 2021, 2020]

# ── LOAD ──────────────────────────────────────────────────
master_tract, master_zcta, master_county = load_masters()
benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties = load_benchmarks()

# ── SESSION STATE ─────────────────────────────────────────
for k in ["selected_geo", "selected_geo_name",
          "svc_search_lat", "svc_search_lon", "svc_search_label", "svc_search_results"]:
    st.session_state.setdefault(k, None)

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title(APP_TITLE)
st.sidebar.caption("Second Harvest Food Bank of Northwest PA service region")

st.sidebar.markdown("---")
year = st.sidebar.selectbox("Year", YEARS)
geography = st.sidebar.radio("Geography", ["Zip Code", "Tract", "County"], horizontal=True)

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark")
benchmark_options = ["National", "Pennsylvania", "Erie County",
                     "Compare to Another Regional County"]
selected_benchmark = st.sidebar.selectbox("Compare against", benchmark_options)

compare_county = None
if selected_benchmark == "Compare to Another Regional County":
    county_list = sorted(
        benchmarks_counties[benchmarks_counties["name"].isin(COUNTY_NAMES)]["name"].unique().tolist()
    )
    compare_county = st.sidebar.selectbox("Select county", county_list)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Census figures are ACS 5-year estimates (2020–2023), verified against the "
    "U.S. Census Bureau API. See the About tab for details."
)

# ── DATA PREP (single join per geography) ─────────────────
merged = build_geo(geography, year)
geo_id_col = {"Tract": "GEOID", "Zip Code": "ZCTA5CE20", "County": "GEOID"}[geography]

benchmark_row = get_benchmark_row(
    selected_benchmark, compare_county, year,
    benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties,
)

# ── TABS ──────────────────────────────────────────────────
(t_about, t_demo, t_econ, t_snap, t_download, t_dict) = st.tabs([
    "About", "Demographics", "Economic", "SNAP Retailers", "Download", "Data Dictionary",
])

with t_about:
    tab_about.render(master_tract, benchmarks_counties, year)

with t_demo:
    tab_demographics.render(merged, master_tract, geography, year, geo_id_col)

with t_econ:
    tab_economic.render(
        merged, master_tract, master_zcta, benchmarks_national, benchmarks_pa,
        benchmarks_erie, benchmarks_counties, benchmark_row, geography, year,
        selected_benchmark, compare_county, geo_id_col,
    )

with t_snap:
    snap = load_snap()
    tab_snap.render(merged, snap, benchmark_row, geography)

with t_download:
    tab_download.render(master_tract, master_zcta, master_county, load_snap())

with t_dict:
    tab_dict.render(data_dictionary)
