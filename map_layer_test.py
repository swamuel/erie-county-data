"""
map_layer_test.py — Standalone layer sandbox for Erie/Crawford project.
Run with:  streamlit run map_layer_test.py
Place this file in your project root (same level as app_v2.py).
"""

import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np

st.set_page_config(page_title="Map Layer Sandbox", layout="wide")

# ── CONSTANTS ─────────────────────────────────────────────
MAP_STYLE  = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
VIEW_STATE = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0)
VIEW_3D    = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=45, bearing=-10)

TIGER_TRACT = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
ERIE_FIPS   = ["049", "039"]

TOOLTIP = {"backgroundColor": "steelblue", "color": "white",
           "fontSize": "12px", "padding": "10px"}

# ── DATA LOADING ──────────────────────────────────────────
@st.cache_data
def load_tracts():
    gdf = gpd.read_file(TIGER_TRACT)
    gdf = gdf[gdf["COUNTYFP"].isin(ERIE_FIPS) & (gdf["TRACTCE"] != "990000")]
    gdf = gdf.to_crs(epsg=4326)
    return gdf

@st.cache_data
def load_census():
    return pd.read_csv("data/raw/erie_tract_data.csv", dtype={"tract_code": str})

@st.cache_data
def load_stops():
    return pd.read_csv("data/raw/emta_stops.csv")

@st.cache_data
def load_routes():
    return pd.read_csv("data/raw/emta_shapes.csv")

@st.cache_data
def load_pantries():
    df = pd.read_csv("data/raw/ErieCountyFoodPantries.csv")
    return df.dropna(subset=["lat", "lon"])

@st.cache_data
def load_grocery():
    import io
    data = """name,address,category,tier,lat,lon,color_r,color_g,color_b
Wegmans,"6143 Peach St, Erie, PA 16509",Full-Service,premium,42.059697509359,-80.092752419107,34,197,94
Erie Food Co-op,"1341 W 26th St, Erie, PA 16508",Full-Service,premium,42.101519483029,-80.101573690663,34,197,94
Westside Market,"1119 Powell Ave, Erie, PA 16505",Full-Service,premium,42.092592950101,-80.167800022656,34,197,94
Serafins Market,"601 E 24th St, Erie, PA 16503",Full-Service,specialty,42.118445294357,-80.061449311105,16,185,129
Giant Eagle,"2067 Interchange Rd, Erie, PA 16509",Full-Service,standard,42.064628318859,-80.101431953152,59,130,246
TOPS Markets,"712 W 38th St, Erie, PA 16508",Full-Service,standard,42.096165473845,-80.083175555562,59,130,246
ALDI,"2647 W 12th St, Erie, PA 16505",Value & Discount,value,42.10175338954,-80.140057571448,251,191,36
Save A Lot,"1512 Peach St, Erie, PA 16501",Value & Discount,value,42.120536654671,-80.081113233066,251,191,36
Dollar General,"1414 Peach St, Erie, PA 16501",Discount Variety,dollar,42.12112131288,-80.081507902509,249,115,22
Dollar Tree,"3810 Peach St, Erie, PA 16508",Discount Variety,dollar,42.095973991281,-80.082361163124,249,115,22
Walmart Supercenter,"2711 Elm St, Erie, PA 16504",Big Box,bigbox,42.121925542987,-80.043028242179,139,92,246
Target,"6700 Peach St, Erie, PA 16509",Big Box,bigbox,42.058462763365,-80.091602235009,139,92,246
Country Fair,"3826 Peach St, Erie, PA 16508",Convenience & Fuel,convenience,42.095684590251,-80.082517533042,156,163,175
Sheetz,"2060 Interchange Rd, Erie, PA 16509",Convenience & Fuel,convenience,42.065293918088,-80.10352784034,156,163,175
Speedway,"1502 W 26th St, Erie, PA 16508",Convenience & Fuel,convenience,42.100146664254,-80.105671379114,156,163,175"""
    return pd.read_csv(io.StringIO(data))

@st.cache_data
def load_food():
    return pd.read_csv("data/raw/usda_food_atlas.csv", dtype={"tract_code": str})

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title("🗺 Layer Sandbox")
st.sidebar.caption("Toggle layers and styles to explore combinations.")

map_style_choice = st.sidebar.radio("Base map", ["Light (Positron)", "Dark"])
base_map = MAP_STYLE if map_style_choice == "Light (Positron)" else DARK_STYLE

year = st.sidebar.selectbox("Census year", [2023, 2022, 2021, 2020, 2019], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("**Polygon layers**")
show_choropleth   = st.sidebar.checkbox("Choropleth (poverty rate)", value=True)
choropleth_opacity = st.sidebar.slider("Choropleth opacity", 0.05, 1.0, 0.4, 0.05) if show_choropleth else 0.4
show_food_desert  = st.sidebar.checkbox("Food desert outlines", value=False)

st.sidebar.markdown("**Point layers**")
show_stops    = st.sidebar.checkbox("Transit stops (scatter)", value=True)
show_heatmap  = st.sidebar.checkbox("Transit stops (heatmap)", value=False)
show_pantries = st.sidebar.checkbox("Food pantry locations", value=False)
show_centroids = st.sidebar.checkbox("Tract centroids (3D columns)", value=False)

st.sidebar.markdown("**Grocery stores**")
show_grocery_scatter  = st.sidebar.checkbox("Grocery stores (points)", value=False)
show_grocery_heatmap  = st.sidebar.checkbox("Grocery access (heatmap)", value=False)

st.sidebar.markdown("**Line layers**")
show_routes = st.sidebar.checkbox("Bus routes", value=False)

use_3d = show_centroids
pitch_val = 45 if use_3d else 0
view = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=pitch_val, bearing=-10 if use_3d else 0)

# ── LOAD DATA ─────────────────────────────────────────────
with st.spinner("Loading data..."):
    try:
        gdf     = load_tracts()
        census  = load_census()
        stops   = load_stops()
        routes  = load_routes()
        pantries = load_pantries()
        food    = load_food()
        grocery = load_grocery()
        data_ok = True
    except Exception as e:
        st.error(f"Data load error: {e}")
        st.info("Make sure this file is in your project root alongside data/raw/")
        st.stop()

# ── MERGE CENSUS ──────────────────────────────────────────
yr_data = census[census["year"] == year].copy()
yr_data["TRACTCE"] = yr_data["tract_code"].astype(str).str.zfill(6)
merged = gdf.merge(yr_data, on="TRACTCE", how="left")

# poverty color — white (low) to deep red (high)
def poverty_color(val, opacity=180):
    if pd.isna(val):
        return [200, 200, 200, 80]
    v = min(max(val / 60.0, 0), 1)
    r = int(255 * v + 240 * (1 - v))
    g = int(50  * v + 240 * (1 - v))
    b = int(50  * v + 240 * (1 - v))
    return [r, g, b, int(opacity * 255)]

merged["fill_color"] = merged["poverty_rate"].apply(
    lambda x: poverty_color(x, choropleth_opacity)
)
merged["line_color"] = [[80, 80, 80, 120]] * len(merged)

# ── BUILD LAYERS ──────────────────────────────────────────
layers = []

# 1 — Choropleth polygon layer
if show_choropleth:
    choro_json = json.loads(merged[["geometry","TRACTCE","NAMELSAD","poverty_rate","fill_color","line_color"]].to_json())
    layers.append(pdk.Layer(
        "GeoJsonLayer",
        data=choro_json,
        get_fill_color="properties.fill_color",
        get_line_color="properties.line_color",
        line_width_min_pixels=1,
        pickable=True,
        tooltip=True,
    ))

# 2 — Food desert outlines
if show_food_desert:
    food["TRACTCE"] = food["tract_code"].astype(str).str.zfill(6)
    desert_tracts = food[food["food_desert_1_10"] == 1]["TRACTCE"].tolist()
    desert_gdf = merged[merged["TRACTCE"].isin(desert_tracts)].copy()
    desert_json = json.loads(desert_gdf[["geometry","TRACTCE"]].to_json())
    layers.append(pdk.Layer(
        "GeoJsonLayer",
        data=desert_json,
        get_fill_color=[0, 0, 0, 0],
        get_line_color=[230, 100, 0, 220],
        line_width_min_pixels=2,
        pickable=False,
    ))

# 3 — Transit stops scatter
if show_stops:
    stops_clean = stops.dropna(subset=["stop_lat", "stop_lon"]).copy()
    stops_clean["radius"] = stops_clean["daily_visits"].clip(upper=200) * 4 + 80
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=stops_clean,
        get_position=["stop_lon", "stop_lat"],
        get_radius="radius",
        get_fill_color=[30, 144, 255, 180],
        get_line_color=[255, 255, 255, 200],
        line_width_min_pixels=1,
        stroked=True,
        pickable=True,
    ))

# 4 — Transit heatmap
if show_heatmap:
    stops_clean = stops.dropna(subset=["stop_lat", "stop_lon"]).copy()
    stops_clean["weight"] = stops_clean["daily_visits"].fillna(1).clip(upper=300)
    layers.append(pdk.Layer(
        "HeatmapLayer",
        data=stops_clean,
        get_position=["stop_lon", "stop_lat"],
        get_weight="weight",
        radiusPixels=60,
        opacity=0.6,
    ))

# 5 — Food pantries
if show_pantries:
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=pantries,
        get_position=["lon", "lat"],
        get_radius=400,
        get_fill_color=[34, 197, 94, 220],
        get_line_color=[255, 255, 255, 200],
        line_width_min_pixels=1,
        stroked=True,
        pickable=True,
    ))

# 6 — 3D columns (tract centroids sized by poverty rate)
if show_centroids:
    centroids = merged.copy()
    centroids["centroid"] = centroids.geometry.centroid
    centroids["lon"] = centroids["centroid"].x
    centroids["lat"] = centroids["centroid"].y
    centroids["elevation"] = (centroids["poverty_rate"].fillna(0) * 120).clip(upper=6000)
    centroids["col_color"] = centroids["poverty_rate"].apply(
        lambda x: [220, 50, 50, 200] if (not pd.isna(x) and x > 30) else [80, 160, 220, 180]
    )
    col_df = centroids[["lon","lat","elevation","col_color","NAMELSAD","poverty_rate"]].dropna(subset=["lon","lat"])
    layers.append(pdk.Layer(
        "ColumnLayer",
        data=col_df,
        get_position=["lon", "lat"],
        get_elevation="elevation",
        elevation_scale=1,
        radius=500,
        get_fill_color="col_color",
        pickable=True,
        auto_highlight=True,
    ))

# 7 — Grocery store scatter (colored by tier)
if show_grocery_scatter:
    grocery["fill_color"] = grocery.apply(
        lambda r: [int(r.color_r), int(r.color_g), int(r.color_b), 220], axis=1
    )
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=grocery,
        get_position=["lon", "lat"],
        get_radius=600,
        get_fill_color="fill_color",
        get_line_color=[255, 255, 255, 200],
        line_width_min_pixels=1,
        stroked=True,
        pickable=True,
    ))

# 8 — Grocery access heatmap
# Weights: premium/standard full-service stores radiate more than dollar/convenience
TIER_WEIGHTS = {
    "premium": 10, "specialty": 9, "standard": 8,
    "value": 5, "bigbox": 7, "dollar": 2, "convenience": 1,
}
if show_grocery_heatmap:
    grocery["weight"] = grocery["tier"].map(TIER_WEIGHTS).fillna(3)
    layers.append(pdk.Layer(
        "HeatmapLayer",
        data=grocery,
        get_position=["lon", "lat"],
        get_weight="weight",
        radiusPixels=80,
        opacity=0.7,
    ))

# 9 — Bus routes
if show_routes:
    route_records = []
    for _, row in routes.iterrows():
        try:
            coords = [[float(lon), float(lat)]
                      for lat, lon in zip(
                          str(row.get("shape_pt_lat","")).split(","),
                          str(row.get("shape_pt_lon","")).split(","))
                      if lat and lon]
            if len(coords) > 1:
                color = [int(row.get("route_color_r", 30)),
                         int(row.get("route_color_g", 100)),
                         int(row.get("route_color_b", 200)), 180]
                route_records.append({"path": coords, "color": color})
        except Exception:
            continue

    if route_records:
        layers.append(pdk.Layer(
            "PathLayer",
            data=route_records,
            get_path="path",
            get_color="color",
            width_min_pixels=2,
            pickable=False,
        ))

# ── RENDER ────────────────────────────────────────────────
st.title("Map Layer Sandbox")
active = []
if show_choropleth:        active.append("choropleth")
if show_food_desert:       active.append("food desert outlines")
if show_stops:             active.append("transit stops (scatter)")
if show_heatmap:           active.append("transit heatmap")
if show_pantries:          active.append("food pantries")
if show_centroids:         active.append("3D poverty columns")
if show_grocery_scatter:   active.append("grocery stores (scatter)")
if show_grocery_heatmap:   active.append("grocery access (heatmap)")
if show_routes:            active.append("bus routes")

st.caption(f"Active layers: {', '.join(active) if active else 'none'}")

if not layers:
    st.info("Turn on at least one layer in the sidebar.")
else:
    tooltip_content = {
        "html": "<b>{properties.NAMELSAD}{name}</b><br/>{category}",
        "style": {"backgroundColor": "#1e293b", "color": "white",
                  "fontSize": "12px", "padding": "8px", "borderRadius": "4px"}
    }
    deck = pdk.Deck(
        map_style=base_map,
        initial_view_state=view,
        layers=layers,
        tooltip=tooltip_content,
    )
    st.pydeck_chart(deck, use_container_width=True, height=620)

# ── LEGEND ───────────────────────────────────────────────
if show_grocery_scatter or show_grocery_heatmap:
    st.markdown("**Grocery store tier legend**")
    cols = st.columns(6)
    legend = [
        ("🟢", "Premium / Full-Service", "Wegmans, Co-op, Giant Eagle, TOPS"),
        ("🟡", "Value & Discount", "ALDI, Save A Lot"),
        ("🟠", "Dollar Stores", "Dollar General, Dollar Tree"),
        ("🟣", "Big Box", "Walmart, Target"),
        ("⚫", "Convenience", "Country Fair, Sheetz, Speedway"),
        ("🔵", "Specialty", "Serafins Market"),
    ]
    for col, (icon, label, stores) in zip(cols, legend):
        col.markdown(f"{icon} **{label}**\n{stores}")

# ── NOTES ─────────────────────────────────────────────────
with st.expander("Layer notes & observations"):
    st.markdown("""
**Things to try:**
- Choropleth alone → then add transit stops → notice where high-poverty tracts have few stops
- Swap scatter stops for heatmap → different story, less precise but smoother
- Turn on food desert outlines with choropleth → see overlap between poverty and food access
- Turn on 3D columns (auto-switches to pitched view) → red = >30% poverty rate, blue = lower
- Dark base map + heatmap → most dramatic visual
- **Grocery scatter** → colored by store tier (green = full-service, orange = dollar stores, gray = convenience)
- **Grocery heatmap** → weighted by store quality — shows where full-service food access is concentrated vs. thin
- **Choropleth + grocery heatmap** → the key food access story: are the highest-poverty tracts in food access dead zones?
- **Food desert outlines + grocery heatmap** → see how the USDA desert designation aligns with actual store density

**Grocery tier color key:**
- 🟢 Green — Premium & Full-Service (Wegmans, Co-op, Giant Eagle, TOPS)
- 🟡 Amber — Value & Discount (ALDI, Save A Lot)
- 🟠 Orange — Dollar stores (Dollar General, Dollar Tree)
- 🟣 Purple — Big Box (Walmart, Target)
- ⚫ Gray — Convenience & Fuel (Country Fair, Sheetz, Speedway)

**What each layer type is good for:**
- **Choropleth** — comparing a single variable across all tracts simultaneously
- **ScatterplotLayer** — precise locations, can encode a second variable via size or color
- **HeatmapLayer** — density and clustering, crosses tract boundaries, more intuitive for non-technical audiences
- **ColumnLayer (3D)** — comparing magnitudes dramatically, good for presentations
- **PathLayer** — networks and routes, shows coverage and gaps
- **Outline only GeoJsonLayer** — highlighting a subset without covering the map underneath

**Note:** Run `python fetch_grocery_stores.py` from your project root to generate the grocery data file before using those layers.
    """)