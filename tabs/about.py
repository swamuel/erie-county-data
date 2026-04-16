import streamlit as st
import pandas as pd


def render(demographics, benchmarks_counties, year):
    st.title("Erie & Crawford County Community Data")
    st.markdown("### A public data tool for understanding neighborhood conditions across Erie and Crawford Counties, Pennsylvania.")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("What This Is")
        st.markdown(
            "This tool brings together census data, food security estimates, and transit information "
            "to help residents, nonprofits, planners, and researchers understand conditions at the "
            "neighborhood level. Data is available at the census tract, ZIP code, and county level "
            "for both Erie County and Crawford County."
        )

        st.subheader("How to Use It")
        st.markdown(
            "**Geography** — Use the sidebar to switch between Tract, ZIP Code, and County views. "
            "All tabs update to reflect the selected geography.\n\n"
            "**Year** — Select any year from 2019 to 2023. Data reflects ACS 5-year estimates "
            "centered on that year.\n\n"
            "**Benchmark** — Compare any area against national averages, Pennsylvania, Erie County, "
            "or any other PA county. Colors on the map are anchored to the selected benchmark.\n\n"
            "**Mode** — Simple mode shows the map and core controls. Advanced mode unlocks "
            "analytical tools like threshold filters, multi-variable queries, and transit analysis.\n\n"
            "**Insights tab** — Non-map analysis tools including a ranking table, county comparison "
            "dashboard, trend charts, and correlation explorer."
        )

    with col_b:
        st.subheader("Data Sources")
        sources = pd.DataFrame([
            {"Source": "U.S. Census Bureau — ACS 5-Year Estimates", "Variables": "Income, poverty, rent burden, no vehicle, education", "Geography": "Tract, ZIP", "Updated": "Annual"},
            {"Source": "Second Harvest / Feeding America", "Variables": "Food insecurity, unemployment, disability, homeownership", "Geography": "Tract", "Updated": "Annual"},
            {"Source": "EMTA (Erie Metropolitan Transit Authority)", "Variables": "Bus routes, stop locations, service frequency", "Geography": "Point", "Updated": "As published"},
            {"Source": "Census TIGER/Line", "Variables": "Tract, ZIP, and county boundaries", "Geography": "All", "Updated": "2023 vintage"},
        ])
        st.dataframe(sources, use_container_width=True, hide_index=True)

        st.subheader("Known Limitations")
        st.markdown(
            "- ACS estimates are 5-year rolling averages, not snapshots of a single year.\n"
            "- Food insecurity rates are modeled estimates, not measured counts.\n"
            "- Some Crawford County tracts have suppressed values due to small sample sizes.\n"
            "- Transit data reflects EMTA service only — Crawford County has no EMTA coverage.\n"
            "- ZIP code data does not include food insecurity or transit stop variables.\n"
            "- County-level data is sourced from benchmark files and may differ from tract aggregations."
        )

    st.markdown("---")
    st.subheader("County Snapshot")
    demo_latest = demographics[demographics["year"] == 2023].copy()
    erie_demo = demo_latest[demo_latest["county_fips"] == "049"]
    crawford_demo = demo_latest[demo_latest["county_fips"] == "039"]

    snap_col1, snap_col2 = st.columns(2)
    for snap_col, label, demo_df in [
        (snap_col1, "Erie County", erie_demo),
        (snap_col2, "Crawford County", crawford_demo),
    ]:
        with snap_col:
            st.markdown(f"**{label}**")
            if len(demo_df) > 0:
                total_pop = demo_df["total_population"].sum()
                med_age = demo_df["median_age"].mean()
                pct_white = (demo_df["white_non_hispanic"].sum() / demo_df["race_total"].sum() * 100) if "white_non_hispanic" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                pct_black = (demo_df["black_alone"].sum() / demo_df["race_total"].sum() * 100) if "black_alone" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                pct_hisp = (demo_df["hispanic_latino"].sum() / demo_df["race_total"].sum() * 100) if "hispanic_latino" in demo_df.columns and demo_df["race_total"].sum() > 0 else None
                st.metric("Total Population", f"{total_pop:,.0f}" if total_pop else "—")
                st.metric("Median Age", f"{med_age:.1f}" if med_age else "—")
                if pct_white:
                    st.caption(f"White non-Hispanic: {pct_white:.1f}%")
                if pct_black:
                    st.caption(f"Black or African American: {pct_black:.1f}%")
                if pct_hisp:
                    st.caption(f"Hispanic or Latino: {pct_hisp:.1f}%")

    st.markdown("---")
    st.subheader("About This Project")
    st.markdown(
        "This tool was built as an open resource for community organizations, planners, and residents "
        "working to understand and address inequality across Erie and Crawford Counties. "
        "Data is sourced from publicly available federal and local datasets. "
        "The project is ongoing — new data sources will be added over time.\n\n"
        f"Questions, corrections, or data suggestions: **samuelrandrew@gmail.com**\n\n"
        "Source code: [github.com/swamuel/erie-county-data](https://github.com/swamuel/erie-county-data)"
    )
