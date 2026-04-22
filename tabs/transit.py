import streamlit as st
import pydeck as pdk
import json

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE, HIGHER_IS_BETTER
from lib.helpers import value_to_color, get_benchmark_value, format_value, render_detail_panel


def render(merged, shapes, stops, transit_stats, benchmark_row, geography, mode):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]

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

        merged_transit = merged.assign(
            color=merged["no_vehicle_rate"].apply(
                lambda x: value_to_color(x, national_avg_t, reverse=True)
            )
        )

        if geography == "Tract":
            grey = [100, 100, 100, 60]
            if transit_tool == "Coverage Gap Finder" and transit_threshold_veh and transit_threshold_freq:
                gap_mask = (
                    (merged_transit["no_vehicle_rate"] > transit_threshold_veh) &
                    (merged_transit["total_daily_visits"] < transit_threshold_freq)
                ).tolist()
                merged_transit = merged_transit.copy()
                colors = merged_transit["color"].tolist()
                merged_transit["color"] = [c if m else grey for c, m in zip(colors, gap_mask)]
                st.metric("Coverage gap tracts", int(sum(gap_mask)))

            elif transit_tool == "Transit Desert Finder" and desert_threshold:
                desert_mask = (merged_transit["nearest_stop_miles"] > desert_threshold).tolist()
                merged_transit = merged_transit.copy()
                colors = merged_transit["color"].tolist()
                merged_transit["color"] = [c if m else grey for c, m in zip(colors, desert_mask)]
                st.metric("Transit desert tracts", int(sum(desert_mask)))

        _transit_cols = [c for c in ["geometry", "color", "display_name", "no_vehicle_rate", "stop_count", "nearest_stop_miles", "total_daily_visits"] if c in merged_transit.columns]
        transit_json = json.loads(merged_transit[_transit_cols].to_json())

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
