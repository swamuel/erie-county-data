import streamlit as st

from lib.data_loader import (
    load_data, load_boundaries, load_stratification_data, load_pantry_data,
    load_transit_shapes, load_poi_data,
    build_merged_tract, build_merged_zcta, build_merged_county
)
from lib.config import data_dictionary
from lib.helpers import get_benchmark_row, get_available_vars

import tabs.about as tab_about_mod
import tabs.demographics as tab_demographics_mod
import tabs.economic as tab_economic_mod
import tabs.transit as tab_transit_mod
import tabs.food_access as tab_food_access_mod
import tabs.health as tab_health_mod
import tabs.services as tab_services_mod
import tabs.query_tool as tab_query_tool_mod
import tabs.insights as tab_insights_mod
import tabs.download as tab_download_mod
import tabs.data_dictionary as tab_dict_mod

from lib.constants import COUNTY_FIPS, COUNTY_NAMES, APP_TITLE
st.set_page_config(page_title=APP_TITLE, layout="wide")

# ── LOAD DATA ─────────────────────────────────────────────
(census, sh_data, pantries,
 benchmarks_national, benchmarks_pa, benchmarks_erie,
 benchmarks_counties, transit_stats, zcta_data,
 cdc_places, food_atlas, demographics,
 cdc_places_zcta, zcta_poi_stats) = load_data()

gdf_tracts, gdf_counties, gdf_zctas = load_boundaries()
strat_df = load_stratification_data()
pantry_monthly, pantry_index = load_pantry_data()

# ── SESSION STATE ─────────────────────────────────────────
if "selected_geo" not in st.session_state:
    st.session_state.selected_geo = None
if "selected_geo_name" not in st.session_state:
    st.session_state.selected_geo_name = None
if "svc_search_lat" not in st.session_state:
    st.session_state.svc_search_lat = None
if "svc_search_lon" not in st.session_state:
    st.session_state.svc_search_lon = None
if "svc_search_label" not in st.session_state:
    st.session_state.svc_search_label = None
if "svc_search_results" not in st.session_state:
    st.session_state.svc_search_results = None

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title(APP_TITLE)

mode = st.sidebar.radio("Mode", ["Simple", "Advanced"], horizontal=True)

st.sidebar.markdown("---")
year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

st.sidebar.markdown("---")
geography = st.sidebar.radio(
    "Geography",
    ["Zip Code", "Tract", "County"],
    horizontal=True
)

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark")

benchmark_options = ["National", "Pennsylvania", "Erie County", "Crawford County", "Compare to Another PA County"]
selected_benchmark = st.sidebar.selectbox("Compare against", benchmark_options)

compare_county = None
if selected_benchmark == "Compare to Another PA County":
    county_list = sorted(benchmarks_counties["name"].unique().tolist())
    compare_county = st.sidebar.selectbox("Select county", county_list)

# ── DATA PREP ─────────────────────────────────────────────
if geography == "Tract":
    merged = build_merged_tract(
        year, gdf_tracts, census, sh_data, transit_stats,
        cdc_places, food_atlas, demographics
    )
    geo_id_col = "TRACTCE"
    geo_name_col = "NAMELSAD"

elif geography == "Zip Code":
    merged = build_merged_zcta(year, gdf_zctas, zcta_data, cdc_places_zcta, zcta_poi_stats)
    geo_id_col = "ZCTA5CE20"
    geo_name_col = "area_name"

elif geography == "County":
    merged = build_merged_county(year, gdf_counties, benchmarks_counties)
    geo_id_col = "COUNTYFP"
    geo_name_col = "NAME"

benchmark_row = get_benchmark_row(
    selected_benchmark, compare_county, year,
    benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties
)
available_vars = get_available_vars(geography, merged)

# ── TABS ──────────────────────────────────────────────────
tab_about, tab_demographics, tab_econ, tab_transit, tab_food, tab_health, tab_services, tab_query, tab_insights, tab_download, tab_dict = st.tabs([
    "About", "Demographics", "Economic", "Transit", "Food Access", "Health", "Services", "Query Tool", "Insights", "Download", "Data Dictionary"
])

with tab_about:
    tab_about_mod.render(demographics, benchmarks_counties, year)

with tab_demographics:
    tab_demographics_mod.render(merged, demographics, geography, year)

with tab_econ:
    tab_economic_mod.render(
        merged, census, zcta_data, gdf_tracts, gdf_zctas,
        benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties,
        benchmark_row, available_vars, geography, year, mode, selected_benchmark,
        compare_county, strat_df
    )

with tab_transit:
    shapes, stops = load_transit_shapes()
    tab_transit_mod.render(merged, shapes, stops, transit_stats, benchmark_row, geography, mode)

with tab_food:
    tab_food_access_mod.render(merged, pantries, pantry_monthly, pantry_index, benchmark_row, geography)

with tab_health:
    tab_health_mod.render(merged, benchmark_row, geography)

with tab_services:
    pois, poi_stats = load_poi_data()
    tab_services_mod.render(merged, pois, benchmark_row, geography)

with tab_query:
    tab_query_tool_mod.render(merged, benchmark_row, available_vars, geography)

with tab_insights:
    tab_insights_mod.render(
        merged, census, zcta_data, benchmarks_counties,
        benchmark_row, available_vars, geography, year, selected_benchmark, compare_county
    )

with tab_download:
    pois, poi_stats = load_poi_data()
    tab_download_mod.render(
        census, sh_data, demographics, cdc_places, food_atlas,
        poi_stats, pois, strat_df, pantry_monthly, pantry_index, zcta_data,
        cdc_places_zcta, zcta_poi_stats
    )

with tab_dict:
    tab_dict_mod.render(data_dictionary)
