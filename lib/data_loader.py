import streamlit as st
import pandas as pd
import geopandas as gpd


@st.cache_data
def load_data():
    census = pd.read_csv("data/raw/erie_tract_data.csv")
    sh_data = pd.read_csv("data/raw/erie_food_insecurity.csv")
    shapes = pd.read_csv("data/raw/emta_shapes.csv")
    stops = pd.read_csv("data/raw/emta_stops.csv")
    pantries = pd.read_csv("data/raw/ErieCountyFoodPantries.csv")
    benchmarks_national = pd.read_csv("data/raw/benchmarks_national.csv")
    benchmarks_pa = pd.read_csv("data/raw/benchmarks_pennsylvania.csv")
    benchmarks_erie = pd.read_csv("data/raw/benchmarks_erie.csv")
    benchmarks_counties = pd.read_csv("data/raw/benchmarks_pa_counties.csv")
    transit_stats = pd.read_csv("data/processed/tract_transit_stats.csv")
    zcta_data = pd.read_csv("data/raw/zcta_data.csv")
    cdc_places = pd.read_csv("data/raw/cdc_places_tract.csv", dtype={"tract_code": str})
    food_atlas = pd.read_csv("data/raw/usda_food_atlas.csv", dtype={"tract_code": str})
    demographics = pd.read_csv("data/raw/tract_demographics.csv", dtype={"tract_code": str})
    pois = pd.read_csv("data/raw/erie_pois.csv")
    poi_stats = pd.read_csv("data/processed/tract_poi_stats.csv", dtype={"TRACTCE": str})
    if "snap_eligible" not in pois.columns:
        pois["snap_eligible"] = pois["geocode_source"] == "usda_snap"
    else:
        pois["snap_eligible"] = pois["snap_eligible"].astype(str).str.lower() == "true"
    return (census, sh_data, shapes, stops, pantries,
            benchmarks_national, benchmarks_pa, benchmarks_erie,
            benchmarks_counties, transit_stats, zcta_data,
            cdc_places, food_atlas, demographics, pois, poi_stats)


@st.cache_data
def load_boundaries():
    tract_url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    tracts = gpd.read_file(tract_url)
    tracts = tracts[tracts["COUNTYFP"].isin(["049", "039"])]
    tracts = tracts[tracts["TRACTCE"] != "990000"]

    county_url = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
    counties = gpd.read_file(county_url)
    counties = counties[
        (counties["COUNTYFP"].isin(["049", "039"])) &
        (counties["STATEFP"] == "42")
    ]

    zcta_url = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
    zcta_list = [str(z).zfill(5) for z in [
        16110, 16111, 16131, 16134, 16314, 16316, 16327, 16328, 16335,
        16354, 16360, 16403, 16404, 16406, 16422, 16424, 16432, 16433,
        16434, 16435, 16440, 16401, 16407, 16410, 16411, 16412, 16413,
        16415, 16417, 16421, 16423, 16426, 16427, 16428, 16430, 16438,
        16441, 16442, 16443, 16501, 16502, 16503, 16504, 16505, 16506,
        16507, 16508, 16509, 16510, 16511, 16563
    ]]
    zctas = gpd.read_file(zcta_url)
    zctas = zctas[zctas["ZCTA5CE20"].isin(zcta_list)]

    return tracts, counties, zctas


@st.cache_data
def load_stratification_data():
    df = pd.read_csv("data/processed/income_stratification.csv")
    return df


@st.cache_data
def load_pantry_data():
    monthly = pd.read_csv("data/processed/pantry_agency_monthly.csv", parse_dates=["date"])
    index = pd.read_csv("data/processed/pantry_agency_index.csv")
    return monthly, index
