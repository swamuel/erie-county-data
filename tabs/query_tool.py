import streamlit as st
import pydeck as pdk
import json

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import format_value, get_benchmark_value, diff_string, value_to_color


def render(merged, benchmark_row, available_vars, geography):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]
    geo_label = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

    st.subheader("Multi-Variable Query")
    st.markdown(f"Find {geo_label.lower()}s that meet multiple conditions across available variables.")

    col_q1, col_q2 = st.columns([1, 3])

    with col_q1:
        logic_q = st.radio(
            "Match",
            ["ALL conditions (AND)", "ANY condition (OR)"],
            horizontal=True, key="query_logic"
        )

        query_conditions_q = {}
        for label, col in available_vars.items():
            with st.expander(label):
                enabled = st.checkbox(f"Include {label}", key=f"query_enable_{col}")
                if enabled:
                    direction = st.radio(
                        "Direction", ["Above", "Below"],
                        horizontal=True, key=f"query_dir_{col}"
                    )
                    query_conditions_q[col] = direction

    with col_q2:
        national_avg_q = get_benchmark_value(benchmark_row, "poverty_rate")
        merged_query = merged.assign(
            color=merged["poverty_rate"].apply(
                lambda x: value_to_color(x, national_avg_q, reverse=True)
            )
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
                merged_query = merged_query.copy()
                merged_query["color"] = merged_query.apply(
                    lambda row: row["color"] if final_mask_q[row.name] else [100, 100, 100, 60],
                    axis=1
                )
                st.metric(f"Matching {geo_label.lower()}s", int(final_mask_q.sum()))

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
            initial_view_state=VIEW_STATE,
            tooltip={
                "html": "<b>{display_name}</b><br/>"
                        "Poverty: {poverty_rate}%<br/>"
                        "Income: ${median_household_income}<br/>"
                        "Food Insecurity: {food_insecurity_rate}%",
                "style": TOOLTIP_STYLE
            },
            map_style=MAP_STYLE
        ), height=600)
