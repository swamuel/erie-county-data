import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np

st.set_page_config(page_title="Erie County Data", layout="wide")
st.title("Erie County Community Data")

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
    return census, sh_data, shapes, stops, pantries, benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties

@st.cache_data
def load_boundaries():
    url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    gdf = gpd.read_file(url)
    gdf = gdf[gdf["COUNTYFP"] == "049"]
    gdf = gdf[gdf["TRACTCE"] != "990000"]
    return gdf

census, sh_data, shapes, stops, pantries, benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties = load_data()
gdf = load_boundaries()

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
        r = 255
        g = int(255 * (normalized * 2))
    else:
        r = int(255 * (1 - (normalized - 0.5) * 2))
        g = 255
    return [r, g, 0, 160]

def get_benchmark_row(selected_benchmark, compare_county, year):
    if selected_benchmark == "National":
        df = benchmarks_national
        row = df[df["year"] == year]
    elif selected_benchmark == "Pennsylvania":
        df = benchmarks_pa
        row = df[df["year"] == year]
    elif selected_benchmark == "Erie County":
        df = benchmarks_erie
        row = df[df["year"] == year]
    elif selected_benchmark == "Compare to Another PA County":
        df = benchmarks_counties
        row = df[(df["year"] == year) & (df["name"] == compare_county)]
    else:
        row = benchmarks_national[benchmarks_national["year"] == year]
    return row

def build_tooltip_line(label, col, show_comparison, benchmark_row):
    if show_comparison and col in benchmark_row.columns:
        if col == "median_household_income":
            return f"{label}: ${{{col}}} ({{{col}_diff_str}} vs benchmark)<br/>"
        else:
            return f"{label}: {{{col}}}% ({{{col}_diff_str}}% vs benchmark)<br/>"
    else:
        if col == "median_household_income":
            return f"{label}: ${{{col}}}<br/>"
        else:
            return f"{label}: {{{col}}}%<br/>"

# ── SIDEBAR ──────────────────────────────────────────────
st.sidebar.title("Controls")

year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

layer_options = {
    "Median Household Income": ("median_household_income", False),
    "Poverty Rate (%)": ("poverty_rate", True),
    "Bachelor's Degree (%)": ("bachelors_rate", False),
    "Rent Burden Rate (%)": ("rent_burden_rate", True),
    "No Vehicle Rate (%)": ("no_vehicle_rate", True)
}

selected_layer = st.sidebar.selectbox("Census Layer", list(layer_options.keys()))
column, reverse = layer_options[selected_layer]

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark Context")

benchmark_options = ["National", "Pennsylvania", "Erie County", "Compare to Another PA County"]
selected_benchmark = st.sidebar.selectbox("Compare tracts against", benchmark_options)

compare_county = None
if selected_benchmark == "Compare to Another PA County":
    county_list = sorted(benchmarks_counties["name"].unique().tolist())
    compare_county = st.sidebar.selectbox("Select county", county_list)

show_comparison = st.sidebar.toggle("Show vs Benchmark in Tooltip", value=False, key="comparison_toggle")
show_routes = st.sidebar.checkbox("Show EMTA Routes", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("Tooltip Variables")

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

default_variables = [
    "Median Household Income",
    "Poverty Rate",
    "Food Insecurity Rate",
    "No Vehicle Rate"
]

selected_tooltip_vars = st.sidebar.multiselect(
    "Select variables to show",
    options=list(all_variables.keys()),
    default=default_variables
)

st.sidebar.markdown("---")
st.sidebar.subheader("Analytical Tools")

tool_options = ["None", "Threshold Filter", "Multi-Variable Query"]
selected_tool = st.sidebar.selectbox("Select Tool", tool_options)

threshold_direction = None
threshold_value = None
highlight_layer = None
query_conditions = {}
logic = None

if selected_tool == "Threshold Filter":
    st.sidebar.markdown(f"Find tracts where **{selected_layer}** is:")
    threshold_direction = st.sidebar.radio(
        "Direction",
        ["Above", "Below"],
        horizontal=True,
        key="threshold_direction"
    )

if selected_tool == "Multi-Variable Query":
    st.sidebar.markdown("Set conditions for each variable:")
    logic = st.sidebar.radio(
        "Match",
        ["ALL conditions (AND)", "ANY condition (OR)"],
        horizontal=True,
        key="query_logic"
    )
    for label, col in all_variables.items():
        with st.sidebar.expander(label):
            enabled = st.checkbox(f"Include {label}", key=f"enable_{col}")
            if enabled:
                direction = st.radio(
                    "Direction",
                    ["Above", "Below"],
                    horizontal=True,
                    key=f"dir_{col}"
                )
                query_conditions[col] = ("direction_placeholder", direction)

# ── DATA ─────────────────────────────────────────────────
df_year = census[census["year"] == year].copy()
df_year["tract_code"] = df_year["tract_code"].astype(str).str.zfill(6)

sh_year = sh_data[sh_data["year"] == min(year, 2023)].copy()
sh_year["tract_code"] = sh_year["tract_code"].astype(str).str.zfill(6)

merged = gdf.merge(df_year, left_on="TRACTCE", right_on="tract_code", how="left")
merged = merged.merge(sh_year[["tract_code", "food_insecurity_rate",
                                "unemployment_rate", "disability_rate",
                                "homeownership_rate"]],
                      left_on="TRACTCE", right_on="tract_code", how="left")

# Threshold slider - after merged is available
if selected_tool == "Threshold Filter":
    col_min = float(merged[column].min())
    col_max = float(merged[column].max())
    col_mean = float(merged[column].mean())

    threshold_value = st.sidebar.slider(
        "Threshold",
        min_value=col_min,
        max_value=col_max,
        value=col_mean,
        step=(col_max - col_min) / 100
    )

    matching = merged[
        merged[column] > threshold_value
        if threshold_direction == "Above"
        else merged[column] < threshold_value
    ]
    st.sidebar.metric("Matching tracts", len(matching))

# Multi-variable sliders - after merged is available
if selected_tool == "Multi-Variable Query" and query_conditions:
    updated_conditions = {}
    for col, (_, direction) in query_conditions.items():
        col_min = float(merged[col].min())
        col_max = float(merged[col].max())
        col_mean = float(merged[col].mean())
        threshold = st.sidebar.slider(
            f"{col} threshold",
            min_value=col_min,
            max_value=col_max,
            value=col_mean,
            step=(col_max - col_min) / 100,
            key=f"thresh_{col}"
        )
        updated_conditions[col] = (direction, threshold)
    query_conditions = updated_conditions

# ── BENCHMARKS & COLORS ──────────────────────────────────
benchmark_row = get_benchmark_row(selected_benchmark, compare_county, year)
national_avg = benchmark_row[column].values[0] if len(benchmark_row) > 0 else None

if national_avg is not None:
    st.sidebar.markdown("---")
    if column == "median_household_income":
        st.sidebar.metric(f"Benchmark: {selected_benchmark}", f"${national_avg:,.0f}")
    else:
        st.sidebar.metric(f"Benchmark: {selected_benchmark}", f"{national_avg}%")

merged["color"] = merged[column].apply(
    lambda x: value_to_color(x, national_avg, reverse)
)

if show_comparison:
    for col in ["median_household_income", "poverty_rate", "rent_burden_rate",
                "no_vehicle_rate", "unemployment_rate", "disability_rate"]:
        if col in benchmark_row.columns:
            nat_avg = benchmark_row[col].values[0]
            merged[f"{col}_diff"] = (merged[col] - nat_avg).round(1)
            merged[f"{col}_diff_str"] = merged[f"{col}_diff"].apply(
                lambda x: f"+{x}" if x > 0 else str(x)
            )

# ── ANALYTICAL TOOL FILTERING ────────────────────────────
if selected_tool == "Threshold Filter" and threshold_value is not None:
    if threshold_direction == "Above":
        highlight_mask = merged[column] > threshold_value
    else:
        highlight_mask = merged[column] < threshold_value

    merged["color"] = merged.apply(
        lambda row: row["color"] if highlight_mask[row.name]
        else [100, 100, 100, 60],
        axis=1
    )

elif selected_tool == "Multi-Variable Query" and query_conditions:
    masks = []
    for col, (direction, threshold) in query_conditions.items():
        if direction == "Above":
            masks.append(merged[col] > threshold)
        else:
            masks.append(merged[col] < threshold)

    if masks:
        if "AND" in logic:
            final_mask = masks[0]
            for m in masks[1:]:
                final_mask = final_mask & m
        else:
            final_mask = masks[0]
            for m in masks[1:]:
                final_mask = final_mask | m

        st.sidebar.metric("Matching tracts", int(final_mask.sum()))

        merged["color"] = merged.apply(
            lambda row: row["color"] if final_mask[row.name]
            else [100, 100, 100, 60],
            axis=1
        )

# ── GEOJSON ──────────────────────────────────────────────
merged_json = json.loads(merged.to_json())

# ── MAP LAYERS ───────────────────────────────────────────
tract_layer = pdk.Layer(
    "GeoJsonLayer",
    data=merged_json,
    get_fill_color="properties.color",
    get_line_color=[255, 255, 255, 50],
    line_width_min_pixels=1,
    pickable=True,
    auto_highlight=False,
    highlight_color=[0, 0, 0, 0]
)

route_layer = None
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
    route_layer = pdk.Layer(
        "PathLayer",
        data=route_paths,
        get_path="path",
        get_color="color",
        width_min_pixels=2,
        pickable=False
    )

# ── TOOLTIP ──────────────────────────────────────────────
tooltip_html = "<b>{NAMELSAD}</b><br/>"
for label in selected_tooltip_vars:
    col = all_variables[label]
    tooltip_html += build_tooltip_line(label, col, show_comparison, benchmark_row)

tooltip = {
    "html": tooltip_html,
    "style": {
        "backgroundColor": "steelblue",
        "color": "white",
        "fontSize": "12px",
        "padding": "10px"
    }
}

# ── RENDER ───────────────────────────────────────────────
view_state = pdk.ViewState(
    latitude=42.1167,
    longitude=-80.0,
    zoom=10,
    pitch=0
)

layers = [tract_layer]
if highlight_layer:
    layers.append(highlight_layer)
if route_layer:
    layers.append(route_layer)

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip
)

st.pydeck_chart(deck)