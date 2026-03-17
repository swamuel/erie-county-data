"""
income_growth_sandbox.py — Income growth vs benchmark sandbox.
Run with:  streamlit run income_growth_sandbox.py
Place in project root alongside app_v2.py.
"""

import streamlit as st
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import mapping

st.set_page_config(page_title="Income Growth Sandbox", layout="wide")

# ── CONSTANTS ─────────────────────────────────────────────
MAP_LIGHT  = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
MAP_DARK   = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
TIGER_URL  = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
COUNTY_URL = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
ERIE_FIPS  = ["049", "039"]

# ── DATA LOADING ──────────────────────────────────────────
@st.cache_data
def load_tracts():
    gdf = gpd.read_file(TIGER_URL)
    gdf = gdf[gdf["COUNTYFP"].isin(ERIE_FIPS) & (gdf["TRACTCE"] != "990000")]
    return gdf.to_crs(epsg=4326)

@st.cache_data
def load_county_outlines():
    gdf = gpd.read_file(COUNTY_URL)
    gdf = gdf[(gdf["STATEFP"] == "42") & (gdf["COUNTYFP"].isin(ERIE_FIPS))]
    return gdf.to_crs(epsg=4326)

@st.cache_data
def load_census():
    return pd.read_csv("data/raw/erie_tract_data.csv", dtype={"tract_code": str})

@st.cache_data
def load_benchmark(name):
    paths = {
        "National":     "data/raw/benchmarks_national.csv",
        "Pennsylvania": "data/raw/benchmarks_pennsylvania.csv",
        "Erie County":  "data/raw/benchmarks_erie.csv",
    }
    return pd.read_csv(paths[name])

# ── GROWTH COMPUTATION ────────────────────────────────────
def compute_growth(census_df, benchmark_name, start_year, end_year):
    bench   = load_benchmark(benchmark_name)
    b_start = bench.loc[bench["year"] == start_year, "median_household_income"].values
    b_end   = bench.loc[bench["year"] == end_year,   "median_household_income"].values

    if not len(b_start) or not len(b_end):
        st.error(f"Missing benchmark data for {start_year} or {end_year}.")
        return None

    bench_growth = (b_end[0] - b_start[0]) / b_start[0] * 100

    t0 = census_df[census_df["year"] == start_year][["tract_code", "median_household_income"]].rename(
        columns={"median_household_income": "income_start"})
    t1 = census_df[census_df["year"] == end_year  ][["tract_code", "median_household_income"]].rename(
        columns={"median_household_income": "income_end"})

    df = t0.merge(t1, on="tract_code", how="inner")
    df = df[
        df["income_start"].notna() & (df["income_start"] > 0) &
        df["income_end"].notna()   & (df["income_end"]   > 0)
    ].copy()

    df["tract_growth_pct"] = (df["income_end"] - df["income_start"]) / df["income_start"] * 100
    df["bench_growth_pct"] = round(bench_growth, 1)
    df["relative_growth"]  = df["tract_growth_pct"] - bench_growth
    df["TRACTCE"]          = df["tract_code"].astype(str).str.zfill(6)
    df["bench_start"]      = b_start[0]
    df["bench_end"]        = b_end[0]
    return df

# ── COLOR SCALE ───────────────────────────────────────────
def diverging_color(val, opacity, cap):
    alpha = int(opacity * 255)
    if pd.isna(val):
        return [200, 200, 200, 60]
    v = max(min(val / cap, 1.0), -1.0)
    if v >= 0:
        return [int(255 * (1 - v)), int(160 + 95 * v), int(255 * (1 - v)), alpha]
    else:
        v = abs(v)
        return [int(180 + 75 * v), int(255 * (1 - v)), int(255 * (1 - v)), alpha]

# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.title("Income Growth Sandbox")
st.sidebar.caption("Tract income growth relative to a benchmark.")

st.sidebar.markdown("---")
st.sidebar.markdown("### Map")
dark_mode = st.sidebar.toggle("Dark base map", value=False)
base_map  = MAP_DARK if dark_mode else MAP_LIGHT
opacity   = st.sidebar.slider("Fill opacity", 0.1, 1.0, 0.75, 0.05)
cap       = st.sidebar.slider(
    "Color scale cap (± pts)",
    min_value=5, max_value=30, value=15, step=1,
    help="Differences beyond this saturate the color. Lower = more contrast."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Comparison")
benchmark  = st.sidebar.selectbox("Compare against", ["National", "Pennsylvania", "Erie County"])
years      = [2019, 2020, 2021, 2022, 2023]
ca, cb     = st.sidebar.columns(2)
start_year = ca.selectbox("From", years, index=0)
end_year   = cb.selectbox("To",   years, index=4)

if start_year >= end_year:
    st.sidebar.error("'From' must be before 'To'.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown("### Filters")
show_outlines = st.sidebar.checkbox("County outlines", value=True)
show_no_data  = st.sidebar.checkbox("Highlight no-data tracts", value=False)
county_filter = st.sidebar.selectbox("County", ["Both", "Erie County", "Crawford County"])

# ── LOAD & COMPUTE ────────────────────────────────────────
with st.spinner("Loading..."):
    tracts   = load_tracts()
    census   = load_census()
    counties = load_county_outlines()

growth = compute_growth(census, benchmark, start_year, end_year)
if growth is None:
    st.stop()

bench_growth = growth["bench_growth_pct"].iloc[0]
bench_start  = growth["bench_start"].iloc[0]
bench_end    = growth["bench_end"].iloc[0]

# ── MERGE ─────────────────────────────────────────────────
merged = tracts.merge(growth, on="TRACTCE", how="left").copy()

if county_filter == "Erie County":
    merged = merged[merged["COUNTYFP"] == "049"].copy()
elif county_filter == "Crawford County":
    merged = merged[merged["COUNTYFP"] == "039"].copy()

# ── PREPARE LAYER DATA ───────────────────────────────────
# Add display columns to merged GeoDataFrame then convert via .to_json()
# This is the most reliable path — GeoPandas GeoJSON output works with Pydeck
merged["fill_color"] = merged["relative_growth"].apply(
    lambda x: diverging_color(x, opacity, cap)
)
merged["line_color"] = [[80, 80, 80, 100]] * len(merged)

# Flat string fields for tooltip substitution
def fmt_rel(x):
    if pd.isna(x): return "N/A"
    return f"+{x:.1f} pts" if x >= 0 else f"{x:.1f} pts"

merged["t_name"] = merged["NAMELSAD"].fillna("Unknown")
merged["t_rel"]  = merged["relative_growth"].apply(fmt_rel)
merged["t_tg"]   = merged["tract_growth_pct"].apply(
    lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
merged["t_bg"]   = merged["bench_growth_pct"].apply(
    lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
merged["t_inc"]  = merged.apply(
    lambda r: f"${int(r.income_start):,} to ${int(r.income_end):,}"
    if pd.notna(r.get("income_start")) and pd.notna(r.get("income_end")) else "N/A",
    axis=1
)

layer_cols = [
    "geometry", "TRACTCE",
    "fill_color", "line_color",
    "t_name", "t_rel", "t_tg", "t_bg", "t_inc"
]
geojson = json.loads(merged[layer_cols].to_json())

# ── LAYERS ────────────────────────────────────────────────
layers = []

layers.append(pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    get_fill_color="properties.fill_color",
    get_line_color="properties.line_color",
    line_width_min_pixels=1,
    pickable=True,
    auto_highlight=True,
))

if show_outlines:
    county_geojson = json.loads(counties[["geometry", "NAME"]].to_json())
    layers.append(pdk.Layer(
        "GeoJsonLayer",
        data=county_geojson,
        get_fill_color=[0, 0, 0, 0],
        get_line_color=[30, 30, 30, 220],
        line_width_min_pixels=2,
        pickable=False,
    ))

# ── HEADER ────────────────────────────────────────────────
st.title("Income Growth vs Benchmark")
st.caption(
    f"Tract median household income growth **{start_year}–{end_year}** "
    f"compared to **{benchmark}** average growth of **{bench_growth:.1f}%** "
    f"(${bench_start:,.0f} \u2192 ${bench_end:,.0f})"
)

# Color legend bar
lc, mc, rc = st.columns([1, 2, 1])
lc.markdown(
    f"<div style='background:linear-gradient(to right,rgb(255,70,70),white);"
    f"height:14px;border-radius:4px;'></div>"
    f"<div style='font-size:11px;color:#64748b;margin-top:3px;'>Fell behind (&minus;{cap} pts)</div>",
    unsafe_allow_html=True
)
mc.markdown(
    f"<div style='background:white;border:1px solid #cbd5e1;"
    f"height:14px;border-radius:4px;'></div>"
    f"<div style='font-size:11px;color:#64748b;text-align:center;margin-top:3px;'>"
    f"Kept pace with {benchmark}</div>",
    unsafe_allow_html=True
)
rc.markdown(
    f"<div style='background:linear-gradient(to right,white,rgb(30,190,90));"
    f"height:14px;border-radius:4px;'></div>"
    f"<div style='font-size:11px;color:#64748b;text-align:right;margin-top:3px;'>"
    f"Outpaced (+{cap} pts)</div>",
    unsafe_allow_html=True
)

st.markdown("<br/>", unsafe_allow_html=True)

# ── MAP ───────────────────────────────────────────────────
st.pydeck_chart(
    pdk.Deck(
        map_style=base_map,
        initial_view_state=pdk.ViewState(
            latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0
        ),
        layers=layers,
        tooltip={
            "html": "<b>{t_name}</b><br/>vs benchmark: <b>{t_rel}</b><br/>Tract growth: {t_tg}<br/>Benchmark growth: {t_bg}<br/>{t_inc}",
            "style": {"backgroundColor":"#1e293b","color":"white","fontSize":"12px","padding":"10px","borderRadius":"4px"}
        },
    ),
    use_container_width=True,
    height=580,
)

# ── SUMMARY STATS ─────────────────────────────────────────
st.markdown("---")
st.markdown("### Summary")

valid  = growth[growth["relative_growth"].notna()]
ahead  = int((valid["relative_growth"] > 0).sum())
behind = int((valid["relative_growth"] < 0).sum())
med    = valid["relative_growth"].median()
mean   = valid["relative_growth"].mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tracts ahead of benchmark",     f"{ahead}")
c2.metric("Tracts behind benchmark",       f"{behind}")
c3.metric("Median relative growth",        f"{med:+.1f} pts")
c4.metric("Mean relative growth",          f"{mean:+.1f} pts")
c5.metric(f"{benchmark} benchmark growth", f"{bench_growth:.1f}%")

# ── RANKING TABLE ─────────────────────────────────────────
st.markdown("### Tract ranking")
st.caption("Sorted by relative growth. Click any column header to re-sort.")

table = valid.merge(
    tracts[["TRACTCE", "NAMELSAD", "COUNTYFP"]].drop_duplicates(),
    on="TRACTCE", how="left"
)
table["County"] = table["COUNTYFP"].map({"049": "Erie", "039": "Crawford"})

display = table[[
    "NAMELSAD", "County",
    "income_start", "income_end",
    "tract_growth_pct", "relative_growth"
]].copy()
display.columns = [
    "Tract", "County",
    f"{start_year} Income", f"{end_year} Income",
    "Growth %", f"vs {benchmark} (pts)"
]
display[f"{start_year} Income"]      = display[f"{start_year} Income"].apply(lambda x: f"${int(x):,}")
display[f"{end_year} Income"]        = display[f"{end_year} Income"].apply(  lambda x: f"${int(x):,}")
display["Growth %"]                  = display["Growth %"].round(1)
display[f"vs {benchmark} (pts)"]     = display[f"vs {benchmark} (pts)"].round(1)
display = display.sort_values(f"vs {benchmark} (pts)", ascending=False)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Growth %":                    st.column_config.NumberColumn(format="%.1f%%"),
        f"vs {benchmark} (pts)":       st.column_config.NumberColumn(format="%.1f"),
    }
)