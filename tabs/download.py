import streamlit as st

from lib.exports import (
    build_combined_export,
    build_pantry_export,
    build_poi_export,
    build_data_dictionary,
    build_zcta_export,
    AI_CONTEXT,
)


def render(census, sh_data, demographics, cdc_places, food_atlas, poi_stats, pois, strat_df, pantry_monthly, pantry_index, zcta_data, cdc_places_zcta=None, zcta_poi_stats=None):
    st.header("Download Data")
    st.markdown(
        "Download the full Northwest PA regional dataset for use in your own analysis "
        "or to upload to an AI assistant for insight generation. All files include only "
        "the most recent available data year per variable."
    )

    # ── Build all exports ─────────────────────────────────────────────────────
    combined_df = build_combined_export(census, sh_data, demographics, cdc_places, food_atlas, poi_stats, strat_df)
    pantry_monthly_export, pantry_index_export = build_pantry_export(pantry_monthly, pantry_index)
    poi_export_df = build_poi_export(pois)
    dict_df = build_data_dictionary()
    zcta_df = build_zcta_export(zcta_data, cdc_places_zcta, zcta_poi_stats)

    # ── Download UI ───────────────────────────────────────────────────────────
    st.markdown("---")

    # Row 1 — Combined tract dataset
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### Combined Tract Dataset")
        st.caption(
            f"{len(combined_df):,} tracts · {len(combined_df.columns)} variables · "
            "ACS, CDC PLACES, USDA Food Atlas, Income Stratification, POI Service Stats"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=combined_df.to_csv(index=False).encode("utf-8"),
            file_name="nwpa_combined.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 2 — ZIP Code summary
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### ZIP Code Summary")
        st.caption(
            f"{zcta_df['zip_code'].nunique()} ZIP codes · {len(zcta_df.columns) - 4} variables · "
            "ACS economics, demographics, race/ethnicity · CDC PLACES health outcomes · "
            "2019–2023 ACS · 2023 CDC PLACES"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=zcta_df.to_csv(index=False).encode("utf-8"),
            file_name="nwpa_zip_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 3 — Community services POI file
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### Community Services — Point of Interest Data")
        st.caption(
            f"{len(poi_export_df):,} service locations · "
            "Food retail, health, civic & social services · "
            "Each point assigned to census tract for spatial analysis · "
            "USDA SNAP + OpenStreetMap"
        )
        st.warning(
            "**In progress:** SNAP food retailer data now covers all 11 counties. "
            "Health, civic, and social service locations (OpenStreetMap) are currently "
            "limited to Erie and Crawford counties — full regional coverage coming soon.",
            icon="🚧",
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=poi_export_df.to_csv(index=False).encode("utf-8"),
            file_name="nwpa_pois_clean.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 3 — Pantry monthly data
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### Food Pantry Monthly Data")
        st.caption(
            f"{len(pantry_monthly_export):,} agency-month rows · "
            f"{pantry_index_export['agency_name'].nunique()} agencies · "
            "Jul 2024 – Jun 2025 · Second Harvest Food Bank"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=pantry_monthly_export.to_csv(index=False).encode("utf-8"),
            file_name="nwpa_pantry_monthly.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 4 — Data dictionary
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### Data Dictionary")
        st.caption(
            f"{len(dict_df):,} variables defined · "
            "Variable names, definitions, sources, units, and years"
        )
    with col2:
        st.download_button(
            label="Download CSV",
            data=dict_df.to_csv(index=False).encode("utf-8"),
            file_name="data_dictionary.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")

    # Row 5 — AI context document
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### AI Context Document")
        st.caption(
            "Plain-English dataset summaries + 23 suggested prompts including spatial analysis. "
            "Upload alongside the CSV files when starting an AI analysis session."
        )
    with col2:
        st.download_button(
            label="Download TXT",
            data=AI_CONTEXT.encode("utf-8"),
            file_name="nwpa_ai_context.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("---")

    # ── Previews ──────────────────────────────────────────────────────────────
    with st.expander("Preview combined dataset"):
        st.dataframe(combined_df.head(20), use_container_width=True, hide_index=True)

    with st.expander("Preview data dictionary"):
        st.dataframe(dict_df, use_container_width=True, hide_index=True)
