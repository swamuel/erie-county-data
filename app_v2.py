import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
import numpy as np
import plotly.graph_objects as go

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
    return (census, sh_data, shapes, stops, pantries,
            benchmarks_national, benchmarks_pa, benchmarks_erie,
            benchmarks_counties, transit_stats)

@st.cache_data
def load_boundaries():
    url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
    gdf = gpd.read_file(url)
    gdf = gdf[gdf["COUNTYFP"].isin(["049", "039"])]
    gdf = gdf[gdf["TRACTCE"] != "990000"]
    return gdf

(census, sh_data, shapes, stops, pantries,
 benchmarks_national, benchmarks_pa, benchmarks_erie,
 benchmarks_counties, transit_stats) = load_data()

gdf = load_boundaries()

# ── SESSION STATE ─────────────────────────────────────────
if "selected_tract" not in st.session_state:
    st.session_state.selected_tract = None
if "selected_tract_name" not in st.session_state:
    st.session_state.selected_tract_name = None

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
        # Muted red/orange — terracotta
        t = normalized * 2
        r = int(200 - (t * 40))
        g = int(80 + (t * 60))
        b = int(60 + (t * 20))
    else:
        # Muted green — sage to forest
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
    if pd.isna(value):
        return "No data"
    if column == "median_household_income":
        return f"${value:,.0f}"
    return f"{value}%"

def diff_string(tract_val, benchmark_val):
    if pd.isna(tract_val) or benchmark_val is None:
        return ""
    diff = round(tract_val - benchmark_val, 1)
    arrow = "▲" if diff > 0 else "▼"
    return f"{arrow} {abs(diff)}"

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title("Erie & Crawford County Data")

mode = st.sidebar.radio("Mode", ["Simple", "Advanced"], horizontal=True)

st.sidebar.markdown("---")

year = st.sidebar.selectbox("Year", [2023, 2022, 2021, 2020, 2019])

view_mode = st.sidebar.radio(
    "View", ["Current Year", "Trend (2019-2023)"], horizontal=True
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

merged = gdf.merge(df_year, left_on="TRACTCE", right_on="tract_code", how="left")
merged = merged.merge(
    sh_year[["tract_code", "food_insecurity_rate", "unemployment_rate",
             "disability_rate", "homeownership_rate"]],
    left_on="TRACTCE", right_on="tract_code", how="left"
)

transit_stats["TRACTCE"] = transit_stats["TRACTCE"].astype(str).str.zfill(6)
merged = merged.merge(transit_stats, on="TRACTCE", how="left")

benchmark_row = get_benchmark_row(selected_benchmark, compare_county, year)

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

# ── DETAIL PANEL FUNCTION ─────────────────────────────────
def render_detail_panel(merged_df, column, selected_layer):
    if st.session_state.selected_tract is None:
        st.caption("Select a tract above to see detailed data.")
        return

    tract_code = st.session_state.selected_tract
    tract_name = st.session_state.selected_tract_name
    tract_data = merged_df[merged_df["TRACTCE"] == tract_code]

    if len(tract_data) == 0:
        st.warning("No data found for selected tract.")
        return

    row = tract_data.iloc[0]
    st.subheader(tract_name)

    m1, m2, m3, m4 = st.columns(4)
    for col_widget, var_label, var_col in [
        (m1, "Median Income", "median_household_income"),
        (m2, "Poverty Rate", "poverty_rate"),
        (m3, "Rent Burden", "rent_burden_rate"),
        (m4, "No Vehicle", "no_vehicle_rate"),
    ]:
        with col_widget:
            val = row[var_col]
            bval = get_benchmark_value(benchmark_row, var_col)
            delta = f"{diff_string(val, bval)} vs benchmark" if bval else None
            col_widget.metric(var_label, format_value(val, var_col), delta)

    st.markdown("---")

    if view_mode == "Trend (2019-2023)":
        tract_all_years = census[
            census["tract_code"].astype(str).str.zfill(6) == tract_code
        ].copy()

        if len(tract_all_years) > 0:
            bench_all_years = []
            for y in [2019, 2020, 2021, 2022, 2023]:
                br = get_benchmark_row(selected_benchmark, compare_county, y)
                bv = get_benchmark_value(br, column)
                bench_all_years.append({"year": y, "benchmark": bv})
            bench_df = pd.DataFrame(bench_all_years)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=tract_all_years["year"],
                y=tract_all_years[column],
                mode="lines+markers",
                name=tract_name,
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

    st.markdown("**All Variables**")
    table_rows = []
    for label, col in all_variables.items():
        if col in row.index:
            val = row[col]
            bval = get_benchmark_value(benchmark_row, col)
            table_rows.append({
                "Variable": label,
                "This Tract": format_value(val, col),
                "Benchmark": format_value(bval, col) if bval is not None else "—",
                "Difference": diff_string(val, bval) if bval is not None else "—"
            })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)


# ── TABS ──────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Overview", "Economic", "Transit", "Food Access", "Query Tool"
])

# ═══════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════
with tab1:
    st.subheader("Erie & Crawford County Community Data")
    st.markdown(
        "Explore neighborhood-level data across Erie and Crawford Counties. "
        "Select a tab to dive into Economic, Transit, or Food Access data. "
        "Use the tract selector below the map to see detailed information."
    )

    national_avg_overview = get_benchmark_value(benchmark_row, "poverty_rate")
    merged["color"] = merged["poverty_rate"].apply(
        lambda x: value_to_color(x, national_avg_overview, reverse=True)
    )
    overview_json = json.loads(merged.to_json())

    overview_layer = pdk.Layer(
        "GeoJsonLayer",
        data=overview_json,
        get_fill_color="properties.color",
        get_line_color=[255, 255, 255, 50],
        line_width_min_pixels=1,
        pickable=True
    )

    st.pydeck_chart(pdk.Deck(
        layers=[overview_layer],
        initial_view_state=pdk.ViewState(
            latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
        ),
        tooltip={
            "html": "<b>{NAMELSAD}</b><br/>Poverty Rate: {poverty_rate}%",
            "style": {"backgroundColor": "steelblue", "color": "white",
                      "fontSize": "12px", "padding": "10px"}
        },
        map_style="road"
    ))

# ═══════════════════════════════════════════════════════
# TAB 2 — ECONOMIC
# ═══════════════════════════════════════════════════════
with tab2:
    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        st.subheader("Economic Data")

        layer_options = {
            "Median Household Income": ("median_household_income", False),
            "Poverty Rate (%)": ("poverty_rate", True),
            "Bachelor's Degree (%)": ("bachelors_rate", False),
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
                for label, col in all_variables.items():
                    with st.expander(label):
                        enabled = st.checkbox(f"Include {label}", key=f"econ_enable_{col}")
                        if enabled:
                            direction = st.radio(
                                "Direction", ["Above", "Below"],
                                horizontal=True, key=f"econ_dir_{col}"
                            )
                            query_conditions[col] = direction

        # Tract selector
        st.markdown("---")
        st.markdown("**Explore a Tract**")
        tract_options = ["None"] + sorted(merged["NAMELSAD"].dropna().tolist())
        selected_name = st.selectbox(
            "Select tract", tract_options, key="econ_tract_select"
        )
        if selected_name != "None":
            sel_row = merged[merged["NAMELSAD"] == selected_name].iloc[0]
            st.session_state.selected_tract = sel_row["TRACTCE"]
            st.session_state.selected_tract_name = selected_name
        else:
            st.session_state.selected_tract = None
            st.session_state.selected_tract_name = None

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
            st.metric("Matching tracts", int(mask.sum()))

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
                st.metric("Matching tracts", int(final_mask.sum()))

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
            initial_view_state=pdk.ViewState(
                latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
            ),
            tooltip={
                "html": "<b>{NAMELSAD}</b><br/>"
                        "Income: ${median_household_income}<br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "Rent Burden: {rent_burden_rate}%<br/>"
                        "No Vehicle: {no_vehicle_rate}%",
                "style": {"backgroundColor": "steelblue", "color": "white",
                          "fontSize": "12px", "padding": "10px"}
            },
            map_style="road"

        ))

        st.markdown("---")
        render_detail_panel(merged_econ, column, selected_layer)

# ═══════════════════════════════════════════════════════
# TAB 3 — TRANSIT
# ═══════════════════════════════════════════════════════
with tab3:
    col_controls_t, col_map_t = st.columns([1, 3])

    with col_controls_t:
        st.subheader("Transit Coverage")
        show_routes = st.checkbox("Show EMTA Routes", value=True, key="transit_routes")
        show_stops = st.checkbox("Show Bus Stops", value=True, key="transit_stops")
        show_no_vehicle = st.checkbox("Show No Vehicle Layer", value=True, key="transit_no_vehicle")

        if mode == "Advanced":
            st.markdown("---")
            st.markdown("**Transit Analysis Tools**")
            transit_tool = st.selectbox(
                "Tool",
                ["None", "Coverage Gap Finder", "Transit Desert Finder"],
                key="transit_tool"
            )

            transit_threshold_veh = None
            transit_threshold_freq = None
            desert_threshold = None

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
        else:
            transit_tool = "None"
            transit_threshold_veh = None
            transit_threshold_freq = None
            desert_threshold = None

    with col_map_t:
        transit_layers = []

        benchmark_row_t = get_benchmark_row(selected_benchmark, compare_county, year)
        national_avg_t = get_benchmark_value(benchmark_row_t, "no_vehicle_rate")

        merged_transit = merged.copy()
        merged_transit["color"] = merged_transit["no_vehicle_rate"].apply(
            lambda x: value_to_color(x, national_avg_t, reverse=True)
        )

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

        st.pydeck_chart(pdk.Deck(
            layers=transit_layers,
            initial_view_state=pdk.ViewState(
                latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
            ),
            tooltip={
                "html": "<b>{stop_name}</b><br/>"
                        "Daily visits: {daily_visits}<br/>"
                        "First bus: {first_service}<br/>"
                        "Last bus: {last_service}<br/>"
                        "<b>{NAMELSAD}</b><br/>"
                        "No Vehicle Rate: {no_vehicle_rate}%<br/>"
                        "Stop count: {stop_count}<br/>"
                        "Nearest stop: {nearest_stop_miles} miles",
                "style": {"backgroundColor": "steelblue", "color": "white",
                          "fontSize": "12px", "padding": "10px"}
            },
            map_style="road"
        ))

# ═══════════════════════════════════════════════════════
# TAB 4 — FOOD ACCESS
# ═══════════════════════════════════════════════════════
with tab4:
    col_controls_f, col_map_f = st.columns([1, 3])

    with col_controls_f:
        st.subheader("Food Access")
        show_pantries = st.checkbox("Show Food Pantries", value=True, key="food_pantries")
        show_food_layer = st.checkbox("Show Food Insecurity Layer", value=True, key="food_layer")

    with col_map_f:
        food_layers = []

        national_avg_f = get_benchmark_value(benchmark_row, "poverty_rate")
        merged_food = merged.copy()
        merged_food["color"] = merged_food["food_insecurity_rate"].apply(
            lambda x: value_to_color(x, national_avg_f, reverse=True)
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

        st.pydeck_chart(pdk.Deck(
            layers=food_layers,
            initial_view_state=pdk.ViewState(
                latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
            ),
            tooltip={
                "html": "<b>{PantryName}</b><br/>"
                        "Hours: {hours}<br/>"
                        "<b>{NAMELSAD}</b><br/>"
                        "Food Insecurity: {food_insecurity_rate}%",
                "style": {"backgroundColor": "steelblue", "color": "white",
                          "fontSize": "12px", "padding": "10px"}
            },
            map_style="road"
        ))

# ═══════════════════════════════════════════════════════
# TAB 5 — QUERY TOOL
# ═══════════════════════════════════════════════════════
with tab5:
    st.subheader("Multi-Variable Query")
    st.markdown("Find tracts that meet multiple conditions across all variables.")

    col_q1, col_q2 = st.columns([1, 3])

    with col_q1:
        logic_q = st.radio(
            "Match",
            ["ALL conditions (AND)", "ANY condition (OR)"],
            horizontal=True, key="query_logic"
        )

        query_conditions_q = {}
        for label, col in all_variables.items():
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
                st.metric("Matching tracts", int(final_mask_q.sum()))

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
            initial_view_state=pdk.ViewState(
                latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
            ),
            tooltip={
                "html": "<b>{NAMELSAD}</b><br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "Income: ${median_household_income}<br/>"
                        "Food Insecurity: {food_insecurity_rate}%",
                "style": {"backgroundColor": "steelblue", "color": "white",
                          "fontSize": "12px", "padding": "10px"}
            },
        map_style="road"
        ))