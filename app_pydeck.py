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
    transit_stats = pd.read_csv("data/processed/tract_transit_stats.csv")
    return census, sh_data, shapes, stops, pantries, benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties, transit_stats

@st.cache_data
def load_boundaries():
    url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    gdf = gpd.read_file(url)
    gdf = gdf[gdf["COUNTYFP"].isin(["049", "039"])]
    gdf = gdf[gdf["TRACTCE"] != "990000"]
    return gdf

census, sh_data, shapes, stops, pantries, benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties, transit_stats = load_data()
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

# ── GLOBAL SIDEBAR CONTROLS ──────────────────────────────
st.sidebar.title("Controls")

year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark Context")

benchmark_options = ["National", "Pennsylvania", "Erie County", "Compare to Another PA County"]
selected_benchmark = st.sidebar.selectbox("Compare tracts against", benchmark_options)

compare_county = None
if selected_benchmark == "Compare to Another PA County":
    county_list = sorted(benchmarks_counties["name"].unique().tolist())
    compare_county = st.sidebar.selectbox("Select county", county_list)

show_comparison = st.sidebar.toggle("Show vs Benchmark in Tooltip", value=False, key="comparison_toggle")

# ── DATA PREP ────────────────────────────────────────────
df_year = census[census["year"] == year].copy()
df_year["tract_code"] = df_year["tract_code"].astype(str).str.zfill(6)

sh_year = sh_data[sh_data["year"] == min(year, 2023)].copy()
sh_year["tract_code"] = sh_year["tract_code"].astype(str).str.zfill(6)

merged = gdf.merge(df_year, left_on="TRACTCE", right_on="tract_code", how="left")
merged = merged.merge(sh_year[["tract_code", "food_insecurity_rate",
                                "unemployment_rate", "disability_rate",
                                "homeownership_rate"]],
                      left_on="TRACTCE", right_on="tract_code", how="left")

# ── TABS ─────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Census Data", "Transit", "Food Access"])

# ═══════════════════════════════════════════════════════
# TAB 1 — CENSUS DATA
# ═══════════════════════════════════════════════════════
with tab1:
    st.subheader("Census Tract Data")

    col1, col2 = st.columns([1, 3])

    with col1:
        layer_options = {
            "Median Household Income": ("median_household_income", False),
            "Poverty Rate (%)": ("poverty_rate", True),
            "Bachelor's Degree (%)": ("bachelors_rate", False),
            "Rent Burden Rate (%)": ("rent_burden_rate", True),
            "No Vehicle Rate (%)": ("no_vehicle_rate", True)
        }

        selected_layer = st.selectbox("Census Layer", list(layer_options.keys()))
        column, reverse = layer_options[selected_layer]

        st.markdown("**Tooltip Variables**")
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

        selected_tooltip_vars = st.multiselect(
            "Select variables to show",
            options=list(all_variables.keys()),
            default=default_variables
        )

        st.markdown("**Analytical Tools**")
        tool_options = ["None", "Threshold Filter", "Multi-Variable Query"]
        selected_tool = st.selectbox("Select Tool", tool_options)

        threshold_direction = None
        threshold_value = None
        highlight_layer = None
        query_conditions = {}
        logic = None

        if selected_tool == "Threshold Filter":
            st.markdown(f"Find tracts where **{selected_layer}** is:")
            threshold_direction = st.radio(
                "Direction",
                ["Above", "Below"],
                horizontal=True,
                key="threshold_direction"
            )

        if selected_tool == "Multi-Variable Query":
            logic = st.radio(
                "Match",
                ["ALL conditions (AND)", "ANY condition (OR)"],
                horizontal=True,
                key="query_logic"
            )
            for label, col in all_variables.items():
                with st.expander(label):
                    enabled = st.checkbox(f"Include {label}", key=f"enable_{col}")
                    if enabled:
                        direction = st.radio(
                            "Direction",
                            ["Above", "Below"],
                            horizontal=True,
                            key=f"dir_{col}"
                        )
                        query_conditions[col] = ("direction_placeholder", direction)

    with col2:
        # Threshold slider
        if selected_tool == "Threshold Filter":
            col_min = float(merged[column].min())
            col_max = float(merged[column].max())
            col_mean = float(merged[column].mean())
            threshold_value = st.slider(
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
            st.metric("Matching tracts", len(matching))

        # Multi-variable sliders
        if selected_tool == "Multi-Variable Query" and query_conditions:
            updated_conditions = {}
            for col, (_, direction) in query_conditions.items():
                col_min = float(merged[col].min())
                col_max = float(merged[col].max())
                col_mean = float(merged[col].mean())
                threshold = st.slider(
                    f"{col} threshold",
                    min_value=col_min,
                    max_value=col_max,
                    value=col_mean,
                    step=(col_max - col_min) / 100,
                    key=f"thresh_{col}"
                )
                updated_conditions[col] = (direction, threshold)
            query_conditions = updated_conditions

        # Benchmark and colors
        benchmark_row = get_benchmark_row(selected_benchmark, compare_county, year)
        national_avg = benchmark_row[column].values[0] if len(benchmark_row) > 0 else None

        if national_avg is not None:
            if column == "median_household_income":
                st.metric(f"Benchmark: {selected_benchmark}", f"${national_avg:,.0f}")
            else:
                st.metric(f"Benchmark: {selected_benchmark}", f"{national_avg}%")

        merged_census = merged.copy()
        merged_census["color"] = merged_census[column].apply(
            lambda x: value_to_color(x, national_avg, reverse)
        )

        if show_comparison:
            for col in ["median_household_income", "poverty_rate", "rent_burden_rate",
                        "no_vehicle_rate", "unemployment_rate", "disability_rate"]:
                if col in benchmark_row.columns:
                    nat_avg = benchmark_row[col].values[0]
                    merged_census[f"{col}_diff"] = (merged_census[col] - nat_avg).round(1)
                    merged_census[f"{col}_diff_str"] = merged_census[f"{col}_diff"].apply(
                        lambda x: f"+{x}" if x > 0 else str(x)
                    )

        # Apply filters
        if selected_tool == "Threshold Filter" and threshold_value is not None:
            if threshold_direction == "Above":
                highlight_mask = merged_census[column] > threshold_value
            else:
                highlight_mask = merged_census[column] < threshold_value
            merged_census["color"] = merged_census.apply(
                lambda row: row["color"] if highlight_mask[row.name]
                else [100, 100, 100, 60],
                axis=1
            )

        elif selected_tool == "Multi-Variable Query" and query_conditions:
            masks = []
            for col, (direction, threshold) in query_conditions.items():
                if direction == "Above":
                    masks.append(merged_census[col] > threshold)
                else:
                    masks.append(merged_census[col] < threshold)
            if masks:
                if "AND" in logic:
                    final_mask = masks[0]
                    for m in masks[1:]:
                        final_mask = final_mask & m
                else:
                    final_mask = masks[0]
                    for m in masks[1:]:
                        final_mask = final_mask | m
                st.metric("Matching tracts", int(final_mask.sum()))
                merged_census["color"] = merged_census.apply(
                    lambda row: row["color"] if final_mask[row.name]
                    else [100, 100, 100, 60],
                    axis=1
                )

        merged_json = json.loads(merged_census.to_json())

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

        view_state = pdk.ViewState(
            latitude=42.1167,
            longitude=-80.0,
            zoom=10,
            pitch=0
        )

        deck = pdk.Deck(
            layers=[tract_layer],
            initial_view_state=view_state,
            tooltip=tooltip
        )

        st.pydeck_chart(deck)

# ═══════════════════════════════════════════════════════
# TAB 2 — TRANSIT
# ═══════════════════════════════════════════════════════
with tab2:
    st.subheader("Transit Coverage")

    col1, col2 = st.columns([1, 3])

    with col1:
        show_routes = st.checkbox("Show EMTA Routes", value=True, key="transit_routes")
        show_stops = st.checkbox("Show Bus Stops", value=True, key="transit_stops")
        show_no_vehicle = st.checkbox("Show No Vehicle Rate Layer", value=True, key="transit_no_vehicle")

        st.markdown("**Transit Analysis Tools**")
        transit_tool = st.selectbox(
            "Select Tool",
            ["None", "Coverage Gap Finder", "Transit Desert Finder"],
            key="transit_tool"
        )

        transit_threshold_veh = None
        transit_threshold_freq = None
        desert_threshold = None

        if transit_tool == "Coverage Gap Finder":
            st.markdown("Find tracts where residents lack cars **and** bus service is limited")
            transit_threshold_veh = st.slider(
                "No Vehicle Rate above (%)",
                min_value=0.0,
                max_value=100.0,
                value=15.0,
                step=0.5,
                key="veh_threshold"
            )
            transit_threshold_freq = st.slider(
                "Total daily bus visits below",
                min_value=0.0,
                max_value=float(transit_stats["total_daily_visits"].max()),
                value=100.0,
                step=5.0,
                key="freq_threshold"
            )

        if transit_tool == "Transit Desert Finder":
            st.markdown("Find tracts beyond a certain distance from the nearest stop")
            desert_threshold = st.slider(
                "Distance to nearest stop greater than (miles)",
                min_value=0.0,
                max_value=float(transit_stats["nearest_stop_miles"].max()),
                value=1.0,
                step=0.1,
                key="desert_threshold"
            )

    with col2:
        transit_layers = []

        # Prep merged transit data
        benchmark_row_t = get_benchmark_row(selected_benchmark, compare_county, year)
        national_avg_t = benchmark_row_t["no_vehicle_rate"].values[0] if len(benchmark_row_t) > 0 else None

        merged_transit = merged.copy()
        transit_stats["TRACTCE"] = transit_stats["TRACTCE"].astype(str).str.zfill(6)
        merged_transit = merged_transit.merge(transit_stats, on="TRACTCE", how="left")

        # Calculate base colors
        merged_transit["color"] = merged_transit["no_vehicle_rate"].apply(
            lambda x: value_to_color(x, national_avg_t, reverse=True)
        )

        # Apply transit tools — must come after color calculation
        if transit_tool == "Coverage Gap Finder" and transit_threshold_veh and transit_threshold_freq:
            gap_mask = (
                (merged_transit["no_vehicle_rate"] > transit_threshold_veh) &
                (merged_transit["total_daily_visits"] < transit_threshold_freq)
            )
            merged_transit["color"] = merged_transit.apply(
                lambda row: row["color"] if gap_mask[row.name]
                else [100, 100, 100, 60],
                axis=1
            )
            st.metric("Coverage gap tracts", int(gap_mask.sum()))

        elif transit_tool == "Transit Desert Finder" and desert_threshold:
            desert_mask = merged_transit["nearest_stop_miles"] > desert_threshold
            merged_transit["color"] = merged_transit.apply(
                lambda row: row["color"] if desert_mask[row.name]
                else [100, 100, 100, 60],
                axis=1
            )
            st.metric("Transit desert tracts", int(desert_mask.sum()))

        transit_json = json.loads(merged_transit.to_json())

        # No vehicle choropleth
        if show_no_vehicle:
            transit_layer = pdk.Layer(
                "GeoJsonLayer",
                data=transit_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=False
            )
            transit_layers.append(transit_layer)

        # Routes
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
            transit_layers.append(route_layer)

        # Stops
        if show_stops:
            stops_data = stops.copy()
            stops_data["radius"] = stops_data["daily_visits"].apply(
                lambda x: max(30, min(150, x * 1.5))
            )
            stops_data["color"] = [[50, 50, 50, 200]] * len(stops_data)

            stops_layer = pdk.Layer(
                "ScatterplotLayer",
                data=stops_data,
                get_position=["stop_lon", "stop_lat"],
                get_radius="radius",
                get_fill_color="color",
                pickable=True,
                opacity=0.8
            )
            transit_layers.append(stops_layer)

        transit_tooltip = {
            "html": "<b>{stop_name}</b><br/>"
                    "Daily visits: {daily_visits}<br/>"
                    "First bus: {first_service}<br/>"
                    "Last bus: {last_service}<br/>"
                    "<b>{NAMELSAD}</b><br/>"
                    "No Vehicle Rate: {no_vehicle_rate}%<br/>"
                    "Stop count: {stop_count}<br/>"
                    "Total daily visits: {total_daily_visits}<br/>"
                    "Nearest stop: {nearest_stop_miles} miles",
            "style": {
                "backgroundColor": "steelblue",
                "color": "white",
                "fontSize": "12px",
                "padding": "10px"
            }
        }

        view_state_t = pdk.ViewState(
            latitude=42.1167,
            longitude=-80.0,
            zoom=10,
            pitch=0
        )

        deck_t = pdk.Deck(
            layers=transit_layers,
            initial_view_state=view_state_t,
            tooltip=transit_tooltip
        )

        st.pydeck_chart(deck_t)

# ═══════════════════════════════════════════════════════
# TAB 3 — FOOD ACCESS
# ═══════════════════════════════════════════════════════
with tab3:
    st.subheader("Food Access")

    col1, col2 = st.columns([1, 3])

    with col1:
        show_pantries = st.checkbox("Show Food Pantries", value=True)
        show_food_insecurity = st.checkbox("Show Food Insecurity Layer", value=True)

    with col2:
        food_layers = []

        # Food insecurity choropleth
        if show_food_insecurity:
            benchmark_row_f = get_benchmark_row(selected_benchmark, compare_county, year)
            national_avg_f = benchmark_row_f["poverty_rate"].values[0] if len(benchmark_row_f) > 0 else None

            merged_food = merged.copy()
            merged_food["color"] = merged_food["food_insecurity_rate"].apply(
                lambda x: value_to_color(x, national_avg_f, reverse=True)
            )
            food_json = json.loads(merged_food.to_json())

            food_layer = pdk.Layer(
                "GeoJsonLayer",
                data=food_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=False
            )
            food_layers.append(food_layer)

        # Pantries
        if show_pantries:
            pantries_data = pantries.dropna(subset=["lat", "lon"]).copy()
            pantries_data["color"] = [[0, 150, 0, 220]] * len(pantries_data)
            pantries_data["hours"] = pantries_data["Open"].fillna("Hours not available")

            pantries_layer = pdk.Layer(
                "ScatterplotLayer",
                data=pantries_data,
                get_position=["lon", "lat"],
                get_radius=200,
                get_fill_color="color",
                pickable=True,
                opacity=0.9
            )
            food_layers.append(pantries_layer)

        food_tooltip = {
            "html": "<b>{PantryName}</b><br/>"
                    "Hours: {hours}<br/>"
                    "<b>{NAMELSAD}</b><br/>"
                    "Food Insecurity: {food_insecurity_rate}%",
            "style": {
                "backgroundColor": "steelblue",
                "color": "white",
                "fontSize": "12px",
                "padding": "10px"
            }
        }

        view_state_f = pdk.ViewState(
            latitude=42.1167,
            longitude=-80.0,
            zoom=10,
            pitch=0
        )

        deck_f = pdk.Deck(
            layers=food_layers,
            initial_view_state=view_state_f,
            tooltip=food_tooltip
        )

        st.pydeck_chart(deck_f)