import streamlit as st
import pandas as pd
import plotly.express as px

from lib.config import all_variables, HIGHER_IS_BETTER, TRACT_ONLY_VARS
from lib.helpers import format_value, get_benchmark_value, diff_string


def render(merged, census, zcta_data, benchmarks_counties, benchmark_row, available_vars, geography, year, selected_benchmark, compare_county):
    geo_id_col = {"Tract": "TRACTCE", "Zip Code": "ZCTA5CE20", "County": "COUNTYFP"}[geography]

    geo_label = {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]
    st.subheader(f"Insights — {geo_label} Level")

    ins1, ins2, ins3, ins4 = st.tabs([
        "Ranking Table", "County Summary", "Trend Charts", "Correlation Explorer"
    ])

    # Build a clean numeric dataframe from merged for insights
    insights_cols = ["display_name", "county_name"] + [
        col for col in available_vars.values() if col in merged.columns
    ]
    # county_name may not exist at county level
    if "county_name" not in merged.columns:
        merged = merged.copy()
        merged["county_name"] = merged.get("NAME", "Unknown")
    insights_df = merged[insights_cols].copy()
    insights_df = insights_df[insights_df["display_name"].notna()]

    # ── RANKING TABLE ────────────────────────────────────
    with ins1:
        st.markdown("Rank all areas by any variable. Use this to find the highest need or highest performing areas.")

        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        with r_col1:
            rank_var_label = st.selectbox("Variable", list(available_vars.keys()), key="rank_var")
            rank_var = available_vars[rank_var_label]
        with r_col2:
            rank_direction = st.radio("Sort", ["Highest first", "Lowest first"], key="rank_dir")
        with r_col3:
            rank_n = st.slider("Show top N", 5, len(insights_df), min(20, len(insights_df)), key="rank_n")
        with r_col4:
            county_filter = st.multiselect(
                "Filter by county",
                options=sorted(insights_df["county_name"].dropna().unique().tolist()),
                default=[],
                key="rank_county"
            )

        rank_df = insights_df.copy()
        if county_filter:
            rank_df = rank_df[rank_df["county_name"].isin(county_filter)]

        rank_df = rank_df[["display_name", "county_name", rank_var]].dropna(subset=[rank_var])
        rank_df = rank_df.sort_values(
            rank_var,
            ascending=(rank_direction == "Lowest first")
        ).head(rank_n).reset_index(drop=True)
        rank_df.index += 1

        bval_rank = get_benchmark_value(benchmark_row, rank_var)
        rank_df["vs Benchmark"] = rank_df[rank_var].apply(
            lambda v: diff_string(v, bval_rank) if bval_rank else "—"
        )
        rank_df["Value"] = rank_df[rank_var].apply(lambda v: format_value(v, rank_var))
        rank_df = rank_df.rename(columns={"display_name": geo_label, "county_name": "County"})
        rank_df = rank_df[[geo_label, "County", "Value", "vs Benchmark"]]

        st.dataframe(rank_df, use_container_width=True)

    # ── COUNTY SUMMARY ───────────────────────────────────
    with ins2:
        st.markdown("Side-by-side comparison of Erie and Crawford Counties on all available variables.")

        erie_bench = benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == "Erie County")
        ]
        crawford_bench = benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == "Crawford County")
        ]
        ref_bench = benchmark_row

        summary_rows = []
        for label, col in available_vars.items():
            erie_val = get_benchmark_value(erie_bench, col)
            crawford_val = get_benchmark_value(crawford_bench, col)
            ref_val = get_benchmark_value(ref_bench, col)
            summary_rows.append({
                "Variable": label,
                "Erie County": format_value(erie_val, col),
                "Crawford County": format_value(crawford_val, col),
                f"Benchmark ({selected_benchmark})": format_value(ref_val, col),
                "Erie vs Benchmark": diff_string(erie_val, ref_val) if ref_val else "—",
                "Crawford vs Benchmark": diff_string(crawford_val, ref_val) if ref_val else "—",
            })

        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # Headline metrics for Erie
        st.markdown("---")
        st.markdown("**Erie County Headlines**")
        h1, h2, h3, h4 = st.columns(4)
        for h_col, label, col, hib in [
            (h1, "Median Income", "median_household_income", True),
            (h2, "Poverty Rate", "poverty_rate", False),
            (h3, "Rent Burden", "rent_burden_rate", False),
            (h4, "No Vehicle", "no_vehicle_rate", False),
        ]:
            val = get_benchmark_value(erie_bench, col)
            bval = get_benchmark_value(ref_bench, col)
            diff = round(float(val) - float(bval), 1) if val and bval else None
            h_col.metric(label, format_value(val, col), delta=diff,
                         delta_color="normal" if hib else "inverse")

        st.markdown("**Crawford County Headlines**")
        h1b, h2b, h3b, h4b = st.columns(4)
        for h_col, label, col, hib in [
            (h1b, "Median Income", "median_household_income", True),
            (h2b, "Poverty Rate", "poverty_rate", False),
            (h3b, "Rent Burden", "rent_burden_rate", False),
            (h4b, "No Vehicle", "no_vehicle_rate", False),
        ]:
            val = get_benchmark_value(crawford_bench, col)
            bval = get_benchmark_value(ref_bench, col)
            diff = round(float(val) - float(bval), 1) if val and bval else None
            h_col.metric(label, format_value(val, col), delta=diff,
                         delta_color="normal" if hib else "inverse")

    # ── TREND CHARTS ─────────────────────────────────────
    with ins3:
        st.markdown("Track how a variable has changed from 2019 to 2023 across all areas.")

        t_col1, t_col2, t_col3 = st.columns(3)
        with t_col1:
            trend_var_label = st.selectbox("Variable", list(available_vars.keys()), key="trend_var")
            trend_var = available_vars[trend_var_label]
        with t_col2:
            trend_county = st.multiselect(
                "Filter by county",
                options=sorted(insights_df["county_name"].dropna().unique().tolist()),
                default=[],
                key="trend_county"
            )
        with t_col3:
            trend_top_n = st.slider("Max areas to show", 3, 20, 10, key="trend_n")

        # Build time series from correct source
        if geography == "Tract":
            ts_data = census.copy()
            ts_data["tract_code"] = ts_data["tract_code"].astype(str).str.zfill(6)
            ts_data = ts_data.merge(
                merged[["TRACTCE", "display_name", "county_name"]],
                left_on="tract_code", right_on="TRACTCE", how="inner"
            )
            ts_id = "display_name"
        elif geography == "Zip Code":
            ts_data = zcta_data.copy()
            ts_data["zcta"] = ts_data["zcta"].astype(str).str.zfill(5)
            ts_data = ts_data.merge(
                merged[["ZCTA5CE20", "display_name", "county_name"]],
                left_on="zcta", right_on="ZCTA5CE20", how="inner"
            )
            ts_id = "display_name"
        else:
            ts_data = pd.concat([
                benchmarks_counties[benchmarks_counties["name"] == "Erie County"].assign(display_name="Erie County", county_name="Erie"),
                benchmarks_counties[benchmarks_counties["name"] == "Crawford County"].assign(display_name="Crawford County", county_name="Crawford"),
            ])
            ts_id = "display_name"

        if trend_county:
            ts_data = ts_data[ts_data["county_name"].isin(trend_county)]

        if trend_var in ts_data.columns:
            # Pick top N areas by their value in the selected year
            latest = ts_data[ts_data["year"] == year].nlargest(trend_top_n, trend_var)
            top_names = latest[ts_id].tolist()
            ts_filtered = ts_data[ts_data[ts_id].isin(top_names)]

            # Benchmark line — use benchmarks_counties to get per-year values.
            # For National/PA/Erie benchmarks we do not have those DataFrames in scope here,
            # so we use benchmarks_counties filtered appropriately.
            bench_years = []
            for y in [2019, 2020, 2021, 2022, 2023]:
                if selected_benchmark == "Compare to Another PA County" and compare_county:
                    br = benchmarks_counties[
                        (benchmarks_counties["year"] == y) &
                        (benchmarks_counties["name"] == compare_county)
                    ]
                elif selected_benchmark in ("Erie County", "Crawford County"):
                    br = benchmarks_counties[
                        (benchmarks_counties["year"] == y) &
                        (benchmarks_counties["name"] == selected_benchmark)
                    ]
                else:
                    # For National / Pennsylvania we only have the current year resolved;
                    # fall back to Erie County benchmark as the nearest available series.
                    br = benchmarks_counties[
                        (benchmarks_counties["year"] == y) &
                        (benchmarks_counties["name"] == "Erie County")
                    ]
                bv = get_benchmark_value(br, trend_var)
                bench_years.append({"year": y, "value": bv, ts_id: f"Benchmark ({selected_benchmark})"})
            bench_ts = pd.DataFrame(bench_years)

            plot_df = pd.concat([
                ts_filtered[[ts_id, "year", trend_var]].rename(columns={trend_var: "value"}),
                bench_ts
            ])

            fig_trend = px.line(
                plot_df, x="year", y="value", color=ts_id,
                title=f"{trend_var_label} — 2019 to 2023",
                labels={"value": trend_var_label, "year": "Year", ts_id: "Area"}
            )
            fig_trend.update_traces(
                selector=lambda t: t.name.startswith("Benchmark"),
                line=dict(dash="dash", width=2)
            )
            fig_trend.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info(f"{trend_var_label} is not available for trend analysis at this geography level.")

    # ── CORRELATION EXPLORER ─────────────────────────────
    with ins4:
        st.markdown("Explore the relationship between any two variables across all areas.")

        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1:
            x_var_label = st.selectbox("X Axis", list(available_vars.keys()), key="corr_x")
            x_var = available_vars[x_var_label]
        with c_col2:
            y_var_label = st.selectbox(
                "Y Axis",
                [l for l in available_vars.keys() if l != x_var_label],
                key="corr_y"
            )
            y_var = available_vars[y_var_label]
        with c_col3:
            color_by = st.radio("Color by", ["County", "None"], horizontal=True, key="corr_color")

        scatter_df = insights_df[["display_name", "county_name", x_var, y_var]].dropna()

        if len(scatter_df) > 1:
            fig_scatter = px.scatter(
                scatter_df,
                x=x_var,
                y=y_var,
                color="county_name" if color_by == "County" else None,
                hover_name="display_name",
                trendline="ols",
                labels={
                    x_var: x_var_label,
                    y_var: y_var_label,
                    "county_name": "County"
                },
                title=f"{x_var_label} vs {y_var_label}"
            )
            fig_scatter.update_layout(height=500, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_scatter, use_container_width=True)

            # Correlation coefficient
            corr = scatter_df[[x_var, y_var]].corr().iloc[0, 1]
            direction = "positive" if corr > 0 else "negative"
            strength = "strong" if abs(corr) > 0.6 else "moderate" if abs(corr) > 0.3 else "weak"
            st.caption(f"Pearson correlation: **{corr:.2f}** — {strength} {direction} relationship across {len(scatter_df)} areas.")
        else:
            st.info("Not enough data to plot. Try switching to Tract geography for more data points.")
