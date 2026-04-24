"""
tabs/desert_analysis.py
Desert Analysis tab — custom threshold-based desert builder at ZCTA level.
Self-contained, not affected by sidebar year/geography/benchmark controls.
Requires data/processed/zcta_access_stats.csv (run generate_zcta_access_stats.py).
"""
import streamlit as st
import pydeck as pdk
import pandas as pd
import json
import numpy as np

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.service_overlays import build_service_layers
from lib.pdf_export import build_desert_analysis_pdf

# ── Slider definitions ────────────────────────────────────────────────────────

DISTANCE_SLIDERS = [
    ("nearest_pantry_miles",   "Nearest food pantry (miles)",        "gt"),
    ("nearest_snap_miles",     "Nearest SNAP-eligible store (miles)", "gt"),
    ("nearest_grocery_miles",  "Nearest full-service grocery (miles)","gt"),
    ("nearest_clinic_miles",   "Nearest clinic (miles)",             "gt"),
    ("nearest_hospital_miles", "Nearest hospital (miles)",           "gt"),
    ("nearest_pharmacy_miles", "Nearest pharmacy (miles)",           "gt"),
]

RATE_SLIDERS = [
    ("no_vehicle_rate",    "No vehicle rate (%)",  "gt"),
    ("poverty_rate",       "Poverty rate (%)",     "gt"),
    ("no_insurance_rate",  "Uninsured rate (%)",   "gt"),
]

INCOME_SLIDERS = [
    ("median_household_income", "Median household income ($)", "lt"),
]

ALL_SLIDERS = DISTANCE_SLIDERS + RATE_SLIDERS + INCOME_SLIDERS

PRESETS = {
    "Food Access Desert": {
        "nearest_pantry_miles":  {"enabled": True,  "value": 3.0},
        "nearest_snap_miles":    {"enabled": True,  "value": 2.0},
        "no_vehicle_rate":       {"enabled": True,  "value": 15.0},
    },
    "Transportation Desert": {
        "no_vehicle_rate":       {"enabled": True,  "value": 20.0},
        "nearest_pantry_miles":  {"enabled": True,  "value": 5.0},
    },
    "Health Access Desert": {
        "nearest_hospital_miles":{"enabled": True,  "value": 10.0},
        "nearest_clinic_miles":  {"enabled": True,  "value": 5.0},
        "no_insurance_rate":     {"enabled": True,  "value": 15.0},
    },
    "Combined Hardship": {
        "poverty_rate":           {"enabled": True,  "value": 20.0},
        "nearest_grocery_miles":  {"enabled": True,  "value": 3.0},
        "nearest_clinic_miles":   {"enabled": True,  "value": 5.0},
    },
}

# Terracotta for flagged ZCTAs, dimmed gray for non-flagged
COLOR_FLAGGED     = [188, 74, 60, 220]
COLOR_NOT_FLAGGED = [200, 200, 200, 80]


def _sk(col, suffix):
    return f"da_{col}_{suffix}"


def _apply_preset(preset_name, all_cols):
    p = PRESETS[preset_name]
    for col, _, _ in ALL_SLIDERS:
        if col not in all_cols:
            continue
        if col in p:
            st.session_state[_sk(col, "enabled")] = p[col]["enabled"]
            st.session_state[_sk(col, "value")]   = float(p[col]["value"])
        else:
            st.session_state[_sk(col, "enabled")] = False


def _flag_zctas(df, enabled_sliders, logic):
    """Return boolean Series: True if ZCTA meets the desert condition."""
    if not enabled_sliders:
        return pd.Series(False, index=df.index)

    masks = []
    for col, direction, val in enabled_sliders:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if direction == "gt":
            masks.append(s > val)
        else:  # "lt"
            masks.append(s < val)

    if not masks:
        return pd.Series(False, index=df.index)

    combined = masks[0]
    for m in masks[1:]:
        if logic == "AND":
            combined = combined & m
        else:
            combined = combined | m
    return combined.fillna(False)


def render(zcta_access_stats, gdf_zctas,
           pantry_locations=None, pois=None, transit_stops=None):
    """
    zcta_access_stats : DataFrame from zcta_access_stats.csv (or None)
    gdf_zctas         : GeoDataFrame with ZCTA boundaries
    pantry_locations  : DataFrame from pantry_locations.csv (optional overlay)
    pois              : DataFrame from erie_pois.csv (optional overlay)
    transit_stops     : DataFrame from emta_stops.csv (optional overlay)
    """

    st.subheader("Desert Analysis")
    st.caption(
        "Flag ZIP code areas (ZCTAs) that meet custom access thresholds. "
        "Uses zcta_access_stats.csv — run generate_zcta_access_stats.py first."
    )

    if zcta_access_stats is None or len(zcta_access_stats) == 0:
        st.error(
            "zcta_access_stats.csv not found or empty. "
            "Run `python generate_zcta_access_stats.py` then `python process_agency_list.py` first."
        )
        return

    df = zcta_access_stats.copy()
    df["ZCTA5CE20"] = df["ZCTA5CE20"].astype(str).str.zfill(5)

    # ── Column availability ───────────────────────────────────
    all_cols = set(df.columns)

    # ── Session state init ────────────────────────────────────
    for col, _, _ in ALL_SLIDERS:
        if col not in all_cols:
            continue
        if _sk(col, "enabled") not in st.session_state:
            st.session_state[_sk(col, "enabled")] = False
        if _sk(col, "value") not in st.session_state:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            mid = float(series.median()) if len(series) > 0 else 0.0
            st.session_state[_sk(col, "value")] = mid

    if "da_logic" not in st.session_state:
        st.session_state["da_logic"] = "AND"

    # ── Top controls row ──────────────────────────────────────
    top_left, top_right = st.columns([2, 1])

    with top_left:
        st.markdown("**Quick Presets**")
        pcols = st.columns(4)
        preset_names = list(PRESETS.keys())
        for i, pname in enumerate(preset_names):
            if pcols[i].button(pname, key=f"da_preset_{i}", use_container_width=True):
                _apply_preset(pname, all_cols)

    with top_right:
        st.markdown("**Logic**")
        logic = st.radio(
            "A ZCTA is flagged when it meets:",
            ["AND", "OR"],
            key="da_logic",
            horizontal=True,
            help="AND = must meet ALL enabled thresholds. OR = meets ANY threshold.",
        )

    # ── County filter ─────────────────────────────────────────
    if "county_name" in df.columns:
        county_options = sorted(df["county_name"].dropna().unique().tolist())
    else:
        county_options = []

    if county_options:
        selected_counties = st.multiselect(
            "County filter",
            options=county_options,
            default=county_options,
            key="da_county_filter",
        )
        if selected_counties:
            df_filtered = df[df["county_name"].isin(selected_counties)]
        else:
            df_filtered = df.copy()
    else:
        df_filtered = df.copy()

    # ── Threshold sliders ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Threshold Sliders")
    st.caption("Enable a checkbox to include that threshold in the desert definition.")

    def render_slider_group(label, slider_defs):
        st.markdown(f"**{label}**")
        for col, display_label, direction in slider_defs:
            if col not in all_cols:
                st.caption(f"_{display_label} — data not available_")
                continue

            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) == 0:
                st.caption(f"_{display_label} — no data_")
                continue

            col_min = float(series.min())
            col_max = float(series.max())
            if col_min == col_max:
                st.caption(f"_{display_label} — constant value {col_min}_")
                continue

            # Clamp stored value to current data range
            stored = st.session_state.get(_sk(col, "value"), float(series.median()))
            stored = max(col_min, min(col_max, stored))

            row = st.columns([0.08, 0.92])
            enabled = row[0].checkbox(
                "", key=_sk(col, "enabled"), label_visibility="collapsed"
            )

            direction_label = ">" if direction == "gt" else "<"
            thresh = row[1].slider(
                f"{display_label}  (flag if {direction_label} threshold)",
                min_value=col_min,
                max_value=col_max,
                value=stored,
                key=_sk(col, "value"),
                disabled=not enabled,
                format="%.1f",
            )

    scol1, scol2 = st.columns(2)
    with scol1:
        render_slider_group("Distance Thresholds (flag if > miles)", DISTANCE_SLIDERS)
    with scol2:
        render_slider_group("Rate Thresholds (flag if > %)", RATE_SLIDERS)
        render_slider_group("Income Threshold (flag if < $)", INCOME_SLIDERS)

    # ── Collect enabled sliders ───────────────────────────────
    enabled_sliders = []
    for col, _, direction in ALL_SLIDERS:
        if col not in all_cols:
            continue
        if st.session_state.get(_sk(col, "enabled"), False):
            val = st.session_state.get(_sk(col, "value"), 0.0)
            enabled_sliders.append((col, direction, val))

    # ── Flag ZCTAs ────────────────────────────────────────────
    df_filtered = df_filtered.copy()
    df_filtered["flagged"] = _flag_zctas(df_filtered, enabled_sliders, logic)

    n_flagged    = int(df_filtered["flagged"].sum())
    n_counties_flagged = 0
    total_pop_flagged  = 0

    if "county_name" in df_filtered.columns:
        n_counties_flagged = int(
            df_filtered.loc[df_filtered["flagged"], "county_name"].nunique()
        )
    if "total_population" in df_filtered.columns:
        pop_series = pd.to_numeric(
            df_filtered.loc[df_filtered["flagged"], "total_population"], errors="coerce"
        )
        total_pop_flagged = int(pop_series.sum())

    # ── Summary metrics ───────────────────────────────────────
    st.markdown("---")
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Flagged ZCTAs",                  f"{n_flagged:,}")
    sm2.metric("Est. population in flagged ZCTAs", f"{total_pop_flagged:,}")
    sm3.metric("Counties with flagged ZCTAs",    f"{n_counties_flagged}")

    if not enabled_sliders:
        st.info("Enable at least one threshold slider to begin flagging ZCTAs.")

    # ── Service overlay toggles ───────────────────────────────
    st.markdown("---")
    with st.expander("Service overlays — show actual locations on the map"):
        ocol1, ocol2, ocol3 = st.columns(3)
        with ocol1:
            st.markdown("**Food**")
            show_pantries = st.checkbox("Food pantries",      key="da_show_pantries")
            show_snap     = st.checkbox("SNAP-eligible stores", key="da_show_snap")
        with ocol2:
            st.markdown("**Health**")
            show_hospitals  = st.checkbox("Hospitals",  key="da_show_hospitals")
            show_clinics    = st.checkbox("Clinics",    key="da_show_clinics")
            show_pharmacies = st.checkbox("Pharmacies", key="da_show_pharmacies")
        with ocol3:
            st.markdown("**Civic & Transit**")
            show_libraries    = st.checkbox("Libraries",         key="da_show_libraries")
            show_comm_centers = st.checkbox("Community centers", key="da_show_comm_centers")
            show_social_svc   = st.checkbox("Social services",   key="da_show_social_svc")
            show_transit      = st.checkbox("Transit stops",     key="da_show_transit")

    overlay_enabled = {
        "pantries":     show_pantries,
        "snap":         show_snap,
        "hospitals":    show_hospitals,
        "clinics":      show_clinics,
        "pharmacies":   show_pharmacies,
        "libraries":    show_libraries,
        "comm_centers": show_comm_centers,
        "social_svc":   show_social_svc,
        "transit":      show_transit,
    }

    # ── Map ───────────────────────────────────────────────────
    # Merge flag into geometry
    if gdf_zctas is not None and len(gdf_zctas) > 0:
        gdf_map = gdf_zctas.merge(
            df_filtered[["ZCTA5CE20", "flagged"]
                + (["area_name"] if "area_name" in df_filtered.columns else [])
                + (["county_name"] if "county_name" in df_filtered.columns else [])
                + [c for c, _, _ in enabled_sliders if c in df_filtered.columns]
            ],
            on="ZCTA5CE20", how="inner",
        )
        gdf_map["color"] = gdf_map["flagged"].map(
            {True: COLOR_FLAGGED, False: COLOR_NOT_FLAGGED}
        )

        # Build tooltip showing active threshold values
        thresh_tooltip = "".join([
            f"<br/>{col}: {{{col}}}"
            for col, _, _ in enabled_sliders
            if col in gdf_map.columns
        ])
        tooltip_html = (
            "<b>{area_name}</b> ({ZCTA5CE20})<br/>"
            "{county_name}"
            + thresh_tooltip
        )

        geojson_data = json.loads(gdf_map.to_json())

        map_layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson_data,
            get_fill_color="properties.color",
            get_line_color=[255, 255, 255, 40],
            line_width_min_pixels=1,
            pickable=True,
        )

        overlay_layers = build_service_layers(
            enabled=overlay_enabled,
            pantry_locations=pantry_locations,
            pois=pois,
            transit_stops=transit_stops,
        )

        st.pydeck_chart(pdk.Deck(
            layers=[map_layer, *overlay_layers],
            initial_view_state=VIEW_STATE,
            tooltip={"html": tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE,
        ), height=520)
    else:
        st.warning("ZCTA boundary data not available for map rendering.")

    # ── Results table ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Flagged ZCTAs")

    if n_flagged == 0:
        st.info("No ZCTAs currently meet the active thresholds.")
        return

    # Build display table
    flagged_df = df_filtered[df_filtered["flagged"]].copy()

    display_cols = ["ZCTA5CE20"]
    if "area_name" in flagged_df.columns:
        display_cols.append("area_name")
    if "county_name" in flagged_df.columns:
        display_cols.append("county_name")

    for col, label, direction in ALL_SLIDERS:
        if col in enabled_sliders_cols(enabled_sliders) and col in flagged_df.columns:
            display_cols.append(col)
            threshold = next(v for c, _, v in enabled_sliders if c == col)
            numeric_col = pd.to_numeric(flagged_df[col], errors="coerce")
            meets = (numeric_col > threshold) if direction == "gt" else (numeric_col < threshold)
            flagged_df[f"_{col}_meets"] = meets.map({True: "Yes", False: "No"}).fillna("—")
            display_cols.append(f"_{col}_meets")

    # Round numeric columns and clean types for Arrow serialization
    for col in display_cols:
        if col not in flagged_df.columns:
            continue
        if pd.api.types.is_float_dtype(flagged_df[col]):
            flagged_df[col] = flagged_df[col].round(2)
        elif flagged_df[col].dtype == object:
            flagged_df[col] = flagged_df[col].fillna("—").astype(str)

    final_display = flagged_df[[c for c in display_cols if c in flagged_df.columns]].reset_index(drop=True)
    rename_map = {
        "ZCTA5CE20":  "ZIP Code",
        "area_name":  "Area",
        "county_name":"County",
    }
    for col, label, _ in ALL_SLIDERS:
        rename_map[col] = label
        rename_map[f"_{col}_meets"] = f"Meets? ({label})"

    final_display = final_display.rename(columns=rename_map)

    st.dataframe(final_display, use_container_width=True, hide_index=True)

    # ── Download buttons ──────────────────────────────────────
    label_by_col = {col: label for col, label, _ in ALL_SLIDERS}
    enabled_slider_details = [
        {
            "col": col,
            "label": label_by_col.get(col, col),
            "direction": direction,
            "threshold": val,
        }
        for col, direction, val in enabled_sliders
    ]

    dcol1, dcol2 = st.columns(2)
    csv_bytes = final_display.to_csv(index=False).encode("utf-8")
    dcol1.download_button(
        label=f"Download flagged ZCTAs ({n_flagged}) as CSV",
        data=csv_bytes,
        file_name="desert_analysis_flagged_zctas.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with dcol2:
        if st.button(
            f"Build PDF report ({n_flagged} ZCTAs)",
            key="da_build_pdf",
            use_container_width=True,
        ):
            with st.spinner("Building PDF..."):
                try:
                    pdf_bytes = build_desert_analysis_pdf(
                        flagged_df=final_display,
                        df_filtered=df_filtered,
                        gdf_zctas=gdf_zctas,
                        enabled_slider_details=enabled_slider_details,
                        logic=logic,
                        summary={
                            "n_flagged": n_flagged,
                            "total_pop_flagged": total_pop_flagged,
                            "n_counties": n_counties_flagged,
                        },
                    )
                    st.session_state["da_pdf_bytes"] = pdf_bytes
                except Exception as e:
                    st.error(f"Failed to build PDF: {e}")

        if st.session_state.get("da_pdf_bytes"):
            st.download_button(
                label="Download PDF report",
                data=st.session_state["da_pdf_bytes"],
                file_name="desert_analysis_report.pdf",
                mime="application/pdf",
                key="da_pdf_download",
                use_container_width=True,
            )


def enabled_sliders_cols(enabled_sliders):
    return {col for col, _, _ in enabled_sliders}
