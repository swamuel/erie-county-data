import streamlit as st
import pydeck as pdk
import json

from lib.config import all_variables, HIGHER_IS_BETTER, TRACT_ONLY_VARS, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import value_to_color, get_benchmark_value, format_value, render_detail_panel

HEALTH_VARS = {
    "Diabetes Rate": "diabetes_rate",
    "High Blood Pressure": "high_bp_rate",
    "Depression Rate": "depression_rate",
    "Obesity Rate": "obesity_rate",
    "Smoking Rate": "smoking_rate",
    "No Health Insurance": "no_insurance_rate",
    "Poor Mental Health (14+ days)": "poor_mental_health_rate",
    "Poor Physical Health (14+ days)": "poor_physical_health_rate",
    "Asthma Rate": "asthma_rate",
    "Heart Disease Rate": "heart_disease_rate",
    "Stroke Rate": "stroke_rate",
    "COPD Rate": "copd_rate",
    "Physical Inactivity": "physical_inactivity_rate",
    "Sleep Deprivation": "sleep_deprivation_rate",
}


def render(merged, benchmark_row, geography):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]
    geo_label  = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

    col_controls_h, col_map_h = st.columns([1, 3])

    # Only show variables that are actually present in the merged data
    available_health_vars = {k: v for k, v in HEALTH_VARS.items() if v in merged.columns}

    with col_controls_h:
        st.subheader("Health Outcomes")
        st.caption("Source: CDC PLACES 2023 release (2021 BRFSS data).")

        if geography == "County":
            st.info("Health data is not available at the County level. Switch to Tract or Zip Code.")
        elif not available_health_vars:
            st.info(
                f"Health data is not yet loaded for {geo_label} geography. "
                "Run `fetch_cdc_places_zcta.py` (ZIP) or check your data files."
            )

        if not available_health_vars:
            return

        health_layer = st.selectbox(
            "Variable", list(available_health_vars.keys()), key="health_layer"
        )
        health_col = available_health_vars[health_layer]

        st.markdown("---")
        st.markdown(f"**Explore a {geo_label}**")
        health_geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
        health_selected = st.selectbox(f"Select {geo_label.lower()}", health_geo_options, key="health_geo_select")
        if health_selected != "None":
            sel_row = merged[merged["display_name"] == health_selected].iloc[0]
            st.session_state.selected_geo = sel_row[geo_id_col]
            st.session_state.selected_geo_name = health_selected

    with col_map_h:
        if health_col in merged.columns:
            health_avg = merged[health_col].mean()
            merged_health = merged.assign(
                color=merged[health_col].apply(
                    lambda x: value_to_color(x, health_avg, reverse=True)
                )
            )
            health_metric_val = merged_health[health_col].median()
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Median {health_layer}", f"{health_metric_val:.1f}%" if health_metric_val else "—")
            c2.metric(f"Highest {geo_label.lower()}", f"{merged_health[health_col].max():.1f}%")
            c3.metric(f"Lowest {geo_label.lower()}", f"{merged_health[health_col].min():.1f}%")
        else:
            merged_health = merged.assign(color=[[200, 200, 200, 140]] * len(merged))

        _health_cols = [c for c in ["geometry", "color", "display_name", health_col, "poverty_rate"] if c in merged_health.columns]
        health_json = json.loads(merged_health[_health_cols].to_json())

        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer",
                data=health_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True
            )],
            initial_view_state=VIEW_STATE,
            tooltip={
                "html": "<b>{display_name}</b><br/>"
                        f"{health_layer}: {{{health_col}}}%<br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "No Insurance: {no_insurance_rate}%",
                "style": TOOLTIP_STYLE
            },
            map_style=MAP_STYLE
        ), height=600)

        st.markdown("---")

        # Health summary table
        st.markdown(f"**All {geo_label}s — Health Summary**")
        health_summary_cols = ["display_name"] + [c for c in available_health_vars.values() if c in merged_health.columns]
        health_table = merged_health[health_summary_cols].dropna(subset=[health_col]).copy()
        health_table = health_table.sort_values(health_col, ascending=False).reset_index(drop=True)
        health_table.index += 1
        health_table = health_table.rename(columns={"display_name": geo_label})
        health_table = health_table.rename(columns={v: k for k, v in available_health_vars.items() if v in health_table.columns})
        st.dataframe(health_table, use_container_width=True)
