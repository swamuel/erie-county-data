import streamlit as st
import pydeck as pdk
import pandas as pd
import json

from lib.config import LAYER_CONFIG, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE, HIGHER_IS_BETTER
from lib.helpers import geocode_address, haversine_miles, haversine_miles_vec, value_to_color, get_benchmark_value, format_value, render_detail_panel


def render(merged, pois, benchmark_row, geography):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]

    svc_col_controls, svc_col_map = st.columns([1, 3])

    with svc_col_controls:
        st.subheader("Community Services")
        st.caption("Food retail: USDA SNAP (March 2026). All other services: OpenStreetMap.")

        svc_view = st.radio("Category", list(LAYER_CONFIG.keys()), horizontal=False, key="svc_view")
        st.markdown("---")
        st.markdown(f"**{svc_view} layers**")

        svc_active_layers = {}
        for subcat, cfg in LAYER_CONFIG[svc_view].items():
            parent_on = st.checkbox(subcat, value=cfg["default_on"], key=f"svc_p_{subcat}")
            if not parent_on:
                continue
            if cfg["subtypes"]:
                selected_subtypes = []
                for sub_label, sub_cfg in cfg["subtypes"].items():
                    sub_on = st.checkbox(f"  \u21b3 {sub_label}", value=sub_cfg["default_on"], key=f"svc_s_{subcat}_{sub_label}")
                    if sub_on:
                        selected_subtypes.append((sub_cfg["value"], sub_cfg["color"]))
                if selected_subtypes:
                    svc_active_layers[subcat] = {"cfg": cfg, "subtypes": selected_subtypes}
            else:
                svc_active_layers[subcat] = {"cfg": cfg, "subtypes": None}

        st.markdown("---")
        svc_show_heatmap = st.checkbox("Show heatmap", value=False, key="svc_heatmap")

        st.markdown("---")
        st.markdown("### What's Near Me?")
        st.caption("Find services within a set distance of any address.")

        svc_address_input = st.text_input("Address", placeholder="e.g. 814 Market St, Meadville, PA",
                                          label_visibility="collapsed", key="svc_address")
        rb1, rb2 = st.columns([2, 1])
        with rb1:
            svc_radius = st.selectbox("Radius", [0.25, 0.5, 1.0, 2.0, 5.0], index=2,
                                      format_func=lambda x: f"{x} mile{'s' if x != 1.0 else ''}",
                                      key="svc_radius")
        with rb2:
            st.markdown("<br/>", unsafe_allow_html=True)
            svc_search_btn = st.button("Search", use_container_width=True, key="svc_search_btn")

        svc_cat_filter = st.multiselect(
            "Limit to categories",
            options=sorted(pois["primary_category"].unique().tolist()),
            default=[], placeholder="All categories", key="svc_cat_filter"
        )

        if svc_search_btn and svc_address_input.strip():
            with st.spinner("Geocoding..."):
                slat, slon, slabel = geocode_address(svc_address_input.strip() + ", PA")
            if slat is None:
                st.error("Address not found. Try including city and state.")
                st.session_state.svc_search_lat = None
                st.session_state.svc_search_results = None
            else:
                st.session_state.svc_search_lat = slat
                st.session_state.svc_search_lon = slon
                st.session_state.svc_search_label = slabel
                nearby = pois.copy()
                nearby["distance_miles"] = haversine_miles_vec(
                    slat, slon, nearby["lat"].values, nearby["lon"].values
                )
                nearby = nearby[nearby["distance_miles"] <= svc_radius].sort_values("distance_miles")
                st.session_state.svc_search_results = nearby
                st.rerun()

        if st.session_state.svc_search_lat:
            svc_results = st.session_state.svc_search_results
            if svc_cat_filter:
                svc_results = svc_results[svc_results["primary_category"].isin(svc_cat_filter)]
            if svc_results is None or len(svc_results) == 0:
                st.info("No services found in that radius.")
            else:
                st.success(f"**{len(svc_results)}** services found")
                cat_counts = (
                    svc_results.groupby(["primary_category", "type"])
                    .size().reset_index(name="Count")
                    .sort_values("Count", ascending=False)
                    .rename(columns={"primary_category": "Category", "type": "Type"})
                )
                with st.expander(f"By category ({len(cat_counts)} types)", expanded=True):
                    st.dataframe(cat_counts, use_container_width=True, hide_index=True)
            if st.button("Clear search", key="svc_clear"):
                st.session_state.svc_search_lat = None
                st.session_state.svc_search_lon = None
                st.session_state.svc_search_label = None
                st.session_state.svc_search_results = None
                st.rerun()

    with svc_col_map:
        svc_layers = []
        svc_visible = []
        svc_point_size = 4

        # Choropleth underlay — poverty rate
        if geography == "Tract" and "poverty_rate" in merged.columns:
            svc_avg = get_benchmark_value(benchmark_row, "poverty_rate")
            svc_merged = merged.assign(
                color=merged["poverty_rate"].apply(
                    lambda x: value_to_color(x, svc_avg, reverse=True)
                )
            )
            svc_geojson = json.loads(svc_merged[["geometry", "color", "display_name", "poverty_rate"]].to_json())
            svc_layers.append(pdk.Layer(
                "GeoJsonLayer", data=svc_geojson,
                get_fill_color="properties.color",
                get_line_color=[120, 120, 120, 40],
                line_width_min_pixels=1, pickable=False,
            ))

        # Build a single combined POI DataFrame — one ScatterplotLayer instead of N
        poi_parts = []
        for subcat, layer_info in svc_active_layers.items():
            cfg = layer_info["cfg"]
            subtypes = layer_info["subtypes"]
            subset = pois[
                (pois["primary_category"] == cfg["primary_category"]) &
                (pois["type"] == cfg["type"])
            ].copy()

            if subtypes:
                for subtype_val, subtype_color in subtypes:
                    sub = subset[subset["subtype"] == subtype_val].copy()
                    if len(sub) == 0:
                        continue
                    sub["fill_color"] = [subtype_color] * len(sub)
                    poi_parts.append(sub)
            else:
                if len(subset) == 0:
                    continue
                subset["fill_color"] = [cfg["color"]] * len(subset)
                poi_parts.append(subset)

        if poi_parts:
            combined = pd.concat(poi_parts, ignore_index=True)
            combined["snap_eligible"] = combined["snap_eligible"].map(
                {True: "\u2713 SNAP/EBT accepted", False: ""}
            ).fillna("")
            poi_display = combined[["name", "address", "lat", "lon", "fill_color", "type", "subtype", "snap_eligible"]]
            svc_visible.append(combined[["lat", "lon"]])
            svc_layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=poi_display,
                get_position=["lon", "lat"],
                get_radius=svc_point_size * 40,
                radius_min_pixels=svc_point_size,
                radius_max_pixels=svc_point_size * 4,
                get_fill_color="fill_color",
                get_line_color=[255, 255, 255, 160],
                line_width_min_pixels=1,
                stroked=True, pickable=True, auto_highlight=True,
            ))

        # Heatmap
        if svc_show_heatmap and svc_visible:
            heat_df = pd.concat(svc_visible).copy()
            heat_df["weight"] = 1
            svc_layers.append(pdk.Layer(
                "HeatmapLayer", data=heat_df,
                get_position=["lon", "lat"],
                get_weight="weight",
                radiusPixels=60, opacity=0.65,
            ))

        # Address search pin
        if st.session_state.svc_search_lat:
            pin_df = pd.DataFrame([{
                "lat": st.session_state.svc_search_lat,
                "lon": st.session_state.svc_search_lon,
            }])
            svc_layers.append(pdk.Layer(
                "ScatterplotLayer", data=pin_df,
                get_position=["lon", "lat"],
                get_radius=200, radius_min_pixels=10, radius_max_pixels=24,
                get_fill_color=[255, 215, 0, 255],
                get_line_color=[0, 0, 0, 255],
                line_width_min_pixels=2, stroked=True, pickable=False,
            ))

        # Color key
        svc_key_items = []
        for subcat, layer_info in svc_active_layers.items():
            if layer_info["subtypes"]:
                for sv, sc in layer_info["subtypes"]:
                    svc_key_items.append((sv, sc))
            else:
                svc_key_items.append((subcat, layer_info["cfg"]["color"]))

        if svc_key_items:
            key_cols = st.columns(min(len(svc_key_items), 4))
            for i, (label, color) in enumerate(svc_key_items):
                r, g, b = color[0], color[1], color[2]
                key_cols[i % 4].markdown(
                    f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:4px'>"
                    f"<div style='width:10px;height:10px;border-radius:50%;"
                    f"background:rgb({r},{g},{b});flex-shrink:0'></div>"
                    f"<span style='font-size:11px'>{label}</span></div>",
                    unsafe_allow_html=True
                )

        total_svc_pts = sum(len(v) for v in svc_visible) if svc_visible else 0
        st.caption(f"**{total_svc_pts}** points visible — {svc_view}")

        svc_view_state = pdk.ViewState(
            latitude=st.session_state.svc_search_lat or VIEW_STATE.latitude,
            longitude=st.session_state.svc_search_lon or VIEW_STATE.longitude,
            zoom=13 if st.session_state.svc_search_lat else VIEW_STATE.zoom,
            pitch=0,
        )

        st.pydeck_chart(pdk.Deck(
            map_style=MAP_STYLE,
            initial_view_state=svc_view_state,
            layers=svc_layers,
            tooltip={
                "html": "<b>{name}</b><br/>{subtype}<br/>{address}<br/>{snap_eligible}",
                "style": TOOLTIP_STYLE,
            },
        ), use_container_width=True, height=600)

        # Results table
        if st.session_state.svc_search_lat and st.session_state.svc_search_results is not None:
            svc_results_display = st.session_state.svc_search_results.copy()
            if svc_cat_filter:
                svc_results_display = svc_results_display[
                    svc_results_display["primary_category"].isin(svc_cat_filter)
                ]
            if len(svc_results_display) > 0:
                st.markdown("---")
                st.markdown("**All results — sorted by distance**")
                all_types = ["All types"] + sorted(svc_results_display["type"].unique().tolist())
                type_filter = st.selectbox("Filter by type", all_types, key="svc_type_filter")
                tbl = svc_results_display[[
                    "name", "primary_category", "type", "subtype", "address", "distance_miles"
                ]].copy()
                tbl["distance_miles"] = tbl["distance_miles"].round(2)
                tbl.columns = ["Name", "Category", "Type", "Subtype", "Address", "Distance (mi)"]
                if type_filter != "All types":
                    tbl = tbl[tbl["Type"] == type_filter]
                st.dataframe(
                    tbl, use_container_width=True, hide_index=True,
                    column_config={"Distance (mi)": st.column_config.NumberColumn(format="%.2f mi")}
                )
