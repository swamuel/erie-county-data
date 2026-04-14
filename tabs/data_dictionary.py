import streamlit as st


def render(data_dictionary):
    st.subheader("Data Dictionary")
    st.markdown(
        "Definitions, sources, and known limitations for every variable in the app. "
        "Use the search box to filter by variable name or keyword."
    )

    search_term = st.text_input("Search variables", placeholder="e.g. poverty, income, food...", key="dict_search")

    display_cols = ["Variable", "Plain Language", "Source", "Geography", "Years Available", "Caveats"]
    dict_display = data_dictionary[display_cols].copy()

    if search_term:
        mask = dict_display.apply(
            lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1
        )
        dict_display = dict_display[mask]

    if len(dict_display) == 0:
        st.info("No variables match your search.")
    else:
        st.dataframe(dict_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown(
        "**A note on ACS 5-year estimates:** All Census Bureau data in this app uses the "
        "American Community Survey 5-year estimates. These are rolling averages across a "
        "5-year period, not snapshots of a single year. The year shown in the sidebar "
        "represents the most recent year in that 5-year window (e.g., selecting 2023 uses "
        "data collected 2019–2023). This improves reliability for small geographies like "
        "census tracts but means the data does not capture rapid year-over-year changes."
    )
