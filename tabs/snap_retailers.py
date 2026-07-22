"""
SNAP Retailers tab — USDA FNS authorized SNAP/EBT retailers, shown by USDA's
own Store Type (no rollups), with simple spatial tools: a merged coverage area,
an address + radius search, and an optional SNAP-participation context layer.
"""

import json

import streamlit as st
import pydeck as pdk
import pandas as pd
import plotly.graph_objects as go

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import geocode_address, haversine_miles_vec, sequential_color
from lib.data_loader import load_boundaries

# Store types that offer little or no fresh/full grocery — a ZIP served only by
# these is flagged as a limited-access area.
LIMITED_TYPES = {"Convenience Store", "Combination Grocery/Other"}

# Distinct color per USDA "Store Type". Colors are just a visual key — no
# grouping or judgement is implied. Unlisted types fall back to gray.
STORE_TYPE_COLORS = {
    "Supermarket":               [27, 158, 119],
    "Super Store":               [17, 122, 101],
    "Large Grocery Store":       [102, 194, 165],
    "Medium Grocery Store":      [65, 174, 118],
    "Small Grocery Store":       [166, 216, 84],
    "Combination Grocery/Other": [230, 171, 2],
    "Convenience Store":         [150, 150, 150],
    "Farmers' Market":           [117, 112, 179],
    "Meat/Poultry Specialty":    [217, 95, 2],
    "Bakery Specialty":          [231, 41, 138],
    "Fruits/Veg Specialty":      [102, 166, 30],
    "Seafood Specialty":         [31, 120, 180],
    "Food Buying Co-op":         [106, 61, 154],
}
MILE_M = 1609.34


def _color_list(store_type):
    return STORE_TYPE_COLORS.get(store_type, [120, 120, 120]) + [220]


@st.cache_data(show_spinner="Building coverage area...")
def _coverage_area_from_points(points: tuple):
    """Union of per-retailer reach buffers (1 mi urban / 10 mi rural) into a
    single coverage polygon, so overlapping urban circles read as one area.
    Buffering is done in UTM 17N (meters) for accurate distances, then
    reprojected to WGS84 for display. Cached on the point set."""
    if not points:
        return None
    import geopandas as gpd
    from shapely.ops import unary_union

    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    g = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lons, lats), crs="EPSG:4326").to_crs(32617)
    buffers = [geom.buffer(MILE_M if urban else MILE_M * 10)
               for geom, (_, _, urban) in zip(g.geometry, points)]
    cov = unary_union(buffers)
    cov_gdf = gpd.GeoDataFrame(geometry=[cov], crs=32617).to_crs("EPSG:4326")
    return json.loads(cov_gdf.to_json())


def _coverage_area(pts):
    points = tuple(zip(pts["lon"].astype(float), pts["lat"].astype(float),
                       pts["is_urban"].astype(bool)))
    return _coverage_area_from_points(points)


def _limited_zctas(snap):
    """ZCTAs whose SNAP retailers are ENTIRELY convenience/combination stores
    (no supermarket, grocery, farmers' market, etc.) — limited food access."""
    df = snap[snap["zcta"].notna() & ~snap["zcta"].astype(str).isin(["nan", "None", ""])]
    limited = []
    for z, g in df.groupby("zcta"):
        types = set(g["store_type_raw"].dropna())
        if types and types <= LIMITED_TYPES:
            limited.append(str(z))
    return limited


def render(merged, snap, benchmark_row, geography):
    # USDA store types present, most common first
    type_counts = snap["store_type_raw"].value_counts()
    all_types = type_counts.index.tolist()

    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        st.subheader("SNAP Retailers")
        st.caption("Stores authorized to accept SNAP/EBT, by USDA Store Type. Source: USDA FNS.")

        selected_types = st.multiselect("USDA store type", options=all_types, default=all_types,
                                        key="snap_types")
        show_coverage = st.checkbox("Show coverage area (1 mi urban / 10 mi rural)",
                                    value=False, key="snap_coverage",
                                    help="Merges the reach around every retailer into one shaded "
                                         "area so coverage gaps stand out (no overlapping circles).")

        shade_by = st.selectbox(
            "Shade areas by",
            ["None", "SNAP participation (ACS)"],
            key="snap_shade",
            help="Color the underlying areas by the share of households receiving SNAP.")

        highlight_limited = st.checkbox(
            "Highlight ZIPs with only convenience/combination stores",
            value=False, key="snap_limited",
            help="Outlines ZIP areas whose only SNAP retailers are convenience "
                 "stores and/or combination grocery — no supermarket or full grocery.")

        st.markdown("---")
        st.markdown("### What's Near an Address?")
        st.caption("Find SNAP retailers within a set distance of any address.")
        address = st.text_input("Address", placeholder="e.g. 814 Market St, Meadville, PA",
                                label_visibility="collapsed", key="svc_address")
        rb1, rb2 = st.columns([2, 1])
        radius = rb1.selectbox("Radius", [0.25, 0.5, 1.0, 2.0, 5.0, 10.0], index=2,
                               format_func=lambda x: f"{x} mile{'s' if x != 1.0 else ''}",
                               key="svc_radius")
        rb2.markdown("<br/>", unsafe_allow_html=True)
        search_btn = rb2.button("Search", use_container_width=True, key="svc_search_btn")

        if search_btn and address.strip():
            with st.spinner("Geocoding..."):
                slat, slon, slabel = geocode_address(address.strip() + ", PA")
            if slat is None:
                st.error("Address not found. Try including city and state.")
                st.session_state.svc_search_lat = None
                st.session_state.svc_search_results = None
            else:
                near = snap.copy()
                near["distance_miles"] = haversine_miles_vec(slat, slon,
                                                             near["lat"].values, near["lon"].values)
                near = near[near["distance_miles"] <= radius].sort_values("distance_miles")
                st.session_state.svc_search_lat = slat
                st.session_state.svc_search_lon = slon
                st.session_state.svc_search_label = slabel
                st.session_state.svc_search_results = near
                st.rerun()

        if st.session_state.svc_search_lat:
            res = st.session_state.svc_search_results
            if selected_types and res is not None:
                res = res[res["store_type_raw"].isin(selected_types)]
            if res is None or len(res) == 0:
                st.info("No SNAP retailers found in that radius.")
            else:
                st.success(f"**{len(res)}** retailers found")
                by_type = (res.groupby("store_type_raw").size().reset_index(name="Count")
                           .sort_values("Count", ascending=False)
                           .rename(columns={"store_type_raw": "Store Type"}))
                st.dataframe(by_type, use_container_width=True, hide_index=True)
            if st.button("Clear search", key="svc_clear"):
                for k in ["svc_search_lat", "svc_search_lon", "svc_search_label", "svc_search_results"]:
                    st.session_state[k] = None
                st.rerun()

    with col_map:
        pts = snap[snap["store_type_raw"].isin(selected_types)].copy() if selected_types else snap.iloc[0:0].copy()
        layers = []
        snap_vmin = snap_vmax = None

        # ── SNAP participation context choropleth ─────────────────────────
        legend_title = legend_sub = None
        if shade_by == "SNAP participation (ACS)" and "snap_participation_rate" in merged.columns:
            valid = merged["snap_participation_rate"].dropna()
            if len(valid) > 1:
                snap_vmin, snap_vmax = float(valid.quantile(0.05)), float(valid.quantile(0.95))
            underlay = merged.assign(
                color=merged["snap_participation_rate"].apply(lambda x: sequential_color(x, snap_vmin, snap_vmax)))
            gj = json.loads(underlay[["geometry", "color", "display_name",
                                      "snap_participation_rate"]].to_json())
            layers.append(pdk.Layer("GeoJsonLayer", data=gj,
                                    get_fill_color="properties.color",
                                    get_line_color=[120, 120, 120, 40],
                                    line_width_min_pixels=1, pickable=False))
            legend_title = "SNAP participation — share of households receiving SNAP"
            legend_sub = "Darker = more households on SNAP · Source: ACS B19058"

        # ── Highlight ZIPs served only by convenience/combination stores ──
        n_limited = 0
        if highlight_limited:
            limited = _limited_zctas(snap)
            n_limited = len(limited)
            if limited:
                _, _, gdf_z = load_boundaries()
                hl = gdf_z[gdf_z["ZCTA5CE20"].isin(limited)]
                if len(hl):
                    gj = json.loads(hl[["ZCTA5CE20", "geometry"]].to_json())
                    layers.append(pdk.Layer(
                        "GeoJsonLayer", data=gj,
                        get_fill_color=[234, 88, 12, 70],
                        get_line_color=[194, 65, 12, 220],
                        line_width_min_pixels=2, stroked=True, filled=True, pickable=False))

        # ── Coverage area (merged buffers, so urban overlap is readable) ───
        if show_coverage and len(pts):
            coverage_json = _coverage_area(pts)
            if coverage_json is not None:
                layers.append(pdk.Layer(
                    "GeoJsonLayer", data=coverage_json,
                    get_fill_color=[59, 130, 246, 55],
                    get_line_color=[37, 99, 235, 140],
                    line_width_min_pixels=1, stroked=True, filled=True, pickable=False))

        # ── Retailer points ───────────────────────────────────────────────
        # Pass ONLY plain-typed columns pydeck can serialize (no numpy bool/GEOID).
        if len(pts):
            point_df = pd.DataFrame({
                "name": pts["name"].astype(str),
                "address": pts["address"].astype(str),
                "store_type": pts["store_type_raw"].astype(str),
                "auth": pts["authorization_date"].fillna("").astype(str),
                "lat": pts["lat"].astype(float),
                "lon": pts["lon"].astype(float),
            })
            point_df["fill_color"] = pts["store_type_raw"].apply(_color_list).tolist()
            layers.append(pdk.Layer(
                "ScatterplotLayer", data=point_df.to_dict("records"),
                get_position=["lon", "lat"], get_radius=160,
                radius_min_pixels=3, radius_max_pixels=14,
                get_fill_color="fill_color", get_line_color=[255, 255, 255, 160],
                line_width_min_pixels=1, stroked=True, pickable=True, auto_highlight=True))

        # ── Address pin ───────────────────────────────────────────────────
        if st.session_state.svc_search_lat:
            pin = [{"lat": float(st.session_state.svc_search_lat),
                    "lon": float(st.session_state.svc_search_lon)}]
            layers.append(pdk.Layer("ScatterplotLayer", data=pin,
                                    get_position=["lon", "lat"], get_radius=200,
                                    radius_min_pixels=10, radius_max_pixels=24,
                                    get_fill_color=[255, 215, 0, 255],
                                    get_line_color=[0, 0, 0, 255],
                                    line_width_min_pixels=2, stroked=True, pickable=False))

        # legend — every USDA store type currently shown, wrapped inline
        shown_types = [t for t in all_types if t in set(pts["store_type_raw"])] if len(pts) else []
        if shown_types:
            chips = "".join(
                f"<div style='display:flex;align-items:center;gap:5px;margin:2px 10px 2px 0'>"
                f"<div style='width:10px;height:10px;border-radius:50%;"
                f"background:rgb({STORE_TYPE_COLORS.get(t, [120,120,120])[0]},"
                f"{STORE_TYPE_COLORS.get(t, [120,120,120])[1]},"
                f"{STORE_TYPE_COLORS.get(t, [120,120,120])[2]})'></div>"
                f"<span style='font-size:11px'>{t}</span></div>"
                for t in shown_types)
            st.markdown(f"<div style='display:flex;flex-wrap:wrap;align-items:center'>{chips}</div>",
                        unsafe_allow_html=True)

        st.caption(f"**{len(pts)}** retailers shown")
        view = pdk.ViewState(
            latitude=st.session_state.svc_search_lat or VIEW_STATE.latitude,
            longitude=st.session_state.svc_search_lon or VIEW_STATE.longitude,
            zoom=12 if st.session_state.svc_search_lat else VIEW_STATE.zoom, pitch=0)
        st.pydeck_chart(pdk.Deck(
            map_style=MAP_STYLE, initial_view_state=view, layers=layers,
            tooltip={"html": "<b>{name}</b><br/>{store_type}<br/>{address}<br/>Authorized: {auth}",
                     "style": TOOLTIP_STYLE}), use_container_width=True, height=600)

        if legend_title and snap_vmin is not None:
            st.markdown(
                f"<div style='margin-top:8px;padding:10px 14px;border:1px solid rgba(120,120,140,0.3);"
                f"border-radius:8px;background:rgba(120,130,160,0.07)'>"
                f"<div style='font-size:14px;font-weight:600;margin-bottom:8px;color:#334155'>"
                f"{legend_title}</div>"
                f"<div style='display:flex;align-items:center;gap:12px;font-size:13px;color:#475569'>"
                f"<span style='font-variant-numeric:tabular-nums'>{snap_vmin:.0f}%</span>"
                f"<div style='flex:1;height:18px;border-radius:5px;"
                f"background:linear-gradient(to right,rgb(236,242,250),rgb(39,58,120))'></div>"
                f"<span style='font-variant-numeric:tabular-nums'>{snap_vmax:.0f}%</span></div>"
                f"<div style='font-size:11px;color:#94a3b8;margin-top:5px'>{legend_sub}</div>"
                f"</div>",
                unsafe_allow_html=True)
        if show_coverage:
            st.caption("Shaded area = within 1 mile (urban) / 10 miles (rural) of a shown retailer. "
                       "Unshaded = a coverage gap.")
        if highlight_limited:
            if n_limited:
                st.markdown(
                    f"<div style='margin-top:8px;padding:8px 12px;border:1px solid rgba(194,65,12,0.4);"
                    f"border-radius:8px;background:rgba(234,88,12,0.10);font-size:13px;color:#9a3412'>"
                    f"<b>{n_limited}</b> ZIP area{'s' if n_limited != 1 else ''} (outlined in orange) "
                    f"have <b>only</b> convenience and/or combination stores for SNAP — "
                    f"no supermarket or full grocery.</div>", unsafe_allow_html=True)
            else:
                st.caption("No ZIP areas are served exclusively by convenience/combination stores.")

        # ── Retailer mix bar chart ────────────────────────────────────────
        if len(pts):
            counts = pts["store_type_raw"].value_counts()
            total = int(counts.sum())
            order = counts.index.tolist()[::-1]  # largest on top
            colors = ["rgb({},{},{})".format(*STORE_TYPE_COLORS.get(t, [120, 120, 120])) for t in order]
            fig = go.Figure(go.Bar(
                x=[int(counts[t]) for t in order], y=order, orientation="h",
                marker_color=colors,
                text=[f"{int(counts[t])} ({counts[t] / total * 100:.0f}%)" for t in order],
                textposition="auto",
                hovertemplate="%{y}: %{x} retailers<extra></extra>"))
            fig.update_layout(
                title=dict(text=f"Retailer mix — {total} retailers shown", font=dict(size=14)),
                height=max(220, 26 * len(order) + 70),
                margin=dict(t=40, b=20, l=10, r=20),
                xaxis=dict(title="Number of SNAP retailers", gridcolor="rgba(200,200,200,0.15)"),
                yaxis=dict(automargin=True),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # results table
        if st.session_state.svc_search_lat and st.session_state.svc_search_results is not None:
            res = st.session_state.svc_search_results.copy()
            if selected_types:
                res = res[res["store_type_raw"].isin(selected_types)]
            if len(res):
                st.markdown("---")
                st.markdown("**All results — sorted by distance**")
                tbl = res[["name", "store_type_raw", "address", "distance_miles"]].copy()
                tbl["distance_miles"] = tbl["distance_miles"].round(2)
                tbl.columns = ["Name", "Store Type", "Address", "Distance (mi)"]
                st.dataframe(tbl, use_container_width=True, hide_index=True,
                             column_config={"Distance (mi)": st.column_config.NumberColumn(format="%.2f mi")})
