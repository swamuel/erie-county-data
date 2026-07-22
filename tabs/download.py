import streamlit as st

from lib.config import data_dictionary


def _row(title, caption, df, filename):
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"#### {title}")
        st.caption(caption)
    with c2:
        st.download_button(
            "Download CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=filename, mime="text/csv", use_container_width=True,
        )
    st.markdown("---")


def render(master_tract, master_zcta, master_county, snap):
    st.header("Download Data")
    st.markdown(
        "Download the datasets that power this app. Census figures are ACS 5-year "
        "estimates (2020–2023) and are verified against the U.S. Census Bureau API "
        "(see the About tab)."
    )
    st.markdown("---")

    _row("Census Tract Data",
         f"{master_tract['GEOID'].nunique()} tracts · {master_tract['year'].min()}–{master_tract['year'].max()} · "
         "income, poverty, rent burden, no-vehicle, education, population, age, race/ethnicity",
         master_tract, "nwpa_tracts.csv")

    _row("ZIP Code Data",
         f"{master_zcta['ZCTA5CE20'].nunique()} ZIP codes · {master_zcta['year'].min()}–{master_zcta['year'].max()} · "
         "ACS economics and demographics",
         master_zcta, "nwpa_zip_codes.csv")

    _row("County Data",
         f"{master_county['GEOID'].nunique()} counties · {master_county['year'].min()}–{master_county['year'].max()} · "
         "county-level ACS economic benchmarks",
         master_county, "nwpa_counties.csv")

    _row("SNAP Retailers",
         f"{len(snap):,} USDA-authorized SNAP/EBT retailers · USDA store type, "
         "authorization date, coordinates, urban/rural flag",
         snap, "nwpa_snap_retailers.csv")

    _row("Data Dictionary",
         f"{len(data_dictionary)} variable definitions with sources, geography, and caveats",
         data_dictionary, "nwpa_data_dictionary.csv")

    with st.expander("Preview census tract data"):
        st.dataframe(master_tract.head(20), use_container_width=True, hide_index=True)
    with st.expander("Preview data dictionary"):
        st.dataframe(data_dictionary, use_container_width=True, hide_index=True)
