import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

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
    return (census, sh_data, shapes, stops, pantries,
            benchmarks_national, benchmarks_pa, benchmarks_erie,
            benchmarks_counties, transit_stats, zcta_data)

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
 benchmarks_counties, transit_stats, zcta_data) = load_data()

gdf_tracts, gdf_counties, gdf_zctas = load_boundaries()

# ── SESSION STATE ─────────────────────────────────────────
if "selected_geo" not in st.session_state:
    st.session_state.selected_geo = None
if "selected_geo_name" not in st.session_state:
    st.session_state.selected_geo_name = None

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
    "Homeownership Rate": "homeownership_rate"
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
    "homeownership_rate": True
}

TRACT_ONLY_VARS = {
    "food_insecurity_rate", "unemployment_rate", "disability_rate",
    "homeownership_rate", "stop_count", "total_daily_visits", "nearest_stop_miles"
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

def get_view_state_for_selection(merged_df):
    """Return a focused view state if a geo is selected, otherwise default."""
    if st.session_state.selected_geo is None:
        return VIEW_STATE
    geo_data = merged_df[merged_df[geo_id_col] == st.session_state.selected_geo]
    if len(geo_data) == 0:
        return VIEW_STATE
    centroid = geo_data.geometry.centroid.iloc[0]
    zoom = 12 if geography == "Tract" else 11 if geography == "Zip Code" else 9
    return pdk.ViewState(
        latitude=centroid.y,
        longitude=centroid.x,
        zoom=zoom,
        pitch=0
    )

def get_available_vars(geography, merged_df):
    """Return variables available for the current geography and merged dataframe."""
    available = {}
    for label, col in all_variables.items():
        if geography != "Tract" and col in TRACT_ONLY_VARS:
            continue
        if col in merged_df.columns:
            available[label] = col
    return available

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
    if True:
        if geography == "Tract":
            time_series = census[
                census["tract_code"].astype(str).str.zfill(6) == geo_code
            ].copy()
        elif geography == "Zip Code":
            time_series = zcta_data[
                zcta_data["zcta"].astype(str).str.zfill(5) == geo_code
            ].copy()
        else:
            time_series = None

        if time_series is not None and len(time_series) > 0 and column in time_series.columns:
            bench_all_years = []
            for y in [2019, 2020, 2021, 2022, 2023]:
                br = get_benchmark_row(selected_benchmark, compare_county, y)
                bv = get_benchmark_value(br, column)
                bench_all_years.append({"year": y, "benchmark": bv})
            bench_df = pd.DataFrame(bench_all_years)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=time_series["year"],
                y=time_series[column],
                mode="lines+markers",
                name=geo_name,
                line=dict(color="#2196F3", width=3),
                marker=dict(size=8)
            ))
            fig.add_trace(go.Scatter(
                x=bench_df["year"],
                y=bench_df["benchmark"],
                mode="lines",
                name=f"{selected_benchmark} benchmark",
                line=dict(color="#FF9800", width=2, dash="dash")
            ))
            fig.update_layout(
                title=f"{selected_layer} — 2019 to 2023",
                xaxis_title="Year",
                yaxis_title=selected_layer,
                height=350,
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02)
            )
            st.plotly_chart(fig, use_container_width=True)
        elif geography == "County":
            st.caption("Trend charts are not available at the county level.")

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
tab_about, tab_econ, tab_transit, tab_food, tab_query, tab_insights, tab_dict = st.tabs([
    "About", "Economic", "Transit", "Food Access", "Query Tool", "Insights", "Data Dictionary"
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
        st.subheader("Economic Data")

        if geography == "Tract":
            layer_options = {
                "Median Household Income": ("median_household_income", False),
                "Poverty Rate (%)": ("poverty_rate", True),
                "Bachelor's Degree (%)": ("bachelors_rate", False),
                "Rent Burden Rate (%)": ("rent_burden_rate", True),
                "No Vehicle Rate (%)": ("no_vehicle_rate", True)
            }
        else:
            layer_options = {
                "Median Household Income": ("median_household_income", False),
                "Poverty Rate (%)": ("poverty_rate", True),
                "Rent Burden Rate (%)": ("rent_burden_rate", True),
                "No Vehicle Rate (%)": ("no_vehicle_rate", True)
            }

        selected_layer = st.selectbox(
            "Variable", list(layer_options.keys()), key="econ_layer"
        )
        column, reverse = layer_options[selected_layer]

        econ_tool = "None"
        threshold_value = None
        threshold_direction = None
        query_conditions = {}
        logic = None

        if mode == "Advanced":
            st.markdown("---")
            st.markdown("**Analytical Tools**")
            econ_tool = st.selectbox(
                "Tool",
                ["None", "Threshold Filter", "Multi-Variable Query"],
                key="econ_tool"
            )

            if econ_tool == "Threshold Filter":
                threshold_direction = st.radio(
                    "Direction", ["Above", "Below"],
                    horizontal=True, key="econ_thresh_dir"
                )
                col_min = float(merged[column].min())
                col_max = float(merged[column].max())
                col_mean = float(merged[column].mean())
                threshold_value = st.slider(
                    "Threshold", min_value=col_min, max_value=col_max,
                    value=col_mean, step=(col_max - col_min) / 100,
                    key="econ_thresh_val"
                )

            if econ_tool == "Multi-Variable Query":
                logic = st.radio(
                    "Match",
                    ["ALL conditions (AND)", "ANY condition (OR)"],
                    horizontal=True, key="econ_query_logic"
                )
                for label, col in available_vars.items():
                    with st.expander(label):
                        enabled = st.checkbox(f"Include {label}", key=f"econ_enable_{col}")
                        if enabled:
                            direction = st.radio(
                                "Direction", ["Above", "Below"],
                                horizontal=True, key=f"econ_dir_{col}"
                            )
                            query_conditions[col] = direction

        st.markdown("---")
        st.markdown(f"**Explore a {geo_label}**")
        geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
        selected_name = st.selectbox(
            f"Select {geo_label.lower()}", geo_options, key="econ_geo_select"
        )
        if selected_name != "None":
            sel_row = merged[merged["display_name"] == selected_name].iloc[0]
            st.session_state.selected_geo = sel_row[geo_id_col]
            st.session_state.selected_geo_name = selected_name
        else:
            st.session_state.selected_geo = None
            st.session_state.selected_geo_name = None

    with col_map:
        national_avg = get_benchmark_value(benchmark_row, column)

        if national_avg is not None:
            st.metric(
                f"Benchmark: {selected_benchmark}",
                format_value(national_avg, column)
            )

        merged_econ = merged.copy()
        merged_econ["color"] = merged_econ[column].apply(
            lambda x: value_to_color(x, national_avg, reverse)
        )

        if econ_tool == "Threshold Filter" and threshold_value is not None:
            mask = (merged_econ[column] > threshold_value
                    if threshold_direction == "Above"
                    else merged_econ[column] < threshold_value)
            merged_econ["color"] = merged_econ.apply(
                lambda row: row["color"] if mask[row.name] else [100, 100, 100, 60], axis=1
            )
            st.metric(f"Matching {geo_label.lower()}s", int(mask.sum()))

        elif econ_tool == "Multi-Variable Query" and query_conditions:
            updated = {}
            for col, direction in query_conditions.items():
                col_min = float(merged_econ[col].min())
                col_max = float(merged_econ[col].max())
                col_mean = float(merged_econ[col].mean())
                thresh = st.slider(
                    f"{col} threshold", min_value=col_min, max_value=col_max,
                    value=col_mean, step=(col_max - col_min) / 100,
                    key=f"econ_thresh_{col}"
                )
                updated[col] = (direction, thresh)
            masks = [
                merged_econ[col] > t if d == "Above" else merged_econ[col] < t
                for col, (d, t) in updated.items()
            ]
            if masks:
                final_mask = masks[0]
                for m in masks[1:]:
                    final_mask = (final_mask & m) if "AND" in logic else (final_mask | m)
                merged_econ["color"] = merged_econ.apply(
                    lambda row: row["color"] if final_mask[row.name] else [100, 100, 100, 60],
                    axis=1
                )
                st.metric(f"Matching {geo_label.lower()}s", int(final_mask.sum()))

        econ_json = json.loads(merged_econ.to_json())

        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer",
                data=econ_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            )],
            initial_view_state=get_view_state_for_selection(merged_econ),
            tooltip={
                "html": "<b>{display_name}</b><br/>"
                        "Income: ${median_household_income}<br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "Rent Burden: {rent_burden_rate}%<br/>"
                        "No Vehicle: {no_vehicle_rate}%",
                "style": TOOLTIP_STYLE
            },
            map_style=MAP_STYLE
        ), height=600)

        st.markdown("---")
        render_detail_panel(merged_econ, column, selected_layer)

# ═══════════════════════════════════════════════════════
# TAB 3 — TRANSIT
# ═══════════════════════════════════════════════════════
with tab_transit:
    col_controls_t, col_map_t = st.columns([1, 3])

    with col_controls_t:
        st.subheader("Transit Coverage")

        if geography != "Tract":
            st.info("Transit stop and coverage analysis is only available at the Tract level. "
                    "Switch Geography to Tract to use these tools.")

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
            initial_view_state=get_view_state_for_selection(merged_econ),
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

        if geography != "Tract":
            st.info("Food insecurity data is only available at the Tract level. "
                    "The map shows Poverty Rate at your selected geography.")

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
            initial_view_state=get_view_state_for_selection(merged_econ),
            tooltip={"html": food_tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE
        ), height=600)

# ═══════════════════════════════════════════════════════
# TAB 5 — QUERY TOOL
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
            initial_view_state=get_view_state_for_selection(merged_econ),
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

    # Build insights dataframe first
    insights_cols = ["display_name", "county_name"] + [
        col for col in available_vars.values() if col in merged.columns
    ]
    if "county_name" not in merged.columns:
        merged["county_name"] = merged.get("NAME", "Unknown")
    insights_df = merged[insights_cols].copy()
    insights_df = insights_df[insights_df["display_name"].notna()]

    # Shared filter
    all_display_names = sorted(insights_df["display_name"].dropna().unique().tolist())

    if geography != "County":
        with st.expander(f"Filter to specific {geo_label.lower()}s (optional)", expanded=False):
            selected_areas = st.multiselect(
                f"Select {geo_label.lower()}s to include — leave blank to include all",
                options=all_display_names,
                default=[],
                key="insights_area_filter"
            )
    else:
        selected_areas = []

    if selected_areas:
        filtered_insights_df = insights_df[insights_df["display_name"].isin(selected_areas)]
        st.caption(f"Showing {len(filtered_insights_df)} of {len(all_display_names)} {geo_label.lower()}s.")
    else:
        filtered_insights_df = insights_df.copy()

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

        rank_df = filtered_insights_df.copy()
        st.write(f"rank_df has {len(rank_df)} rows, insights_df has {len(insights_df)} rows")
        if not selected_areas and county_filter:
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
                options=sorted(filtered_insights_df["county_name"].dropna().unique().tolist()),
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
            merge_cols = ["ZCTA5CE20", "display_name"]
            if "county_name" in merged.columns:
                merge_cols.append("county_name")
            ts_data = ts_data.merge(
                merged[merge_cols],
                left_on="zcta", right_on="ZCTA5CE20", how="inner"
            )
            if "county_name" not in ts_data.columns:
                ts_data["county_name"] = "Unknown"
            ts_id = "display_name"
        else:
            ts_data = pd.concat([
                benchmarks_counties[benchmarks_counties["name"] == "Erie County"].assign(display_name="Erie County",
                                                                                         county_name="Erie"),
                benchmarks_counties[benchmarks_counties["name"] == "Crawford County"].assign(
                    display_name="Crawford County", county_name="Crawford"),
            ])
            ts_id = "display_name"

        # Apply shared area filter
        if selected_areas:
            ts_data = ts_data = ts_data[ts_data["display_name"].isin(filtered_insights_df["display_name"])]
        elif trend_county and "county_name" in ts_data.columns:
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

        scatter_df = filtered_insights_df[["display_name", "county_name", x_var, y_var]].dropna()

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