import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd

st.set_page_config(page_title="Erie County Data", layout="wide")

st.title("Erie County Community Data")
st.markdown("Census tract level data for Erie County, PA")

# Load data
@st.cache_data
def load_data():
    census = pd.read_csv("data/raw/erie_tract_data.csv")
    sh_data = pd.read_csv("data/raw/erie_food_insecurity.csv")
    shapes = pd.read_csv("data/raw/emta_shapes.csv")
    stops = pd.read_csv("data/raw/emta_stops.csv")
    pantries = pd.read_csv("data/raw/ErieCountyFoodPantries.csv")
    return census, sh_data, shapes, stops, pantries

@st.cache_data
def load_boundaries():
    url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    gdf = gpd.read_file(url)
    return gdf[gdf["COUNTYFP"] == "049"]

census, sh_data, shapes, stops, pantries = load_data()
gdf = load_boundaries()

# Sidebar
st.sidebar.title("Controls")

year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

census_layer = st.sidebar.selectbox("Census Layer", [
    "median_household_income",
    "poverty_rate",
    "bachelors_rate",
    "rent_burden_rate",
    "no_vehicle_rate"
], format_func=lambda x: {
    "median_household_income": "Median Household Income",
    "poverty_rate": "Poverty Rate (%)",
    "bachelors_rate": "Bachelor's Degree (%)",
    "rent_burden_rate": "Rent Burden Rate (%)",
    "no_vehicle_rate": "No Vehicle Rate (%)"
}[x])

show_food_insecurity = st.sidebar.checkbox("Show Food Insecurity Layer", value=False)
show_routes = st.sidebar.checkbox("Show EMTA Routes", value=True)
show_stops = st.sidebar.checkbox("Show Bus Stops", value=False)
show_pantries = st.sidebar.checkbox("Show Food Pantries", value=True)

# Filter data to selected year
df_year = census[census["year"] == year].copy()
df_year["tract_code"] = df_year["tract_code"].astype(str).str.zfill(6)

sh_year = sh_data[sh_data["year"] == min(year, 2023)].copy()
sh_year["tract_code"] = sh_year["tract_code"].astype(str).str.zfill(6)

# Merge
merged = gdf.merge(df_year[["tract_code", "median_household_income",
                              "poverty_rate", "bachelors_rate",
                              "rent_burden_rate", "no_vehicle_rate"]],
                   left_on="TRACTCE", right_on="tract_code", how="left")

merged = merged.merge(sh_year[["tract_code", "food_insecurity_rate",
                                "unemployment_rate", "disability_rate",
                                "homeownership_rate"]],
                      left_on="TRACTCE", right_on="tract_code", how="left")

merged = merged[merged["TRACTCE"] != "990000"]

# Build map
m = folium.Map(location=[42.1167, -80.0], zoom_start=11)

# Census choropleth
folium.Choropleth(
    geo_data=merged,
    data=merged,
    columns=["TRACTCE", census_layer],
    key_on="feature.properties.TRACTCE",
    fill_color="RdYlGn" if census_layer == "median_household_income" else "RdYlGn_r",
    fill_opacity=0.7,
    line_opacity=0.2,
    legend_name=census_layer.replace("_", " ").title(),
    nan_fill_color="gray"
).add_to(m)

# Food insecurity layer
if show_food_insecurity:
    folium.Choropleth(
        geo_data=merged,
        data=merged,
        columns=["TRACTCE", "food_insecurity_rate"],
        key_on="feature.properties.TRACTCE",
        fill_color="RdYlGn_r",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Food Insecurity Rate (%)",
        nan_fill_color="gray"
    ).add_to(m)

# EMTA routes
if show_routes:
    for shape_id, group in shapes.groupby("shape_id"):
        coords = list(zip(group["shape_pt_lat"], group["shape_pt_lon"]))
        route_name = group["route_long_name"].iloc[0]
        route_color = "#" + str(group["route_color"].iloc[0])
        folium.PolyLine(
            locations=coords,
            color=route_color,
            weight=2,
            opacity=0.8,
            tooltip=route_name
        ).add_to(m)

# Bus stops
if show_stops:
    for _, stop in stops.iterrows():
        radius = max(3, min(10, stop["daily_visits"] / 15))
        folium.CircleMarker(
            location=[stop["stop_lat"], stop["stop_lon"]],
            radius=radius,
            color="#333333",
            fill=True,
            fill_color="#333333",
            fill_opacity=0.6,
            tooltip=(
                f"{stop['stop_name']}<br>"
                f"Daily visits: {int(stop['daily_visits'])}<br>"
                f"First bus: {stop['first_service']}<br>"
                f"Last bus: {stop['last_service']}"
            )
        ).add_to(m)

# Food pantries
if show_pantries:
    for _, pantry in pantries.iterrows():
        hours = pantry["Open"] if pd.notna(pantry["Open"]) else "Hours not available"
        folium.Marker(
            location=[pantry["lat"], pantry["lon"]],
            tooltip=f"{pantry['PantryName']}<br>Hours: {hours}",
            icon=folium.Icon(color="green", icon="cutlery", prefix="fa")
        ).add_to(m)

# Tooltip
folium.GeoJson(
    merged,
    style_function=lambda x: {"fillOpacity": 0, "weight": 0},
    tooltip=folium.GeoJsonTooltip(
        fields=["NAMELSAD", "median_household_income",
                "poverty_rate", "food_insecurity_rate",
                "no_vehicle_rate"],
        aliases=["Tract:", "Median Income:", "Poverty Rate:",
                 "Food Insecurity %:", "No Vehicle %:"],
        localize=True,
        na_fields=True
    )
).add_to(m)

# Render map
st_folium(m, width=1200, height=600)

# Data table
st.subheader("Tract Level Data")
display_cols = ["TRACTCE", "median_household_income", "poverty_rate",
                "food_insecurity_rate", "no_vehicle_rate"]
st.dataframe(merged[display_cols].sort_values("poverty_rate", ascending=False))