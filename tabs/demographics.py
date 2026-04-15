import streamlit as st
import pydeck as pdk
import pandas as pd
import plotly.graph_objects as go
import json

from lib.config import DEMOGRAPHIC_VARS, HIGHER_IS_BETTER, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import value_to_color


def render(merged, demographics, geography, year):
    st.subheader("Demographics")

    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]
    geo_label  = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

    if geography == "County":
        st.info("Detailed demographic breakdowns are not available at the County level. Switch to Tract or Zip Code.")
        return

    # Only show variables that exist in the merged data
    available_demo_vars = {k: v for k, v in DEMOGRAPHIC_VARS.items() if v in merged.columns}
    if not available_demo_vars:
        st.info(f"Demographic data is not yet available for {geo_label} geography.")
        return

    # ── Variable selector & summary metrics ───────────────────────────────────
    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        selected_label = st.selectbox(
            "Variable", list(available_demo_vars.keys()), key="demo_layer"
        )
        column = available_demo_vars[selected_label]

        st.markdown("---")

        valid = merged[column].dropna()
        if len(valid) > 0:
            if column == "total_population":
                st.metric("Total Population", f"{int(valid.sum()):,}")
                st.metric(f"Largest {geo_label.lower()}", f"{int(valid.max()):,}")
                st.metric(f"Smallest {geo_label.lower()}", f"{int(valid.min()):,}")
            elif column == "median_age":
                st.metric("Mean Median Age", f"{valid.mean():.1f}")
                st.metric(f"Oldest {geo_label.lower()}", f"{valid.max():.1f}")
                st.metric(f"Youngest {geo_label.lower()}", f"{valid.min():.1f}")
            else:
                st.metric(f"Mean {selected_label}", f"{valid.mean():.1f}%")
                st.metric(f"Highest {geo_label.lower()}", f"{valid.max():.1f}%")
                st.metric(f"Lowest {geo_label.lower()}", f"{valid.min():.1f}%")

        st.markdown("---")
        st.markdown(f"**Explore a {geo_label}**")
        geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
        selected_display = st.selectbox(f"Select {geo_label.lower()}", geo_options, key="demo_geo_select")
        if selected_display != "None":
            sel_row = merged[merged["display_name"] == selected_display].iloc[0]
            st.session_state.selected_geo = sel_row[geo_id_col]
            st.session_state.selected_geo_name = selected_display

    # ── Choropleth map ─────────────────────────────────────────────────────────
    with col_map:
        avg = merged[column].mean() if column in merged.columns else None
        reverse = not HIGHER_IS_BETTER.get(column, True)

        merged_demo = merged.assign(
            color=merged[column].apply(
                lambda x: value_to_color(x, avg, reverse=reverse)
            )
        )

        map_cols = ["geometry", "color", "display_name", geo_id_col, column]
        map_cols = [c for c in map_cols if c in merged_demo.columns]
        demo_json = json.loads(merged_demo[map_cols].to_json())

        fmt = "${:,.0f}" if column == "median_household_income" else "{}"
        tooltip_val = f"{{{column}}}"

        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer",
                data=demo_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1,
                pickable=True,
            )],
            initial_view_state=VIEW_STATE,
            tooltip={
                "html": f"<b>{{display_name}}</b><br/>{selected_label}: {tooltip_val}",
                "style": TOOLTIP_STYLE,
            },
            map_style=MAP_STYLE,
        ), height=500)

    # ── Race/Ethnicity breakdown chart ─────────────────────────────────────────
    st.markdown("---")
    st.subheader(f"Race & Ethnicity by {geo_label}")
    st.caption(f"Top 20 {geo_label.lower()}s by population — {year} ACS 5-year estimates.")

    race_cols_pct = {
        "pct_white_non_hispanic": "White Non-Hispanic",
        "pct_black":              "Black or African American",
        "pct_hispanic":           "Hispanic or Latino",
        "pct_asian":              "Asian",
        "pct_other":              "Other / Multiracial",
    }
    race_cols_raw = {
        "white_non_hispanic": "White Non-Hispanic",
        "black_alone":        "Black or African American",
        "hispanic_latino":    "Hispanic or Latino",
        "asian_alone":        "Asian",
        "other_race":         "Other / Multiracial",
    }

    # For Tract geography use the separate demographics CSV (has raw counts);
    # for ZIP geography use the merged GeoDataFrame (has pct columns from zcta_data).
    if geography == "Tract":
        demo_year = demographics[demographics["year"] == year].copy()
        use_raw = all(c in demo_year.columns for c in race_cols_raw)
        use_pct = not use_raw and all(c in demo_year.columns for c in race_cols_pct)
        if "total_population" in demo_year.columns:
            demo_year = demo_year.sort_values("total_population", ascending=False).head(20)
        if "tract_code" in demo_year.columns:
            demo_year["tract_label"] = demo_year["tract_code"].astype(str).str.zfill(6)
        elif "TRACTCE" in demo_year.columns:
            demo_year["tract_label"] = demo_year["TRACTCE"].astype(str).str.zfill(6)
        else:
            demo_year["tract_label"] = demo_year.index.astype(str)
        tract_names = merged[["TRACTCE", "display_name"]].drop_duplicates()
        demo_year = demo_year.merge(
            tract_names, left_on="tract_label", right_on="TRACTCE", how="left"
        )
        demo_year["label"] = demo_year["display_name"].fillna(demo_year["tract_label"])
    else:
        # Use merged directly — zcta_data pct columns already joined
        demo_year = merged.copy()
        use_raw = False
        use_pct = all(c in demo_year.columns for c in race_cols_pct)
        if "total_population" in demo_year.columns:
            demo_year = demo_year.sort_values("total_population", ascending=False).head(20)
        demo_year["label"] = demo_year["display_name"]

    if not use_raw and not use_pct:
        st.info("Race/ethnicity breakdown not available in demographics data.")

        fig = go.Figure()
        RACE_COLORS = {
            "White Non-Hispanic":       "#4e79a7",
            "Black or African American":"#f28e2b",
            "Hispanic or Latino":       "#e15759",
            "Asian":                    "#76b7b2",
            "Other / Multiracial":      "#b07aa1",
        }

        if use_raw:
            total = demo_year[[c for c in race_cols_raw]].sum(axis=1).replace(0, float("nan"))
            for col, label in race_cols_raw.items():
                if col not in demo_year.columns:
                    continue
                pct = (demo_year[col] / total * 100).round(1)
                fig.add_trace(go.Bar(
                    name=label,
                    x=demo_year["label"],
                    y=pct,
                    marker_color=RACE_COLORS.get(label, "#999"),
                    hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>",
                ))
        else:
            for col, label in race_cols_pct.items():
                if col not in demo_year.columns:
                    continue
                fig.add_trace(go.Bar(
                    name=label,
                    x=demo_year["label"],
                    y=demo_year[col].round(1),
                    marker_color=RACE_COLORS.get(label, "#999"),
                    hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>",
                ))

        fig.update_layout(
            barmode="stack",
            height=380,
            margin=dict(t=10, b=120, l=20, r=20),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
            yaxis=dict(title="Share of population (%)", range=[0, 100],
                       gridcolor="rgba(200,200,200,0.15)"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="left", x=0, font=dict(size=11)),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Summary table ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader(f"All {geo_label}s — Demographic Summary")
    table_cols = ["display_name"] + [c for c in available_demo_vars.values() if c in merged.columns]
    table = merged[table_cols].dropna(subset=["display_name"]).copy()
    table = table.rename(columns={"display_name": geo_label})
    table = table.rename(columns={v: k for k, v in available_demo_vars.items() if v in table.columns})
    table = table.sort_values("Total Population", ascending=False).reset_index(drop=True) \
        if "Total Population" in table.columns else table
    table.index += 1
    st.dataframe(table, use_container_width=True)
