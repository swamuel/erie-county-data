import streamlit as st
import pydeck as pdk
import pandas as pd
import json
import plotly.graph_objects as go

from lib.config import MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE, HIGHER_IS_BETTER
from lib.helpers import value_to_color, get_benchmark_value, format_value, render_detail_panel, haversine_miles

PROGRAM_LABELS = {
    "Food Pantry/TEFAP": "Food Pantry (TEFAP)",
    "Food Pantry/No TEFAP": "Food Pantry (No TEFAP)",
    "Produce Express": "Produce Express",
    "BackPacks": "Backpack Program",
    "School Pantry": "School Pantry",
    "Non-Emerg. Meal/Snack": "Meal / Snack Program",
    "Kids Cafe": "Kids Cafe",
    "Original": "Other",
}


def render(merged, pantries, pantry_monthly, pantry_index, benchmark_row, geography):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]

    col_controls_f, col_map_f = st.columns([1, 3])

    with col_controls_f:
        st.subheader("Food Access")
        show_pantries = st.checkbox("Show Food Pantries", value=True, key="food_pantries")
        show_food_layer = st.checkbox("Show Food Insecurity Layer", value=True, key="food_layer")
        show_food_deserts = st.checkbox("Show Food Deserts (USDA)", value=False, key="food_deserts")

        if geography != "Tract":
            st.info("Food insecurity data is only available at the Tract level. "
                    "The map shows Poverty Rate at your selected geography.")
        elif show_food_deserts:
            st.caption(
                "Food deserts (orange outline) = low income tracts where "
                "at least 500 people or 33% of the population live more than "
                "1 mile from a grocery store (urban) or 10 miles (rural)."
            )

    with col_map_f:
        food_layers = []

        if geography == "Tract" and "food_insecurity_rate" in merged.columns:
            food_color_col = "food_insecurity_rate"
        else:
            food_color_col = "poverty_rate"

        food_benchmark = get_benchmark_value(benchmark_row, "poverty_rate")
        merged_food = merged.assign(
            color=merged[food_color_col].apply(
                lambda x: value_to_color(x, food_benchmark, reverse=True)
            )
        )

        # Food desert outline layer
        if show_food_deserts and geography == "Tract" and "food_desert_1_10" in merged_food.columns:
            desert_tracts = merged_food[merged_food["food_desert_1_10"] == 1]
            if len(desert_tracts) > 0:
                desert_json = json.loads(desert_tracts.to_json())
                food_layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data=desert_json,
                    get_fill_color=[0, 0, 0, 0],
                    get_line_color=[255, 140, 0, 255],
                    line_width_min_pixels=3,
                    pickable=False
                ))
                st.metric("Food desert tracts", len(desert_tracts))

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

        food_tooltip_html = (
            "<b>{PantryName}</b><br/>"
            "Hours: {hours}<br/>"
            "<b>{display_name}</b><br/>"
            "Food Insecurity: {food_insecurity_rate}%"
            if geography == "Tract"
            else
            "<b>{PantryName}</b><br/>"
            "Hours: {hours}<br/>"
            "<b>{display_name}</b><br/>"
            "Poverty Rate: {poverty_rate}%"
        )

        st.pydeck_chart(pdk.Deck(
            layers=food_layers,
            initial_view_state=VIEW_STATE,
            tooltip={"html": food_tooltip_html, "style": TOOLTIP_STYLE},
            map_style=MAP_STYLE
        ), height=600)

    # ── Pantry Detail Section ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Food Pantry & Program Activity")
    st.caption("Monthly reporting data from Second Harvest Food Bank partner agencies.")

    # ── County filter ─────────────────────────────────────────────────────────────
    available_pantry_counties = sorted(pantry_index["county"].dropna().unique().tolist())
    selected_pantry_counties = st.multiselect(
        "Filter by county",
        options=available_pantry_counties,
        default=available_pantry_counties,
        key="pantry_county_filter"
    )

    if selected_pantry_counties:
        filtered_index = pantry_index[pantry_index["county"].isin(selected_pantry_counties)]
    else:
        filtered_index = pantry_index.copy()

    show_county_tag = len(selected_pantry_counties) != 1

    # ── Build grouped dropdown options ────────────────────────────────────────────
    options = ["— Select a pantry or program —"]
    option_keys = [None]

    for prog_type in PROGRAM_LABELS.keys():
        group = filtered_index[filtered_index["program_type"] == prog_type].sort_values("agency_name")
        if group.empty:
            continue
        header = f"── {PROGRAM_LABELS[prog_type]} ──"
        options.append(header)
        option_keys.append(None)
        for _, row in group.iterrows():
            county_tag = f" ({row['county']})" if show_county_tag else ""
            label = f"  {row['agency_name']}{county_tag}"
            options.append(label)
            option_keys.append((row["agency_ref"], row["program_type"]))

    selected_idx = st.selectbox(
        "Select a program",
        range(len(options)),
        format_func=lambda i: options[i],
        key="pantry_selector"
    )

    selected_key = option_keys[selected_idx]

    # ── Detail panel ──────────────────────────────────────────────────────────────
    if selected_key is not None:
        sel_ref, sel_prog = selected_key

        agency_info = pantry_index[
            (pantry_index["agency_ref"] == sel_ref) &
            (pantry_index["program_type"] == sel_prog)
        ].iloc[0]

        agency_monthly = pantry_monthly[
            (pantry_monthly["agency_ref"] == sel_ref) &
            (pantry_monthly["program_type"] == sel_prog)
        ].sort_values("date")

        st.markdown(f"### {agency_info['agency_name']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Program Type", PROGRAM_LABELS.get(sel_prog, sel_prog))
        col2.metric("County", agency_info["county"])
        col3.metric(
            "Reporting Period",
            f"{pd.to_datetime(agency_info['first_month']).strftime('%b %Y')} – "
            f"{pd.to_datetime(agency_info['last_month']).strftime('%b %Y')}"
        )

        total_served = int(agency_monthly["total_individuals"].sum())
        avg_monthly = agency_monthly["total_individuals"].mean()
        peak_row = agency_monthly.loc[agency_monthly["total_individuals"].idxmax()]
        peak_month = peak_row["date"].strftime("%b %Y")
        peak_val = int(peak_row["total_individuals"])

        s1, s2, s3 = st.columns(3)
        s1.metric("Total Individuals Served", f"{total_served:,}")
        s2.metric("Avg per Month", f"{avg_monthly:,.0f}")
        s3.metric("Peak Month", f"{peak_month} ({peak_val:,})")

        st.markdown("#### Monthly Individuals Served")

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(
            x=agency_monthly["date"],
            y=agency_monthly["total_individuals"],
            mode="lines+markers",
            line=dict(color="#2d6a4f", width=2),
            marker=dict(size=6),
            name="Individuals Served",
            hovertemplate="%{x|%b %Y}: %{y:,} individuals<extra></extra>"
        ))
        x_min = agency_monthly["date"].min()
        x_max = agency_monthly["date"].max()

        line_fig.update_layout(
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis_title=None,
            yaxis_title="Individuals",
            xaxis=dict(
                range=[x_min, x_max],
                tickmode="array",
                tickvals=agency_monthly["date"].tolist(),
                tickformat="%b %Y",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
        )
        st.plotly_chart(line_fig, use_container_width=True)

        has_age_data = agency_monthly[["children", "adults", "seniors"]].sum().sum() > 0

        if has_age_data:
            st.markdown("#### Individuals Served by Age Group")

            bar_fig = go.Figure()
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["children"],
                name="Children (0–17)",
                marker_color="#52b788",
                hovertemplate="%{x|%b %Y}: %{y:,} children<extra></extra>"
            ))
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["adults"],
                name="Adults (18–59)",
                marker_color="#2d6a4f",
                hovertemplate="%{x|%b %Y}: %{y:,} adults<extra></extra>"
            ))
            bar_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["seniors"],
                name="Seniors (60+)",
                marker_color="#1b4332",
                hovertemplate="%{x|%b %Y}: %{y:,} seniors<extra></extra>"
            ))
            bar_fig.update_layout(
                barmode="stack",
                height=300,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title=None,
                yaxis_title="Individuals",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
                xaxis=dict(
                    range=[x_min, x_max],
                    tickmode="array",
                    tickvals=agency_monthly["date"].tolist(),
                    tickformat="%b %Y",
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )
            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("Age group breakdown not available for this program type.")

        has_new_hh_data = agency_monthly["new_households"].sum() > 0

        if has_new_hh_data:
            st.markdown("#### New Households per Month")
            st.caption("First-time households — an indicator of whether demand is expanding.")

            hh_fig = go.Figure()
            hh_fig.add_trace(go.Bar(
                x=agency_monthly["date"],
                y=agency_monthly["new_households"],
                marker_color="#52b788",
                hovertemplate="%{x|%b %Y}: %{y:,} new households<extra></extra>"
            ))
            hh_fig.update_layout(
                height=280,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis=dict(
                    range=[x_min, x_max],
                    tickmode="array",
                    tickvals=agency_monthly["date"].tolist(),
                    tickformat="%b %Y",
                ),
                yaxis_title="Households",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(200,200,200,0.3)"),
            )
            st.plotly_chart(hh_fig, use_container_width=True)
