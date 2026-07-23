import streamlit as st
import pandas as pd

from lib.constants import APP_TITLE, APP_REGION


def render(master_tract, benchmarks_counties, year):
    st.title(APP_TITLE)
    st.markdown(f"### A public data tool for understanding neighborhood conditions across the {APP_REGION}.")

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("What This Is")
        st.markdown(
            "This tool brings together U.S. Census data and USDA SNAP retailer locations to help "
            "residents, nonprofits, and planners understand economic and demographic conditions at "
            f"the neighborhood level across all 11 counties in the {APP_REGION}."
        )
        st.subheader("How to Use It")
        st.markdown(
            "**Geography** — Use the sidebar to switch between ZIP Code and Tract views. "
            "Every tab updates to the selected geography.\n\n"
            "**Year** — Choose any year from 2020 to 2023. Figures are ACS 5-year estimates.\n\n"
            "**Benchmark** — Compare any area against national, Pennsylvania, Erie County, or another "
            "regional county. Map colors are anchored to the selected benchmark.\n\n"
            "**Tabs** — *Demographics* and *Economic* map census indicators; *SNAP Retailers* maps "
            "USDA-authorized stores with a coverage area, SNAP-participation context, and an address "
            "search; *Download* provides the underlying data; *Data Dictionary* defines every variable."
        )

    with col_b:
        st.subheader("Data Sources")
        sources = pd.DataFrame([
            {"Source": "U.S. Census Bureau — ACS 5-Year Estimates",
             "Variables": "Income, poverty, rent burden, no vehicle, education, population, age, race/ethnicity",
             "Geography": "Tract, ZIP, County", "Years": "2020–2023"},
            {"Source": "USDA FNS — SNAP Retailer Locator",
             "Variables": "Authorized SNAP/EBT retailers", "Geography": "Point", "Years": "Current"},
            {"Source": "Census TIGER/Line",
             "Variables": "Tract, ZIP, and county boundaries", "Geography": "All", "Years": "2020 vintage"},
        ])
        st.dataframe(sources, use_container_width=True, hide_index=True)

        st.subheader("Known Limitations")
        st.markdown(
            "- ACS estimates are 5-year rolling averages, not single-year snapshots. Small geographies "
            "carry wider margins of error, so a single tract's number should be read as an estimate.\n"
            "- **Cameron and Forest counties** have very small populations (~4,500 and ~7,000); some "
            "estimates may be suppressed or missing.\n"
            "- SNAP authorization changes frequently; the map is a current snapshot. Being authorized "
            "does not indicate how much healthy food a store stocks.\n"
            "- 2019 is excluded because it predates the 2020 tract boundaries used for mapping."
        )

    st.markdown("---")
    st.subheader("About This Project")
    st.markdown(
        f"An open resource for community organizations, planners, and residents working across the "
        f"{APP_REGION}. Data comes from publicly available federal datasets and is verified against "
        "the source before each release.\n\n"
        "Questions, corrections, or data suggestions: **samuelrandrew@gmail.com**"
    )
