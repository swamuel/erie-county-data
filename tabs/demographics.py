import streamlit as st
import pydeck as pdk
import plotly.graph_objects as go
import json

from lib.config import DEMOGRAPHIC_VARS, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import sequential_color

RACE_COLORS = {
    "White Non-Hispanic":        "#4e79a7",
    "Black or African American": "#f28e2b",
    "Hispanic or Latino":        "#e15759",
    "Asian":                     "#76b7b2",
    "Other / Multiracial":       "#b07aa1",
}
RACE_RAW = {
    "white_non_hispanic": "White Non-Hispanic",
    "black_alone":        "Black or African American",
    "hispanic_latino":    "Hispanic or Latino",
    "asian_alone":        "Asian",
    "other_race":         "Other / Multiracial",
}
RACE_PCT = {
    "pct_white_non_hispanic": "White Non-Hispanic",
    "pct_black":              "Black or African American",
    "pct_hispanic":          "Hispanic or Latino",
    "pct_asian":             "Asian",
    "pct_other":             "Other / Multiracial",
}


def render(merged, master_tract, geography, year, geo_id_col):
    st.subheader("Demographics")
    geo_label = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

    if geography == "County":
        st.info("Detailed demographic breakdowns are not available at the County level. "
                "Switch to Tract or ZIP Code.")
        return

    available = {k: v for k, v in DEMOGRAPHIC_VARS.items() if v in merged.columns}
    if not available:
        st.info(f"Demographic data is not available for {geo_label} geography.")
        return

    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        selected_label = st.selectbox("Variable", list(available.keys()), key="demo_layer")
        column = available[selected_label]

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

    # ── Choropleth ────────────────────────────────────────────────────────
    with col_map:
        # Soft sequential scale anchored to the data's own range (5th–95th pct)
        # so the map is informative, not good/bad.
        if len(valid) > 1:
            vmin, vmax = float(valid.quantile(0.05)), float(valid.quantile(0.95))
        else:
            vmin = vmax = None
        merged_demo = merged.assign(
            color=merged[column].apply(lambda x: sequential_color(x, vmin, vmax))
        )
        map_cols = [c for c in ["geometry", "color", "display_name", column] if c in merged_demo.columns]
        demo_json = json.loads(merged_demo[map_cols].to_json())

        tooltip_val = f"{{{column}}}"
        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer(
                "GeoJsonLayer", data=demo_json,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255, 50],
                line_width_min_pixels=1, pickable=True,
            )],
            initial_view_state=VIEW_STATE,
            tooltip={"html": f"<b>{{display_name}}</b><br/>{selected_label}: {tooltip_val}",
                     "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE,
        ), height=500)

        if vmin is not None:
            unit = "" if column in ("total_population", "median_age") else "%"
            lo = f"{vmin:,.0f}{unit}" if column == "total_population" else f"{vmin:.1f}{unit}"
            hi = f"{vmax:,.0f}{unit}" if column == "total_population" else f"{vmax:.1f}{unit}"
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;font-size:11px;color:#64748b'>"
                f"<span>{lo}</span>"
                f"<div style='flex:1;height:10px;border-radius:3px;"
                f"background:linear-gradient(to right,rgb(236,242,250),rgb(39,58,120))'></div>"
                f"<span>{hi}</span></div>",
                unsafe_allow_html=True,
            )

    # ── Race / ethnicity breakdown ────────────────────────────────────────
    st.markdown("---")
    st.subheader(f"Race & Ethnicity by {geo_label}")
    st.caption(f"Top 20 {geo_label.lower()}s by population — {year} ACS 5-year estimates.")

    if geography == "Tract":
        d = master_tract[master_tract["year"] == year].copy()
        names = merged[["GEOID", "display_name"]].drop_duplicates()
        d = d.merge(names, on="GEOID", how="left")
        d["label"] = d["display_name"].fillna(d["GEOID"])
    else:
        d = merged.copy()
        d["label"] = d["display_name"]

    # Prefer raw counts (recompute shares) where available, else stored pct columns.
    if all(c in d.columns for c in RACE_RAW):
        mode = "raw"
    elif all(c in d.columns for c in RACE_PCT):
        mode = "pct"
    else:
        mode = None

    if mode is None:
        st.info("Race/ethnicity breakdown not available for this geography.")
    else:
        if "total_population" in d.columns:
            d = d.sort_values("total_population", ascending=False).head(20)

        fig = go.Figure()
        if mode == "raw":
            total = d[list(RACE_RAW)].sum(axis=1).replace(0, float("nan"))
            for col, label in RACE_RAW.items():
                fig.add_trace(go.Bar(
                    name=label, x=d["label"], y=(d[col] / total * 100).round(1),
                    marker_color=RACE_COLORS.get(label, "#999"),
                    hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>",
                ))
        else:
            for col, label in RACE_PCT.items():
                fig.add_trace(go.Bar(
                    name=label, x=d["label"], y=d[col].round(1),
                    marker_color=RACE_COLORS.get(label, "#999"),
                    hovertemplate=f"%{{x}}<br>{label}: %{{y:.1f}}%<extra></extra>",
                ))
        fig.update_layout(
            barmode="stack", height=380, margin=dict(t=10, b=120, l=20, r=20),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
            yaxis=dict(title="Share of population (%)", range=[0, 100],
                       gridcolor="rgba(200,200,200,0.15)"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                        font=dict(size=11)),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Summary table ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader(f"All {geo_label}s — Demographic Summary")
    table_cols = ["display_name"] + [c for c in available.values() if c in merged.columns]
    table = merged[table_cols].dropna(subset=["display_name"]).copy()
    table = table.rename(columns={"display_name": geo_label})
    table = table.rename(columns={v: k for k, v in available.items() if v in table.columns})
    if "Total Population" in table.columns:
        table = table.sort_values("Total Population", ascending=False)
    table = table.reset_index(drop=True)
    table.index += 1
    st.dataframe(table, use_container_width=True)
