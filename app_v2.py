import streamlit as st

from lib.data_loader import load_data, load_boundaries, load_stratification_data, load_pantry_data
from lib.config import data_dictionary
from lib.helpers import get_benchmark_row, get_available_vars

import tabs.about as tab_about_mod
import tabs.economic as tab_economic_mod
import tabs.transit as tab_transit_mod
import tabs.food_access as tab_food_access_mod
import tabs.health as tab_health_mod
import tabs.services as tab_services_mod
import tabs.query_tool as tab_query_tool_mod
import tabs.insights as tab_insights_mod
import tabs.download as tab_download_mod
import tabs.data_dictionary as tab_dict_mod

st.set_page_config(page_title="Erie & Crawford County Data", layout="wide")

# ── LOAD DATA ─────────────────────────────────────────────
(census, sh_data, shapes, stops, pantries,
 benchmarks_national, benchmarks_pa, benchmarks_erie,
 benchmarks_counties, transit_stats, zcta_data,
 cdc_places, food_atlas, demographics, pois, poi_stats) = load_data()

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
st.sidebar.title("Erie & Crawford County Data")

mode = st.sidebar.radio("Mode", ["Simple", "Advanced"], horizontal=True)

st.sidebar.markdown("---")
year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

st.sidebar.markdown("---")
geography = st.sidebar.radio(
    "Geography",
    ["Tract", "Zip Code", "County"],
    horizontal=True
)

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark")

benchmark_options = ["National", "Pennsylvania", "Erie County", "Compare to Another PA County"]
selected_benchmark = st.sidebar.selectbox("Compare against", benchmark_options)

compare_county = None
if selected_benchmark == "Compare to Another PA County":
    county_list = sorted(benchmarks_counties["name"].unique().tolist())
    compare_county = st.sidebar.selectbox("Select county", county_list)

# ── DATA PREP ─────────────────────────────────────────────
import pandas as pd
import geopandas as gpd

df_year = census[census["year"] == year].copy()
df_year["tract_code"] = df_year["tract_code"].astype(str).str.zfill(6)

sh_year = sh_data[sh_data["year"] == min(year, 2023)].copy()
sh_year["tract_code"] = sh_year["tract_code"].astype(str).str.zfill(6)

transit_stats_prep = transit_stats.copy()
transit_stats_prep["TRACTCE"] = transit_stats_prep["TRACTCE"].astype(str).str.zfill(6)

if geography == "Tract":
    merged = gdf_tracts.merge(df_year, left_on="TRACTCE", right_on="tract_code", how="left")
    merged = merged.merge(
        sh_year[["tract_code", "food_insecurity_rate", "unemployment_rate",
                 "disability_rate", "homeownership_rate"]],
        left_on="TRACTCE", right_on="tract_code", how="left"
    )
    merged = merged.merge(transit_stats_prep, on="TRACTCE", how="left")

    cdc_prep = cdc_places.copy()
    cdc_prep["TRACTCE"] = cdc_prep["tract_code"].astype(str).str.zfill(6)
    cdc_drop = [c for c in ["tract_code", "county_fips", "countyname", "year", "tract_geoid"] if c in cdc_prep.columns]
    merged = merged.merge(cdc_prep.drop(columns=cdc_drop), on="TRACTCE", how="left")
    merged = merged.loc[:, ~merged.columns.duplicated()]

    atlas_prep = food_atlas.copy()
    atlas_prep["tract_code"] = atlas_prep["tract_code"].astype(str).str.zfill(6)
    atlas_cols = ["tract_code", "food_desert_1_10", "food_desert_half_10",
                  "food_desert_vehicle", "low_income_tract", "low_access_pop",
                  "low_access_low_income_pop", "atlas_poverty_rate", "urban_tract"]
    atlas_cols = [c for c in atlas_cols if c in atlas_prep.columns]
    merged = merged.merge(
        atlas_prep[atlas_cols], left_on="TRACTCE", right_on="tract_code", how="left"
    ).drop(columns=["tract_code_y"], errors="ignore")
    merged = merged.rename(columns={"tract_code_x": "tract_code"})
    merged = merged.loc[:, ~merged.columns.duplicated()]

    demo_year = demographics[demographics["year"] == year].copy()
    demo_year["tract_code"] = demo_year["tract_code"].astype(str).str.zfill(6)
    demo_keep = ["total_population", "median_age", "pct_white_non_hispanic",
                 "pct_black", "pct_hispanic", "pct_asian", "pct_other"]
    demo_keep = [c for c in demo_keep if c in demo_year.columns]
    demo_year["TRACTCE"] = demo_year["tract_code"]
    merged = merged.merge(demo_year[["TRACTCE"] + demo_keep], on="TRACTCE", how="left")
    merged = merged.loc[:, ~merged.columns.duplicated()]

    geo_id_col = "TRACTCE"
    geo_name_col = "NAMELSAD"
    merged["display_name"] = merged["NAMELSAD"]

elif geography == "Zip Code":
    zcta_year = zcta_data[zcta_data["year"] == year].copy()
    zcta_year["zcta"] = zcta_year["zcta"].astype(str).str.zfill(5)
    gdf_zctas_copy = gdf_zctas.copy()
    gdf_zctas_copy["ZCTA5CE20"] = gdf_zctas_copy["ZCTA5CE20"].astype(str).str.zfill(5)
    merged = gdf_zctas_copy.merge(zcta_year, left_on="ZCTA5CE20", right_on="zcta", how="left")
    geo_id_col = "ZCTA5CE20"
    geo_name_col = "area_name"
    merged["display_name"] = merged["area_name"].fillna("Unknown") + " (" + merged["ZCTA5CE20"] + ")"

elif geography == "County":
    county_data = benchmarks_counties[
        (benchmarks_counties["year"] == year) &
        (benchmarks_counties["name"].isin(["Erie County", "Crawford County"]))
    ].copy()
    county_fips_map = {"Erie County": "049", "Crawford County": "039"}
    county_data["COUNTYFP"] = county_data["name"].map(county_fips_map)
    merged = gdf_counties.merge(county_data, on="COUNTYFP", how="left")
    geo_id_col = "COUNTYFP"
    geo_name_col = "NAME"
    merged["display_name"] = merged["NAME"]

benchmark_row = get_benchmark_row(
    selected_benchmark, compare_county, year,
    benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties
)
available_vars = get_available_vars(geography, merged)

# ── TABS ──────────────────────────────────────────────────
tab_about, tab_econ, tab_transit, tab_food, tab_health, tab_services, tab_query, tab_insights, tab_download, tab_dict = st.tabs([
    "About", "Economic", "Transit", "Food Access", "Health", "Services", "Query Tool", "Insights", "Download", "Data Dictionary"
])

with tab_about:
    tab_about_mod.render(demographics, benchmarks_counties, year)

with tab_econ:
    tab_economic_mod.render(
        merged, census, zcta_data, gdf_tracts, gdf_zctas,
        benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties,
        benchmark_row, available_vars, geography, year, mode, selected_benchmark,
        compare_county, strat_df
    )

with tab_transit:
    tab_transit_mod.render(merged, shapes, stops, transit_stats, benchmark_row, geography, mode)

with tab_food:
    tab_food_access_mod.render(merged, pantries, pantry_monthly, pantry_index, benchmark_row, geography)

with tab_health:
    tab_health_mod.render(merged, benchmark_row, geography)

with tab_services:
    tab_services_mod.render(merged, pois, benchmark_row, geography)

with tab_query:
    tab_query_tool_mod.render(merged, benchmark_row, available_vars, geography)

with tab_insights:
    tab_insights_mod.render(
        merged, census, zcta_data, benchmarks_counties,
        benchmark_row, available_vars, geography, year, selected_benchmark, compare_county
    )

with tab_download:
    tab_download_mod.render(
        census, sh_data, demographics, cdc_places, food_atlas,
        poi_stats, pois, strat_df, pantry_monthly, pantry_index
    )

with tab_dict:
    tab_dict_mod.render(data_dictionary)
