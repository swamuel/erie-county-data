import streamlit as st
import pydeck as pdk
import pandas as pd
import json
import plotly.graph_objects as go

from lib.config import all_variables, HIGHER_IS_BETTER, TRACT_ONLY_VARS, DEMOGRAPHIC_VARS, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import value_to_color, get_benchmark_value, format_value, diff_string, render_detail_panel


def diverging_growth_color(val, cap, higher_better):
    if pd.isna(val):
        return [200, 200, 200, 140]
    signed = val if higher_better else -val
    normalized = (signed / cap) / 2 + 0.5
    normalized = max(0.0, min(1.0, normalized))
    if normalized < 0.5:
        t = normalized * 2
        r = int(200 - (t * 40))
        g = int(80 + (t * 60))
        b = int(60 + (t * 20))
    else:
        t = (normalized - 0.5) * 2
        r = int(160 - (t * 120))
        g = int(140 + (t * 70))
        b = int(80 - (t * 20))
    return [r, g, b, 180]


def render(merged, census, zcta_data, gdf_tracts, gdf_zctas,
           benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties,
           benchmark_row, available_vars, geography, year, mode, selected_benchmark,
           compare_county, strat_df):

    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]
    geo_label = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]

    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        # ── VIEW TOGGLE ───────────────────────────────────────
        econ_view = st.radio(
            "View",
            ["Snapshot", "Change Over Time"],
            horizontal=True,
            key="econ_view_toggle"
        )

        st.markdown("---")

        # ══════════════════════════════════════════════════════
        # SNAPSHOT VIEW
        # ══════════════════════════════════════════════════════
        if econ_view == "Snapshot":
            st.subheader("Economic Indicators")
            _demo_cols = set(DEMOGRAPHIC_VARS.values())
            econ_vars = {k: v for k, v in all_variables.items()
                         if v not in _demo_cols
                         and (v not in TRACT_ONLY_VARS or geography == "Tract")}
            selected_layer = st.selectbox(
                "Variable", list(econ_vars.keys()), key="econ_layer"
            )
            column = econ_vars[selected_layer]

            st.markdown("---")
            st.markdown("**Explore a Location**")
            geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
            selected_display = st.selectbox(
                f"Select {geo_label}", geo_options, key="econ_geo_select"
            )
            if selected_display != "None":
                sel_row = merged[merged["display_name"] == selected_display].iloc[0]
                st.session_state.selected_geo = sel_row[geo_id_col]
                st.session_state.selected_geo_name = selected_display

        # ══════════════════════════════════════════════════════
        # CHANGE OVER TIME VIEW
        # ══════════════════════════════════════════════════════
        else:
            st.subheader("Change Over Time")
            st.caption("How did each tract change relative to the benchmark?")

            if geography == "County":
                st.info("Change Over Time is not available at the County level.")

            GROWTH_VARS = {
                "Median Household Income": "median_household_income",
                "Poverty Rate": "poverty_rate",
                "Rent Burden Rate": "rent_burden_rate",
                "No Vehicle Rate": "no_vehicle_rate",
                "Bachelor's Degree Rate": "bachelors_rate",
            }
            growth_var_label = st.selectbox(
                "Variable", list(GROWTH_VARS.keys()), key="growth_var"
            )
            growth_col = GROWTH_VARS[growth_var_label]
            higher_is_better_growth = HIGHER_IS_BETTER.get(growth_col, True)

            all_years = sorted(census["year"].unique().tolist())
            gc1, gc2 = st.columns(2)
            growth_start = gc1.selectbox("From", all_years, index=0, key="growth_start")
            growth_end = gc2.selectbox("To", all_years, index=len(all_years) - 1, key="growth_end")

            if growth_start >= growth_end:
                st.error("'From' year must be before 'To' year.")
            else:
                growth_cap = st.slider(
                    "Color scale cap (\u00b1 pts)",
                    min_value=5, max_value=30, value=15, step=1,
                    help="Differences beyond this saturate the color.",
                    key="growth_cap"
                )
                show_legend = st.checkbox("Show legend", value=False, key="growth_legend")

    # ══════════════════════════════════════════════════════════
    # MAP COLUMN
    # ══════════════════════════════════════════════════════════
    with col_map:

        # ── SNAPSHOT MAP ──────────────────────────────────────
        if econ_view == "Snapshot":
            column = econ_vars[selected_layer]
            bench_avg = get_benchmark_value(benchmark_row, column)
            reverse = not HIGHER_IS_BETTER.get(column, True)

            merged_econ = merged.assign(
                color=merged[column].apply(
                    lambda x: value_to_color(x, bench_avg, reverse=reverse)
                )
            )

            if column in merged_econ.columns:
                valid_vals = merged_econ[column].dropna()
                m1, m2, m3 = st.columns(3)
                m1.metric("Median", format_value(valid_vals.median(), column))
                m2.metric("Highest", format_value(valid_vals.max(), column))
                m3.metric("Lowest", format_value(valid_vals.min(), column))

            econ_json = json.loads(merged_econ.to_json())

            st.pydeck_chart(pdk.Deck(
                layers=[pdk.Layer(
                    "GeoJsonLayer",
                    data=econ_json,
                    get_fill_color="properties.color",
                    get_line_color=[255, 255, 255, 50],
                    line_width_min_pixels=1,
                    pickable=True,
                )],
                initial_view_state=VIEW_STATE,
                tooltip={
                    "html": f"<b>{{display_name}}</b><br/>{selected_layer}: {{{column}}}",
                    "style": TOOLTIP_STYLE,
                },
                map_style=MAP_STYLE,
            ), height=560)

            render_detail_panel(merged_econ, column, selected_layer, geo_id_col, geography, benchmark_row)

        # ── GROWTH MAP ────────────────────────────────────────
        else:
            if geography == "County" or growth_start >= growth_end:
                st.info("Select Tract geography and a valid year range to view change over time.")
            else:
                if geography == "Tract":
                    src = census
                    id_col = "tract_code"
                    join_col = "TRACTCE"
                    gdf_base = gdf_tracts
                elif geography == "Zip Code":
                    src = zcta_data
                    id_col = "zcta"
                    join_col = "ZCTA5CE20"
                    gdf_base = gdf_zctas
                else:
                    src = id_col = join_col = gdf_base = None

                t0 = src[src["year"] == growth_start][[id_col, growth_col]].rename(
                    columns={growth_col: "val_start"})
                t1 = src[src["year"] == growth_end][[id_col, growth_col]].rename(
                    columns={growth_col: "val_end"})
                growth_df = t0.merge(t1, on=id_col, how="inner")
                growth_df = growth_df[
                    growth_df["val_start"].notna() & (growth_df["val_start"] != 0) &
                    growth_df["val_end"].notna()
                ].copy()
                growth_df["JOINKEY"] = growth_df[id_col].astype(str).str.zfill(
                    6 if geography == "Tract" else 5
                )

                is_dollar = (growth_col == "median_household_income")
                if is_dollar:
                    growth_df["tract_change"] = (
                        (growth_df["val_end"] - growth_df["val_start"])
                        / growth_df["val_start"] * 100
                    )
                    change_label = "% growth"
                else:
                    growth_df["tract_change"] = growth_df["val_end"] - growth_df["val_start"]
                    change_label = "pp change"

                bench_label = selected_benchmark
                if selected_benchmark == "National":
                    bench_src = benchmarks_national
                elif selected_benchmark == "Pennsylvania":
                    bench_src = benchmarks_pa
                elif selected_benchmark == "Erie County":
                    bench_src = benchmarks_erie
                else:
                    bench_src = benchmarks_counties[
                        benchmarks_counties["name"] == compare_county
                    ]

                b0 = bench_src.loc[bench_src["year"] == growth_start, growth_col].values
                b1 = bench_src.loc[bench_src["year"] == growth_end, growth_col].values

                if len(b0) and len(b1) and b0[0] and b0[0] != 0:
                    bench_change = (b1[0] - b0[0]) / b0[0] * 100 if is_dollar else b1[0] - b0[0]
                else:
                    bench_change = None

                growth_df["relative_change"] = (
                    growth_df["tract_change"] - bench_change
                    if bench_change is not None else float("nan")
                )

                gdf_base = gdf_base.copy()
                gdf_base[join_col] = gdf_base[join_col].astype(str).str.zfill(
                    6 if geography == "Tract" else 5
                )
                if geography == "Zip Code":
                    zcta_names = zcta_data[["zcta", "area_name"]].drop_duplicates()
                    zcta_names["zcta"] = zcta_names["zcta"].astype(str).str.zfill(5)
                    growth_df = growth_df.merge(zcta_names, left_on="JOINKEY", right_on="zcta", how="left")
                merged_growth = gdf_base.merge(
                    growth_df, left_on=join_col, right_on="JOINKEY", how="left"
                )

                merged_growth["color"] = merged_growth["relative_change"].apply(
                    lambda x: diverging_growth_color(x, growth_cap, higher_is_better_growth)
                )

                def fmt_change(x):
                    if pd.isna(x): return "N/A"
                    sign = "+" if x >= 0 else ""
                    return f"{sign}{x:.1f}"

                if geography == "Zip Code":
                    merged_growth["t_name"] = (
                        merged_growth["area_name"].fillna("Unknown") +
                        " (" + merged_growth["JOINKEY"].astype(str) + ")"
                    )
                else:
                    merged_growth["t_name"] = merged_growth["NAMELSAD"].fillna("Unknown")

                merged_growth["t_abs"] = merged_growth["tract_change"].apply(fmt_change)
                merged_growth["t_rel"] = merged_growth["relative_change"].apply(fmt_change)
                merged_growth["t_start"] = merged_growth["val_start"].apply(
                    lambda x: format_value(x, growth_col) if pd.notna(x) else "N/A")
                merged_growth["t_end"] = merged_growth["val_end"].apply(
                    lambda x: format_value(x, growth_col) if pd.notna(x) else "N/A")
                bench_str = f"{bench_change:+.1f}" if bench_change is not None else "N/A"

                valid_rel = merged_growth["relative_change"].dropna()
                ahead = int((valid_rel > 0).sum()) if higher_is_better_growth else int((valid_rel < 0).sum())
                behind = len(valid_rel) - ahead
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(f"{geo_label}s ahead of benchmark", str(ahead))
                m2.metric(f"{geo_label}s behind benchmark", str(behind))
                m3.metric(f"Benchmark change ({bench_label})", f"{bench_str} {change_label}")
                m4.metric("Median tract change",
                          fmt_change(merged_growth["tract_change"].median()) + f" {change_label}")

                if show_legend:
                    lc, mc, rc = st.columns([1, 2, 1])
                    good_label = "Improved" if higher_is_better_growth else "Fell"
                    bad_label = "Fell" if higher_is_better_growth else "Improved"
                    lc.markdown(
                        f"<div style='background:linear-gradient(to right,rgb(200,80,60),rgb(160,140,80));"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b'>{bad_label} behind</div>",
                        unsafe_allow_html=True
                    )
                    mc.markdown(
                        f"<div style='background:rgb(160,140,80);border:1px solid #e2e8f0;"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b;text-align:center'>Kept pace</div>",
                        unsafe_allow_html=True
                    )
                    rc.markdown(
                        f"<div style='background:linear-gradient(to right,rgb(160,140,80),rgb(40,210,60));"
                        f"height:12px;border-radius:3px'></div>"
                        f"<div style='font-size:10px;color:#64748b;text-align:right'>{good_label} vs benchmark</div>",
                        unsafe_allow_html=True
                    )

                geo_key_col = join_col
                geojson_cols = ["geometry", "color", "t_name", "t_abs", "t_rel", "t_start", "t_end"]
                if geo_key_col in merged_growth.columns:
                    geojson_cols = [geo_key_col] + geojson_cols
                growth_geojson = json.loads(
                    merged_growth[[c for c in geojson_cols if c in merged_growth.columns]].to_json()
                )

                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer(
                        "GeoJsonLayer",
                        data=growth_geojson,
                        get_fill_color="properties.color",
                        get_line_color=[80, 80, 80, 100],
                        line_width_min_pixels=1,
                        pickable=True,
                        auto_highlight=True,
                    )],
                    initial_view_state=VIEW_STATE,
                    tooltip={
                        "html": (
                            f"<b>{{t_name}}</b><br/>"
                            f"{growth_var_label}: {{t_start}} &rarr; {{t_end}}<br/>"
                            f"Change: {{t_abs}} {change_label}<br/>"
                            f"vs {bench_label}: {{t_rel}} {change_label}"
                        ),
                        "style": TOOLTIP_STYLE,
                    },
                    map_style=MAP_STYLE,
                ), height=560)

                with st.expander("Full tract ranking"):
                    rank_df = merged_growth[["t_name", "t_start", "t_end",
                                             "tract_change", "relative_change"]].copy()
                    rank_df.columns = [
                        geo_label,
                        f"{growth_start} Value",
                        f"{growth_end} Value",
                        f"Change ({change_label})",
                        f"vs {bench_label} ({change_label})",
                    ]
                    rank_df = rank_df.dropna(subset=[f"Change ({change_label})"])
                    rank_df[f"Change ({change_label})"] = rank_df[f"Change ({change_label})"].round(1)
                    rank_df[f"vs {bench_label} ({change_label})"] = rank_df[
                        f"vs {bench_label} ({change_label})"
                    ].round(1)
                    rank_df = rank_df.sort_values(f"vs {bench_label} ({change_label})", ascending=False)
                    st.dataframe(rank_df, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════
    # INCOME STRATIFICATION — full width below map/controls
    # ══════════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("Household Income Stratification")
    st.caption(
        "Share of households by income tier per census tract, 2019–2023. "
        "Tiers are fixed dollar thresholds: bottom (under $35k), middle ($35k–$75k), top ($75k+). "
        "Year-over-year shifts may partly reflect inflation in addition to real income change."
    )

    BAND_LABELS = {
        "under_10k":  "Under $10k",
        "10k_15k":    "$10k–$15k",
        "15k_20k":    "$15k–$20k",
        "20k_25k":    "$20k–$25k",
        "25k_30k":    "$25k–$30k",
        "30k_35k":    "$30k–$35k",
        "35k_40k":    "$35k–$40k",
        "40k_45k":    "$40k–$45k",
        "45k_50k":    "$45k–$50k",
        "50k_60k":    "$50k–$60k",
        "60k_75k":    "$60k–$75k",
        "75k_100k":   "$75k–$100k",
        "100k_125k":  "$100k–$125k",
        "125k_150k":  "$125k–$150k",
        "150k_200k":  "$150k–$200k",
        "200k_plus":  "$200k+",
    }

    TIER_COLORS = {
        "Bottom (under $35k)": "#c45c3a",
        "Middle ($35k–$75k)":  "#e9c46a",
        "Top ($75k+)":         "#2d6a4f",
    }

    BAND_COLORS = [
        "#b5432a", "#c45c3a", "#d4754a", "#e08c5a", "#e9a46a", "#e9c46a",
        "#c8c86a", "#a8c86a", "#88c87a", "#68b87a", "#4da870", "#2d6a4f",
        "#266045", "#1f563c", "#184c33", "#11422a",
    ]

    strat_col1, strat_col2 = st.columns([2, 1])
    with strat_col1:
        strat_county = st.radio(
            "County",
            options=["Erie", "Crawford"],
            horizontal=True,
            key="strat_county"
        )
    with strat_col2:
        view_mode = st.radio(
            "View",
            options=["Tiers", "All bands"],
            horizontal=True,
            key="strat_view_mode"
        )

    county_tracts = strat_df[strat_df["county"] == strat_county][["geoid", "NAME"]].drop_duplicates()
    county_tracts = county_tracts.sort_values("NAME")
    county_tracts["display"] = county_tracts["NAME"].str.replace(r";.*$", "", regex=True).str.strip()
    tract_options = county_tracts["geoid"].tolist()
    tract_labels  = dict(zip(county_tracts["geoid"], county_tracts["display"]))

    selected_tract = st.selectbox(
        "Select a census tract",
        options=tract_options,
        format_func=lambda g: tract_labels.get(g, g),
        key="strat_tract_selector"
    )

    tract_data = strat_df[strat_df["geoid"] == selected_tract].sort_values("year")

    if tract_data.empty:
        st.warning("No data found for this tract.")
    else:
        tract_name = tract_labels.get(selected_tract, selected_tract)

        latest   = tract_data[tract_data["year"] == tract_data["year"].max()].iloc[0]
        earliest = tract_data[tract_data["year"] == tract_data["year"].min()].iloc[0]
        bottom_delta = round(latest["share_bottom"] - earliest["share_bottom"], 1)
        top_delta    = round(latest["share_top"]    - earliest["share_top"],    1)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Households (latest)", f"{int(latest['total_households']):,}")
        m2.metric("Bottom Tier Share", f"{latest['share_bottom']:.1f}%",
                  delta=f"{bottom_delta:+.1f}pp since 2019", delta_color="inverse")
        m3.metric("Middle Tier Share", f"{latest['share_middle']:.1f}%")
        m4.metric("Top Tier Share", f"{latest['share_top']:.1f}%",
                  delta=f"{top_delta:+.1f}pp since 2019")

        st.markdown(f"#### {tract_name} — Income Distribution by Year")

        fig = go.Figure()

        if view_mode == "Tiers":
            fig.add_trace(go.Bar(
                name="Bottom (under $35k)",
                x=tract_data["year"], y=tract_data["share_bottom"],
                marker_color=TIER_COLORS["Bottom (under $35k)"],
                hovertemplate="%{x}: %{y:.1f}% bottom tier<extra></extra>"
            ))
            fig.add_trace(go.Bar(
                name="Middle ($35k–$75k)",
                x=tract_data["year"], y=tract_data["share_middle"],
                marker_color=TIER_COLORS["Middle ($35k–$75k)"],
                hovertemplate="%{x}: %{y:.1f}% middle tier<extra></extra>"
            ))
            fig.add_trace(go.Bar(
                name="Top ($75k+)",
                x=tract_data["year"], y=tract_data["share_top"],
                marker_color=TIER_COLORS["Top ($75k+)"],
                hovertemplate="%{x}: %{y:.1f}% top tier<extra></extra>"
            ))
        else:
            for i, (band, label) in enumerate(BAND_LABELS.items()):
                share_col = f"share_{band}"
                if share_col not in tract_data.columns:
                    continue
                fig.add_trace(go.Bar(
                    name=label,
                    x=tract_data["year"], y=tract_data[share_col],
                    marker_color=BAND_COLORS[i],
                    hovertemplate=f"%{{x}}: %{{y:.1f}}% {label}<extra></extra>"
                ))

        fig.update_layout(
            barmode="stack",
            height=380,
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis=dict(
                tickmode="array",
                tickvals=tract_data["year"].tolist(),
                tickformat="d",
            ),
            yaxis=dict(
                title="Share of households (%)",
                range=[0, 100],
                gridcolor="rgba(200,200,200,0.15)",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        )
        st.plotly_chart(fig, use_container_width=True)

        if view_mode == "All bands":
            st.caption(
                "Individual income bands carry wider margins of error than tier totals, "
                "particularly for small tracts. Use band-level detail for directional insight "
                "rather than precise estimates."
            )
