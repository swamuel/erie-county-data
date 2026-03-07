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
    benchmarks = pd.read_csv("data/raw/national_benchmarks.csv")
    return census, sh_data, shapes, stops, pantries, benchmarks

@st.cache_data
def load_boundaries():
    url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    gdf = gpd.read_file(url)
    gdf = gdf[gdf["COUNTYFP"] == "049"]
    gdf = gdf[gdf["TRACTCE"] != "990000"]
    return gdf

census, sh_data, shapes, stops, pantries, benchmarks = load_data()
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

# Sidebar controls
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
show_comparison = st.sidebar.toggle("Show vs National Average", value=False, key="comparison_toggle")
show_routes = st.sidebar.checkbox("Show EMTA Routes", value=True)

# Filter and merge data
df_year = census[census["year"] == year].copy()
df_year["tract_code"] = df_year["tract_code"].astype(str).str.zfill(6)

sh_year = sh_data[sh_data["year"] == min(year, 2023)].copy()
sh_year["tract_code"] = sh_year["tract_code"].astype(str).str.zfill(6)

merged = gdf.merge(df_year, left_on="TRACTCE", right_on="tract_code", how="left")
merged = merged.merge(sh_year[["tract_code", "food_insecurity_rate",
                                "unemployment_rate", "disability_rate",
                                "homeownership_rate"]],
                      left_on="TRACTCE", right_on="tract_code", how="left")

# Calculate colors
benchmark_row = benchmarks[benchmarks["year"] == year]
national_avg = benchmark_row[column].values[0] if len(benchmark_row) > 0 else None
merged["color"] = merged[column].apply(
    lambda x: value_to_color(x, national_avg, reverse)
)

# Calculate comparison diffs if toggled
if show_comparison:
    for col in ["median_household_income", "poverty_rate", "rent_burden_rate",
                "no_vehicle_rate", "unemployment_rate", "disability_rate"]:
        if col in benchmark_row.columns:
            nat_avg = benchmark_row[col].values[0]
            merged[f"{col}_diff"] = (merged[col] - nat_avg).round(1)
            merged[f"{col}_diff_str"] = merged[f"{col}_diff"].apply(
                lambda x: f"+{x}" if x > 0 else str(x)
            )

# Convert to GeoJSON AFTER all columns are added
merged_json = json.loads(merged.to_json())

# Build tract layer
tract_layer = pdk.Layer(
    "GeoJsonLayer",
    data=merged_json,
    get_fill_color="properties.color",
    get_line_color=[255, 255, 255, 50],
    line_width_min_pixels=1,
    pickable=True,
    auto_highlight=True,
    highlight_color=[255, 255, 255, 80]
)

# EMTA Routes
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

# Tooltip
if show_comparison:
    tooltip = {
        "html": "<b>{NAMELSAD}</b><br/>"
                "Income: ${median_household_income} ({median_household_income_diff_str} vs avg)<br/>"
                "Poverty: {poverty_rate}% ({poverty_rate_diff_str}% vs avg)<br/>"
                "Rent Burden: {rent_burden_rate}% ({rent_burden_rate_diff_str}% vs avg)<br/>"
                "No Vehicle: {no_vehicle_rate}% ({no_vehicle_rate_diff_str}% vs avg)<br/>"
                "Food Insecurity: {food_insecurity_rate}%<br/>"
                "Unemployment: {unemployment_rate}% ({unemployment_rate_diff_str}% vs avg)",
        "style": {
            "backgroundColor": "steelblue",
            "color": "white",
            "fontSize": "12px",
            "padding": "10px"
        }
    }
else:
    tooltip = {
        "html": "<b>{NAMELSAD}</b><br/>"
                "Income: ${median_household_income}<br/>"
                "Poverty: {poverty_rate}%<br/>"
                "Rent Burden: {rent_burden_rate}%<br/>"
                "No Vehicle: {no_vehicle_rate}%<br/>"
                "Food Insecurity: {food_insecurity_rate}%<br/>"
                "Unemployment: {unemployment_rate}%<br/>"
                "Disability: {disability_rate}%",
        "style": {
            "backgroundColor": "steelblue",
            "color": "white",
            "fontSize": "12px",
            "padding": "10px"
        }
    }

# Map view
view_state = pdk.ViewState(
    latitude=42.1167,
    longitude=-80.0,
    zoom=10,
    pitch=0
)

# Build layers
layers = [tract_layer]
if route_layer:
    layers.append(route_layer)

# Render
deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    tooltip=tooltip
)

st.pydeck_chart(deck)