import streamlit as st
import pydeck as pdk
import pandas as pd
import json

from lib.config import ECONOMIC_VARS, HIGHER_IS_BETTER, TRACT_ONLY_VARS, MAP_STYLE, VIEW_STATE, TOOLTIP_STYLE
from lib.helpers import diverging_benchmark_color, get_benchmark_value, format_value, render_detail_panel
from lib.data_loader import load_boundaries


# Muted diverging palette shared with the snapshot map (amber ↔ blue).
_WORSE, _MID, _BETTER = (211, 150, 60), (238, 236, 231), (66, 123, 165)


def diverging_growth_color(val, cap, higher_better):
    if pd.isna(val):
        return [225, 228, 235, 140]
    signed = val if higher_better else -val
    t = max(0.0, min(1.0, (signed / cap) / 2 + 0.5))
    if t < 0.5:
        f = t / 0.5
        rgb = [int(_WORSE[i] + (_MID[i] - _WORSE[i]) * f) for i in range(3)]
    else:
        f = (t - 0.5) / 0.5
        rgb = [int(_MID[i] + (_BETTER[i] - _MID[i]) * f) for i in range(3)]
    return rgb + [190]


def render(merged, master_tract, master_zcta,
           benchmarks_national, benchmarks_pa, benchmarks_erie, benchmarks_counties,
           benchmark_row, geography, year, selected_benchmark, compare_county,
           geo_id_col):

    geo_label = {"Tract": "Tract", "Zip Code": "ZIP Code"}[geography]
    benchmark_label = compare_county if selected_benchmark == "Compare to Another Regional County" else selected_benchmark
    col_controls, col_map = st.columns([1, 3])

    with col_controls:
        econ_view = st.radio("View", ["Snapshot", "Change Over Time"],
                             horizontal=True, key="econ_view_toggle")
        st.markdown("---")

        if econ_view == "Snapshot":
            st.subheader("Economic Indicators")
            econ_vars = {k: v for k, v in ECONOMIC_VARS.items()
                         if (v not in TRACT_ONLY_VARS or geography == "Tract")
                         and v in merged.columns}
            if not econ_vars:
                st.info(f"No economic indicators available for {geo_label} geography.")
                return
            selected_layer = st.selectbox("Variable", list(econ_vars.keys()), key="econ_layer")
            column = econ_vars[selected_layer]

            st.markdown("---")
            st.markdown("**Explore a Location**")
            geo_options = ["None"] + sorted(merged["display_name"].dropna().tolist())
            selected_display = st.selectbox(f"Select {geo_label}", geo_options, key="econ_geo_select")
            if selected_display != "None":
                sel_row = merged[merged["display_name"] == selected_display].iloc[0]
                st.session_state.selected_geo = sel_row[geo_id_col]
                st.session_state.selected_geo_name = selected_display
        else:
            st.subheader("Change Over Time")
            st.caption("How did each area change relative to the benchmark?")
            GROWTH_VARS = {k: v for k, v in ECONOMIC_VARS.items()
                           if v not in TRACT_ONLY_VARS or geography == "Tract"}
            growth_var_label = st.selectbox("Variable", list(GROWTH_VARS.keys()), key="growth_var")
            growth_col = GROWTH_VARS[growth_var_label]
            higher_is_better_growth = HIGHER_IS_BETTER.get(growth_col, True)

            src = master_tract if geography == "Tract" else master_zcta
            all_years = sorted(src["year"].unique().tolist())
            gc1, gc2 = st.columns(2)
            growth_start = gc1.selectbox("From", all_years, index=0, key="growth_start")
            growth_end = gc2.selectbox("To", all_years, index=len(all_years) - 1, key="growth_end")
            if growth_start >= growth_end:
                st.error("'From' year must be before 'To' year.")
            else:
                growth_cap = st.slider("Color scale cap (± pts)", 5, 30, 15, 1,
                                       help="Differences beyond this saturate the color.",
                                       key="growth_cap")
                show_legend = st.checkbox("Show legend", value=False, key="growth_legend")

    with col_map:
        if econ_view == "Snapshot":
            bench_avg = get_benchmark_value(benchmark_row, column)
            reverse = not HIGHER_IS_BETTER.get(column, True)
            merged_econ = merged.assign(
                color=merged[column].apply(lambda x: diverging_benchmark_color(x, bench_avg, reverse=reverse))
            )
            valid_vals = merged_econ[column].dropna()
            if len(valid_vals):
                m1, m2, m3 = st.columns(3)
                m1.metric("Median", format_value(valid_vals.median(), column))
                m2.metric("Highest", format_value(valid_vals.max(), column))
                m3.metric("Lowest", format_value(valid_vals.min(), column))

            cols = [c for c in ["geometry", "color", "display_name", column] if c in merged_econ.columns]
            econ_json = json.loads(merged_econ[cols].to_json())
            st.pydeck_chart(pdk.Deck(
                layers=[pdk.Layer("GeoJsonLayer", data=econ_json,
                                  get_fill_color="properties.color",
                                  get_line_color=[255, 255, 255, 50],
                                  line_width_min_pixels=1, pickable=True)],
                initial_view_state=VIEW_STATE,
                tooltip={"html": f"<b>{{display_name}}</b><br/>{selected_layer}: {{{column}}}",
                         "style": TOOLTIP_STYLE},
                map_style=MAP_STYLE,
            ), height=560)

            if bench_avg is not None:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;font-size:11px;color:#64748b'>"
                    f"<span>Worse than {benchmark_label}</span>"
                    f"<div style='flex:1;height:12px;border-radius:3px;"
                    f"background:linear-gradient(to right,rgb(211,150,60),rgb(238,236,231),rgb(66,123,165))'></div>"
                    f"<span>Better than {benchmark_label}</span></div>"
                    f"<div style='font-size:10px;color:#94a3b8;text-align:center;margin-top:2px'>"
                    f"Neutral = near {benchmark_label} ({format_value(bench_avg, column)})</div>",
                    unsafe_allow_html=True)

            render_detail_panel(merged_econ, column, selected_layer, geo_id_col, geography,
                                 benchmark_row, benchmark_label)

        else:
            if growth_start >= growth_end:
                st.info("Select a valid year range to view change over time.")
            else:
                gdf_t, _, gdf_z = load_boundaries()
                if geography == "Tract":
                    src, key, gdf_base = master_tract, "GEOID", gdf_t
                else:
                    src, key, gdf_base = master_zcta, "ZCTA5CE20", gdf_z

                t0 = src[src["year"] == growth_start][[key, growth_col]].rename(columns={growth_col: "val_start"})
                t1 = src[src["year"] == growth_end][[key, growth_col]].rename(columns={growth_col: "val_end"})
                g = t0.merge(t1, on=key, how="inner")
                g = g[g["val_start"].notna() & (g["val_start"] != 0) & g["val_end"].notna()].copy()

                is_dollar = (growth_col == "median_household_income")
                if is_dollar:
                    g["tract_change"] = (g["val_end"] - g["val_start"]) / g["val_start"] * 100
                    change_label = "% growth"
                else:
                    g["tract_change"] = g["val_end"] - g["val_start"]
                    change_label = "pp change"

                bench_label = selected_benchmark
                if selected_benchmark == "National":
                    bench_src = benchmarks_national
                elif selected_benchmark == "Pennsylvania":
                    bench_src = benchmarks_pa
                elif selected_benchmark == "Erie County":
                    bench_src = benchmarks_erie
                else:
                    bench_src = benchmarks_counties[benchmarks_counties["name"] == compare_county]

                b0 = bench_src.loc[bench_src["year"] == growth_start, growth_col].values
                b1 = bench_src.loc[bench_src["year"] == growth_end, growth_col].values
                if len(b0) and len(b1) and b0[0] and b0[0] != 0:
                    bench_change = (b1[0] - b0[0]) / b0[0] * 100 if is_dollar else b1[0] - b0[0]
                else:
                    bench_change = None
                g["relative_change"] = (g["tract_change"] - bench_change
                                        if bench_change is not None else float("nan"))

                merged_growth = gdf_base.merge(g, on=key, how="left")
                merged_growth["color"] = merged_growth["relative_change"].apply(
                    lambda x: diverging_growth_color(x, growth_cap, higher_is_better_growth))

                def fmt(x):
                    if pd.isna(x): return "N/A"
                    return f"{'+' if x >= 0 else ''}{x:.1f}"

                if geography == "Zip Code":
                    merged_growth["t_name"] = merged_growth[key].astype(str)
                else:
                    merged_growth["t_name"] = merged_growth["NAMELSAD"].fillna("Unknown")
                merged_growth["t_abs"] = merged_growth["tract_change"].apply(fmt)
                merged_growth["t_rel"] = merged_growth["relative_change"].apply(fmt)
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
                m4.metric("Median change", fmt(merged_growth["tract_change"].median()) + f" {change_label}")

                if show_legend:
                    lc, mc, rc = st.columns([1, 2, 1])
                    good = "Improved" if higher_is_better_growth else "Fell"
                    bad = "Fell" if higher_is_better_growth else "Improved"
                    lc.markdown(f"<div style='background:linear-gradient(to right,rgb(211,150,60),rgb(238,236,231));height:12px;border-radius:3px'></div><div style='font-size:10px;color:#64748b'>{bad} behind</div>", unsafe_allow_html=True)
                    mc.markdown("<div style='background:rgb(238,236,231);height:12px;border-radius:3px'></div><div style='font-size:10px;color:#64748b;text-align:center'>Kept pace</div>", unsafe_allow_html=True)
                    rc.markdown(f"<div style='background:linear-gradient(to right,rgb(238,236,231),rgb(66,123,165));height:12px;border-radius:3px'></div><div style='font-size:10px;color:#64748b;text-align:right'>{good} vs benchmark</div>", unsafe_allow_html=True)

                cols = [key, "geometry", "color", "t_name", "t_abs", "t_rel", "t_start", "t_end"]
                growth_geojson = json.loads(
                    merged_growth[[c for c in cols if c in merged_growth.columns]].to_json())
                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer("GeoJsonLayer", data=growth_geojson,
                                      get_fill_color="properties.color",
                                      get_line_color=[80, 80, 80, 100],
                                      line_width_min_pixels=1, pickable=True, auto_highlight=True)],
                    initial_view_state=VIEW_STATE,
                    tooltip={"html": (f"<b>{{t_name}}</b><br/>{growth_var_label}: {{t_start}} &rarr; {{t_end}}<br/>"
                                      f"Change: {{t_abs}} {change_label}<br/>vs {bench_label}: {{t_rel}} {change_label}"),
                             "style": TOOLTIP_STYLE},
                    map_style=MAP_STYLE,
                ), height=560)

                with st.expander("Full ranking"):
                    rank = merged_growth[["t_name", "t_start", "t_end", "tract_change", "relative_change"]].copy()
                    rank.columns = [geo_label, f"{growth_start} Value", f"{growth_end} Value",
                                    f"Change ({change_label})", f"vs {bench_label} ({change_label})"]
                    rank = rank.dropna(subset=[f"Change ({change_label})"])
                    rank[f"Change ({change_label})"] = rank[f"Change ({change_label})"].round(1)
                    rank[f"vs {bench_label} ({change_label})"] = rank[f"vs {bench_label} ({change_label})"].round(1)
                    rank = rank.sort_values(f"vs {bench_label} ({change_label})", ascending=False)
                    st.dataframe(rank, use_container_width=True, hide_index=True)

