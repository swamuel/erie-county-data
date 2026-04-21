import pandas as pd
import math
import json
import streamlit as st
from lib.config import all_variables, TRACT_ONLY_VARS


def value_to_color(value, national_avg, reverse=False, spread=0.25):
    if pd.isna(value) or pd.isna(national_avg):
        return [200, 200, 200, 140]
    low = national_avg * (1 - spread)
    high = national_avg * (1 + spread)
    normalized = (value - low) / (high - low)
    normalized = max(0, min(1, normalized))
    if reverse:
        normalized = 1 - normalized
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


def get_benchmark_row(selected_benchmark, compare_county, year,
                      benchmarks_national, benchmarks_pa,
                      benchmarks_erie, benchmarks_counties):
    if selected_benchmark == "National":
        return benchmarks_national[benchmarks_national["year"] == year]
    elif selected_benchmark == "Pennsylvania":
        return benchmarks_pa[benchmarks_pa["year"] == year]
    elif selected_benchmark == "Erie County":
        return benchmarks_erie[benchmarks_erie["year"] == year]
    elif selected_benchmark in benchmarks_counties["name"].unique().tolist():
        # Any in-region county selected directly as a benchmark
        return benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == selected_benchmark)
        ]
    elif selected_benchmark == "Compare to Another PA County":
        return benchmarks_counties[
            (benchmarks_counties["year"] == year) &
            (benchmarks_counties["name"] == compare_county)
        ]
    return benchmarks_national[benchmarks_national["year"] == year]


def get_benchmark_value(benchmark_row, column):
    if len(benchmark_row) > 0 and column in benchmark_row.columns:
        return benchmark_row[column].values[0]
    return None


def format_value(value, column):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "No data"
    if column == "median_household_income":
        return f"${value:,.0f}"
    return f"{value}%"


def diff_string(tract_val, benchmark_val, col=None):
    if tract_val is None or benchmark_val is None:
        return ""
    try:
        if pd.isna(tract_val):
            return ""
    except Exception:
        pass
    diff = round(float(tract_val) - float(benchmark_val), 1)
    arrow = "▲" if diff > 0 else "▼"
    return f"{arrow} {abs(diff)}"


def get_geo_label(geography):
    return {"Tract": "Tract", "Zip Code": "ZIP Code", "County": "County"}[geography]


def get_available_vars(geography, merged_df):
    """Return variables available for the current geography and merged dataframe."""
    available = {}
    for label, col in all_variables.items():
        if geography != "Tract" and col in TRACT_ONLY_VARS:
            continue
        if col in merged_df.columns:
            available[label] = col
    return available


def geocode_address(address):
    """Geocode an address using Nominatim. No API key required."""
    import urllib.request
    import urllib.parse
    query = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "ErieCountyDataApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            results = json.loads(resp.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None, None, None


def haversine_miles(lat1, lon1, lat2, lon2):
    """Distance in miles between two lat/lon points."""
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def render_detail_panel(merged_df, column, selected_layer, geo_id_col, geography, benchmark_row):
    geo_label = get_geo_label(geography)

    if st.session_state.selected_geo is None:
        st.caption(f"Select a {geo_label.lower()} above to see detailed data.")
        return

    geo_code = st.session_state.selected_geo
    geo_name = st.session_state.selected_geo_name
    geo_data = merged_df[merged_df[geo_id_col] == geo_code]

    if len(geo_data) == 0:
        st.warning(f"No data found for selected {geo_label.lower()}.")
        return

    row = geo_data.iloc[0]
    st.subheader(geo_name)

    m1, m2, m3, m4 = st.columns(4)
    for col_widget, var_label, var_col, higher_is_better in [
        (m1, "Median Income", "median_household_income", True),
        (m2, "Poverty Rate", "poverty_rate", False),
        (m3, "Rent Burden", "rent_burden_rate", False),
        (m4, "No Vehicle", "no_vehicle_rate", False),
    ]:
        with col_widget:
            val = row[var_col] if var_col in row.index else None
            bval = get_benchmark_value(benchmark_row, var_col)
            if bval and val is not None:
                try:
                    diff = round(float(val) - float(bval), 1)
                except Exception:
                    diff = None
            else:
                diff = None

            col_widget.metric(
                var_label,
                format_value(val, var_col),
                delta=diff,
                delta_color="normal" if higher_is_better else "inverse"
            )

    st.markdown("---")

    # Trend chart
    # Variable table
    st.markdown(f"**All Variables — {geo_label} Detail**")
    table_rows = []
    for label, col in all_variables.items():
        if geography != "Tract" and col in TRACT_ONLY_VARS:
            continue
        if col not in row.index:
            continue
        val = row[col]
        bval = get_benchmark_value(benchmark_row, col)
        table_rows.append({
            "Variable": label,
            f"This {geo_label}": format_value(val, col),
            "Benchmark": format_value(bval, col) if bval is not None else "—",
            "Difference": diff_string(val, bval) if bval is not None else "—"
        })
    if table_rows:
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No variable data available for this selection.")
