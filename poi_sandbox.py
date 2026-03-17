"""
poi_sandbox.py — Community Services & POI layer sandbox.
Run with:  streamlit run poi_sandbox.py
Place in project root alongside app_v2.py.

Features:
  - Three-tier category toggles (view → subcategory → subtype)
  - Dynamic zoom-reactive point sizing
  - Choropleth underlay
  - Heatmap overlay
  - County filter (Erie / Crawford / Both)
"""

import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np
import math

st.set_page_config(page_title="Services & POI Sandbox", layout="wide")

# Session state for address search
if "search_lat"     not in st.session_state: st.session_state.search_lat     = None
if "search_lon"     not in st.session_state: st.session_state.search_lon     = None
if "search_label"   not in st.session_state: st.session_state.search_label   = None
if "search_results" not in st.session_state: st.session_state.search_results = None

# ── CONSTANTS ─────────────────────────────────────────────
MAP_LIGHT  = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
MAP_DARK   = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
TIGER_URL  = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
ERIE_FIPS  = ["049", "039"]
VIEW_STATE = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0)

ZCTA_URL = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
ZCTA_LIST = [str(z).zfill(5) for z in [
    16110, 16111, 16131, 16134, 16314, 16316, 16327, 16328, 16335,
    16354, 16360, 16403, 16404, 16406, 16422, 16424, 16432, 16433,
    16434, 16435, 16440, 16401, 16407, 16410, 16411, 16412, 16413,
    16415, 16417, 16421, 16423, 16426, 16427, 16428, 16430, 16438,
    16441, 16442, 16443, 16501, 16502, 16503, 16504, 16505, 16506,
    16507, 16508, 16509, 16510, 16511, 16563
]]

# ── THREE-TIER LAYER CONFIG ───────────────────────────────
# Structure:
#   VIEW → list of SUBCATEGORIES
#   Each SUBCATEGORY has:
#     primary_category, type, default_on, color, subtypes (optional)
#   Each SUBTYPE has:
#     subtype value to filter on, default_on, color_override

LAYER_CONFIG = {

    "Food & Grocery": {
        "Supermarkets": {
            "primary_category": "Food & Grocery",
            "type":             "Supermarket",
            "default_on":       True,
            "color":            [34,  197, 94,  220],
            "subtypes":         None,
        },
        "Large Grocery Stores": {
            "primary_category": "Food & Grocery",
            "type":             "Large Grocery Store",
            "default_on":       True,
            "color":            [52,  211, 153, 220],
            "subtypes":         None,
        },
        "Medium Grocery Stores": {
            "primary_category": "Food & Grocery",
            "type":             "Medium Grocery Store",
            "default_on":       True,
            "color":            [110, 231, 183, 220],
            "subtypes":         None,
        },
        "Small Grocery Stores": {
            "primary_category": "Food & Grocery",
            "type":             "Small Grocery Store",
            "default_on":       False,
            "color":            [167, 243, 208, 220],
            "subtypes":         None,
        },
        "Combination / Mixed Retail": {
            "primary_category": "Food & Grocery",
            "type":             "Combination Grocery/Other",
            "default_on":       False,
            "color":            [251, 191, 36,  220],
            "subtypes":         None,
        },
        "Specialty Food": {
            "primary_category": "Food & Grocery",
            "type":             "Specialty Food Store",
            "default_on":       False,
            "color":            [16,  185, 129, 220],
            "subtypes": {
                "Meat / Poultry": {
                    "value":      "Meat/Poultry Specialty",
                    "default_on": True,
                    "color":      [239, 68,  68,  200],
                },
                "Bakery": {
                    "value":      "Bakery Specialty",
                    "default_on": True,
                    "color":      [251, 146, 60,  200],
                },
                "Fruits / Veg": {
                    "value":      "Fruits/Veg Specialty",
                    "default_on": True,
                    "color":      [34,  197, 94,  200],
                },
            },
        },
        "Farmers Markets": {
            "primary_category": "Food & Grocery",
            "type":             "Farmers' Market",
            "default_on":       True,
            "color":            [5,   150, 105, 220],
            "subtypes":         None,
        },
        "Convenience Stores": {
            "primary_category": "Food & Grocery",
            "type":             "Convenience Store",
            "default_on":       False,
            "color":            [156, 163, 175, 200],
            "subtypes":         None,
        },
    },

    "Health": {
        "Hospitals": {
            "primary_category": "Health",
            "type":             "Hospital",
            "default_on":       True,
            "color":            [220, 38,  38,  240],
            "subtypes":         None,
        },
        "Pharmacies": {
            "primary_category": "Health",
            "type":             "Pharmacy",
            "default_on":       True,
            "color":            [239, 68,  68,  220],
            "subtypes":         None,
        },
        "Clinics & Care": {
            "primary_category": "Health",
            "type":             "Clinic",
            "default_on":       True,
            "color":            [251, 146, 60,  200],
            "subtypes": {
                "Outpatient Clinic": {
                    "value":      "Outpatient Clinic",
                    "default_on": True,
                    "color":      [251, 146, 60,  220],
                },
                "Medical Office": {
                    "value":      "Medical Office",
                    "default_on": False,
                    "color":      [253, 186, 116, 200],
                },
                "Dental Office": {
                    "value":      "Dental Office",
                    "default_on": False,
                    "color":      [251, 191, 36,  200],
                },
                "Veterinary": {
                    "value":      "Veterinary",
                    "default_on": False,
                    "color":      [100, 180, 100, 200],
                },
            },
        },
    },

    "Civic & Social": {
        "Libraries": {
            "primary_category": "Education & Civic",
            "type":             "Library",
            "default_on":       True,
            "color":            [59,  130, 246, 220],
            "subtypes":         None,
        },
        "Schools": {
            "primary_category": "Education & Civic",
            "type":             "School",
            "default_on":       False,
            "color":            [99,  102, 241, 200],
            "subtypes": {
                "K-12 Schools": {
                    "value":      "K-12 School",
                    "default_on": True,
                    "color":      [99,  102, 241, 200],
                },
                "Early Childhood": {
                    "value":      "Early Childhood",
                    "default_on": False,
                    "color":      [129, 140, 248, 200],
                },
            },
        },
        "Higher Education": {
            "primary_category": "Education & Civic",
            "type":             "Higher Education",
            "default_on":       True,
            "color":            [67,  56,  202, 220],
            "subtypes":         None,
        },
        "Community Centers": {
            "primary_category": "Civic & Social",
            "type":             "Community Center",
            "default_on":       True,
            "color":            [168, 85,  247, 220],
            "subtypes":         None,
        },
        "Social Services": {
            "primary_category": "Civic & Social",
            "type":             "Social Services",
            "default_on":       True,
            "color":            [192, 132, 252, 200],
            "subtypes":         None,
        },
        "Financial": {
            "primary_category": "Civic & Social",
            "type":             "Financial",
            "default_on":       False,
            "color":            [100, 100, 180, 200],
            "subtypes":         None,
        },
        "Government": {
            "primary_category": "Civic & Social",
            "type":             "Government",
            "default_on":       False,
            "color":            [107, 114, 128, 200],
            "subtypes": {
                "Government Offices": {
                    "value":      "Government Office",
                    "default_on": True,
                    "color":      [107, 114, 128, 220],
                },
                "Post Offices": {
                    "value":      "Post Office",
                    "default_on": False,
                    "color":      [156, 163, 175, 200],
                },
            },
        },
        "Emergency Services": {
            "primary_category": "Civic & Social",
            "type":             "Emergency Services",
            "default_on":       False,
            "color":            [239, 68,  68,  200],
            "subtypes": {
                "Fire Stations": {
                    "value":      "Fire Station",
                    "default_on": True,
                    "color":      [239, 68,  68,  220],
                },
                "Police Stations": {
                    "value":      "Police Station",
                    "default_on": True,
                    "color":      [59,  130, 246, 220],
                },
            },
        },
        "Faith Communities": {
            "primary_category": "Civic & Social",
            "type":             "Faith Community",
            "default_on":       False,
            "color":            [180, 140, 200, 180],
            "subtypes":         None,
        },
    },
}

# ── DATA LOADING ──────────────────────────────────────────
@st.cache_data
def load_pois():
    df = pd.read_csv("data/raw/erie_pois.csv")
    return df.dropna(subset=["lat", "lon"])

@st.cache_data
def load_tracts():
    gdf = gpd.read_file(TIGER_URL)
    gdf = gdf[gdf["COUNTYFP"].isin(ERIE_FIPS) & (gdf["TRACTCE"] != "990000")]
    return gdf.to_crs(epsg=4326)

@st.cache_data
def load_census():
    return pd.read_csv("data/raw/erie_tract_data.csv", dtype={"tract_code": str})

@st.cache_data
def load_zctas():
    gdf = gpd.read_file(ZCTA_URL)
    return gdf[gdf["ZCTA5CE20"].isin(ZCTA_LIST)].to_crs(epsg=4326)

@st.cache_data
def load_zcta_data():
    return pd.read_csv("data/raw/zcta_data.csv", dtype={"zcta": str})

@st.cache_data
def load_poi_stats():
    return pd.read_csv("data/processed/tract_poi_stats.csv", dtype={"TRACTCE": str})

# ── GEOCODING & DISTANCE ─────────────────────────────────
def geocode_address(address):
    """Geocode an address using Nominatim (OpenStreetMap). No API key needed."""
    import urllib.request
    import urllib.parse
    query  = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url    = f"https://nominatim.openstreetmap.org/search?{query}"
    req    = urllib.request.Request(url, headers={"User-Agent": "ErieCountyDataApp/1.0"})
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
    R  = 3958.8  # Earth radius in miles
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a  = math.sin(dφ/2)**2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title("Services & POI Sandbox")

st.sidebar.markdown("---")
base_map      = MAP_LIGHT
point_size    = 4
county_filter = "Both"
county_fips_map = {"Erie County": "049", "Crawford County": "039"}

st.sidebar.markdown("### Geography")
geography = st.sidebar.radio("Boundary", ["Tract", "ZIP Code"], horizontal=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### Food Access")
snap_only = st.sidebar.checkbox(
    "SNAP authorized stores only",
    value=False,
    help="Show only food retailers authorized to accept SNAP/EBT benefits"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Choropleth underlay")
show_choro = st.sidebar.checkbox("Show tract choropleth", value=False)
choro_var = choro_opacity = None
if show_choro:
    choro_options = {
        "Poverty Rate":            "poverty_rate",
        "Median Household Income": "median_household_income",
        "No Vehicle Rate":         "no_vehicle_rate",
        "Rent Burden Rate":        "rent_burden_rate",
    }
    choro_label   = st.sidebar.selectbox("Variable", list(choro_options.keys()))
    choro_var     = choro_options[choro_label]
    choro_opacity = 0.3

st.sidebar.markdown("---")
st.sidebar.markdown("### Heatmap")
show_heatmap   = st.sidebar.checkbox("Show heatmap of visible points", value=False)
heatmap_radius = st.sidebar.slider("Radius (px)", 20, 120, 60, 5) if show_heatmap else 60

st.sidebar.markdown("---")
active_view = st.sidebar.radio(
    "View", list(LAYER_CONFIG.keys()), horizontal=False
)

# ── DYNAMIC SUBCATEGORY + SUBTYPE TOGGLES ─────────────────
st.sidebar.markdown(f"**{active_view} layers**")

# active_layers maps layer_key → list of subtype values to include (or None = all)
active_layers = {}

for subcat, cfg in LAYER_CONFIG[active_view].items():
    parent_on = st.sidebar.checkbox(subcat, value=cfg["default_on"], key=f"p_{subcat}")

    if not parent_on:
        continue

    if cfg["subtypes"]:
        # Show indented subtype toggles
        selected_subtypes = []
        for sub_label, sub_cfg in cfg["subtypes"].items():
            sub_on = st.sidebar.checkbox(
                f"  ↳ {sub_label}",
                value=sub_cfg["default_on"],
                key=f"s_{subcat}_{sub_label}"
            )
            if sub_on:
                selected_subtypes.append((sub_cfg["value"], sub_cfg["color"]))
        if selected_subtypes:
            active_layers[subcat] = {
                "cfg":      cfg,
                "subtypes": selected_subtypes,
            }
    else:
        active_layers[subcat] = {
            "cfg":      cfg,
            "subtypes": None,
        }

# ── LOAD DATA ─────────────────────────────────────────────
with st.spinner("Loading..."):
    pois      = load_pois()
    # Normalize snap_eligible to bool — add column if missing
    if "snap_eligible" not in pois.columns:
        pois["snap_eligible"] = pois["geocode_source"] == "usda_snap"
    else:
        pois["snap_eligible"] = pois["snap_eligible"].astype(str).str.lower() == "true"
    tracts    = load_tracts()
    zctas     = load_zctas()
    census    = load_census()
    zcta_data = load_zcta_data()
    stats     = load_poi_stats()

# ── COUNTY FILTER ─────────────────────────────────────────
# County filter for tract geography
if county_filter != "Both":
    fips            = county_fips_map[county_filter]
    tracts_filtered = tracts[tracts["COUNTYFP"] == fips].copy()
    tract_ids       = tracts_filtered["TRACTCE"].tolist()
    pois_filtered   = pois[pois["TRACTCE"].astype(str).str.zfill(6).isin(tract_ids)].copy()
    stats_filtered  = stats[stats["TRACTCE"].astype(str).str.zfill(6).isin(tract_ids)].copy()
else:
    tracts_filtered  = tracts.copy()
    pois_filtered    = pois.copy()
    stats_filtered   = stats.copy()

# SNAP filter — applies to food layer only
if snap_only:
    pois_filtered = pois_filtered[
        (pois_filtered["primary_category"] != "Food & Grocery") |
        (pois_filtered["snap_eligible"].astype(str).str.lower() == "true")
    ].copy()

# ZIP code geography uses ZCTA boundaries (county filter not applicable)
zctas_filtered   = zctas.copy()
zcta_yr          = zcta_data[zcta_data["year"] == 2023].copy()
zcta_yr["zcta"]  = zcta_yr["zcta"].astype(str).str.zfill(5)

# ── BUILD LAYERS ──────────────────────────────────────────
layers = []
all_visible = []

def choro_color(val, avg, reverse=False, op=0.3):
    if pd.isna(val) or pd.isna(avg):
        return [200, 200, 200, 60]
    norm = (val - avg * 0.75) / (avg * 0.5)
    norm = max(0.0, min(1.0, norm))
    if reverse:
        norm = 1 - norm
    alpha = int(op * 255)
    if norm < 0.5:
        t = norm * 2
        return [int(200 - t*40), int(80 + t*60), int(60 + t*20), alpha]
    t = (norm - 0.5) * 2
    return [int(160 - t*120), int(140 + t*70), int(80 - t*20), alpha]

# 1 — Choropleth underlay
if show_choro and choro_var:
    reverse = choro_var != "median_household_income"

    if geography == "Tract":
        yr_data = census[census["year"] == 2023].copy()
        yr_data["TRACTCE"] = yr_data["tract_code"].astype(str).str.zfill(6)
        merged  = tracts_filtered.merge(yr_data, on="TRACTCE", how="left")
        nat_avg = yr_data[choro_var].median()
        merged["fill_color"] = merged[choro_var].apply(
            lambda x: choro_color(x, nat_avg, reverse=reverse, op=choro_opacity)
        )
        choro_json = json.loads(merged[["geometry", "TRACTCE", "fill_color"]].to_json())
    else:
        merged  = zctas_filtered.merge(zcta_yr, left_on="ZCTA5CE20", right_on="zcta", how="left")
        nat_avg = zcta_yr[choro_var].median() if choro_var in zcta_yr.columns else None
        if nat_avg:
            merged["fill_color"] = merged[choro_var].apply(
                lambda x: choro_color(x, nat_avg, reverse=reverse, op=choro_opacity)
            )
        else:
            merged["fill_color"] = [[200, 200, 200, 60]] * len(merged)
        choro_json = json.loads(merged[["geometry", "ZCTA5CE20", "fill_color"]].to_json())

    layers.append(pdk.Layer(
        "GeoJsonLayer",
        data=choro_json,
        get_fill_color="properties.fill_color",
        get_line_color=[120, 120, 120, 60],
        line_width_min_pixels=1,
        pickable=False,
    ))

# 2 — POI scatter layers
for subcat, layer_info in active_layers.items():
    cfg      = layer_info["cfg"]
    subtypes = layer_info["subtypes"]

    subset = pois_filtered[
        (pois_filtered["primary_category"] == cfg["primary_category"]) &
        (pois_filtered["type"]             == cfg["type"])
    ].copy()

    if subtypes:
        # One layer per subtype with its own color
        for subtype_val, subtype_color in subtypes:
            sub = subset[subset["subtype"] == subtype_val].copy()
            if len(sub) == 0:
                continue
            sub["fill_color"]    = [subtype_color] * len(sub)
            sub["snap_eligible"] = sub["snap_eligible"].astype(str).apply(
                lambda x: "✓ SNAP/EBT accepted" if x.lower() == "true" else ""
            )
            all_visible.append(sub)
            layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=sub[["name", "address", "lat", "lon", "fill_color",
                           "primary_category", "type", "subtype", "snap_eligible"]],
                get_position=["lon", "lat"],
                get_radius=point_size * 40,
                radius_min_pixels=point_size,
                radius_max_pixels=point_size * 4,
                get_fill_color="fill_color",
                get_line_color=[255, 255, 255, 160],
                line_width_min_pixels=1,
                stroked=True,
                pickable=True,
                auto_highlight=True,
            ))
    else:
        if len(subset) == 0:
            continue
        subset["fill_color"]    = [cfg["color"]] * len(subset)
        subset["snap_eligible"] = subset["snap_eligible"].astype(str).apply(
            lambda x: "✓ SNAP/EBT accepted" if x.lower() == "true" else ""
        )
        all_visible.append(subset)
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=subset[["name", "address", "lat", "lon", "fill_color",
                         "primary_category", "type", "subtype", "snap_eligible"]],
            get_position=["lon", "lat"],
            get_radius=point_size * 40,
            radius_min_pixels=point_size,
            radius_max_pixels=point_size * 4,
            get_fill_color="fill_color",
            get_line_color=[255, 255, 255, 160],
            line_width_min_pixels=1,
            stroked=True,
            pickable=True,
            auto_highlight=True,
        ))

# 3 — Address search pin
if st.session_state.search_lat:
    pin_df = pd.DataFrame([{
        "lat":   st.session_state.search_lat,
        "lon":   st.session_state.search_lon,
        "label": st.session_state.search_label or "Search location",
    }])
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=pin_df,
        get_position=["lon", "lat"],
        get_radius=200,
        radius_min_pixels=10,
        radius_max_pixels=24,
        get_fill_color=[255, 215, 0, 255],   # gold pin
        get_line_color=[0, 0, 0, 255],
        line_width_min_pixels=2,
        stroked=True,
        pickable=False,
    ))

# 4 — Heatmap
if show_heatmap and all_visible:
    heat_df = pd.concat(all_visible)[["lat", "lon"]].copy()
    heat_df["weight"] = 1
    layers.append(pdk.Layer(
        "HeatmapLayer",
        data=heat_df,
        get_position=["lon", "lat"],
        get_weight="weight",
        radiusPixels=heatmap_radius,
        opacity=0.65,
    ))

# ── HEADER ────────────────────────────────────────────────
st.title("Community Services & POI Map")

total_pts = sum(len(v) for v in all_visible)
st.caption(
    f"View: **{active_view}** — "
    f"County: **{county_filter}** — "
    f"**{total_pts}** points visible"
)

with st.expander("Debug — type values in data", expanded=False):
    food = pois[pois["primary_category"] == "Food & Grocery"]
    st.write(f"Food & Grocery records: {len(food)}")
    st.write("Unique type values:")
    st.write(food["type"].value_counts())

# ── COLOR KEY ─────────────────────────────────────────────
key_items = []
for subcat, layer_info in active_layers.items():
    cfg      = layer_info["cfg"]
    subtypes = layer_info["subtypes"]
    if subtypes:
        for subtype_val, subtype_color in subtypes:
            key_items.append((subtype_val, subtype_color))
    else:
        key_items.append((subcat, cfg["color"]))

if key_items:
    cols = st.columns(min(len(key_items), 6))
    for i, (label, color) in enumerate(key_items):
        r, g, b = color[0], color[1], color[2]
        cols[i % 6].markdown(
            f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:4px'>"
            f"<div style='width:10px;height:10px;border-radius:50%;"
            f"background:rgb({r},{g},{b});flex-shrink:0'></div>"
            f"<span style='font-size:11px'>{label}</span></div>",
            unsafe_allow_html=True
        )

st.markdown("<br/>", unsafe_allow_html=True)

# ── MAP ───────────────────────────────────────────────────
st.pydeck_chart(
    pdk.Deck(
        map_style=base_map,
        initial_view_state=pdk.ViewState(
            latitude=st.session_state.search_lat or 41.95,
            longitude=st.session_state.search_lon or -80.15,
            zoom=13 if st.session_state.search_lat else 8.5,
            pitch=0,
        ),
        layers=layers,
        tooltip={
            "html": "<b>{name}</b><br/>{subtype}<br/>{address}<br/>{snap_eligible}",
            "style": {
                "backgroundColor": "#1e293b",
                "color":           "white",
                "fontSize":        "12px",
                "padding":         "10px",
                "borderRadius":    "4px",
            }
        },
    ),
    use_container_width=True,
    height=600,
)

# ── ADDRESS SEARCH ────────────────────────────────────────
st.markdown("---")
st.markdown("### What's Near Me?")
st.caption("Enter any address in Erie or Crawford County to find nearby services.")

# Input row — address takes full width, radius and button on same line below
address_input = st.text_input(
    "Address",
    placeholder="e.g. 1341 W 26th St, Erie, PA",
    label_visibility="collapsed"
)
rb1, rb2, rb3 = st.columns([2, 2, 1])
with rb1:
    radius_miles = st.selectbox(
        "Radius", [0.25, 0.5, 1.0, 2.0, 5.0], index=2,
        format_func=lambda x: f"{x} mile{'s' if x != 1.0 else ''}",
        label_visibility="visible"
    )
with rb2:
    # Category pre-filter — narrow results before searching
    cat_pre_filter = st.multiselect(
        "Only show categories",
        options=sorted(pois["primary_category"].unique().tolist()),
        default=[],
        placeholder="All categories",
    )
with rb3:
    st.markdown("<br/>", unsafe_allow_html=True)
    search_btn = st.button("Search", use_container_width=True)

if search_btn and address_input.strip():
    with st.spinner("Geocoding address..."):
        lat, lon, label = geocode_address(address_input.strip() + ", PA")
    if lat is None:
        st.error("Address not found. Try adding the city and state — e.g. '123 Main St, Erie, PA'")
        st.session_state.search_lat     = None
        st.session_state.search_results = None
    else:
        st.session_state.search_lat   = lat
        st.session_state.search_lon   = lon
        st.session_state.search_label = label

        nearby = pois.copy()
        nearby["distance_miles"] = nearby.apply(
            lambda r: haversine_miles(lat, lon, r["lat"], r["lon"]), axis=1
        )
        nearby = nearby[nearby["distance_miles"] <= radius_miles].copy()
        nearby = nearby.sort_values("distance_miles")
        st.session_state.search_results = nearby
        st.rerun()

if st.session_state.search_lat:
    results = st.session_state.search_results

    # Apply category pre-filter if set
    if cat_pre_filter:
        results = results[results["primary_category"].isin(cat_pre_filter)]

    if results is None or len(results) == 0:
        st.info("No services found within that radius for the selected categories.")
    else:
        st.success(
            f"📍 **{address_input or 'Search location'}** — "
            f"{len(results)} services within {radius_miles} mile(s)"
        )

        # Summary counts table — full width
        cat_counts = (
            results.groupby(["primary_category", "type"])
            .size().reset_index(name="Count")
            .sort_values("Count", ascending=False)
            .rename(columns={"primary_category": "Category", "type": "Type"})
        )
        with st.expander(f"Summary by category ({len(cat_counts)} types found)", expanded=True):
            st.dataframe(cat_counts, use_container_width=True, hide_index=True)

        # Full results table — full width, filter by type
        st.markdown("**All results — sorted by distance**")

        all_types = ["All types"] + sorted(results["type"].unique().tolist())
        type_filter = st.selectbox("Filter by type", all_types, key="result_type_filter")

        display_results = results[[
            "name", "primary_category", "type", "subtype", "address", "distance_miles"
        ]].copy()
        display_results["distance_miles"] = display_results["distance_miles"].round(2)
        display_results.columns = ["Name", "Category", "Type", "Subtype", "Address", "Distance (mi)"]

        if type_filter != "All types":
            display_results = display_results[display_results["Type"] == type_filter]

        st.dataframe(
            display_results,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Distance (mi)": st.column_config.NumberColumn(format="%.2f mi"),
            }
        )

    if st.button("Clear search"):
        st.session_state.search_lat     = None
        st.session_state.search_lon     = None
        st.session_state.search_label   = None
        st.session_state.search_results = None
        st.rerun()

# ── STATS PANEL ───────────────────────────────────────────
st.markdown("---")
st.markdown("### Service Access by Tract")
st.caption("Precomputed from tract_poi_stats.csv — counts and nearest distances per tract.")

stat_options = {
    "Nearest full-service grocery (miles)": "nearest_grocery_full_miles",
    "Nearest pharmacy (miles)":             "nearest_pharmacy_miles",
    "Nearest hospital (miles)":             "nearest_hospital_miles",
    "Nearest clinic (miles)":               "nearest_clinic_miles",
    "Nearest library (miles)":              "nearest_library_miles",
    "Nearest community center (miles)":     "nearest_community_center_miles",
    "Nearest social services (miles)":      "nearest_social_services_miles",
    "Count — full-service grocery":         "count_grocery_full",
    "Count — pharmacy":                     "count_pharmacy",
    "Count — clinic":                       "count_clinic",
    "Count — library":                      "count_library",
    "Count — community center":             "count_community_center",
    "Count — social services":              "count_social_services",
    "Total civic POIs in tract":            "count_total_civic",
}

sc1, sc2 = st.columns(2)
with sc1:
    stat_label = st.selectbox("Metric", list(stat_options.keys()))
    stat_col   = stat_options[stat_label]
with sc2:
    top_n = st.slider("Top / bottom N", 5, 30, 15)

if stat_col in stats_filtered.columns:
    display = stats_filtered[["TRACTCE", stat_col]].dropna().copy()
    display.columns = ["Tract", stat_label]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mean",   f"{display[stat_label].mean():.1f}")
    m2.metric("Median", f"{display[stat_label].median():.1f}")
    m3.metric("Max",    f"{display[stat_label].max():.1f}")
    m4.metric("Min",    f"{display[stat_label].min():.1f}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Highest (most need / farthest)**")
        st.dataframe(
            display.sort_values(stat_label, ascending=False).head(top_n),
            use_container_width=True, hide_index=True
        )
    with col_b:
        st.markdown("**Best access / closest**")
        st.dataframe(
            display.sort_values(stat_label, ascending=True).head(top_n),
            use_container_width=True, hide_index=True
        )