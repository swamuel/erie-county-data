import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import math

st.set_page_config(page_title="Erie & Crawford County Data", layout="wide")

# ── LOAD DATA ────────────────────────────────────────────
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

(census, sh_data, shapes, stops, pantries,
 benchmarks_national, benchmarks_pa, benchmarks_erie,
 benchmarks_counties, transit_stats, zcta_data,
 cdc_places, food_atlas, demographics, pois, poi_stats) = load_data()

gdf_tracts, gdf_counties, gdf_zctas = load_boundaries()

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

# ── VARIABLES ─────────────────────────────────────────────
all_variables = {
    "Median Household Income": "median_household_income",
    "Poverty Rate": "poverty_rate",
    "Rent Burden Rate": "rent_burden_rate",
    "No Vehicle Rate": "no_vehicle_rate",
    "Food Insecurity Rate": "food_insecurity_rate",
    "Unemployment Rate": "unemployment_rate",
    "Disability Rate": "disability_rate",
    "Bachelor's Degree Rate": "bachelors_rate",
    "Homeownership Rate": "homeownership_rate",
    # Health — CDC PLACES
    "Diabetes Rate": "diabetes_rate",
    "High Blood Pressure": "high_bp_rate",
    "Depression Rate": "depression_rate",
    "Obesity Rate": "obesity_rate",
    "Smoking Rate": "smoking_rate",
    "No Health Insurance": "no_insurance_rate",
    "Poor Mental Health": "poor_mental_health_rate",
    "Poor Physical Health": "poor_physical_health_rate",
    "Asthma Rate": "asthma_rate",
    "Heart Disease Rate": "heart_disease_rate",
    "Stroke Rate": "stroke_rate",
    "COPD Rate": "copd_rate",
    "Physical Inactivity": "physical_inactivity_rate",
    "Sleep Deprivation": "sleep_deprivation_rate",
    # Food Access — USDA
    "Food Desert (1mi/10mi)": "food_desert_1_10",
    "Food Desert (Vehicle)": "food_desert_vehicle",
    "Low Income Tract": "low_income_tract",
    # Demographics
    "Total Population": "total_population",
    "Median Age": "median_age",
    "% White Non-Hispanic": "pct_white_non_hispanic",
    "% Black": "pct_black",
    "% Hispanic": "pct_hispanic",
    "% Asian": "pct_asian",
}

HIGHER_IS_BETTER = {
    "median_household_income": True,
    "poverty_rate": False,
    "rent_burden_rate": False,
    "no_vehicle_rate": False,
    "food_insecurity_rate": False,
    "unemployment_rate": False,
    "disability_rate": False,
    "bachelors_rate": True,
    "homeownership_rate": True,
    "diabetes_rate": False,
    "high_bp_rate": False,
    "depression_rate": False,
    "obesity_rate": False,
    "smoking_rate": False,
    "no_insurance_rate": False,
    "poor_mental_health_rate": False,
    "poor_physical_health_rate": False,
    "asthma_rate": False,
    "heart_disease_rate": False,
    "stroke_rate": False,
    "copd_rate": False,
    "physical_inactivity_rate": False,
    "sleep_deprivation_rate": False,
    "food_desert_1_10": False,
    "food_desert_vehicle": False,
    "low_income_tract": False,
    "total_population": True,
    "median_age": True,
    "pct_white_non_hispanic": True,
    "pct_black": True,
    "pct_hispanic": True,
    "pct_asian": True,
}

TRACT_ONLY_VARS = {
    "food_insecurity_rate", "unemployment_rate", "disability_rate",
    "homeownership_rate", "stop_count", "total_daily_visits", "nearest_stop_miles",
    "diabetes_rate", "high_bp_rate", "depression_rate", "obesity_rate",
    "smoking_rate", "no_insurance_rate", "poor_mental_health_rate",
    "poor_physical_health_rate", "asthma_rate", "heart_disease_rate",
    "stroke_rate", "copd_rate", "physical_inactivity_rate", "sleep_deprivation_rate",
    "food_desert_1_10", "food_desert_vehicle", "low_income_tract",
    "low_access_pop", "low_access_low_income_pop",
    "total_population", "median_age",
    "pct_white_non_hispanic", "pct_black", "pct_hispanic", "pct_asian",
}

# ── DATA DICTIONARY ────────────────────────────────────────
data_dictionary = pd.DataFrame([
    {
        "Variable": "Median Household Income",
        "Column": "median_household_income",
        "Plain Language": "The middle income value for all households — half earn more, half earn less.",
        "Technical Definition": "ACS B19013: Median household income in the past 12 months (inflation-adjusted dollars).",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "ACS 5-year estimates represent a rolling average, not a single point in time. Small geographies may have wide margins of error."
    },
    {
        "Variable": "Poverty Rate",
        "Column": "poverty_rate",
        "Plain Language": "Percentage of residents living below the federal poverty line.",
        "Technical Definition": "ACS B17001: Population for whom poverty status is determined, below poverty level / total.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Federal poverty thresholds do not adjust for regional cost of living. May understate hardship in high-cost areas."
    },
    {
        "Variable": "Rent Burden Rate",
        "Column": "rent_burden_rate",
        "Plain Language": "Percentage of renters paying 35% or more of their income on rent.",
        "Technical Definition": "ACS B25070: Gross rent as a percentage of household income — 35% or more / total renter-occupied units.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Only captures renters. Homeowners with high mortgage costs are not reflected. Threshold of 35% is more conservative than the standard 30%."
    },
    {
        "Variable": "No Vehicle Rate",
        "Column": "no_vehicle_rate",
        "Plain Language": "Percentage of households with no access to a personal vehicle.",
        "Technical Definition": "ACS B08201: Households with no vehicle available / total households.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Does not distinguish between households that chose not to own a vehicle and those who cannot afford one."
    },
    {
        "Variable": "Food Insecurity Rate",
        "Column": "food_insecurity_rate",
        "Plain Language": "Estimated percentage of residents who lack reliable access to enough food.",
        "Technical Definition": "Modeled tract-level food insecurity estimates from Feeding America / Second Harvest North Central PA.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "These are modeled estimates, not direct measurements. Methodology uses poverty, unemployment, and demographic variables to estimate food insecurity. Should not be interpreted as a precise count."
    },
    {
        "Variable": "Unemployment Rate",
        "Column": "unemployment_rate",
        "Plain Language": "Percentage of the labor force that is unemployed.",
        "Technical Definition": "Derived from Second Harvest source data. Unemployed civilians / civilian labor force.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "Does not include discouraged workers or those who have left the labor force. Tract-level estimates may have higher variability than county-level BLS data."
    },
    {
        "Variable": "Disability Rate",
        "Column": "disability_rate",
        "Plain Language": "Percentage of residents with any disability.",
        "Technical Definition": "Derived from Second Harvest source data. Population with a disability / total civilian noninstitutionalized population.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "Disability is self-reported and covers a broad range of conditions. Does not distinguish severity or type of disability."
    },
    {
        "Variable": "Bachelor's Degree Rate",
        "Column": "bachelors_rate",
        "Plain Language": "Percentage of adults 25 and older with at least a bachelor's degree.",
        "Technical Definition": "ACS B15003: Population 25 years and over with bachelor's degree / total population 25 and over.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract only",
        "Years Available": "2019–2023",
        "Caveats": "Educational attainment is a lagging indicator — reflects workforce composition built over decades, not recent trends."
    },
    {
        "Variable": "Homeownership Rate",
        "Column": "homeownership_rate",
        "Plain Language": "Percentage of housing units that are owner-occupied.",
        "Technical Definition": "Derived from Second Harvest source data. Owner-occupied units / total occupied housing units.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "High homeownership does not necessarily indicate housing stability. Does not capture mortgage distress or property tax burden."
    },
    {
        "Variable": "Diabetes Rate",
        "Column": "diabetes_rate",
        "Plain Language": "Percentage of adults diagnosed with diabetes.",
        "Technical Definition": "CDC PLACES model-based estimate. Crude prevalence of diagnosed diabetes among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Model-based estimates, not direct survey counts. Based on Behavioral Risk Factor Surveillance System data modeled down to tract level. Should not be compared to clinical data."
    },
    {
        "Variable": "High Blood Pressure",
        "Column": "high_bp_rate",
        "Plain Language": "Percentage of adults with high blood pressure.",
        "Technical Definition": "CDC PLACES crude prevalence of high blood pressure among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Model-based estimate. BRFSS data for blood pressure collected every other year."
    },
    {
        "Variable": "Depression Rate",
        "Column": "depression_rate",
        "Plain Language": "Percentage of adults who have ever been told they have a depressive disorder.",
        "Technical Definition": "CDC PLACES crude prevalence of depression among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Self-reported diagnosis. Likely undercounts true prevalence due to underdiagnosis, especially in rural areas."
    },
    {
        "Variable": "Obesity Rate",
        "Column": "obesity_rate",
        "Plain Language": "Percentage of adults with a BMI of 30 or higher.",
        "Technical Definition": "CDC PLACES crude prevalence of obesity (BMI >= 30) among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Based on self-reported height and weight. BMI is a limited measure of health and does not account for body composition."
    },
    {
        "Variable": "No Health Insurance",
        "Column": "no_insurance_rate",
        "Plain Language": "Percentage of adults under 65 without health insurance.",
        "Technical Definition": "CDC PLACES crude prevalence of no health insurance among adults aged 18-64.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Excludes adults 65+ who are generally covered by Medicare. Model-based estimate."
    },
    {
        "Variable": "Food Desert (1mi/10mi)",
        "Column": "food_desert_1_10",
        "Plain Language": "Tract designated as a food desert — low income and low access to a grocery store.",
        "Technical Definition": "USDA LILA designation: low income tract where a significant share of residents are more than 1 mile (urban) or 10 miles (rural) from a supermarket or large grocery store.",
        "Source": "USDA Economic Research Service — Food Access Research Atlas 2019",
        "Geography": "Tract only",
        "Years Available": "2019 (single year)",
        "Caveats": "Based on 2019 store locations. Does not account for stores opened or closed since then. Dollar stores and convenience stores are not counted as grocery stores."
    },
    {
        "Variable": "Total Population",
        "Column": "total_population",
        "Plain Language": "Total number of residents in the tract.",
        "Technical Definition": "ACS B01003_001E: Total population.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract only",
        "Years Available": "2019–2023",
        "Caveats": "ACS 5-year rolling estimate. Group quarters population (college dorms, prisons) is included."
    },
])

# ── HELPER FUNCTIONS ──────────────────────────────────────
def value_to_color(value, national_avg, reverse=False, spread=0.25):
    if pd.isna(value) or pd.isna(national_avg):
        return [200, 200, 200, 140]
    low = national_avg * (1 - spread)
    high = national_avg * (1 + spread)
    normalized = (value - low) / (high - low)
    normalized = max(0, min(1, normalized))
    if reverse:
        normalized = 1 - normalized
    if normalized < 0.5:
        t = normalized * 2
        r = int(200 - (t * 40))
        g = int(80 + (t * 60))
        b = int(60 + (t * 20))
    else:
        t = (normalized - 0.5) * 2
        r = int(160 - (t * 120))
        g = int(140 + (t * 70))
        b = int(80 - (t * 20))
    return [r, g, b, 180]

def get_benchmark_row(selected_benchmark, compare_county, year):
    if selected_benchmark == "National":
        return benchmarks_national[benchmarks_national["year"] == year]
    elif selected_benchmark == "Pennsylvania":
        return benchmarks_pa[benchmarks_pa["year"] == year]
    elif selected_benchmark == "Erie County":
        return benchmarks_erie[benchmarks_erie["year"] == year]
    elif selected_benchmark == "Compare to Another PA County":
        return benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == compare_county)
        ]
    return benchmarks_national[benchmarks_national["year"] == year]

def get_benchmark_value(benchmark_row, column):
    if len(benchmark_row) > 0 and column in benchmark_row.columns:
        return benchmark_row[column].values[0]
    return None

def format_value(value, column):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "No data"
    if column == "median_household_income":
        return f"${value:,.0f}"
    return f"{value}%"

def diff_string(tract_val, benchmark_val, col=None):
    if tract_val is None or benchmark_val is None:
        return ""
    try:
        if pd.isna(tract_val):
            return ""
    except Exception:
        pass
    diff = round(float(tract_val) - float(benchmark_val), 1)
    arrow = "▲" if diff > 0 else "▼"
    return f"{arrow} {abs(diff)}"

def get_geo_label(geography):
    return {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

def get_available_vars(geography, merged_df):
    """Return variables available for the current geography and merged dataframe."""
    available = {}
    for label, col in all_variables.items():
        if geography != "Tract" and col in TRACT_ONLY_VARS:
            continue
        if col in merged_df.columns:
            available[label] = col
    return available

def geocode_address(address):
    """Geocode an address using Nominatim. No API key required."""
    import urllib.request
    import urllib.parse
    query = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "ErieCountyDataApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            results = json.loads(resp.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None, None, None

def haversine_miles(lat1, lon1, lat2, lon2):
    """Distance in miles between two lat/lon points."""
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ── SERVICES LAYER CONFIG ─────────────────────────────────
LAYER_CONFIG = {
    "Food & Grocery": {
        "Supermarkets":            {"primary_category":"Food & Grocery","type":"Supermarket","default_on":True,"color":[34,197,94,220],"subtypes":None},
        "Large Grocery Stores":    {"primary_category":"Food & Grocery","type":"Large Grocery Store","default_on":True,"color":[52,211,153,220],"subtypes":None},
        "Medium Grocery Stores":   {"primary_category":"Food & Grocery","type":"Medium Grocery Store","default_on":True,"color":[110,231,183,220],"subtypes":None},
        "Small Grocery Stores":    {"primary_category":"Food & Grocery","type":"Small Grocery Store","default_on":False,"color":[167,243,208,220],"subtypes":None},
        "Combination / Mixed Retail":{"primary_category":"Food & Grocery","type":"Combination Grocery/Other","default_on":False,"color":[251,191,36,220],"subtypes":None},
        "Specialty Food":          {"primary_category":"Food & Grocery","type":"Specialty Food Store","default_on":False,"color":[16,185,129,220],"subtypes":{
            "Meat / Poultry":{"value":"Meat/Poultry Specialty","default_on":True,"color":[239,68,68,200]},
            "Bakery":        {"value":"Bakery Specialty",       "default_on":True,"color":[251,146,60,200]},
            "Fruits / Veg":  {"value":"Fruits/Veg Specialty",  "default_on":True,"color":[34,197,94,200]},
        }},
        "Farmers Markets":         {"primary_category":"Food & Grocery","type":"Farmers' Market","default_on":True,"color":[5,150,105,220],"subtypes":None},
        "Convenience Stores":      {"primary_category":"Food & Grocery","type":"Convenience Store","default_on":False,"color":[156,163,175,200],"subtypes":None},
    },
    "Health": {
        "Hospitals":               {"primary_category":"Health","type":"Hospital","default_on":True,"color":[220,38,38,240],"subtypes":None},
        "Pharmacies":              {"primary_category":"Health","type":"Pharmacy","default_on":True,"color":[239,68,68,220],"subtypes":None},
        "Clinics & Care":          {"primary_category":"Health","type":"Clinic","default_on":True,"color":[251,146,60,200],"subtypes":{
            "Outpatient Clinic":{"value":"Outpatient Clinic","default_on":True, "color":[251,146,60,220]},
            "Medical Office":   {"value":"Medical Office",   "default_on":False,"color":[253,186,116,200]},
            "Dental Office":    {"value":"Dental Office",    "default_on":False,"color":[251,191,36,200]},
            "Veterinary":       {"value":"Veterinary",       "default_on":False,"color":[100,180,100,200]},
        }},
    },
    "Civic & Social": {
        "Libraries":               {"primary_category":"Education & Civic","type":"Library","default_on":True,"color":[59,130,246,220],"subtypes":None},
        "Schools":                 {"primary_category":"Education & Civic","type":"School","default_on":False,"color":[99,102,241,200],"subtypes":{
            "K-12 Schools":    {"value":"K-12 School",    "default_on":True, "color":[99,102,241,200]},
            "Early Childhood": {"value":"Early Childhood","default_on":False,"color":[129,140,248,200]},
        }},
        "Higher Education":        {"primary_category":"Education & Civic","type":"Higher Education","default_on":True,"color":[67,56,202,220],"subtypes":None},
        "Community Centers":       {"primary_category":"Civic & Social","type":"Community Center","default_on":True,"color":[168,85,247,220],"subtypes":None},
        "Social Services":         {"primary_category":"Civic & Social","type":"Social Services","default_on":True,"color":[192,132,252,200],"subtypes":None},
        "Financial":               {"primary_category":"Civic & Social","type":"Financial","default_on":False,"color":[100,100,180,200],"subtypes":None},
        "Government":              {"primary_category":"Civic & Social","type":"Government","default_on":False,"color":[107,114,128,200],"subtypes":{
            "Government Offices":{"value":"Government Office","default_on":True, "color":[107,114,128,220]},
            "Post Offices":      {"value":"Post Office",      "default_on":False,"color":[156,163,175,200]},
        }},
        "Emergency Services":      {"primary_category":"Civic & Social","type":"Emergency Services","default_on":False,"color":[239,68,68,200],"subtypes":{
            "Fire Stations":   {"value":"Fire Station",   "default_on":True,"color":[239,68,68,220]},
            "Police Stations": {"value":"Police Station", "default_on":True,"color":[59,130,246,220]},
        }},
        "Faith Communities":       {"primary_category":"Civic & Social","type":"Faith Community","default_on":False,"color":[180,140,200,180],"subtypes":None},
    },
}

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

    # CDC PLACES health data
    cdc_prep = cdc_places.copy()
    cdc_prep["TRACTCE"] = cdc_prep["tract_code"].astype(str).str.zfill(6)
    cdc_drop = [c for c in ["tract_code", "county_fips", "countyname", "year", "tract_geoid"] if c in cdc_prep.columns]
    merged = merged.merge(
        cdc_prep.drop(columns=cdc_drop),
        on="TRACTCE",
        how="left"
    )
    # Drop any duplicate columns created by merges
    merged = merged.loc[:, ~merged.columns.duplicated()]

    # USDA Food Atlas
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
    # Drop any duplicate columns created by merges
    merged = merged.loc[:, ~merged.columns.duplicated()]

    # Demographics
    demo_year = demographics[demographics["year"] == year].copy()
    demo_year["tract_code"] = demo_year["tract_code"].astype(str).str.zfill(6)
    demo_keep = ["total_population", "median_age", "pct_white_non_hispanic",
                 "pct_black", "pct_hispanic", "pct_asian", "pct_other"]
    demo_keep = [c for c in demo_keep if c in demo_year.columns]
    demo_year["TRACTCE"] = demo_year["tract_code"]
    merged = merged.merge(demo_year[["TRACTCE"] + demo_keep], on="TRACTCE", how="left")
    # Drop any duplicate columns created by merges
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

benchmark_row = get_benchmark_row(selected_benchmark, compare_county, year)
available_vars = get_available_vars(geography, merged)

# ── DETAIL PANEL FUNCTION ─────────────────────────────────
def render_detail_panel(merged_df, column, selected_layer):
    geo_label = get_geo_label(geography)

    if st.session_state.selected_geo is None:
        st.caption(f"Select a {geo_label.lower()} above to see detailed data.")
        return

    geo_code = st.session_state.selected_geo
    geo_name = st.session_state.selected_geo_name
    geo_data = merged_df[merged_df[geo_id_col] == geo_code]

    if len(geo_data) == 0:
        st.warning(f"No data found for selected {geo_label.lower()}.")
        return

    row = geo_data.iloc[0]
    st.subheader(geo_name)

    m1, m2, m3, m4 = st.columns(4)
    for col_widget, var_label, var_col, higher_is_better in [
        (m1, "Median Income", "median_household_income", True),
        (m2, "Poverty Rate", "poverty_rate", False),
        (m3, "Rent Burden", "rent_burden_rate", False),
        (m4, "No Vehicle", "no_vehicle_rate", False),
    ]:
        with col_widget:
            val = row[var_col] if var_col in row.index else None
            bval = get_benchmark_value(benchmark_row, var_col)
            if bval and val is not None:
                try:
                    diff = round(float(val) - float(bval), 1)
                except Exception:
                    diff = None
            else:
                diff = None

            col_widget.metric(
                var_label,
                format_value(val, var_col),
                delta=diff,
                delta_color="normal" if higher_is_better else "inverse"
            )

    st.markdown("---")

    # Trend chart
    # Variable table
    st.markdown(f"**All Variables — {geo_label} Detail**")
    table_rows = []
    for label, col in all_variables.items():
        if geography != "Tract" and col in TRACT_ONLY_VARS:
            continue
        if col not in row.index:
            continue
        val = row[col]
        bval = get_benchmark_value(benchmark_row, col)
        table_rows.append({
            "Variable": label,
            f"This {geo_label}": format_value(val, col),
            "Benchmark": format_value(bval, col) if bval is not None else "—",
            "Difference": diff_string(val, bval) if bval is not None else "—"
        })
    if table_rows:
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No variable data available for this selection.")


# ── TABS ──────────────────────────────────────────────────
tab_about, tab_econ, tab_transit, tab_food, tab_health, tab_services, tab_query, tab_insights,tab_download, tab_dict = st.tabs([
    "About", "Economic", "Transit", "Food Access", "Health", "Services", "Query Tool", "Insights","Download", "Data Dictionary"
])

MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
VIEW_STATE = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0)
TOOLTIP_STYLE = {"backgroundColor": "steelblue", "color": "white",
                 "fontSize": "12px", "padding": "10px"}

# ═══════════════════════════════════════════════════════
# TAB 1 — ABOUT
# ═══════════════════════════════════════════════════════
with tab_about:
    st.title("Erie & Crawford County Community Data")
    st.markdown("### A public data tool for understanding neighborhood conditions across Erie and Crawford Counties, Pennsylvania.")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("What This Is")
        st.markdown(
            "This tool brings together census data, food security estimates, and transit information "
            "to help residents, nonprofits, planners, and researchers understand conditions at the "
            "neighborhood level. Data is available at the census tract, ZIP code, and county level "
            "for both Erie County and Crawford County."
        )

        st.subheader("How to Use It")
        st.markdown(
            "**Geography** — Use the sidebar to switch between Tract, ZIP Code, and County views. "
            "All tabs update to reflect the selected geography.\n\n"
            "**Year** — Select any year from 2019 to 2023. Data reflects ACS 5-year estimates "
            "centered on that year.\n\n"
            "**Benchmark** — Compare any area against national averages, Pennsylvania, Erie County, "
            "or any other PA county. Colors on the map are anchored to the selected benchmark.\n\n"
            "**Mode** — Simple mode shows the map and core controls. Advanced mode unlocks "
            "analytical tools like threshold filters, multi-variable queries, and transit analysis.\n\n"
            "**Insights tab** — Non-map analysis tools including a ranking table, county comparison "
            "dashboard, trend charts, and correlation explorer."
        )

    with col_b:
        st.subheader("Data Sources")
        sources = pd.DataFrame([
            {"Source": "U.S. Census Bureau — ACS 5-Year Estimates", "Variables": "Income, poverty, rent burden, no vehicle, education", "Geography": "Tract, ZIP", "Updated": "Annual"},
            {"Source": "Second Harvest / Feeding America", "Variables": "Food insecurity, unemployment, disability, homeownership", "Geography": "Tract", "Updated": "Annual"},
            {"Source": "EMTA (Erie Metropolitan Transit Authority)", "Variables": "Bus routes, stop locations, service frequency", "Geography": "Point", "Updated": "As published"},
            {"Source": "Census TIGER/Line", "Variables": "Tract, ZIP, and county boundaries", "Geography": "All", "Updated": "2023 vintage"},
        ])
        st.dataframe(sources, use_container_width=True, hide_index=True)

        st.subheader("Known Limitations")
        st.markdown(
            "- ACS estimates are 5-year rolling averages, not snapshots of a single year.\n"
            "- Food insecurity rates are modeled estimates, not measured counts.\n"
            "- Some Crawford County tracts have suppressed values due to small sample sizes.\n"
            "- Transit data reflects EMTA service only — Crawford County has no EMTA coverage.\n"
            "- ZIP code data does not include food insecurity or transit stop variables.\n"
            "- County-level data is sourced from benchmark files and may differ from tract aggregations."
        )

    st.markdown("---")
    st.subheader("County Snapshot")
    demo_latest = demographics[demographics["year"] == 2023].copy()
    erie_demo = demo_latest[demo_latest["county_fips"] == "049"]
    crawford_demo = demo_latest[demo_latest["county_fips"] == "039"]

    snap_col1, snap_col2 = st.columns(2)
    for snap_col, label, demo_df in [
        (snap_col1, "Erie County", erie_demo),
        (snap_col2, "Crawford County", crawford_demo),
    ]:
        with snap_col:
            st.markdown(f"**{label}**")
            if len(demo_df) > 0:
                total_pop = demo_df["total_population"].sum()
                med_age = demo_df["median_age"].mean()
                pct_white = (demo_df["white_non_hispanic"].sum() / demo_df["race_total"].sum() * 100) if "white_non_hispanic" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                pct_black = (demo_df["black_alone"].sum() / demo_df["race_total"].sum() * 100) if "black_alone" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                pct_hisp = (demo_df["hispanic_latino"].sum() / demo_df["race_total"].sum() * 100) if "hispanic_latino" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                st.metric("Total Population", f"{total_pop:,.0f}" if total_pop else "—")
                st.metric("Median Age", f"{med_age:.1f}" if med_age else "—")
                if pct_white:
                    st.caption(f"White non-Hispanic: {pct_white:.1f}%")
                if pct_black:
                    st.caption(f"Black or African American: {pct_black:.1f}%")
                if pct_hisp:
                    st.caption(f"Hispanic or Latino: {pct_hisp:.1f}%")

    st.markdown("---")
    st.subheader("About This Project")
    st.markdown(
        "This tool was built as an open resource for community organizations, planners, and residents "
        "working to understand and address inequality across Erie and Crawford Counties. "
        "Data is sourced from publicly available federal and local datasets. "
        "The project is ongoing — new data sources will be added over time.\n\n"
        f"Questions, corrections, or data suggestions: **samuelrandrew@gmail.com**\n\n"
        "Source code: [github.com/swamuel/erie-county-data](https://github.com/swamuel/erie-county-data)"
    )

# ═══════════════════════════════════════════════════════
# TAB 2 — ECONOMIC
# ═══════════════════════════════════════════════════════
with tab_econ:
    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        geo_label = get_geo_label(geography)

        # ── VIEW TOGGLE ───────────────────────────────────────
        econ_view = st.radio(
            "View",
            ["Snapshot", "Change Over Time"],
            horizontal=True,
            key="econ_view_toggle"
        )

        st.markdown("---")

        # ══════════════════════════════════════════════════════
        # SNAPSHOT VIEW
        # ══════════════════════════════════════════════════════
        if econ_view == "Snapshot":
            st.subheader("Economic Indicators")
            econ_vars = {k: v for k, v in all_variables.items()
                         if v not in TRACT_ONLY_VARS or geography == "Tract"}
            selected_layer = st.selectbox(
                "Variable", list(econ_vars.keys()), key="econ_layer"
            )
            column = econ_vars[selected_layer]

            st.markdown("---")
            st.markdown("**Explore a Location**")
            geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
            selected_display = st.selectbox(
                f"Select {geo_label}", geo_options, key="econ_geo_select"
            )
            if selected_display != "None":
                sel_row = merged[merged["display_name"] == selected_display].iloc[0]
                st.session_state.selected_geo = sel_row[geo_id_col]
                st.session_state.selected_geo_name = selected_display

        # ══════════════════════════════════════════════════════
        # CHANGE OVER TIME VIEW
        # ══════════════════════════════════════════════════════
        else:
            st.subheader("Change Over Time")
            st.caption("How did each tract change relative to the benchmark?")

            if geography == "County":
                st.info("Change Over Time is not available at the County level.")

            GROWTH_VARS = {
                "Median Household Income": "median_household_income",
                "Poverty Rate": "poverty_rate",
                "Rent Burden Rate": "rent_burden_rate",
                "No Vehicle Rate": "no_vehicle_rate",
                "Bachelor's Degree Rate": "bachelors_rate",
            }
            growth_var_label = st.selectbox(
                "Variable", list(GROWTH_VARS.keys()), key="growth_var"
            )
            growth_col = GROWTH_VARS[growth_var_label]
            higher_is_better_growth = HIGHER_IS_BETTER.get(growth_col, True)

            all_years = sorted(census["year"].unique().tolist())
            gc1, gc2 = st.columns(2)
            growth_start = gc1.selectbox("From", all_years, index=0, key="growth_start")
            growth_end = gc2.selectbox("To", all_years, index=len(all_years) - 1, key="growth_end")

            if growth_start >= growth_end:
                st.error("'From' year must be before 'To' year.")
            else:
                growth_cap = st.slider(
                    "Color scale cap (± pts)",
                    min_value=5, max_value=30, value=15, step=1,
                    help="Differences beyond this saturate the color.",
                    key="growth_cap"
                )
                show_legend = st.checkbox("Show legend", value=False, key="growth_legend")

    # ══════════════════════════════════════════════════════════
    # MAP COLUMN
    # ══════════════════════════════════════════════════════════
    with col_map:

        # ── SNAPSHOT MAP ──────────────────────────────────────
        if econ_view == "Snapshot":
            column = econ_vars[selected_layer]
            bench_avg = get_benchmark_value(benchmark_row, column)
            reverse = not HIGHER_IS_BETTER.get(column, True)

            merged_econ = merged.copy()
            merged_econ["color"] = merged_econ[column].apply(
                lambda x: value_to_color(x, bench_avg, reverse=reverse)
            )

            if column in merged_econ.columns:
                valid_vals = merged_econ[column].dropna()
                m1, m2, m3 = st.columns(3)
                m1.metric("Median", format_value(valid_vals.median(), column))
                m2.metric("Highest", format_value(valid_vals.max(), column))
                m3.metric("Lowest", format_value(valid_vals.min(), column))

            econ_json = json.loads(merged_econ.to_json())

            st.pydeck_chart(pdk.Deck(
                layers=[pdk.Layer(
                    "GeoJsonLayer",
                    data=econ_json,
                    get_fill_color="properties.color",
                    get_line_color=[255, 255, 255, 50],
                    line_width_min_pixels=1,
                    pickable=True,
                )],
                initial_view_state=VIEW_STATE,
                tooltip={
                    "html": f"<b>{{display_name}}</b><br/>{selected_layer}: {{{column}}}",
                    "style": TOOLTIP_STYLE,
                },
                map_style=MAP_STYLE,
            ), height=560)

            render_detail_panel(merged_econ, column, selected_layer)

        # ── GROWTH MAP ────────────────────────────────────────
        else:
            if geography == "County" or growth_start >= growth_end:
                st.info("Select Tract geography and a valid year range to view change over time.")
            else:
                if geography == "Tract":
                    src = census
                    id_col = "tract_code"
                    join_col = "TRACTCE"
                    gdf_base = gdf_tracts
                elif geography == "Zip Code":
                    src = zcta_data
                    id_col = "zcta"
                    join_col = "ZCTA5CE20"
                    gdf_base = gdf_zctas
                else:
                    src = id_col = join_col = gdf_base = None

                t0 = src[src["year"] == growth_start][[id_col, growth_col]].rename(
                    columns={growth_col: "val_start"})
                t1 = src[src["year"] == growth_end][[id_col, growth_col]].rename(
                    columns={growth_col: "val_end"})
                growth_df = t0.merge(t1, on=id_col, how="inner")
                growth_df = growth_df[
                    growth_df["val_start"].notna() & (growth_df["val_start"] != 0) &
                    growth_df["val_end"].notna()
                ].copy()
                growth_df["JOINKEY"] = growth_df[id_col].astype(str).str.zfill(
                    6 if geography == "Tract" else 5
                )

                is_dollar = (growth_col == "median_household_income")
                if is_dollar:
                    growth_df["tract_change"] = (
                        (growth_df["val_end"] - growth_df["val_start"])
                        / growth_df["val_start"] * 100
                    )
                    change_label = "% growth"
                else:
                    growth_df["tract_change"] = growth_df["val_end"] - growth_df["val_start"]
                    change_label = "pp change"

                bench_label = selected_benchmark
                if selected_benchmark == "National":
                    bench_src = benchmarks_national
                elif selected_benchmark == "Pennsylvania":
                    bench_src = benchmarks_pa
                elif selected_benchmark == "Erie County":
                    bench_src = benchmarks_erie
                else:
                    bench_src = benchmarks_counties[
                        benchmarks_counties["name"] == compare_county
                    ]

                b0 = bench_src.loc[bench_src["year"] == growth_start, growth_col].values
                b1 = bench_src.loc[bench_src["year"] == growth_end, growth_col].values

                if len(b0) and len(b1) and b0[0] and b0[0] != 0:
                    bench_change = (b1[0] - b0[0]) / b0[0] * 100 if is_dollar else b1[0] - b0[0]
                else:
                    bench_change = None

                growth_df["relative_change"] = (
                    growth_df["tract_change"] - bench_change
                    if bench_change is not None else float("nan")
                )

                gdf_base[join_col] = gdf_base[join_col].astype(str).str.zfill(
                    6 if geography == "Tract" else 5
                )
                if geography == "Zip Code":
                    zcta_names = zcta_data[["zcta", "area_name"]].drop_duplicates()
                    zcta_names["zcta"] = zcta_names["zcta"].astype(str).str.zfill(5)
                    growth_df = growth_df.merge(zcta_names, left_on="JOINKEY", right_on="zcta", how="left")
                merged_growth = gdf_base.merge(
                    growth_df, left_on=join_col, right_on="JOINKEY", how="left"
                )

                def diverging_growth_color(val, cap, higher_better):
                    if pd.isna(val):
                        return [200, 200, 200, 140]
                    signed = val if higher_better else -val
                    normalized = (signed / cap) / 2 + 0.5
                    normalized = max(0.0, min(1.0, normalized))
                    if normalized < 0.5:
                        t = normalized * 2
                        r = int(200 - (t * 40))
                        g = int(80 + (t * 60))
                        b = int(60 + (t * 20))
                    else:
                        t = (normalized - 0.5) * 2
                        r = int(160 - (t * 120))
                        g = int(140 + (t * 70))
                        b = int(80 - (t * 20))
                    return [r, g, b, 180]

                merged_growth["color"] = merged_growth["relative_change"].apply(
                    lambda x: diverging_growth_color(x, growth_cap, higher_is_better_growth)
                )

                def fmt_change(x):
                    if pd.isna(x): return "N/A"
                    sign = "+" if x >= 0 else ""
                    return f"{sign}{x:.1f}"

                if geography == "Zip Code":
                    merged_growth["t_name"] = (
                        merged_growth["area_name"].fillna("Unknown") +
                        " (" + merged_growth["JOINKEY"].astype(str) + ")"
                    )
                else:
                    merged_growth["t_name"] = merged_growth["NAMELSAD"].fillna("Unknown")

                merged_growth["t_abs"] = merged_growth["tract_change"].apply(fmt_change)
                merged_growth["t_rel"] = merged_growth["relative_change"].apply(fmt_change)
                merged_growth["t_start"] = merged_growth["val_start"].apply(
                    lambda x: format_value(x, growth_col) if pd.notna(x) else "N/A")
                merged_growth["t_end"] = merged_growth["val_end"].apply(
                    lambda x: format_value(x, growth_col) if pd.notna(x) else "N/A")
                bench_str = f"{bench_change:+.1f}" if bench_change is not None else "N/A"

                valid_rel = merged_growth["relative_change"].dropna()
                ahead = int((valid_rel > 0).sum()) if higher_is_better_growth else int((valid_rel < 0).sum())
                behind = len(valid_rel) - ahead
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(f"{geo_label}s ahead of benchmark", str(ahead))
                m2.metric(f"{geo_label}s behind benchmark", str(behind))
                m3.metric(f"Benchmark change ({bench_label})", f"{bench_str} {change_label}")
                m4.metric("Median tract change",
                          fmt_change(merged_growth["tract_change"].median()) + f" {change_label}")

                if show_legend:
                    lc, mc, rc = st.columns([1, 2, 1])
                    good_label = "Improved" if higher_is_better_growth else "Fell"
                    bad_label = "Fell" if higher_is_better_growth else "Improved"
                    lc.markdown(
                        f"<div style='background:linear-gradient(to right,rgb(200,80,60),rgb(160,140,80));"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b'>{bad_label} behind</div>",
                        unsafe_allow_html=True
                    )
                    mc.markdown(
                        f"<div style='background:rgb(160,140,80);border:1px solid #e2e8f0;"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b;text-align:center'>Kept pace</div>",
                        unsafe_allow_html=True
                    )
                    rc.markdown(
                        f"<div style='background:linear-gradient(to right,rgb(160,140,80),rgb(40,210,60));"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b;text-align:right'>{good_label} vs benchmark</div>",
                        unsafe_allow_html=True
                    )

                geo_key_col = join_col
                geojson_cols = ["geometry", "color", "t_name", "t_abs", "t_rel", "t_start", "t_end"]
                if geo_key_col in merged_growth.columns:
                    geojson_cols = [geo_key_col] + geojson_cols
                growth_geojson = json.loads(
                    merged_growth[[c for c in geojson_cols if c in merged_growth.columns]].to_json()
                )

                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer(
                        "GeoJsonLayer",
                        data=growth_geojson,
                        get_fill_color="properties.color",
                        get_line_color=[80, 80, 80, 100],
                        line_width_min_pixels=1,
                        pickable=True,
                        auto_highlight=True,
                    )],
                    initial_view_state=VIEW_STATE,
                    tooltip={
                        "html": (
                            f"<b>{{t_name}}</b><br/>"
                            f"{growth_var_label}: {{t_start}} &rarr; {{t_end}}<br/>"
                            f"Change: {{t_abs}} {change_label}<br/>"
                            f"vs {bench_label}: {{t_rel}} {change_label}"
                        ),
                        "style": TOOLTIP_STYLE,
                    },
                    map_style=MAP_STYLE,
                ), height=560)

                with st.expander("Full tract ranking"):
                    rank_df = merged_growth[["t_name", "t_start", "t_end",
                                             "tract_change", "relative_change"]].copy()
                    rank_df.columns = [
                        geo_label,
                        f"{growth_start} Value",
                        f"{growth_end} Value",
                        f"Change ({change_label})",
                        f"vs {bench_label} ({change_label})",
                    ]
                    rank_df = rank_df.dropna(subset=[f"Change ({change_label})"])
                    rank_df[f"Change ({change_label})"] = rank_df[f"Change ({change_label})"].round(1)
                    rank_df[f"vs {bench_label} ({change_label})"] = rank_df[
                        f"vs {bench_label} ({change_label})"
                    ].round(1)
                    rank_df = rank_df.sort_values(f"vs {bench_label} ({change_label})", ascending=False)
                    st.dataframe(rank_df, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════
    # INCOME STRATIFICATION — full width below map/controls
    # ══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("📊 Household Income Stratification")
    st.caption(
        "Share of households by income tier per census tract, 2019–2023. "
        "Tiers are fixed dollar thresholds: bottom (under $35k), middle ($35k–$75k), top ($75k+). "
        "Year-over-year shifts may partly reflect inflation in addition to real income change."
    )

    @st.cache_data
    def load_stratification_data():
        df = pd.read_csv("data/processed/income_stratification.csv")
        return df

    strat_df = load_stratification_data()

    BAND_LABELS = {
        "under_10k":  "Under $10k",
        "10k_15k":    "$10k–$15k",
        "15k_20k":    "$15k–$20k",
        "20k_25k":    "$20k–$25k",
        "25k_30k":    "$25k–$30k",
        "30k_35k":    "$30k–$35k",
        "35k_40k":    "$35k–$40k",
        "40k_45k":    "$40k–$45k",
        "45k_50k":    "$45k–$50k",
        "50k_60k":    "$50k–$60k",
        "60k_75k":    "$60k–$75k",
        "75k_100k":   "$75k–$100k",
        "100k_125k":  "$100k–$125k",
        "125k_150k":  "$125k–$150k",
        "150k_200k":  "$150k–$200k",
        "200k_plus":  "$200k+",
    }

    TIER_COLORS = {
        "Bottom (under $35k)": "#c45c3a",
        "Middle ($35k–$75k)":  "#e9c46a",
        "Top ($75k+)":         "#2d6a4f",
    }

    BAND_COLORS = [
        "#b5432a", "#c45c3a", "#d4754a", "#e08c5a", "#e9a46a", "#e9c46a",
        "#c8c86a", "#a8c86a", "#88c87a", "#68b87a", "#4da870", "#2d6a4f",
        "#266045", "#1f563c", "#184c33", "#11422a",
    ]

    strat_col1, strat_col2 = st.columns([2, 1])
    with strat_col1:
        strat_county = st.radio(
            "County",
            options=["Erie", "Crawford"],
            horizontal=True,
            key="strat_county"
        )
    with strat_col2:
        view_mode = st.radio(
            "View",
            options=["Tiers", "All bands"],
            horizontal=True,
            key="strat_view_mode"
        )

    county_tracts = strat_df[strat_df["county"] == strat_county][["geoid", "NAME"]].drop_duplicates()
    county_tracts = county_tracts.sort_values("NAME")
    county_tracts["display"] = county_tracts["NAME"].str.replace(r";.*$", "", regex=True).str.strip()
    tract_options = county_tracts["geoid"].tolist()
    tract_labels  = dict(zip(county_tracts["geoid"], county_tracts["display"]))

    selected_tract = st.selectbox(
        "Select a census tract",
        options=tract_options,
        format_func=lambda g: tract_labels.get(g, g),
        key="strat_tract_selector"
    )

    tract_data = strat_df[strat_df["geoid"] == selected_tract].sort_values("year")

    if tract_data.empty:
        st.warning("No data found for this tract.")
    else:
        tract_name = tract_labels.get(selected_tract, selected_tract)

        latest   = tract_data[tract_data["year"] == tract_data["year"].max()].iloc[0]
        earliest = tract_data[tract_data["year"] == tract_data["year"].min()].iloc[0]
        bottom_delta = round(latest["share_bottom"] - earliest["share_bottom"], 1)
        top_delta    = round(latest["share_top"]    - earliest["share_top"],    1)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Households (latest)", f"{int(latest['total_households']):,}")
        m2.metric("Bottom Tier Share", f"{latest['share_bottom']:.1f}%",
                  delta=f"{bottom_delta:+.1f}pp since 2019", delta_color="inverse")
        m3.metric("Middle Tier Share", f"{latest['share_middle']:.1f}%")
        m4.metric("Top Tier Share", f"{latest['share_top']:.1f}%",
                  delta=f"{top_delta:+.1f}pp since 2019")

        st.markdown(f"#### {tract_name} — Income Distribution by Year")

        fig = go.Figure()

        if view_mode == "Tiers":
            fig.add_trace(go.Bar(
                name="Bottom (under $35k)",
                x=tract_data["year"], y=tract_data["share_bottom"],
                marker_color=TIER_COLORS["Bottom (under $35k)"],
                hovertemplate="%{x}: %{y:.1f}% bottom tier<extra></extra>"
            ))
            fig.add_trace(go.Bar(
                name="Middle ($35k–$75k)",
                x=tract_data["year"], y=tract_data["share_middle"],
                marker_color=TIER_COLORS["Middle ($35k–$75k)"],
                hovertemplate="%{x}: %{y:.1f}% middle tier<extra></extra>"
            ))
            fig.add_trace(go.Bar(
                name="Top ($75k+)",
                x=tract_data["year"], y=tract_data["share_top"],
                marker_color=TIER_COLORS["Top ($75k+)"],
                hovertemplate="%{x}: %{y:.1f}% top tier<extra></extra>"
            ))
        else:
            for i, (band, label) in enumerate(BAND_LABELS.items()):
                share_col = f"share_{band}"
                if share_col not in tract_data.columns:
                    continue
                fig.add_trace(go.Bar(
                    name=label,
                    x=tract_data["year"], y=tract_data[share_col],
                    marker_color=BAND_COLORS[i],
                    hovertemplate=f"%{{x}}: %{{y:.1f}}% {label}<extra></extra>"
                ))

        fig.update_layout(
            barmode="stack",
            height=380,
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis=dict(
                tickmode="array",
                tickvals=tract_data["year"].tolist(),
                tickformat="d",
            ),
            yaxis=dict(
                title="Share of households (%)",
                range=[0, 100],
                gridcolor="rgba(200,200,200,0.15)",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        )
        st.plotly_chart(fig, use_container_width=True)

        if view_mode == "All bands":
            st.caption(
                "⚠ Individual income bands carry wider margins of error than tier totals, "
                "particularly for small tracts. Use band-level detail for directional insight "
                "rather than precise estimates."
            )
# ═══════════════════════════════════════════════════════
# TAB 3 — TRANSIT
# ═══════════════════════════════════════════════════════
with tab_transit:
    col_controls_t, col_map_t = st.columns([1, 3])

    with col_controls_t:
        st.subheader("Transit Coverage")

        if geography == "County":
            st.info("Change Over Time is not available at the County level.")

        show_routes = st.checkbox("Show EMTA Routes", value=True, key="transit_routes")
        show_stops = st.checkbox("Show Bus Stops", value=True, key="transit_stops")
        show_no_vehicle = st.checkbox("Show No Vehicle Layer", value=True, key="transit_no_vehicle")

        transit_tool = "None"
        transit_threshold_veh = None
        transit_threshold_freq = None
        desert_threshold = None

        if mode == "Advanced" and geography == "Tract":
            st.markdown("---")
            st.markdown("**Transit Analysis Tools**")
            transit_tool = st.selectbox(
                "Tool",
                ["None", "Coverage Gap Finder", "Transit Desert Finder"],
                key="transit_tool"
            )

            if transit_tool == "Coverage Gap Finder":
                st.markdown("Tracts where residents lack cars **and** bus service is limited")
                transit_threshold_veh = st.slider(
                    "No Vehicle Rate above (%)", 0.0, 100.0, 15.0, 0.5, key="veh_threshold"
                )
                transit_threshold_freq = st.slider(
                    "Total daily visits below",
                    0.0, float(transit_stats["total_daily_visits"].max()),
                    100.0, 5.0, key="freq_threshold"
                )

            if transit_tool == "Transit Desert Finder":
                st.markdown("Tracts beyond a distance from the nearest stop")
                desert_threshold = st.slider(
                    "Distance to nearest stop (miles)",
                    0.0, float(transit_stats["nearest_stop_miles"].max()),
                    1.0, 0.1, key="desert_threshold"
                )

    with col_map_t:
        transit_layers = []
        national_avg_t = get_benchmark_value(benchmark_row, "no_vehicle_rate")

        merged_transit = merged.copy()
        merged_transit["color"] = merged_transit["no_vehicle_rate"].apply(
            lambda x: value_to_color(x, national_avg_t, reverse=True)
        )

        if geography == "Tract":
            if transit_tool == "Coverage Gap Finder" and transit_threshold_veh and transit_threshold_freq:
                gap_mask = (
                    (merged_transit["no_vehicle_rate"] > transit_threshold_veh) &
                    (merged_transit["total_daily_visits"] < transit_threshold_freq)
                )
                merged_transit["color"] = merged_transit.apply(
                    lambda row: row["color"] if gap_mask[row.name] else [100, 100, 100, 60], axis=1
                )
                st.metric("Coverage gap tracts", int(gap_mask.sum()))

            elif transit_tool == "Transit Desert Finder" and desert_threshold:
                desert_mask = merged_transit["nearest_stop_miles"] > desert_threshold
                merged_transit["color"] = merged_transit.apply(
                    lambda row: row["color"] if desert_mask[row.name] else [100, 100, 100, 60], axis=1
                )
                st.metric("Transit desert tracts", int(desert_mask.sum()))

        transit_json = json.loads(merged_transit.to_json())

        if show_no_vehicle:
            transit_layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=transit_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            ))

        if show_routes:
            route_paths = []
            for shape_id, group in shapes.groupby("shape_id"):
                group = group.sort_values("shape_pt_sequence")
                coords = [[row["shape_pt_lon"], row["shape_pt_lat"]]
                          for _, row in group.iterrows()]
                color_hex = str(group["route_color"].iloc[0])
                r = int(color_hex[0:2], 16)
                g = int(color_hex[2:4], 16)
                b = int(color_hex[4:6], 16)
                route_paths.append({
                    "path": coords,
                    "name": group["route_long_name"].iloc[0],
                    "color": [r, g, b, 200]
                })
            transit_layers.append(pdk.Layer(
                "PathLayer",
                data=route_paths,
                get_path="path",
                get_color="color",
                width_min_pixels=2,
                pickable=False
            ))

        if show_stops:
            stops_data = stops.copy()
            stops_data["radius"] = stops_data["daily_visits"].apply(
                lambda x: max(30, min(150, x * 1.5))
            )
            stops_data["color"] = [[50, 50, 50, 200]] * len(stops_data)
            transit_layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=stops_data,
                get_position=["stop_lon", "stop_lat"],
                get_radius="radius",
                get_fill_color="color",
                pickable=True,
                opacity=0.8
            ))

        transit_tooltip_html = (
            "<b>{stop_name}</b><br/>"
            "Daily visits: {daily_visits}<br/>"
            "First bus: {first_service}<br/>"
            "Last bus: {last_service}<br/>"
            "<b>{display_name}</b><br/>"
            "No Vehicle Rate: {no_vehicle_rate}%<br/>"
            "Stop count: {stop_count}<br/>"
            "Nearest stop: {nearest_stop_miles} miles"
            if geography == "Tract"
            else
            "<b>{display_name}</b><br/>"
            "No Vehicle Rate: {no_vehicle_rate}%"
        )

        st.pydeck_chart(pdk.Deck(
            layers=transit_layers,
            initial_view_state=VIEW_STATE,
            tooltip={"html": transit_tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE
        ), height=600)

# ═══════════════════════════════════════════════════════
# TAB 4 — FOOD ACCESS
# ═══════════════════════════════════════════════════════
with tab_food:
    col_controls_f, col_map_f = st.columns([1, 3])

    with col_controls_f:
        st.subheader("Food Access")
        show_pantries = st.checkbox("Show Food Pantries", value=True, key="food_pantries")
        show_food_layer = st.checkbox("Show Food Insecurity Layer", value=True, key="food_layer")
        show_food_deserts = st.checkbox("Show Food Deserts (USDA)", value=False, key="food_deserts")

        if geography != "Tract":
            st.info("Food insecurity data is only available at the Tract level. "
                    "The map shows Poverty Rate at your selected geography.")
        elif show_food_deserts:
            st.caption(
                "Food deserts (orange outline) = low income tracts where "
                "at least 500 people or 33% of the population live more than "
                "1 mile from a grocery store (urban) or 10 miles (rural)."
            )

    with col_map_f:
        food_layers = []
        merged_food = merged.copy()

        if geography == "Tract" and "food_insecurity_rate" in merged_food.columns:
            food_color_col = "food_insecurity_rate"
        else:
            food_color_col = "poverty_rate"

        food_benchmark = get_benchmark_value(benchmark_row, "poverty_rate")
        merged_food["color"] = merged_food[food_color_col].apply(
            lambda x: value_to_color(x, food_benchmark, reverse=True)
        )

        # Food desert outline layer
        if show_food_deserts and geography == "Tract" and "food_desert_1_10" in merged_food.columns:
            desert_tracts = merged_food[merged_food["food_desert_1_10"] == 1].copy()
            if len(desert_tracts) > 0:
                desert_json = json.loads(desert_tracts.to_json())
                food_layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data=desert_json,
                    get_fill_color=[0, 0, 0, 0],
                    get_line_color=[255, 140, 0, 255],
                    line_width_min_pixels=3,
                    pickable=False
                ))
                st.metric("Food desert tracts", len(desert_tracts))

        food_json = json.loads(merged_food.to_json())

        if show_food_layer:
            food_layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=food_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            ))

        if show_pantries:
            pantries_data = pantries.dropna(subset=["lat", "lon"]).copy()
            pantries_data["color"] = [[0, 150, 0, 220]] * len(pantries_data)
            pantries_data["hours"] = pantries_data["Open"].fillna("Hours not available")
            food_layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=pantries_data,
                get_position=["lon", "lat"],
                get_radius=200,
                get_fill_color="color",
                pickable=True,
                opacity=0.9
            ))

        food_tooltip_html = (
            "<b>{PantryName}</b><br/>"
            "Hours: {hours}<br/>"
            "<b>{display_name}</b><br/>"
            "Food Insecurity: {food_insecurity_rate}%"
            if geography == "Tract"
            else
            "<b>{PantryName}</b><br/>"
            "Hours: {hours}<br/>"
            "<b>{display_name}</b><br/>"
            "Poverty Rate: {poverty_rate}%"
        )

        st.pydeck_chart(pdk.Deck(
            layers=food_layers,
            initial_view_state=VIEW_STATE,
            tooltip={"html": food_tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE
        ), height=600)

    # ── Pantry Detail Section ─────────────────────────────────────────────────────
    # Add this to the bottom of your Food Access tab block in app_v2.py
    # Requires these imports at the top of app_v2.py (add if not already present):
    #   import plotly.graph_objects as go
    #   from plotly.subplots import make_subplots

    st.markdown("---")
    st.subheader("Food Pantry & Program Activity")
    st.caption("Monthly reporting data from Second Harvest Food Bank partner agencies.")


    # ── Load data ─────────────────────────────────────────────────────────────────
    @st.cache_data
    def load_pantry_data():
        monthly = pd.read_csv("data/processed/pantry_agency_monthly.csv", parse_dates=["date"])
        index = pd.read_csv("data/processed/pantry_agency_index.csv")
        return monthly, index


    pantry_monthly, pantry_index = load_pantry_data()

    # ── County filter ─────────────────────────────────────────────────────────────
    pantry_county = st.radio(
        "Filter by county",
        options=["Erie", "Crawford", "Both"],
        horizontal=True,
        key="pantry_county_filter"
    )

    if pantry_county == "Both":
        filtered_index = pantry_index.copy()
    else:
        filtered_index = pantry_index[pantry_index["county"] == pantry_county]

    # ── Build grouped dropdown options ────────────────────────────────────────────
    # Format: {program_type: [(display_label, agency_ref+program_type key), ...]}
    PROGRAM_LABELS = {
        "Food Pantry/TEFAP": "Food Pantry (TEFAP)",
        "Food Pantry/No TEFAP": "Food Pantry (No TEFAP)",
        "Produce Express": "Produce Express",
        "BackPacks": "Backpack Program",
        "School Pantry": "School Pantry",
        "Non-Emerg. Meal/Snack": "Meal / Snack Program",
        "Kids Cafe": "Kids Cafe",
        "Original": "Other",
    }

    # Build a flat list of options grouped by program type
    # Streamlit selectbox doesn't support true grouping, so we use divider labels
    options = ["— Select a pantry or program —"]
    option_keys = [None]  # parallel list mapping option index to (agency_ref, program_type)

    for prog_type in PROGRAM_LABELS.keys():
        group = filtered_index[filtered_index["program_type"] == prog_type].sort_values("agency_name")
        if group.empty:
            continue
        # Group header (non-selectable visual divider)
        header = f"── {PROGRAM_LABELS[prog_type]} ──"
        options.append(header)
        option_keys.append(None)
        for _, row in group.iterrows():
            county_tag = f" ({row['county']})" if pantry_county == "Both" else ""
            label = f"  {row['agency_name']}{county_tag}"
            options.append(label)
            option_keys.append((row["agency_ref"], row["program_type"]))

    selected_idx = st.selectbox(
        "Select a program",
        range(len(options)),
        format_func=lambda i: options[i],
        key="pantry_selector"
    )

    selected_key = option_keys[selected_idx]

    # ── Detail panel ──────────────────────────────────────────────────────────────
    if selected_key is not None:
        sel_ref, sel_prog = selected_key

        # Get agency info
        agency_info = pantry_index[
            (pantry_index["agency_ref"] == sel_ref) &
            (pantry_index["program_type"] == sel_prog)
            ].iloc[0]

        # Get monthly data
        agency_monthly = pantry_monthly[
            (pantry_monthly["agency_ref"] == sel_ref) &
            (pantry_monthly["program_type"] == sel_prog)
            ].sort_values("date")

        # ── Header ────────────────────────────────────────────────────────────────
        st.markdown(f"### {agency_info['agency_name']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Program Type", PROGRAM_LABELS.get(sel_prog, sel_prog))
        col2.metric("County", agency_info["county"])
        col3.metric(
            "Reporting Period",
            f"{pd.to_datetime(agency_info['first_month']).strftime('%b %Y')} – "
            f"{pd.to_datetime(agency_info['last_month']).strftime('%b %Y')}"
        )

        # ── Summary stats ─────────────────────────────────────────────────────────
        total_served = int(agency_monthly["total_individuals"].sum())
        avg_monthly = agency_monthly["total_individuals"].mean()
        peak_row = agency_monthly.loc[agency_monthly["total_individuals"].idxmax()]
        peak_month = peak_row["date"].strftime("%b %Y")
        peak_val = int(peak_row["total_individuals"])

        s1, s2, s3 = st.columns(3)
        s1.metric("Total Individuals Served", f"{total_served:,}")
        s2.metric("Avg per Month", f"{avg_monthly:,.0f}")
        s3.metric("Peak Month", f"{peak_month} ({peak_val:,})")

        # ── Line chart: monthly individuals served ────────────────────────────────
        st.markdown("#### Monthly Individuals Served")

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(
            x=agency_monthly["date"],
            y=agency_monthly["total_individuals"],
            mode="lines+markers",
            line=dict(color="#2d6a4f", width=2),
            marker=dict(size=6),
            name="Individuals Served",
            hovertemplate="%{x|%b %Y}: %{y:,} individuals<extra></extra>"
        ))
        x_min = agency_monthly["date"].min()
        x_max = agency_monthly["date"].max()

        line_fig.update_layout(
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis_title=None,
            yaxis_title="Individuals",
            xaxis=dict(
                range=[x_min, x_max],
                tickmode="array",
                tickvals=agency_monthly["date"].tolist(),
                tickformat="%b %Y",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
        )
        st.plotly_chart(line_fig, use_container_width=True)

        # ── Stacked bar: age group breakdown ─────────────────────────────────────
        # Only show if at least some age group data exists
        has_age_data = agency_monthly[["children", "adults", "seniors"]].sum().sum() > 0

        if has_age_data:
            st.markdown("#### Individuals Served by Age Group")

            bar_fig = go.Figure()
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["children"],
                name="Children (0–17)",
                marker_color="#52b788",
                hovertemplate="%{x|%b %Y}: %{y:,} children<extra></extra>"
            ))
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["adults"],
                name="Adults (18–59)",
                marker_color="#2d6a4f",
                hovertemplate="%{x|%b %Y}: %{y:,} adults<extra></extra>"
            ))
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["seniors"],
                name="Seniors (60+)",
                marker_color="#1b4332",
                hovertemplate="%{x|%b %Y}: %{y:,} seniors<extra></extra>"
            ))
            bar_fig.update_layout(
                barmode="stack",
                height=300,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title=None,
                yaxis_title="Individuals",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
                xaxis=dict(
                    range=[x_min, x_max],
                    tickmode="array",
                    tickvals=agency_monthly["date"].tolist(),
                    tickformat="%b %Y",
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("Age group breakdown not available for this program type.")

        has_new_hh_data = agency_monthly["new_households"].sum() > 0

        if has_new_hh_data:
            st.markdown("#### New Households per Month")
            st.caption("First-time households — an indicator of whether demand is expanding.")

            hh_fig = go.Figure()
            hh_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["new_households"],
                marker_color="#52b788",
                hovertemplate="%{x|%b %Y}: %{y:,} new households<extra></extra>"
            ))
            hh_fig.update_layout(
                height=280,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis=dict(
                    range=[x_min, x_max],
                    tickmode="array",
                    tickvals=agency_monthly["date"].tolist(),
                    tickformat="%b %Y",
                ),
                yaxis_title="Households",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
            )
            st.plotly_chart(hh_fig, use_container_width=True)

# ═══════════════════════════════════════════════════════
# TAB 5 — HEALTH
# ═══════════════════════════════════════════════════════
with tab_health:
    col_controls_h, col_map_h = st.columns([1, 3])

    HEALTH_VARS = {
        "Diabetes Rate": "diabetes_rate",
        "High Blood Pressure": "high_bp_rate",
        "Depression Rate": "depression_rate",
        "Obesity Rate": "obesity_rate",
        "Smoking Rate": "smoking_rate",
        "No Health Insurance": "no_insurance_rate",
        "Poor Mental Health (14+ days)": "poor_mental_health_rate",
        "Poor Physical Health (14+ days)": "poor_physical_health_rate",
        "Asthma Rate": "asthma_rate",
        "Heart Disease Rate": "heart_disease_rate",
        "Stroke Rate": "stroke_rate",
        "COPD Rate": "copd_rate",
        "Physical Inactivity": "physical_inactivity_rate",
        "Sleep Deprivation": "sleep_deprivation_rate",
    }

    with col_controls_h:
        st.subheader("Health Outcomes")
        st.caption("Source: CDC PLACES 2023 release (2021 BRFSS data). Tract level only.")

        if geography != "Tract":
            st.info("Health data from CDC PLACES is only available at the Tract level. Switch Geography to Tract to use this tab.")

        health_layer = st.selectbox(
            "Variable", list(HEALTH_VARS.keys()), key="health_layer"
        )
        health_col = HEALTH_VARS[health_layer]

        st.markdown("---")
        st.markdown("**Explore a Tract**")
        if geography == "Tract":
            health_geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
            health_selected = st.selectbox("Select tract", health_geo_options, key="health_geo_select")
            if health_selected != "None":
                sel_row = merged[merged["display_name"] == health_selected].iloc[0]
                st.session_state.selected_geo = sel_row[geo_id_col]
                st.session_state.selected_geo_name = health_selected

    with col_map_h:
        merged_health = merged.copy()

        if geography == "Tract" and health_col in merged_health.columns:
            health_avg = merged_health[health_col].mean()
            merged_health["color"] = merged_health[health_col].apply(
                lambda x: value_to_color(x, health_avg, reverse=True)
            )
            health_metric_val = merged_health[health_col].median()
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Median {health_layer}", f"{health_metric_val:.1f}%" if health_metric_val else "—")
            c2.metric("Highest tract", f"{merged_health[health_col].max():.1f}%")
            c3.metric("Lowest tract", f"{merged_health[health_col].min():.1f}%")
        else:
            merged_health["color"] = [[200, 200, 200, 140]] * len(merged_health)

        health_json = json.loads(merged_health.to_json())

        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer",
                data=health_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            )],
            initial_view_state=VIEW_STATE,
            tooltip={
                "html": "<b>{display_name}</b><br/>"
                        f"{health_layer}: {{{health_col}}}%<br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "No Insurance: {no_insurance_rate}%",
                "style": TOOLTIP_STYLE
            },
            map_style=MAP_STYLE
        ), height=600)

        if geography == "Tract":
            st.markdown("---")

            # Health summary table for all tracts
            st.markdown("**All Tracts — Health Summary**")
            health_summary_cols = ["display_name"] + [c for c in HEALTH_VARS.values() if c in merged_health.columns]
            health_table = merged_health[health_summary_cols].dropna(subset=[health_col]).copy()
            health_table = health_table.sort_values(health_col, ascending=False).reset_index(drop=True)
            health_table.index += 1
            health_table = health_table.rename(columns={"display_name": "Tract"})
            health_table = health_table.rename(columns={v: k for k, v in HEALTH_VARS.items() if v in health_table.columns})
            st.dataframe(health_table, use_container_width=True)

# ═══════════════════════════════════════════════════════
# TAB 6 — SERVICES
# ═══════════════════════════════════════════════════════
with tab_services:
    svc_col_controls, svc_col_map = st.columns([1, 3])

    with svc_col_controls:
        st.subheader("Community Services")
        st.caption("Food retail: USDA SNAP (March 2026). All other services: OpenStreetMap.")

        svc_view = st.radio("Category", list(LAYER_CONFIG.keys()), horizontal=False, key="svc_view")
        st.markdown("---")
        st.markdown(f"**{svc_view} layers**")

        svc_active_layers = {}
        for subcat, cfg in LAYER_CONFIG[svc_view].items():
            parent_on = st.checkbox(subcat, value=cfg["default_on"], key=f"svc_p_{subcat}")
            if not parent_on:
                continue
            if cfg["subtypes"]:
                selected_subtypes = []
                for sub_label, sub_cfg in cfg["subtypes"].items():
                    sub_on = st.checkbox(f"  ↳ {sub_label}", value=sub_cfg["default_on"], key=f"svc_s_{subcat}_{sub_label}")
                    if sub_on:
                        selected_subtypes.append((sub_cfg["value"], sub_cfg["color"]))
                if selected_subtypes:
                    svc_active_layers[subcat] = {"cfg": cfg, "subtypes": selected_subtypes}
            else:
                svc_active_layers[subcat] = {"cfg": cfg, "subtypes": None}

        st.markdown("---")
        svc_show_heatmap = st.checkbox("Show heatmap", value=False, key="svc_heatmap")

        st.markdown("---")
        st.markdown("### What's Near Me?")
        st.caption("Find services within a set distance of any address.")

        svc_address_input = st.text_input("Address", placeholder="e.g. 1341 W 26th St, Erie, PA",
                                          label_visibility="collapsed", key="svc_address")
        rb1, rb2 = st.columns([2, 1])
        with rb1:
            svc_radius = st.selectbox("Radius", [0.25, 0.5, 1.0, 2.0, 5.0], index=2,
                                      format_func=lambda x: f"{x} mile{'s' if x != 1.0 else ''}",
                                      key="svc_radius")
        with rb2:
            st.markdown("<br/>", unsafe_allow_html=True)
            svc_search_btn = st.button("Search", use_container_width=True, key="svc_search_btn")

        svc_cat_filter = st.multiselect(
            "Limit to categories",
            options=sorted(pois["primary_category"].unique().tolist()),
            default=[], placeholder="All categories", key="svc_cat_filter"
        )

        if svc_search_btn and svc_address_input.strip():
            with st.spinner("Geocoding..."):
                slat, slon, slabel = geocode_address(svc_address_input.strip() + ", PA")
            if slat is None:
                st.error("Address not found. Try including city and state.")
                st.session_state.svc_search_lat = None
                st.session_state.svc_search_results = None
            else:
                st.session_state.svc_search_lat = slat
                st.session_state.svc_search_lon = slon
                st.session_state.svc_search_label = slabel
                nearby = pois.copy()
                nearby["distance_miles"] = nearby.apply(
                    lambda r: haversine_miles(slat, slon, r["lat"], r["lon"]), axis=1
                )
                nearby = nearby[nearby["distance_miles"] <= svc_radius].sort_values("distance_miles")
                st.session_state.svc_search_results = nearby
                st.rerun()

        if st.session_state.svc_search_lat:
            svc_results = st.session_state.svc_search_results
            if svc_cat_filter:
                svc_results = svc_results[svc_results["primary_category"].isin(svc_cat_filter)]
            if svc_results is None or len(svc_results) == 0:
                st.info("No services found in that radius.")
            else:
                st.success(f"**{len(svc_results)}** services found")
                cat_counts = (
                    svc_results.groupby(["primary_category", "type"])
                    .size().reset_index(name="Count")
                    .sort_values("Count", ascending=False)
                    .rename(columns={"primary_category": "Category", "type": "Type"})
                )
                with st.expander(f"By category ({len(cat_counts)} types)", expanded=True):
                    st.dataframe(cat_counts, use_container_width=True, hide_index=True)
            if st.button("Clear search", key="svc_clear"):
                st.session_state.svc_search_lat = None
                st.session_state.svc_search_lon = None
                st.session_state.svc_search_label = None
                st.session_state.svc_search_results = None
                st.rerun()

    with svc_col_map:
        svc_layers = []
        svc_visible = []
        svc_point_size = 4

        # Choropleth underlay — poverty rate
        if geography == "Tract" and "poverty_rate" in merged.columns:
            svc_merged = merged.copy()
            svc_avg = get_benchmark_value(benchmark_row, "poverty_rate")
            svc_merged["color"] = svc_merged["poverty_rate"].apply(
                lambda x: value_to_color(x, svc_avg, reverse=True)
            )
            svc_geojson = json.loads(svc_merged[["geometry", "color", "display_name", "poverty_rate"]].to_json())
            svc_layers.append(pdk.Layer(
                "GeoJsonLayer", data=svc_geojson,
                get_fill_color="properties.color",
                get_line_color=[120, 120, 120, 40],
                line_width_min_pixels=1, pickable=False,
            ))

        # POI scatter layers
        for subcat, layer_info in svc_active_layers.items():
            cfg = layer_info["cfg"]
            subtypes = layer_info["subtypes"]
            subset = pois[
                (pois["primary_category"] == cfg["primary_category"]) &
                (pois["type"] == cfg["type"])
            ].copy()

            if subtypes:
                for subtype_val, subtype_color in subtypes:
                    sub = subset[subset["subtype"] == subtype_val].copy()
                    if len(sub) == 0:
                        continue
                    sub["fill_color"] = [subtype_color] * len(sub)
                    sub["snap_eligible"] = sub["snap_eligible"].apply(
                        lambda x: "✓ SNAP/EBT accepted" if x else ""
                    )
                    svc_visible.append(sub)
                    svc_layers.append(pdk.Layer(
                        "ScatterplotLayer",
                        data=sub[["name", "address", "lat", "lon", "fill_color", "type", "subtype", "snap_eligible"]],
                        get_position=["lon", "lat"],
                        get_radius=svc_point_size * 40,
                        radius_min_pixels=svc_point_size,
                        radius_max_pixels=svc_point_size * 4,
                        get_fill_color="fill_color",
                        get_line_color=[255, 255, 255, 160],
                        line_width_min_pixels=1,
                        stroked=True, pickable=True, auto_highlight=True,
                    ))
            else:
                if len(subset) == 0:
                    continue
                subset["fill_color"] = [cfg["color"]] * len(subset)
                subset["snap_eligible"] = subset["snap_eligible"].apply(
                    lambda x: "✓ SNAP/EBT accepted" if x else ""
                )
                svc_visible.append(subset)
                svc_layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=subset[["name", "address", "lat", "lon", "fill_color", "type", "subtype", "snap_eligible"]],
                    get_position=["lon", "lat"],
                    get_radius=svc_point_size * 40,
                    radius_min_pixels=svc_point_size,
                    radius_max_pixels=svc_point_size * 4,
                    get_fill_color="fill_color",
                    get_line_color=[255, 255, 255, 160],
                    line_width_min_pixels=1,
                    stroked=True, pickable=True, auto_highlight=True,
                ))

        # Heatmap
        if svc_show_heatmap and svc_visible:
            heat_df = pd.concat(svc_visible)[["lat", "lon"]].copy()
            heat_df["weight"] = 1
            svc_layers.append(pdk.Layer(
                "HeatmapLayer", data=heat_df,
                get_position=["lon", "lat"],
                get_weight="weight",
                radiusPixels=60, opacity=0.65,
            ))

        # Address search pin
        if st.session_state.svc_search_lat:
            pin_df = pd.DataFrame([{
                "lat": st.session_state.svc_search_lat,
                "lon": st.session_state.svc_search_lon,
            }])
            svc_layers.append(pdk.Layer(
                "ScatterplotLayer", data=pin_df,
                get_position=["lon", "lat"],
                get_radius=200, radius_min_pixels=10, radius_max_pixels=24,
                get_fill_color=[255, 215, 0, 255],
                get_line_color=[0, 0, 0, 255],
                line_width_min_pixels=2, stroked=True, pickable=False,
            ))

        # Color key
        svc_key_items = []
        for subcat, layer_info in svc_active_layers.items():
            if layer_info["subtypes"]:
                for sv, sc in layer_info["subtypes"]:
                    svc_key_items.append((sv, sc))
            else:
                svc_key_items.append((subcat, layer_info["cfg"]["color"]))

        if svc_key_items:
            key_cols = st.columns(min(len(svc_key_items), 4))
            for i, (label, color) in enumerate(svc_key_items):
                r, g, b = color[0], color[1], color[2]
                key_cols[i % 4].markdown(
                    f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:4px'>"
                    f"<div style='width:10px;height:10px;border-radius:50%;"
                    f"background:rgb({r},{g},{b});flex-shrink:0'></div>"
                    f"<span style='font-size:11px'>{label}</span></div>",
                    unsafe_allow_html=True
                )

        total_svc_pts = sum(len(v) for v in svc_visible)
        st.caption(f"**{total_svc_pts}** points visible — {svc_view}")

        svc_view_state = pdk.ViewState(
            latitude=st.session_state.svc_search_lat or 41.95,
            longitude=st.session_state.svc_search_lon or -80.15,
            zoom=13 if st.session_state.svc_search_lat else 8.5,
            pitch=0,
        )

        st.pydeck_chart(pdk.Deck(
            map_style=MAP_STYLE,
            initial_view_state=svc_view_state,
            layers=svc_layers,
            tooltip={
                "html": "<b>{name}</b><br/>{subtype}<br/>{address}<br/>{snap_eligible}",
                "style": TOOLTIP_STYLE,
            },
        ), use_container_width=True, height=600)

        # Results table
        if st.session_state.svc_search_lat and st.session_state.svc_search_results is not None:
            svc_results_display = st.session_state.svc_search_results.copy()
            if svc_cat_filter:
                svc_results_display = svc_results_display[
                    svc_results_display["primary_category"].isin(svc_cat_filter)
                ]
            if len(svc_results_display) > 0:
                st.markdown("---")
                st.markdown("**All results — sorted by distance**")
                all_types = ["All types"] + sorted(svc_results_display["type"].unique().tolist())
                type_filter = st.selectbox("Filter by type", all_types, key="svc_type_filter")
                tbl = svc_results_display[[
                    "name", "primary_category", "type", "subtype", "address", "distance_miles"
                ]].copy()
                tbl["distance_miles"] = tbl["distance_miles"].round(2)
                tbl.columns = ["Name", "Category", "Type", "Subtype", "Address", "Distance (mi)"]
                if type_filter != "All types":
                    tbl = tbl[tbl["Type"] == type_filter]
                st.dataframe(
                    tbl, use_container_width=True, hide_index=True,
                    column_config={"Distance (mi)": st.column_config.NumberColumn(format="%.2f mi")}
                )

# ═══════════════════════════════════════════════════════
# TAB 6 — QUERY TOOL
# ═══════════════════════════════════════════════════════
with tab_query:
    geo_label = get_geo_label(geography)
    st.subheader("Multi-Variable Query")
    st.markdown(f"Find {geo_label.lower()}s that meet multiple conditions across available variables.")

    col_q1, col_q2 = st.columns([1, 3])

    with col_q1:
        logic_q = st.radio(
            "Match",
            ["ALL conditions (AND)", "ANY condition (OR)"],
            horizontal=True, key="query_logic"
        )

        query_conditions_q = {}
        for label, col in available_vars.items():
            with st.expander(label):
                enabled = st.checkbox(f"Include {label}", key=f"query_enable_{col}")
                if enabled:
                    direction = st.radio(
                        "Direction", ["Above", "Below"],
                        horizontal=True, key=f"query_dir_{col}"
                    )
                    query_conditions_q[col] = direction

    with col_q2:
        merged_query = merged.copy()
        national_avg_q = get_benchmark_value(benchmark_row, "poverty_rate")
        merged_query["color"] = merged_query["poverty_rate"].apply(
            lambda x: value_to_color(x, national_avg_q, reverse=True)
        )

        if query_conditions_q:
            updated_q = {}
            for col, direction in query_conditions_q.items():
                col_min = float(merged_query[col].min())
                col_max = float(merged_query[col].max())
                col_mean = float(merged_query[col].mean())
                thresh = st.slider(
                    f"{col} threshold", min_value=col_min, max_value=col_max,
                    value=col_mean, step=(col_max - col_min) / 100,
                    key=f"query_thresh_{col}"
                )
                updated_q[col] = (direction, thresh)

            masks_q = [
                merged_query[col] > t if d == "Above" else merged_query[col] < t
                for col, (d, t) in updated_q.items()
            ]
            if masks_q:
                final_mask_q = masks_q[0]
                for m in masks_q[1:]:
                    final_mask_q = (final_mask_q & m) if "AND" in logic_q else (final_mask_q | m)
                merged_query["color"] = merged_query.apply(
                    lambda row: row["color"] if final_mask_q[row.name] else [100, 100, 100, 60],
                    axis=1
                )
                st.metric(f"Matching {geo_label.lower()}s", int(final_mask_q.sum()))

        query_json = json.loads(merged_query.to_json())

        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer",
                data=query_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            )],
            initial_view_state=VIEW_STATE,
            tooltip={
                "html": "<b>{display_name}</b><br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "Income: ${median_household_income}<br/>"
                        "Food Insecurity: {food_insecurity_rate}%",
                "style": TOOLTIP_STYLE
            },
            map_style=MAP_STYLE
        ), height=600)

# ═══════════════════════════════════════════════════════
# TAB 6 — INSIGHTS
# ═══════════════════════════════════════════════════════
with tab_insights:
    geo_label = get_geo_label(geography)
    st.subheader(f"Insights — {geo_label} Level")

    ins1, ins2, ins3, ins4 = st.tabs([
        "Ranking Table", "County Summary", "Trend Charts", "Correlation Explorer"
    ])

    # Build a clean numeric dataframe from merged for insights
    insights_cols = ["display_name", "county_name"] + [
        col for col in available_vars.values() if col in merged.columns
    ]
    # county_name may not exist at county level
    if "county_name" not in merged.columns:
        merged["county_name"] = merged.get("NAME", "Unknown")
    insights_df = merged[insights_cols].copy()
    insights_df = insights_df[insights_df["display_name"].notna()]

    # ── RANKING TABLE ────────────────────────────────────
    with ins1:
        st.markdown("Rank all areas by any variable. Use this to find the highest need or highest performing areas.")

        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        with r_col1:
            rank_var_label = st.selectbox("Variable", list(available_vars.keys()), key="rank_var")
            rank_var = available_vars[rank_var_label]
        with r_col2:
            rank_direction = st.radio("Sort", ["Highest first", "Lowest first"], key="rank_dir")
        with r_col3:
            rank_n = st.slider("Show top N", 5, len(insights_df), min(20, len(insights_df)), key="rank_n")
        with r_col4:
            county_filter = st.multiselect(
                "Filter by county",
                options=sorted(insights_df["county_name"].dropna().unique().tolist()),
                default=[],
                key="rank_county"
            )

        rank_df = insights_df.copy()
        if county_filter:
            rank_df = rank_df[rank_df["county_name"].isin(county_filter)]

        rank_df = rank_df[["display_name", "county_name", rank_var]].dropna(subset=[rank_var])
        rank_df = rank_df.sort_values(
            rank_var,
            ascending=(rank_direction == "Lowest first")
        ).head(rank_n).reset_index(drop=True)
        rank_df.index += 1

        bval_rank = get_benchmark_value(benchmark_row, rank_var)
        rank_df["vs Benchmark"] = rank_df[rank_var].apply(
            lambda v: diff_string(v, bval_rank) if bval_rank else "—"
        )
        rank_df["Value"] = rank_df[rank_var].apply(lambda v: format_value(v, rank_var))
        rank_df = rank_df.rename(columns={"display_name": geo_label, "county_name": "County"})
        rank_df = rank_df[[geo_label, "County", "Value", "vs Benchmark"]]

        st.dataframe(rank_df, use_container_width=True)

    # ── COUNTY SUMMARY ───────────────────────────────────
    with ins2:
        st.markdown("Side-by-side comparison of Erie and Crawford Counties on all available variables.")

        erie_bench = benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == "Erie County")
        ]
        crawford_bench = benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == "Crawford County")
        ]
        ref_bench = get_benchmark_row(selected_benchmark, compare_county, year)

        summary_rows = []
        for label, col in available_vars.items():
            erie_val = get_benchmark_value(erie_bench, col)
            crawford_val = get_benchmark_value(crawford_bench, col)
            ref_val = get_benchmark_value(ref_bench, col)
            summary_rows.append({
                "Variable": label,
                "Erie County": format_value(erie_val, col),
                "Crawford County": format_value(crawford_val, col),
                f"Benchmark ({selected_benchmark})": format_value(ref_val, col),
                "Erie vs Benchmark": diff_string(erie_val, ref_val) if ref_val else "—",
                "Crawford vs Benchmark": diff_string(crawford_val, ref_val) if ref_val else "—",
            })

        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # Headline metrics for Erie
        st.markdown("---")
        st.markdown("**Erie County Headlines**")
        h1, h2, h3, h4 = st.columns(4)
        for h_col, label, col, hib in [
            (h1, "Median Income", "median_household_income", True),
            (h2, "Poverty Rate", "poverty_rate", False),
            (h3, "Rent Burden", "rent_burden_rate", False),
            (h4, "No Vehicle", "no_vehicle_rate", False),
        ]:
            val = get_benchmark_value(erie_bench, col)
            bval = get_benchmark_value(ref_bench, col)
            diff = round(float(val) - float(bval), 1) if val and bval else None
            h_col.metric(label, format_value(val, col), delta=diff,
                         delta_color="normal" if hib else "inverse")

        st.markdown("**Crawford County Headlines**")
        h1b, h2b, h3b, h4b = st.columns(4)
        for h_col, label, col, hib in [
            (h1b, "Median Income", "median_household_income", True),
            (h2b, "Poverty Rate", "poverty_rate", False),
            (h3b, "Rent Burden", "rent_burden_rate", False),
            (h4b, "No Vehicle", "no_vehicle_rate", False),
        ]:
            val = get_benchmark_value(crawford_bench, col)
            bval = get_benchmark_value(ref_bench, col)
            diff = round(float(val) - float(bval), 1) if val and bval else None
            h_col.metric(label, format_value(val, col), delta=diff,
                         delta_color="normal" if hib else "inverse")

    # ── TREND CHARTS ─────────────────────────────────────
    with ins3:
        st.markdown("Track how a variable has changed from 2019 to 2023 across all areas.")

        t_col1, t_col2, t_col3 = st.columns(3)
        with t_col1:
            trend_var_label = st.selectbox("Variable", list(available_vars.keys()), key="trend_var")
            trend_var = available_vars[trend_var_label]
        with t_col2:
            trend_county = st.multiselect(
                "Filter by county",
                options=sorted(insights_df["county_name"].dropna().unique().tolist()),
                default=[],
                key="trend_county"
            )
        with t_col3:
            trend_top_n = st.slider("Max areas to show", 3, 20, 10, key="trend_n")

        # Build time series from correct source
        if geography == "Tract":
            ts_data = census.copy()
            ts_data["tract_code"] = ts_data["tract_code"].astype(str).str.zfill(6)
            ts_data = ts_data.merge(
                merged[["TRACTCE", "display_name", "county_name"]],
                left_on="tract_code", right_on="TRACTCE", how="inner"
            )
            ts_id = "display_name"
        elif geography == "Zip Code":
            ts_data = zcta_data.copy()
            ts_data["zcta"] = ts_data["zcta"].astype(str).str.zfill(5)
            ts_data = ts_data.merge(
                merged[["ZCTA5CE20", "display_name", "county_name"]],
                left_on="zcta", right_on="ZCTA5CE20", how="inner"
            )
            ts_id = "display_name"
        else:
            ts_data = pd.concat([
                benchmarks_counties[benchmarks_counties["name"] == "Erie County"].assign(display_name="Erie County", county_name="Erie"),
                benchmarks_counties[benchmarks_counties["name"] == "Crawford County"].assign(display_name="Crawford County", county_name="Crawford"),
            ])
            ts_id = "display_name"

        if trend_county:
            ts_data = ts_data[ts_data["county_name"].isin(trend_county)]

        if trend_var in ts_data.columns:
            # Pick top N areas by their value in the selected year
            latest = ts_data[ts_data["year"] == year].nlargest(trend_top_n, trend_var)
            top_names = latest[ts_id].tolist()
            ts_filtered = ts_data[ts_data[ts_id].isin(top_names)]

            # Benchmark line
            bench_years = []
            for y in [2019, 2020, 2021, 2022, 2023]:
                br = get_benchmark_row(selected_benchmark, compare_county, y)
                bv = get_benchmark_value(br, trend_var)
                bench_years.append({"year": y, "value": bv, ts_id: f"Benchmark ({selected_benchmark})"})
            bench_ts = pd.DataFrame(bench_years)

            plot_df = pd.concat([
                ts_filtered[[ts_id, "year", trend_var]].rename(columns={trend_var: "value"}),
                bench_ts
            ])

            fig_trend = px.line(
                plot_df, x="year", y="value", color=ts_id,
                title=f"{trend_var_label} — 2019 to 2023",
                labels={"value": trend_var_label, "year": "Year", ts_id: "Area"}
            )
            fig_trend.update_traces(
                selector=lambda t: t.name.startswith("Benchmark"),
                line=dict(dash="dash", width=2)
            )
            fig_trend.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info(f"{trend_var_label} is not available for trend analysis at this geography level.")

    # ── CORRELATION EXPLORER ─────────────────────────────
    with ins4:
        st.markdown("Explore the relationship between any two variables across all areas.")

        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1:
            x_var_label = st.selectbox("X Axis", list(available_vars.keys()), key="corr_x")
            x_var = available_vars[x_var_label]
        with c_col2:
            y_var_label = st.selectbox(
                "Y Axis",
                [l for l in available_vars.keys() if l != x_var_label],
                key="corr_y"
            )
            y_var = available_vars[y_var_label]
        with c_col3:
            color_by = st.radio("Color by", ["County", "None"], horizontal=True, key="corr_color")

        scatter_df = insights_df[["display_name", "county_name", x_var, y_var]].dropna()

        if len(scatter_df) > 1:
            fig_scatter = px.scatter(
                scatter_df,
                x=x_var,
                y=y_var,
                color="county_name" if color_by == "County" else None,
                hover_name="display_name",
                trendline="ols",
                labels={
                    x_var: x_var_label,
                    y_var: y_var_label,
                    "county_name": "County"
                },
                title=f"{x_var_label} vs {y_var_label}"
            )
            fig_scatter.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_scatter, use_container_width=True)

            # Correlation coefficient
            corr = scatter_df[[x_var, y_var]].corr().iloc[0, 1]
            direction = "positive" if corr > 0 else "negative"
            strength = "strong" if abs(corr) > 0.6 else "moderate" if abs(corr) > 0.3 else "weak"
            st.caption(f"Pearson correlation: **{corr:.2f}** — {strength} {direction} relationship across {len(scatter_df)} areas.")
        else:
            st.info("Not enough data to plot. Try switching to Tract geography for more data points.")

# ── Download Tab ──────────────────────────────────────────────────────────────
# Add "Download" to your tab list at the top of the app, then paste this block
# into the corresponding `with tab_download:` section.

with tab_download:
    st.header("📥 Download Data")
    st.markdown(
        "Download the full Erie & Crawford County dataset for use in your own analysis "
        "or to upload to an AI assistant for insight generation. All files include only "
        "the most recent available data year per variable."
    )

    # ── Cached build functions ────────────────────────────────────────────────

    @st.cache_data
    def build_combined_export():
        latest_year = census["year"].max()

        # ACS core economic variables
        acs = census[census["year"] == latest_year].copy()
        acs_cols = [
            "tract_code", "county_name", "year",
            "median_household_income", "poverty_rate",
            "rent_burden_rate", "no_vehicle_rate",
            "bachelors_rate", "median_age",
        ]
        acs = acs[[c for c in acs_cols if c in acs.columns]].copy()
        acs["tract_code"] = acs["tract_code"].astype(str).str.zfill(6)
        county_fips_map = {"Erie County": "049", "Crawford County": "039"}
        acs["geoid"] = (
            "42" +
            acs["county_name"].map(county_fips_map).fillna("000") +
            acs["tract_code"]
        )

        # Second Harvest — unemployment, disability, homeownership, food insecurity
        sh_latest = sh_data[sh_data["year"] == sh_data["year"].max()].copy()
        sh_latest["tract_code"] = sh_latest["tract_code"].astype(str).str.zfill(6)
        sh_cols = ["tract_code", "unemployment_rate", "disability_rate",
                   "homeownership_rate", "food_insecurity_rate"]
        sh_latest = sh_latest[[c for c in sh_cols if c in sh_latest.columns]].drop_duplicates("tract_code")

        # Demographics — population, race/ethnicity
        demo_latest = demographics[demographics["year"] == latest_year].copy()
        demo_latest["tract_code"] = demo_latest["tract_code"].astype(str).str.zfill(6)
        demo_cols = ["tract_code", "total_population", "pct_white_non_hispanic",
                     "pct_black", "pct_hispanic", "pct_asian", "pct_other"]
        demo_latest = demo_latest[[c for c in demo_cols if c in demo_latest.columns]].drop_duplicates("tract_code")

        # CDC PLACES health outcomes
        health_cols = [
            "tract_code",
            "diabetes_rate", "high_bp_rate", "obesity_rate", "smoking_rate",
            "depression_rate", "poor_mental_health_rate", "poor_physical_health_rate",
            "no_insurance_rate", "physical_inactivity_rate", "any_disability_rate",
        ]
        health = cdc_places.copy()
        health["tract_code"] = health["tract_code"].astype(str).str.zfill(6)
        health = health[[c for c in health_cols if c in health.columns]].drop_duplicates("tract_code")

        # USDA Food Atlas
        atlas_cols = [
            "tract_code",
            "food_desert_1_10", "food_desert_half_10", "food_desert_vehicle",
            "low_income_tract", "low_access_pop", "low_access_low_income_pop",
        ]
        atlas = food_atlas.copy()
        atlas["tract_code"] = atlas["tract_code"].astype(str).str.zfill(6)
        atlas = atlas[[c for c in atlas_cols if c in atlas.columns]].drop_duplicates("tract_code")

        # Income stratification
        strat = load_stratification_data()
        strat_latest = strat[strat["year"] == strat["year"].max()].copy()
        strat_cols = ["geoid", "share_bottom", "share_middle", "share_top",
                      "hh_bottom", "hh_middle", "hh_top", "total_households"]
        strat_latest = strat_latest[[c for c in strat_cols if c in strat_latest.columns]].copy()
        strat_latest["tract_code"] = strat_latest["geoid"].astype(str).str[5:].str.zfill(6)

        # POI tract stats — counts and nearest distances only (drop raw meter columns)
        poi_exp = poi_stats.copy()
        poi_exp["TRACTCE"] = poi_exp["TRACTCE"].astype(str).str.zfill(6)
        poi_keep = (
            ["TRACTCE"] +
            [c for c in poi_exp.columns if c.startswith("count_")] +
            [c for c in poi_exp.columns if c.endswith("_miles")]
        )
        poi_exp = poi_exp[[c for c in poi_keep if c in poi_exp.columns]]
        poi_exp = poi_exp.rename(columns={"TRACTCE": "tract_code"})

        # Join everything
        combined = acs.copy()
        combined = combined.merge(sh_latest,   on="tract_code", how="left")
        combined = combined.merge(demo_latest,  on="tract_code", how="left")
        combined = combined.merge(health,       on="tract_code", how="left")
        combined = combined.merge(atlas,        on="tract_code", how="left")
        combined = combined.merge(strat_latest.drop(columns=["geoid"]), on="tract_code", how="left")
        combined = combined.merge(poi_exp,      on="tract_code", how="left")

        # Derived spatial density columns
        if "total_population" in combined.columns and "count_grocery_any" in combined.columns:
            combined["food_retail_per_1k"] = (
                combined["count_grocery_any"] / combined["total_population"] * 1000
            ).round(2)
        if "total_population" in combined.columns and "count_snap_retailers" in combined.columns:
            combined["snap_store_per_1k"] = (
                combined["count_snap_retailers"] / combined["total_population"] * 1000
            ).round(2)

        # Column ordering
        id_cols = ["geoid", "tract_code", "county_name", "year"]
        other_cols = [c for c in combined.columns if c not in id_cols]
        combined = combined[id_cols + other_cols]
        combined = combined.sort_values(["county_name", "tract_code"]).reset_index(drop=True)
        return combined

    @st.cache_data
    def build_pantry_export():
        monthly = pd.read_csv("data/processed/pantry_agency_monthly.csv", parse_dates=["date"])
        index   = pd.read_csv("data/processed/pantry_agency_index.csv")
        return monthly, index

    @st.cache_data
    def build_poi_export():
        poi_clean = "data/processed/erie_crawford_pois_clean.csv"
        import os
        if os.path.exists(poi_clean):
            return pd.read_csv(poi_clean)
        # Fallback to raw POIs if process_poi_export.py hasn't been run yet
        raw = pois.copy()
        keep = ["name", "address", "lat", "lon", "primary_category", "type", "subtype"]
        keep = [c for c in keep if c in raw.columns]
        if "snap_eligible" in raw.columns:
            raw["snap_eligible"] = raw["snap_eligible"].astype(str).str.lower().map(
                {"true": "Yes", "false": "No"}
            ).fillna("No")
        else:
            raw["snap_eligible"] = "No"
        return raw[keep + ["snap_eligible"]]

    @st.cache_data
    def build_data_dictionary():
        rows = [
            # Identity
            ("geoid",                     "Census Tract GEOID",              "11-digit FIPS code uniquely identifying each census tract",                                    "Census Bureau",             "ID",      "2023"),
            ("tract_code",                "Tract Code",                      "6-digit tract code within Pennsylvania",                                                        "Census Bureau",             "ID",      "2023"),
            ("county_name",               "County Name",                     "Erie County or Crawford County",                                                                "Census Bureau",             "Text",    "2023"),
            ("year",                      "ACS Reference Year",              "The most recent year in the 5-year ACS estimate window used for ACS variables",                "Census Bureau",             "Year",    "2023"),
            # ACS Economic
            ("median_household_income",   "Median Household Income",         "Median annual household income in dollars",                                                     "ACS 5-Year, B19013",        "Dollars", "2023"),
            ("poverty_rate",              "Poverty Rate",                    "Percent of population with income below federal poverty level",                                 "ACS 5-Year, B17001",        "%",       "2023"),
            ("unemployment_rate",         "Unemployment Rate",               "Percent of civilian labor force that is unemployed",                                            "Second Harvest / Feeding America", "%", "2023"),
            ("no_vehicle_rate",           "No Vehicle Rate",                 "Percent of households with no vehicle available",                                               "ACS 5-Year, B08201",        "%",       "2023"),
            ("rent_burden_rate",          "Rent Burden Rate",                "Percent of renters paying 30%+ of income on rent",                                             "ACS 5-Year, B25070",        "%",       "2023"),
            ("bachelors_rate",            "Bachelor's Degree Rate",          "Percent of adults 25+ with a bachelor's degree or higher",                                     "ACS 5-Year, B15003",        "%",       "2023"),
            ("homeownership_rate",        "Homeownership Rate",              "Percent of occupied housing units that are owner-occupied",                                     "Second Harvest / Feeding America", "%", "2023"),
            ("disability_rate",           "Disability Rate",                 "Percent of residents with any disability",                                                      "Second Harvest / Feeding America", "%", "2023"),
            # ACS Demographics
            ("total_population",          "Total Population",                "Total resident population",                                                                     "ACS 5-Year, B01003",        "Count",   "2023"),
            ("median_age",                "Median Age",                      "Median age of residents",                                                                       "ACS 5-Year, B01002",        "Years",   "2023"),
            ("pct_white_non_hispanic",    "% White Non-Hispanic",            "Percent of population identifying as white non-Hispanic",                                       "ACS 5-Year, B03002",        "%",       "2023"),
            ("pct_black",                 "% Black or African American",     "Percent of population identifying as Black or African American",                                "ACS 5-Year, B03002",        "%",       "2023"),
            ("pct_hispanic",              "% Hispanic or Latino",            "Percent of population identifying as Hispanic or Latino",                                       "ACS 5-Year, B03002",        "%",       "2023"),
            ("pct_asian",                 "% Asian",                         "Percent of population identifying as Asian",                                                    "ACS 5-Year, B03002",        "%",       "2023"),
            ("pct_other",                 "% Other Race/Multiracial",        "Percent of population identifying as another race or multiracial",                              "ACS 5-Year, B03002",        "%",       "2023"),
            # CDC PLACES Health
            ("diabetes_rate",             "Diabetes Rate",                   "Percent of adults diagnosed with diabetes",                                                     "CDC PLACES 2023",           "%",       "2023"),
            ("high_bp_rate",              "High Blood Pressure Rate",        "Percent of adults diagnosed with high blood pressure",                                          "CDC PLACES 2023",           "%",       "2023"),
            ("obesity_rate",              "Obesity Rate",                    "Percent of adults with obesity (BMI >= 30)",                                                    "CDC PLACES 2023",           "%",       "2023"),
            ("smoking_rate",              "Smoking Rate",                    "Percent of adults who currently smoke",                                                         "CDC PLACES 2023",           "%",       "2023"),
            ("depression_rate",           "Depression Rate",                 "Percent of adults ever diagnosed with depression",                                              "CDC PLACES 2023",           "%",       "2023"),
            ("poor_mental_health_rate",   "Poor Mental Health Rate",         "Percent of adults reporting 14+ poor mental health days in past month",                        "CDC PLACES 2023",           "%",       "2023"),
            ("poor_physical_health_rate", "Poor Physical Health Rate",       "Percent of adults reporting 14+ poor physical health days in past month",                      "CDC PLACES 2023",           "%",       "2023"),
            ("no_insurance_rate",         "Uninsured Rate",                  "Percent of adults with no health insurance coverage",                                           "CDC PLACES 2023",           "%",       "2023"),
            ("physical_inactivity_rate",  "Physical Inactivity Rate",        "Percent of adults reporting no leisure-time physical activity",                                 "CDC PLACES 2023",           "%",       "2023"),
            ("any_disability_rate",       "Any Disability Rate",             "Percent of adults with any disability",                                                         "CDC PLACES 2023",           "%",       "2023"),
            # USDA Food Access
            ("food_insecurity_rate",      "Food Insecurity Rate",            "Percent of population estimated to be food insecure",                                           "Second Harvest / Feeding America", "%", "2023"),
            ("low_income_tract",          "Low Income Tract",                "1 if tract qualifies as low income per USDA definition, 0 otherwise",                          "USDA Food Atlas 2020",      "0/1",     "2020"),
            ("food_desert_1_10",          "Food Desert (1mi/10mi)",          "1 if low income and low access using 1-mile urban / 10-mile rural threshold",                  "USDA Food Atlas 2020",      "0/1",     "2020"),
            ("food_desert_half_10",       "Food Desert (0.5mi/10mi)",        "1 if low income and low access using 0.5-mile urban / 10-mile rural threshold",                "USDA Food Atlas 2020",      "0/1",     "2020"),
            ("food_desert_vehicle",       "Food Desert (Vehicle Access)",    "1 if low income and low access accounting for vehicle availability",                            "USDA Food Atlas 2020",      "0/1",     "2020"),
            ("low_access_low_income_pop", "Low Access Low Income Pop %",     "Percent of population that is both low income and lives far from a supermarket. Null for some small/rural tracts due to USDA suppression.", "USDA Food Atlas 2020", "%", "2020"),
            ("low_access_pop",            "Low Access Population %",         "Percent of population living far from a supermarket regardless of income. Null for some small/rural tracts due to USDA suppression.",       "USDA Food Atlas 2020", "%", "2020"),
            # Income Stratification
            ("share_bottom",              "Bottom Tier Share",               "Percent of households with income under $35,000",                                               "ACS 5-Year, B19001",        "%",       "2023"),
            ("share_middle",              "Middle Tier Share",               "Percent of households with income $35,000-$74,999",                                             "ACS 5-Year, B19001",        "%",       "2023"),
            ("share_top",                 "Top Tier Share",                  "Percent of households with income $75,000 or more",                                             "ACS 5-Year, B19001",        "%",       "2023"),
            ("hh_bottom",                 "Bottom Tier Households",          "Count of households with income under $35,000",                                                 "ACS 5-Year, B19001",        "Count",   "2023"),
            ("hh_middle",                 "Middle Tier Households",          "Count of households with income $35,000-$74,999",                                               "ACS 5-Year, B19001",        "Count",   "2023"),
            ("hh_top",                    "Top Tier Households",             "Count of households with income $75,000 or more",                                               "ACS 5-Year, B19001",        "Count",   "2023"),
            ("total_households",          "Total Households",                "Total number of households in tract",                                                            "ACS 5-Year, B19001",        "Count",   "2023"),
            # POI Counts
            ("count_grocery_supermarket", "Supermarket Count",               "Number of supermarkets within the census tract",                                                "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
            ("count_grocery_large",       "Large Grocery Store Count",       "Number of large grocery stores within the tract",                                               "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
            ("count_grocery_medium",      "Medium Grocery Store Count",      "Number of medium grocery stores within the tract",                                              "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
            ("count_grocery_small",       "Small Grocery Store Count",       "Number of small grocery stores within the tract",                                               "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
            ("count_grocery_any",         "Any Grocery Store Count",         "Total number of grocery stores of any size within the tract",                                   "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
            ("count_snap_retailers",      "SNAP-Eligible Retailer Count",    "Number of stores authorized to accept SNAP/EBT benefits within the tract",                     "USDA SNAP",                 "Count",   "2026"),
            ("count_farmers_market",      "Farmers Market Count",            "Number of farmers markets within the tract",                                                    "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_convenience",         "Convenience Store Count",         "Number of convenience stores within the tract",                                                 "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_pharmacy",            "Pharmacy Count",                  "Number of pharmacies within the tract",                                                         "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_hospital",            "Hospital Count",                  "Number of hospitals within the tract",                                                          "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_clinic",              "Clinic Count",                    "Number of clinics and medical offices within the tract",                                        "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_library",             "Library Count",                   "Number of public libraries within the tract",                                                   "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_school",              "School Count",                    "Number of schools within the tract",                                                            "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_community_center",    "Community Center Count",          "Number of community centers within the tract",                                                  "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_social_services",     "Social Services Count",           "Number of social service organizations within the tract",                                       "OpenStreetMap",             "Count",   "2024-2026"),
            ("count_total_civic",         "Total Civic Services Count",      "Total count of all civic and social service locations within the tract",                        "OpenStreetMap",             "Count",   "2024-2026"),
            # Nearest distances
            ("nearest_grocery_full_miles","Nearest Grocery (miles)",         "Distance in miles to the nearest full-service grocery store from the tract centroid",           "USDA SNAP / OpenStreetMap", "Miles",   "2024-2026"),
            ("nearest_pharmacy_miles",    "Nearest Pharmacy (miles)",        "Distance in miles to the nearest pharmacy from the tract centroid",                             "OpenStreetMap",             "Miles",   "2024-2026"),
            ("nearest_hospital_miles",    "Nearest Hospital (miles)",        "Distance in miles to the nearest hospital from the tract centroid",                             "OpenStreetMap",             "Miles",   "2024-2026"),
            ("nearest_clinic_miles",      "Nearest Clinic (miles)",          "Distance in miles to the nearest clinic or medical office from the tract centroid",             "OpenStreetMap",             "Miles",   "2024-2026"),
            ("nearest_library_miles",     "Nearest Library (miles)",         "Distance in miles to the nearest public library from the tract centroid",                       "OpenStreetMap",             "Miles",   "2024-2026"),
            ("nearest_community_center_miles", "Nearest Community Center (miles)", "Distance in miles to the nearest community center from the tract centroid",              "OpenStreetMap",             "Miles",   "2024-2026"),
            ("nearest_social_services_miles",  "Nearest Social Services (miles)",  "Distance in miles to the nearest social services organization from the tract centroid",  "OpenStreetMap",             "Miles",   "2024-2026"),
            # Derived density
            ("food_retail_per_1k",        "Food Retail per 1,000 Residents", "Number of grocery stores of any size per 1,000 residents — a density measure of food retail access", "Derived",          "Rate",    "2023-2026"),
            ("snap_store_per_1k",         "SNAP Stores per 1,000 Residents", "Number of SNAP-authorized retailers per 1,000 residents — measures density of accessible food purchasing options", "Derived", "Rate", "2023-2026"),
        ]
        return pd.DataFrame(rows, columns=["variable", "label", "definition", "source", "unit", "year"])

    # ── AI context document ───────────────────────────────────────────────────
    AI_CONTEXT = """# Erie & Crawford County Community Data — AI Context Document

## About This Dataset
This dataset was compiled from public sources by a community data project covering Erie County
and Crawford County, Pennsylvania. It is designed to support analysis of economic conditions,
health outcomes, food access, service accessibility, and food assistance needs at the census
tract level.

All tract-level data reflects the most recent available year (typically 2023 for ACS and CDC
data, 2020 for USDA food access data). The pantry file is monthly agency-level data from
July 2024 through June 2025. The services/POI data reflects current locations as of 2024-2026.

---

## Files Included

### 1. erie_crawford_combined.csv
One row per census tract. Contains variables from six sources joined on census tract GEOID.

**Sources included:**
- American Community Survey (ACS) 5-Year Estimates — demographics and economic indicators
- Second Harvest / Feeding America — food insecurity, unemployment, disability, homeownership
- CDC PLACES 2023 — tract-level health outcome estimates
- USDA Food Environment Atlas 2020 — food access and food desert classifications
- ACS B19001 — household income distribution by bracket (2023)
- USDA SNAP + OpenStreetMap — service counts and proximity distances by tract

### 2. erie_crawford_pantry_monthly.csv
One row per agency per month. Monthly reporting data from Second Harvest Food Bank of
Northwest PA partner agencies in Erie and Crawford counties, July 2024 through June 2025.

**Key fields:** agency_name, county, program_type, date, total_individuals, children, adults,
seniors, new_households

**Program types:** Food Pantry/TEFAP, Food Pantry/No TEFAP, Produce Express, BackPacks,
School Pantry, Non-Emerg. Meal/Snack, Kids Cafe

### 3. erie_crawford_pois_clean.csv
One row per point of interest (service location). Each POI is assigned to a census tract
via spatial join, enabling linkage to tract-level demographics and outcomes.

**Key fields:** tract_geoid, tract_name, county, name, address, lat, lon,
primary_category, type, subtype, snap_eligible

**Categories:** Food & Grocery (supermarkets, grocery stores, farmers markets, convenience),
Health (hospitals, pharmacies, clinics), Civic & Social (libraries, schools, community
centers, social services)

**Use this file to:**
- Map service locations against demographic conditions
- Find addresses of specific service types in high-need areas
- Join back to the combined CSV using tract_geoid to enrich point data with tract statistics

### 4. data_dictionary.csv
Full variable definitions, sources, units, and years for every column in the combined file.

---

## Suggested Analysis Prompts

### Identifying Need
1. Which census tracts have the highest combined burden of poverty, food insecurity, and poor
   health outcomes? Rank the top 10 most at-risk tracts across Erie and Crawford counties.

2. Which tracts have both high poverty rates and high uninsured rates? What does this suggest
   about healthcare access?

3. Which tracts have the highest share of bottom-tier households combined with the worst
   health outcomes? Are these the same tracts?

### Health & Economic Relationships
4. Is there a relationship between median household income and diabetes or obesity rates?
   Describe the pattern you see.

5. Which health indicators are most strongly associated with poverty rate in this dataset?

6. Compare the health outcomes of tracts in the bottom income tier vs the top income tier.
   What differences stand out?

### Food Access
7. How many residents in Erie and Crawford counties live in census tracts classified as food
   deserts? Which tracts are most affected?

8. Which tracts are low income but NOT classified as food deserts? What might explain adequate
   food access despite low income?

### Income & Inequality
9. Which tracts saw the largest shift in income distribution between 2019 and 2023? Did the
   share of low-income households grow or shrink?

10. Is income stratification correlated with any health outcomes in this dataset?

### Pantry & Food Assistance
11. Which food pantries served the most individuals over the reporting period? Are there
    seasonal patterns in demand?

12. Is the share of new households at food pantries growing month over month? What does this
    suggest about whether demand is expanding?

13. Which program types serve the most children? The most seniors?

### County Comparisons
14. How do Erie and Crawford counties compare on key economic and health indicators?

15. Are there patterns in Crawford County that differ meaningfully from Erie County, given
    Crawford is more rural?

### Spatial Access & Services
16. Which census tracts have zero grocery stores and also have high food insecurity rates?
    Are these tracts also classified as food deserts by the USDA definition?

17. Which tracts have the highest rates of residents without vehicles AND the greatest
    distance to the nearest grocery store? These represent the most acute food access gaps.

18. Compare SNAP-eligible store density (snap_store_per_1k) across tracts by income tier.
    Do low-income tracts have better or worse access to SNAP-authorized retailers?

19. Which tracts are NOT classified as food deserts under the standard distance threshold
    (food_desert_1_10 = 0) but ARE flagged by the vehicle-access definition
    (food_desert_vehicle = 1)? What do these tracts have in common?

20. Is there a relationship between the number of pharmacies or clinics in a tract and
    health outcomes like diabetes rate or poor physical health rate?

21. Identify tracts that are more than 5 miles from the nearest hospital AND have high
    rates of any disability or poor physical health. Which communities face the greatest
    geographic barriers to emergency care?

22. Which tracts have the highest social services counts? Do these correlate with higher
    poverty rates — or are there high-need tracts with few social services?

23. Build a composite access score for each tract using nearest_grocery_full_miles,
    nearest_pharmacy_miles, nearest_clinic_miles, and nearest_library_miles. Which tracts
    score worst on overall service proximity?

---

## Important Caveats
- ACS 5-year estimates are averages over a 5-year period and carry margins of error,
  particularly for small tracts.
- CDC PLACES estimates are modeled, not directly measured.
- USDA Food Atlas data is from 2020 and may not reflect current conditions.
- low_access_pop and low_access_low_income_pop are null for approximately 36% of tracts
  due to USDA suppression methodology for small or rural tracts.
- Income band-level estimates (B19001) carry wider margins of error than median income
  estimates at the tract level.
- Pantry data reflects agencies that report to Second Harvest and may not capture all food
  assistance activity in the region.
- POI data is sourced from USDA SNAP retailer lists and OpenStreetMap and may not be
  complete for all service types.
"""

    # ── Build all exports ─────────────────────────────────────────────────────
    combined_df             = build_combined_export()
    pantry_monthly, pantry_index = build_pantry_export()
    poi_export_df           = build_poi_export()
    dict_df                 = build_data_dictionary()

    # ── Download UI ───────────────────────────────────────────────────────────
    st.markdown("---")

    # Row 1 — Combined tract dataset
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 🗂 Combined Tract Dataset")
        st.caption(
            f"{len(combined_df):,} tracts · {len(combined_df.columns)} variables · "
            "ACS, CDC PLACES, USDA Food Atlas, Income Stratification, POI Service Stats"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=combined_df.to_csv(index=False).encode("utf-8"),
            file_name="erie_crawford_combined.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 2 — Community services POI file
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 📍 Community Services — Point of Interest Data")
        st.caption(
            f"{len(poi_export_df):,} service locations · "
            "Food retail, health, civic & social services · "
            "Each point assigned to census tract for spatial analysis · "
            "USDA SNAP + OpenStreetMap"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=poi_export_df.to_csv(index=False).encode("utf-8"),
            file_name="erie_crawford_pois_clean.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 3 — Pantry monthly data
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 🥫 Food Pantry Monthly Data")
        st.caption(
            f"{len(pantry_monthly):,} agency-month rows · "
            f"{pantry_index['agency_name'].nunique()} agencies · "
            "Jul 2024 – Jun 2025 · Second Harvest Food Bank"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=pantry_monthly.to_csv(index=False).encode("utf-8"),
            file_name="erie_crawford_pantry_monthly.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 4 — Data dictionary
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 📖 Data Dictionary")
        st.caption(
            f"{len(dict_df):,} variables defined · "
            "Variable names, definitions, sources, units, and years"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=dict_df.to_csv(index=False).encode("utf-8"),
            file_name="data_dictionary.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 5 — AI context document
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 🤖 AI Context Document")
        st.caption(
            "Plain-English dataset summaries + 23 suggested prompts including spatial analysis. "
            "Upload alongside the CSV files when starting an AI analysis session."
        )
    with col2:
        st.download_button(
            label="Download TXT",
            data=AI_CONTEXT.encode("utf-8"),
            file_name="erie_crawford_ai_context.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("---")

    # ── Previews ──────────────────────────────────────────────────────────────
    with st.expander("Preview combined dataset"):
        st.dataframe(combined_df.head(20), use_container_width=True, hide_index=True)

    with st.expander("Preview data dictionary"):
        st.dataframe(dict_df, use_container_width=True, hide_index=True)
# ═══════════════════════════════════════════════════════
# TAB 7 — DATA DICTIONARY
# ═══════════════════════════════════════════════════════
with tab_dict:
    st.subheader("Data Dictionary")
    st.markdown(
        "Definitions, sources, and known limitations for every variable in the app. "
        "Use the search box to filter by variable name or keyword."
    )

    search_term = st.text_input("Search variables", placeholder="e.g. poverty, income, food...", key="dict_search")

    display_cols = ["Variable", "Plain Language", "Source", "Geography", "Years Available", "Caveats"]
    dict_display = data_dictionary[display_cols].copy()

    if search_term:
        mask = dict_display.apply(
            lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1
        )
        dict_display = dict_display[mask]

    if len(dict_display) == 0:
        st.info("No variables match your search.")
    else:
        st.dataframe(dict_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown(
        "**A note on ACS 5-year estimates:** All Census Bureau data in this app uses the "
        "American Community Survey 5-year estimates. These are rolling averages across a "
        "5-year period, not snapshots of a single year. The year shown in the sidebar "
        "represents the most recent year in that 5-year window (e.g., selecting 2023 uses "
        "data collected 2019–2023). This improves reliability for small geographies like "
        "census tracts but means the data does not capture rapid year-over-year changes."
    )