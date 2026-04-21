import streamlit as st
import pandas as pd
from lib.constants import APP_TITLE, APP_REGION, COUNTY_NAMES, COUNTY_FIPS, SMALL_COUNTIES


def render(demographics, benchmarks_counties, year):
    st.title(APP_TITLE)
    st.markdown(f"### A public data tool for understanding neighborhood conditions across the {APP_REGION}.")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("What This Is")
        st.markdown(
            "This tool brings together census data, food security estimates, and service location data "
            "to help residents, nonprofits, planners, and researchers understand conditions at the "
            "neighborhood level. Data is available at the census tract, ZIP code, and county level "
            f"across all 11 counties in the {APP_REGION}."
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
            {"Source": "CDC PLACES", "Variables": "Health outcome estimates (diabetes, depression, obesity, etc.)", "Geography": "Tract, ZIP", "Updated": "Annual"},
            {"Source": "USDA Food Environment Atlas", "Variables": "Food desert classifications, food access metrics", "Geography": "Tract", "Updated": "2020"},
            {"Source": "EMTA (Erie Metropolitan Transit Authority)", "Variables": "Bus routes, stop locations, service frequency", "Geography": "Point", "Updated": "As published"},
            {"Source": "Census TIGER/Line", "Variables": "Tract, ZIP, and county boundaries", "Geography": "All", "Updated": "2023 vintage"},
        ])
        st.dataframe(sources, use_container_width=True, hide_index=True)

        st.subheader("Known Limitations")
        st.markdown(
            "- ACS estimates are 5-year rolling averages, not snapshots of a single year.\n"
            "- Food insecurity rates are modeled estimates, not measured counts.\n"
            "- **Cameron and Forest counties** have very small populations (~4,500 and ~7,000 residents). "
            "ACS estimates for these counties may be suppressed, have wide margins of error, or show "
            "as missing in tract-level views.\n"
            "- Transit data reflects EMTA service only — most counties outside Erie have no EMTA coverage.\n"
            "- ZIP code data does not include food insecurity or transit stop variables.\n"
            "- County-level data is sourced from benchmark files and may differ from tract aggregations."
        )

    st.markdown("---")
    st.subheader("Regional Snapshot")
    demo_latest = demographics[demographics["year"] == 2023].copy()

    county_cols = st.columns(min(4, len(COUNTY_FIPS)))
    for i, (county_name, fips) in enumerate(COUNTY_FIPS.items()):
        col = county_cols[i % len(county_cols)]
        county_demo = demo_latest[demo_latest["county_fips"] == fips]
        with col:
            st.markdown(f"**{county_name}**")
            if len(county_demo) > 0:
                total_pop = county_demo["total_population"].sum()
                st.metric("Population", f"{total_pop:,.0f}" if total_pop else "—")
                if county_name in SMALL_COUNTIES:
                    st.caption("⚠️ Small county — estimates may be suppressed")
            else:
                st.caption("No data")

    st.markdown("---")
    st.subheader("About This Project")
    st.markdown(
        f"This tool was built as an open resource for community organizations, planners, and residents "
        f"working to understand and address inequality across the {APP_REGION}. "
        "Data is sourced from publicly available federal and local datasets. "
        "The project is ongoing — new data sources will be added over time.\n\n"
        "Questions, corrections, or data suggestions: **samuelrandrew@gmail.com**\n\n"
        "Source code: [github.com/swamuel/erie-county-data](https://github.com/swamuel/erie-county-data)"
    )
