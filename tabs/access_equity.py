"""
tabs/access_equity.py
Access & Equity tab — self-contained, not affected by sidebar year/geography/benchmark.
Renders a two-column layout: left controls panel, right pydeck choropleth + overlay map.
"""
import streamlit as st
import pydeck as pdk
import pandas as pd
import json
import numpy as np

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import value_to_color
from lib.constants import COUNTY_NAMES, FIPS_TO_NAME
from lib.service_overlays import PROGRAM_TYPE_COLORS, build_service_layers

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_LAYER_OPTIONS = [
    "Food Insecurity Rate",
    "No Vehicle Rate",
    "Poverty Rate",
    "Uninsured Rate",
    "Median Household Income",
    "Poor Physical Health Rate",
    "Poor Mental Health Rate",
    "Unemployment Rate",
    "Disability Rate",
    "Obesity Rate",
    "Diabetes Rate",
]

BASE_LAYER_COLS = {
    "Food Insecurity Rate":    "food_insecurity_rate",
    "No Vehicle Rate":         "no_vehicle_rate",
    "Poverty Rate":            "poverty_rate",
    "Uninsured Rate":          "no_insurance_rate",
    "Median Household Income": "median_household_income",
    "Poor Physical Health Rate": "poor_physical_health_rate",
    "Poor Mental Health Rate": "poor_mental_health_rate",
    "Unemployment Rate":       "unemployment_rate",
    "Disability Rate":         "disability_rate",
    "Obesity Rate":            "obesity_rate",
    "Diabetes Rate":           "diabetes_rate",
}

# Income is higher-is-better (reverse=False in value_to_color)
HIGHER_IS_BETTER_AE = {"median_household_income"}

PRESETS = {
    "Food Access": {
        "base": "Food Insecurity Rate",
        "overlays": {
            "show_pantries": True,
            "show_food_desert_1mi": True,
            "show_food_desert_vehicle": False,
            "show_snap": True,
            "show_hospitals": False,
            "show_clinics": False,
            "show_pharmacies": False,
            "show_libraries": False,
            "show_community_centers": False,
            "show_social_services": False,
            "show_transit": False,
        },
    },
    "Transportation Gap": {
        "base": "No Vehicle Rate",
        "overlays": {
            "show_pantries": True,
            "show_food_desert_1mi": False,
            "show_food_desert_vehicle": True,
            "show_snap": False,
            "show_hospitals": False,
            "show_clinics": False,
            "show_pharmacies": False,
            "show_libraries": False,
            "show_community_centers": False,
            "show_social_services": False,
            "show_transit": True,
        },
    },
    "Health Access": {
        "base": "Uninsured Rate",
        "overlays": {
            "show_pantries": False,
            "show_food_desert_1mi": False,
            "show_food_desert_vehicle": False,
            "show_snap": False,
            "show_hospitals": True,
            "show_clinics": True,
            "show_pharmacies": True,
            "show_libraries": False,
            "show_community_centers": False,
            "show_social_services": False,
            "show_transit": False,
        },
    },
    "Income & Services": {
        "base": "Poverty Rate",
        "overlays": {
            "show_pantries": True,
            "show_food_desert_1mi": False,
            "show_food_desert_vehicle": False,
            "show_snap": False,
            "show_hospitals": False,
            "show_clinics": False,
            "show_pharmacies": False,
            "show_libraries": False,
            "show_community_centers": True,
            "show_social_services": True,
            "show_transit": False,
        },
    },
}

OVERLAY_DEFAULTS = {k: False for k in list(PRESETS["Food Access"]["overlays"].keys())}
OVERLAY_DEFAULTS["show_pantries"] = True
OVERLAY_DEFAULTS["show_food_desert_1mi"] = True
OVERLAY_DEFAULTS["show_snap"] = True


def _apply_preset(preset_name):
    p = PRESETS[preset_name]
    st.session_state["ae_base_layer"] = p["base"]
    for k, v in p["overlays"].items():
        st.session_state[f"ae_{k}"] = v


def _get_county_from_merged(merged):
    """Return a county name column from merged tract GeoDataFrame."""
    if "GEOID" in merged.columns:
        fips = merged["GEOID"].astype(str).str[2:5]
        return fips.map(FIPS_TO_NAME).str.replace(" County", "", regex=False)
    if "COUNTYFP" in merged.columns:
        return merged["COUNTYFP"].astype(str).map(FIPS_TO_NAME).str.replace(" County", "", regex=False)
    return None


def render(merged_tract_2023, pantry_locations, pois, transit_stops):
    """
    merged_tract_2023 : GeoDataFrame from build_merged_tract(2023)
    pantry_locations  : DataFrame from pantry_locations.csv (or None)
    pois              : DataFrame from erie_pois.csv
    transit_stops     : DataFrame from emta_stops.csv
    """

    # ── Session state defaults ────────────────────────────────
    if "ae_base_layer" not in st.session_state:
        st.session_state["ae_base_layer"] = "Food Insecurity Rate"
    for k, v in OVERLAY_DEFAULTS.items():
        if f"ae_{k}" not in st.session_state:
            st.session_state[f"ae_{k}"] = v

    # ── Derive county per tract ───────────────────────────────
    merged = merged_tract_2023.copy()
    county_col = _get_county_from_merged(merged)
    if county_col is not None:
        merged["_ae_county"] = county_col
        short_names = sorted(merged["_ae_county"].dropna().unique().tolist())
    else:
        short_names = [n.replace(" County", "") for n in COUNTY_NAMES]

    # ── Layout ────────────────────────────────────────────────
    col_ctrl, col_map = st.columns([1, 3])

    with col_ctrl:
        st.subheader("Access & Equity")
        st.caption("Self-contained view — not affected by sidebar controls.")

        # ── Preset buttons ────────────────────────────────────
        st.markdown("**Quick Presets**")
        pcols = st.columns(2)
        if pcols[0].button("Food Access",       use_container_width=True, key="ae_preset_1"):
            _apply_preset("Food Access")
        if pcols[1].button("Transport Gap",     use_container_width=True, key="ae_preset_2"):
            _apply_preset("Transportation Gap")
        if pcols[0].button("Health Access",     use_container_width=True, key="ae_preset_3"):
            _apply_preset("Health Access")
        if pcols[1].button("Income & Services", use_container_width=True, key="ae_preset_4"):
            _apply_preset("Income & Services")

        st.markdown("---")

        # ── Base choropleth ───────────────────────────────────
        st.markdown("**Base Layer**")
        available_options = [
            opt for opt in BASE_LAYER_OPTIONS
            if BASE_LAYER_COLS[opt] in merged.columns
        ]
        if st.session_state["ae_base_layer"] not in available_options and available_options:
            st.session_state["ae_base_layer"] = available_options[0]

        base_layer = st.selectbox(
            "Choropleth variable",
            options=available_options,
            key="ae_base_layer",
            label_visibility="collapsed",
        )

        st.markdown("---")

        # ── County filter ─────────────────────────────────────
        st.markdown("**County Filter**")
        selected_counties = st.multiselect(
            "Counties",
            options=short_names,
            default=short_names,
            key="ae_county_filter",
            label_visibility="collapsed",
        )

        st.markdown("---")

        # ── Overlay toggles ───────────────────────────────────
        st.markdown("**Food & Pantry Overlays**")
        show_pantries      = st.checkbox("Food pantry locations",             key="ae_show_pantries")
        show_snap          = st.checkbox("SNAP-eligible stores",              key="ae_show_snap")
        show_fd_1mi        = st.checkbox("Food deserts (1mi/10mi outline)",   key="ae_show_food_desert_1mi")
        show_fd_vehicle    = st.checkbox("Food deserts (vehicle, outline)",   key="ae_show_food_desert_vehicle")

        st.markdown("**Health Overlays**")
        show_hospitals     = st.checkbox("Hospitals",  key="ae_show_hospitals")
        show_clinics       = st.checkbox("Clinics",    key="ae_show_clinics")
        show_pharmacies    = st.checkbox("Pharmacies", key="ae_show_pharmacies")

        st.markdown("**Civic Overlays**")
        show_libraries     = st.checkbox("Libraries",          key="ae_show_libraries")
        show_comm_centers  = st.checkbox("Community centers",  key="ae_show_community_centers")
        show_social_svc    = st.checkbox("Social services",    key="ae_show_social_services")
        show_transit       = st.checkbox("Transit stops",      key="ae_show_transit")

    # ── Map column ────────────────────────────────────────────
    with col_map:
        col_var = BASE_LAYER_COLS.get(base_layer)

        # Apply county filter to tracts
        if county_col is not None and selected_counties and len(selected_counties) < len(short_names):
            display_merged = merged[merged["_ae_county"].isin(selected_counties)]
        else:
            display_merged = merged

        layers = []

        # ── Choropleth base layer ─────────────────────────────
        if col_var and col_var in display_merged.columns:
            reverse = col_var not in HIGHER_IS_BETTER_AE
            region_avg = display_merged[col_var].median()
            if pd.isna(region_avg):
                region_avg = display_merged[col_var].mean()

            choro = display_merged.copy()
            choro["color"] = choro[col_var].apply(
                lambda x: value_to_color(x, region_avg, reverse=reverse)
            )

            # Format tooltip value
            if col_var == "median_household_income":
                choro["_val_fmt"] = choro[col_var].apply(
                    lambda x: f"${x:,.0f}" if pd.notna(x) else "No data"
                )
                tooltip_val = "{_val_fmt}"
            else:
                choro["_val_fmt"] = choro[col_var].apply(
                    lambda x: f"{x:.1f}%" if pd.notna(x) else "No data"
                )
                tooltip_val = "{_val_fmt}"

            keep_cols = [c for c in ["geometry", "color", "display_name", "_val_fmt"] if c in choro.columns]
            choro_json = json.loads(choro[keep_cols].to_json())

            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=choro_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True,
            ))
        else:
            tooltip_val = ""
            st.warning(f"Column '{col_var}' not available in tract data for year 2023.")

        # ── Food desert outline layers ────────────────────────
        if show_fd_1mi and "food_desert_1_10" in display_merged.columns:
            desert_tracts = display_merged[display_merged["food_desert_1_10"] == 1]
            if len(desert_tracts) > 0:
                d_json = json.loads(desert_tracts[["geometry"]].to_json())
                layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data=d_json,
                    get_fill_color=[0, 0, 0, 0],
                    get_line_color=[255, 140, 0, 255],
                    line_width_min_pixels=3,
                    pickable=False,
                ))

        if show_fd_vehicle and "food_desert_vehicle" in display_merged.columns:
            veh_tracts = display_merged[display_merged["food_desert_vehicle"] == 1]
            if len(veh_tracts) > 0:
                v_json = json.loads(veh_tracts[["geometry"]].to_json())
                layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data=v_json,
                    get_fill_color=[0, 0, 0, 0],
                    get_line_color=[139, 92, 246, 255],
                    line_width_min_pixels=3,
                    pickable=False,
                ))

        # ── POI scatter layers ────────────────────────────────
        layers.extend(build_service_layers(
            enabled={
                "pantries":     show_pantries,
                "snap":         show_snap,
                "hospitals":    show_hospitals,
                "clinics":      show_clinics,
                "pharmacies":   show_pharmacies,
                "libraries":    show_libraries,
                "comm_centers": show_comm_centers,
                "social_svc":   show_social_svc,
                "transit":      show_transit,
            },
            pantry_locations=pantry_locations,
            pois=pois,
            transit_stops=transit_stops,
        ))

        # ── Tooltip ───────────────────────────────────────────
        tooltip_html = (
            "<b>{display_name}</b><br/>"
            f"{base_layer}: {tooltip_val}<br/>"
            "<b>{agency_name}</b> {program_type}<br/>"
            "{county} — {address}"
        )

        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=VIEW_STATE,
            tooltip={"html": tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE,
        ), height=580)

    # ── Summary metrics (below map) ───────────────────────────
    st.markdown("---")
    if col_var and col_var in display_merged.columns:
        vals = display_merged[col_var].dropna()
        if len(vals) > 0:
            m1, m2, m3, m4 = st.columns(4)
            if col_var == "median_household_income":
                fmt = lambda x: f"${x:,.0f}"
            else:
                fmt = lambda x: f"{x:.1f}%"

            # Find highest/lowest tract by display_name
            idx_max = display_merged[col_var].idxmax()
            idx_min = display_merged[col_var].idxmin()
            name_max = display_merged.loc[idx_max, "display_name"] if idx_max in display_merged.index else "—"
            name_min = display_merged.loc[idx_min, "display_name"] if idx_min in display_merged.index else "—"

            m1.metric("Median (visible tracts)", fmt(vals.median()))
            m2.metric("Highest tract", fmt(vals.max()), delta=name_max, delta_color="off")
            m3.metric("Lowest tract",  fmt(vals.min()), delta=name_min, delta_color="off")
            m4.metric("Tracts visible", f"{len(display_merged):,}")
