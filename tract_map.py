# Erie County Tract Map
# Census data: ACS 5-Year Estimates 2023
# Transit data: Reproduced with permission granted by Erie Metropolitan Transit Authority (EMTA)

import geopandas as gpd
import folium
import pandas as pd

# Load census data
df = pd.read_csv("data/raw/erie_tract_data.csv")
df_2023 = df[df["year"] == 2023].copy()

sh_data = pd.read_csv("data/raw/erie_food_insecurity.csv")
sh_2023 = sh_data[sh_data["year"] == 2023].copy()
sh_2023["tract_code"] = sh_2023["tract_code"].astype(str).str.zfill(6)

# Load EMTA shapes
shapes = pd.read_csv("data/raw/emta_shapes.csv")
stops = pd.read_csv("data/raw/emta_stops.csv")

# Pull Census TIGER tract boundaries
url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
gdf = gpd.read_file(url)
gdf = gdf[gdf["COUNTYFP"] == "049"]

# Fix tract code type to match
df_2023["tract_code"] = df_2023["tract_code"].astype(str).str.zfill(6)

# Join census data to boundaries
gdf = gdf.merge(df_2023[["tract_code", "median_household_income",
                           "poverty_rate", "bachelors_rate",
                           "rent_burden_rate", "no_vehicle_rate"]],
                left_on="TRACTCE", right_on="tract_code", how="left")

gdf = gdf.merge(sh_2023[["tract_code", "food_insecurity_rate",
                           "unemployment_rate", "disability_rate",
                           "homeownership_rate", "percent_black",
                           "percent_hispanic"]],
                left_on="TRACTCE", right_on="tract_code", how="left")


gdf = gdf[gdf["TRACTCE"] != "990000"]

# Create map
m = folium.Map(location=[42.1167, -80.0], zoom_start=11)

# Census choropleth layers
layers = {
    "Median Household Income": ("median_household_income", "RdYlGn"),
    "Poverty Rate (%)": ("poverty_rate", "RdYlGn_r"),
    "Bachelor's Degree (%)": ("bachelors_rate", "RdYlGn"),
    "Rent Burden Rate (%)": ("rent_burden_rate", "RdYlGn_r"),
    "No Vehicle Rate (%)": ("no_vehicle_rate", "RdYlGn_r"),
    "Food Insecurity Rate (%)": ("food_insecurity_rate", "RdYlGn_r"),
    "Unemployment Rate (%)": ("unemployment_rate", "RdYlGn_r"),
    "Disability Rate (%)": ("disability_rate", "RdYlGn_r"),
    "Homeownership Rate (%)": ("homeownership_rate", "RdYlGn"),
    "Percent Black (%)": ("percent_black", "RdYlGn_r"),
    "Percent Hispanic (%)": ("percent_hispanic", "RdYlGn_r"),
}

for layer_name, (column, colorscale) in layers.items():
    folium.Choropleth(
        geo_data=gdf,
        data=gdf,
        columns=["TRACTCE", column],
        key_on="feature.properties.TRACTCE",
        fill_color=colorscale,
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=layer_name,
        nan_fill_color="gray",
        name=layer_name,
        show=layer_name == "Median Household Income"
    ).add_to(m)

# EMTA transit routes
route_group = folium.FeatureGroup(name="EMTA Bus Routes", show=True)

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
    ).add_to(route_group)

route_group.add_to(m)

# EMTA bus stops
stops_group = folium.FeatureGroup(name="EMTA Bus Stops", show=False)

for _, stop in stops.iterrows():
    # Scale radius by frequency, min 3 max 10
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
    ).add_to(stops_group)

stops_group.add_to(m)

pantries = pd.read_csv("data/raw/ErieCountyFoodPantries.csv")

# Food pantries
pantry_group = folium.FeatureGroup(name="Food Pantries", show=False)

for _, pantry in pantries.iterrows():
    hours = pantry["Open"] if pd.notna(pantry["Open"]) else "Hours not available"

    folium.Marker(
        location=[pantry["lat"], pantry["lon"]],
        tooltip=f"{pantry['PantryName']}<br>Hours: {hours}",
        icon=folium.Icon(color="green", icon="cutlery", prefix="fa")
    ).add_to(pantry_group)

pantry_group.add_to(m)

# Tooltip - added before LayerControl but excluded from it
tooltip_layer = folium.GeoJson(
    gdf,
    name="tooltip",
    style_function=lambda x: {"fillOpacity": 0, "weight": 0},
    tooltip=folium.GeoJsonTooltip(
        fields=["NAMELSAD", "median_household_income",
                "poverty_rate", "bachelors_rate",
                "rent_burden_rate", "no_vehicle_rate",
                "food_insecurity_rate", "unemployment_rate",
                "disability_rate", "homeownership_rate",
                "percent_black", "percent_hispanic"],
        aliases=["Tract:", "Median Income:", "Poverty Rate:",
                 "Bachelor's Degree %:", "Rent Burden %:",
                 "No Vehicle %:", "Food Insecurity %:",
                 "Unemployment %:", "Disability %:",
                 "Homeownership %:", "% Black:",
                 "% Hispanic:"],
        localize=True,
        na_fields=True
    )
)
route_group.add_to(m)
tooltip_layer.add_to(m)

# Layer control - exclude tooltip by adding it after
folium.LayerControl(collapsed=False).add_to(m)

m.save("data/processed/Erie_County.html")
print("Map saved")
print(stops["wheelchair_boarding"].value_counts())