import pandas as pd


AI_CONTEXT = """# Erie & Crawford County Community Data — AI Context Document

## About This Dataset
This dataset was compiled from public sources by a community data project covering Erie County
and Crawford County, Pennsylvania. It is designed to support analysis of economic conditions,
health outcomes, food access, service accessibility, and food assistance needs at the census
tract level.

All tract-level data reflects the most recent available year (typically 2023 for ACS and CDC
data, 2020 for USDA food access data). The pantry file is monthly agency-level data from
July 2024 through June 2025. The services/POI data reflects current locations as of 2024-2026.

---

## Files Included

### 1. erie_crawford_combined.csv
One row per census tract. Contains variables from six sources joined on census tract GEOID.

**Sources included:**
- American Community Survey (ACS) 5-Year Estimates — demographics and economic indicators
- Second Harvest / Feeding America — food insecurity, unemployment, disability, homeownership
- CDC PLACES 2023 — tract-level health outcome estimates
- USDA Food Environment Atlas 2020 — food access and food desert classifications
- ACS B19001 — household income distribution by bracket (2023)
- USDA SNAP + OpenStreetMap — service counts and proximity distances by tract

### 2. erie_crawford_pantry_monthly.csv
One row per agency per month. Monthly reporting data from Second Harvest Food Bank of
Northwest PA partner agencies in Erie and Crawford counties, July 2024 through June 2025.

**Key fields:** agency_name, county, program_type, date, total_individuals, children, adults,
seniors, new_households

**Program types:** Food Pantry/TEFAP, Food Pantry/No TEFAP, Produce Express, BackPacks,
School Pantry, Non-Emerg. Meal/Snack, Kids Cafe

### 3. erie_crawford_pois_clean.csv
One row per point of interest (service location). Each POI is assigned to a census tract
via spatial join, enabling linkage to tract-level demographics and outcomes.

**Key fields:** tract_geoid, tract_name, county, name, address, lat, lon,
primary_category, type, subtype, snap_eligible

**Categories:** Food & Grocery (supermarkets, grocery stores, farmers markets, convenience),
Health (hospitals, pharmacies, clinics), Civic & Social (libraries, schools, community
centers, social services)

**Use this file to:**
- Map service locations against demographic conditions
- Find addresses of specific service types in high-need areas
- Join back to the combined CSV using tract_geoid to enrich point data with tract statistics

### 4. data_dictionary.csv
Full variable definitions, sources, units, and years for every column in the combined file.

---

## Suggested Analysis Prompts

### Identifying Need
1. Which census tracts have the highest combined burden of poverty, food insecurity, and poor
   health outcomes? Rank the top 10 most at-risk tracts across Erie and Crawford counties.

2. Which tracts have both high poverty rates and high uninsured rates? What does this suggest
   about healthcare access?

3. Which tracts have the highest share of bottom-tier households combined with the worst
   health outcomes? Are these the same tracts?

### Health & Economic Relationships
4. Is there a relationship between median household income and diabetes or obesity rates?
   Describe the pattern you see.

5. Which health indicators are most strongly associated with poverty rate in this dataset?

6. Compare the health outcomes of tracts in the bottom income tier vs the top income tier.
   What differences stand out?

### Food Access
7. How many residents in Erie and Crawford counties live in census tracts classified as food
   deserts? Which tracts are most affected?

8. Which tracts are low income but NOT classified as food deserts? What might explain adequate
   food access despite low income?

### Income & Inequality
9. Which tracts saw the largest shift in income distribution between 2019 and 2023? Did the
   share of low-income households grow or shrink?

10. Is income stratification correlated with any health outcomes in this dataset?

### Pantry & Food Assistance
11. Which food pantries served the most individuals over the reporting period? Are there
    seasonal patterns in demand?

12. Is the share of new households at food pantries growing month over month? What does this
    suggest about whether demand is expanding?

13. Which program types serve the most children? The most seniors?

### County Comparisons
14. How do Erie and Crawford counties compare on key economic and health indicators?

15. Are there patterns in Crawford County that differ meaningfully from Erie County, given
    Crawford is more rural?

### Spatial Access & Services
16. Which census tracts have zero grocery stores and also have high food insecurity rates?
    Are these tracts also classified as food deserts by the USDA definition?

17. Which tracts have the highest rates of residents without vehicles AND the greatest
    distance to the nearest grocery store? These represent the most acute food access gaps.

18. Compare SNAP-eligible store density (snap_store_per_1k) across tracts by income tier.
    Do low-income tracts have better or worse access to SNAP-authorized retailers?

19. Which tracts are NOT classified as food deserts under the standard distance threshold
    (food_desert_1_10 = 0) but ARE flagged by the vehicle-access definition
    (food_desert_vehicle = 1)? What do these tracts have in common?

20. Is there a relationship between the number of pharmacies or clinics in a tract and
    health outcomes like diabetes rate or poor physical health rate?

21. Identify tracts that are more than 5 miles from the nearest hospital AND have high
    rates of any disability or poor physical health. Which communities face the greatest
    geographic barriers to emergency care?

22. Which tracts have the highest social services counts? Do these correlate with higher
    poverty rates — or are there high-need tracts with few social services?

23. Build a composite access score for each tract using nearest_grocery_full_miles,
    nearest_pharmacy_miles, nearest_clinic_miles, and nearest_library_miles. Which tracts
    score worst on overall service proximity?

---

## Important Caveats
- ACS 5-year estimates are averages over a 5-year period and carry margins of error,
  particularly for small tracts.
- CDC PLACES estimates are modeled, not directly measured.
- USDA Food Atlas data is from 2020 and may not reflect current conditions.
- low_access_pop and low_access_low_income_pop are null for approximately 36% of tracts
  due to USDA suppression methodology for small or rural tracts.
- Income band-level estimates (B19001) carry wider margins of error than median income
  estimates at the tract level.
- Pantry data reflects agencies that report to Second Harvest and may not capture all food
  assistance activity in the region.
- POI data is sourced from USDA SNAP retailer lists and OpenStreetMap and may not be
  complete for all service types.
"""


def build_combined_export(census, sh_data, demographics, cdc_places, food_atlas, poi_stats, strat_df):
    latest_year = census["year"].max()

    # ACS core economic variables
    acs = census[census["year"] == latest_year].copy()
    acs_cols = [
        "tract_code", "county_name", "year",
        "median_household_income", "poverty_rate",
        "rent_burden_rate", "no_vehicle_rate",
        "bachelors_rate", "median_age",
    ]
    acs = acs[[c for c in acs_cols if c in acs.columns]].copy()
    acs["tract_code"] = acs["tract_code"].astype(str).str.zfill(6)
    county_fips_map = {"Erie County": "049", "Crawford County": "039"}
    acs["geoid"] = (
        "42" +
        acs["county_name"].map(county_fips_map).fillna("000") +
        acs["tract_code"]
    )

    # Second Harvest — unemployment, disability, homeownership, food insecurity
    sh_latest = sh_data[sh_data["year"] == sh_data["year"].max()].copy()
    sh_latest["tract_code"] = sh_latest["tract_code"].astype(str).str.zfill(6)
    sh_cols = ["tract_code", "unemployment_rate", "disability_rate",
               "homeownership_rate", "food_insecurity_rate"]
    sh_latest = sh_latest[[c for c in sh_cols if c in sh_latest.columns]].drop_duplicates("tract_code")

    # Demographics — population, race/ethnicity
    demo_latest = demographics[demographics["year"] == latest_year].copy()
    demo_latest["tract_code"] = demo_latest["tract_code"].astype(str).str.zfill(6)
    demo_cols = ["tract_code", "total_population", "pct_white_non_hispanic",
                 "pct_black", "pct_hispanic", "pct_asian", "pct_other"]
    demo_latest = demo_latest[[c for c in demo_cols if c in demo_latest.columns]].drop_duplicates("tract_code")

    # CDC PLACES health outcomes
    health_cols = [
        "tract_code",
        "diabetes_rate", "high_bp_rate", "obesity_rate", "smoking_rate",
        "depression_rate", "poor_mental_health_rate", "poor_physical_health_rate",
        "no_insurance_rate", "physical_inactivity_rate", "any_disability_rate",
    ]
    health = cdc_places.copy()
    health["tract_code"] = health["tract_code"].astype(str).str.zfill(6)
    health = health[[c for c in health_cols if c in health.columns]].drop_duplicates("tract_code")

    # USDA Food Atlas
    atlas_cols = [
        "tract_code",
        "food_desert_1_10", "food_desert_half_10", "food_desert_vehicle",
        "low_income_tract", "low_access_pop", "low_access_low_income_pop",
    ]
    atlas = food_atlas.copy()
    atlas["tract_code"] = atlas["tract_code"].astype(str).str.zfill(6)
    atlas = atlas[[c for c in atlas_cols if c in atlas.columns]].drop_duplicates("tract_code")

    # Income stratification
    strat_latest = strat_df[strat_df["year"] == strat_df["year"].max()].copy()
    strat_cols = ["geoid", "share_bottom", "share_middle", "share_top",
                  "hh_bottom", "hh_middle", "hh_top", "total_households"]
    strat_latest = strat_latest[[c for c in strat_cols if c in strat_latest.columns]].copy()
    strat_latest["tract_code"] = strat_latest["geoid"].astype(str).str[5:].str.zfill(6)

    # POI tract stats — counts and nearest distances only (drop raw meter columns)
    poi_exp = poi_stats.copy()
    poi_exp["TRACTCE"] = poi_exp["TRACTCE"].astype(str).str.zfill(6)
    poi_keep = (
        ["TRACTCE"] +
        [c for c in poi_exp.columns if c.startswith("count_")] +
        [c for c in poi_exp.columns if c.endswith("_miles")]
    )
    poi_exp = poi_exp[[c for c in poi_keep if c in poi_exp.columns]]
    poi_exp = poi_exp.rename(columns={"TRACTCE": "tract_code"})

    # Join everything
    combined = acs.copy()
    combined = combined.merge(sh_latest,   on="tract_code", how="left")
    combined = combined.merge(demo_latest,  on="tract_code", how="left")
    combined = combined.merge(health,       on="tract_code", how="left")
    combined = combined.merge(atlas,        on="tract_code", how="left")
    combined = combined.merge(strat_latest.drop(columns=["geoid"]), on="tract_code", how="left")
    combined = combined.merge(poi_exp,      on="tract_code", how="left")

    # Derived spatial density columns
    if "total_population" in combined.columns and "count_grocery_any" in combined.columns:
        combined["food_retail_per_1k"] = (
            combined["count_grocery_any"] / combined["total_population"] * 1000
        ).round(2)
    if "total_population" in combined.columns and "count_snap_retailers" in combined.columns:
        combined["snap_store_per_1k"] = (
            combined["count_snap_retailers"] / combined["total_population"] * 1000
        ).round(2)

    # Column ordering
    id_cols = ["geoid", "tract_code", "county_name", "year"]
    other_cols = [c for c in combined.columns if c not in id_cols]
    combined = combined[id_cols + other_cols]
    combined = combined.sort_values(["county_name", "tract_code"]).reset_index(drop=True)
    return combined


def build_pantry_export(pantry_monthly, pantry_index):
    return pantry_monthly, pantry_index


def build_poi_export(pois):
    import os
    poi_clean = "data/processed/erie_crawford_pois_clean.csv"
    if os.path.exists(poi_clean):
        return pd.read_csv(poi_clean)
    # Fallback to raw POIs if process_poi_export.py hasn't been run yet
    raw = pois.copy()
    keep = ["name", "address", "lat", "lon", "primary_category", "type", "subtype"]
    keep = [c for c in keep if c in raw.columns]
    if "snap_eligible" in raw.columns:
        raw["snap_eligible"] = raw["snap_eligible"].astype(str).str.lower().map(
            {"true": "Yes", "false": "No"}
        ).fillna("No")
    else:
        raw["snap_eligible"] = "No"
    return raw[keep + ["snap_eligible"]]


def build_zcta_export(zcta_data, cdc_places_zcta=None, zcta_poi_stats=None):
    import pandas as pd

    # Use the most recent year only for the download
    df = zcta_data.copy()
    df["zcta"] = df["zcta"].astype(str).str.zfill(5)
    latest_year = df["year"].max()
    df = df[df["year"] == latest_year].copy()

    # Merge CDC PLACES health data if available
    if cdc_places_zcta is not None and len(cdc_places_zcta.columns) > 1:
        health = cdc_places_zcta.copy()
        health["zcta"] = health["zcta"].astype(str).str.zfill(5)
        df = df.merge(health, on="zcta", how="left")

    # Merge POI counts and nearest distances if available
    if zcta_poi_stats is not None and len(zcta_poi_stats.columns) > 1:
        poi = zcta_poi_stats.copy()
        poi["ZCTA5CE20"] = poi["ZCTA5CE20"].astype(str).str.zfill(5)
        # Drop raw meter columns — keep only human-readable _miles columns
        poi = poi[[c for c in poi.columns if not c.endswith("_m") or c.endswith("_miles")]]
        df = df.merge(poi, left_on="zcta", right_on="ZCTA5CE20", how="left")
        df = df.drop(columns=["ZCTA5CE20"], errors="ignore")

    id_cols     = ["zcta", "area_name", "county_name", "year"]
    acs_cols    = ["median_household_income", "poverty_rate", "rent_burden_rate",
                   "no_vehicle_rate", "bachelors_rate", "unemployment_rate",
                   "homeownership_rate", "total_population", "median_age"]
    demo_cols   = ["pct_white_non_hispanic", "pct_black", "pct_hispanic",
                   "pct_asian", "pct_other"]
    health_cols = ["diabetes_rate", "high_bp_rate", "depression_rate",
                   "obesity_rate", "smoking_rate", "no_insurance_rate",
                   "poor_mental_health_rate", "poor_physical_health_rate",
                   "asthma_rate", "heart_disease_rate", "stroke_rate",
                   "copd_rate", "any_disability_rate", "sleep_deprivation_rate",
                   "physical_inactivity_rate", "binge_drinking_rate",
                   "arthritis_rate", "high_cholesterol_rate", "cancer_rate",
                   "poor_general_health_rate"]
    poi_cols    = [c for c in df.columns
                   if c.startswith("count_") or c.endswith("_miles")]

    keep = [c for c in id_cols + acs_cols + demo_cols + health_cols + poi_cols
            if c in df.columns]
    df = df[keep].sort_values(["county_name", "zcta"]).reset_index(drop=True)
    df = df.rename(columns={"zcta": "zip_code"})
    return df


def build_data_dictionary():
    rows = [
        # Identity
        ("geoid",                     "Census Tract GEOID",              "11-digit FIPS code uniquely identifying each census tract",                                    "Census Bureau",             "ID",      "2023"),
        ("tract_code",                "Tract Code",                      "6-digit tract code within Pennsylvania",                                                        "Census Bureau",             "ID",      "2023"),
        ("county_name",               "County Name",                     "Erie County or Crawford County",                                                                "Census Bureau",             "Text",    "2023"),
        ("year",                      "ACS Reference Year",              "The most recent year in the 5-year ACS estimate window used for ACS variables",                "Census Bureau",             "Year",    "2023"),
        # ACS Economic
        ("median_household_income",   "Median Household Income",         "Median annual household income in dollars",                                                     "ACS 5-Year, B19013",        "Dollars", "2023"),
        ("poverty_rate",              "Poverty Rate",                    "Percent of population with income below federal poverty level",                                 "ACS 5-Year, B17001",        "%",       "2023"),
        ("unemployment_rate",         "Unemployment Rate",               "Percent of civilian labor force that is unemployed",                                            "Second Harvest / Feeding America", "%", "2023"),
        ("no_vehicle_rate",           "No Vehicle Rate",                 "Percent of households with no vehicle available",                                               "ACS 5-Year, B08201",        "%",       "2023"),
        ("rent_burden_rate",          "Rent Burden Rate",                "Percent of renters paying 30%+ of income on rent",                                             "ACS 5-Year, B25070",        "%",       "2023"),
        ("bachelors_rate",            "Bachelor's Degree Rate",          "Percent of adults 25+ with a bachelor's degree or higher",                                     "ACS 5-Year, B15003",        "%",       "2023"),
        ("homeownership_rate",        "Homeownership Rate",              "Percent of occupied housing units that are owner-occupied",                                     "Second Harvest / Feeding America", "%", "2023"),
        ("disability_rate",           "Disability Rate",                 "Percent of residents with any disability",                                                      "Second Harvest / Feeding America", "%", "2023"),
        # ACS Demographics
        ("total_population",          "Total Population",                "Total resident population",                                                                     "ACS 5-Year, B01003",        "Count",   "2023"),
        ("median_age",                "Median Age",                      "Median age of residents",                                                                       "ACS 5-Year, B01002",        "Years",   "2023"),
        ("pct_white_non_hispanic",    "% White Non-Hispanic",            "Percent of population identifying as white non-Hispanic",                                       "ACS 5-Year, B03002",        "%",       "2023"),
        ("pct_black",                 "% Black or African American",     "Percent of population identifying as Black or African American",                                "ACS 5-Year, B03002",        "%",       "2023"),
        ("pct_hispanic",              "% Hispanic or Latino",            "Percent of population identifying as Hispanic or Latino",                                       "ACS 5-Year, B03002",        "%",       "2023"),
        ("pct_asian",                 "% Asian",                         "Percent of population identifying as Asian",                                                    "ACS 5-Year, B03002",        "%",       "2023"),
        ("pct_other",                 "% Other Race/Multiracial",        "Percent of population identifying as another race or multiracial",                              "ACS 5-Year, B03002",        "%",       "2023"),
        # CDC PLACES Health
        ("diabetes_rate",             "Diabetes Rate",                   "Percent of adults diagnosed with diabetes",                                                     "CDC PLACES 2023",           "%",       "2023"),
        ("high_bp_rate",              "High Blood Pressure Rate",        "Percent of adults diagnosed with high blood pressure",                                          "CDC PLACES 2023",           "%",       "2023"),
        ("obesity_rate",              "Obesity Rate",                    "Percent of adults with obesity (BMI >= 30)",                                                    "CDC PLACES 2023",           "%",       "2023"),
        ("smoking_rate",              "Smoking Rate",                    "Percent of adults who currently smoke",                                                         "CDC PLACES 2023",           "%",       "2023"),
        ("depression_rate",           "Depression Rate",                 "Percent of adults ever diagnosed with depression",                                              "CDC PLACES 2023",           "%",       "2023"),
        ("poor_mental_health_rate",   "Poor Mental Health Rate",         "Percent of adults reporting 14+ poor mental health days in past month",                        "CDC PLACES 2023",           "%",       "2023"),
        ("poor_physical_health_rate", "Poor Physical Health Rate",       "Percent of adults reporting 14+ poor physical health days in past month",                      "CDC PLACES 2023",           "%",       "2023"),
        ("no_insurance_rate",         "Uninsured Rate",                  "Percent of adults with no health insurance coverage",                                           "CDC PLACES 2023",           "%",       "2023"),
        ("physical_inactivity_rate",  "Physical Inactivity Rate",        "Percent of adults reporting no leisure-time physical activity",                                 "CDC PLACES 2023",           "%",       "2023"),
        ("any_disability_rate",       "Any Disability Rate",             "Percent of adults with any disability",                                                         "CDC PLACES 2023",           "%",       "2023"),
        # USDA Food Access
        ("food_insecurity_rate",      "Food Insecurity Rate",            "Percent of population estimated to be food insecure",                                           "Second Harvest / Feeding America", "%", "2023"),
        ("low_income_tract",          "Low Income Tract",                "1 if tract qualifies as low income per USDA definition, 0 otherwise",                          "USDA Food Atlas 2020",      "0/1",     "2020"),
        ("food_desert_1_10",          "Food Desert (1mi/10mi)",          "1 if low income and low access using 1-mile urban / 10-mile rural threshold",                  "USDA Food Atlas 2020",      "0/1",     "2020"),
        ("food_desert_half_10",       "Food Desert (0.5mi/10mi)",        "1 if low income and low access using 0.5-mile urban / 10-mile rural threshold",                "USDA Food Atlas 2020",      "0/1",     "2020"),
        ("food_desert_vehicle",       "Food Desert (Vehicle Access)",    "1 if low income and low access accounting for vehicle availability",                            "USDA Food Atlas 2020",      "0/1",     "2020"),
        ("low_access_low_income_pop", "Low Access Low Income Pop %",     "Percent of population that is both low income and lives far from a supermarket. Null for some small/rural tracts due to USDA suppression.", "USDA Food Atlas 2020", "%", "2020"),
        ("low_access_pop",            "Low Access Population %",         "Percent of population living far from a supermarket regardless of income. Null for some small/rural tracts due to USDA suppression.",       "USDA Food Atlas 2020", "%", "2020"),
        # Income Stratification
        ("share_bottom",              "Bottom Tier Share",               "Percent of households with income under $35,000",                                               "ACS 5-Year, B19001",        "%",       "2023"),
        ("share_middle",              "Middle Tier Share",               "Percent of households with income $35,000-$74,999",                                             "ACS 5-Year, B19001",        "%",       "2023"),
        ("share_top",                 "Top Tier Share",                  "Percent of households with income $75,000 or more",                                             "ACS 5-Year, B19001",        "%",       "2023"),
        ("hh_bottom",                 "Bottom Tier Households",          "Count of households with income under $35,000",                                                 "ACS 5-Year, B19001",        "Count",   "2023"),
        ("hh_middle",                 "Middle Tier Households",          "Count of households with income $35,000-$74,999",                                               "ACS 5-Year, B19001",        "Count",   "2023"),
        ("hh_top",                    "Top Tier Households",             "Count of households with income $75,000 or more",                                               "ACS 5-Year, B19001",        "Count",   "2023"),
        ("total_households",          "Total Households",                "Total number of households in tract",                                                            "ACS 5-Year, B19001",        "Count",   "2023"),
        # POI Counts
        ("count_grocery_supermarket", "Supermarket Count",               "Number of supermarkets within the census tract",                                                "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
        ("count_grocery_large",       "Large Grocery Store Count",       "Number of large grocery stores within the tract",                                               "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
        ("count_grocery_medium",      "Medium Grocery Store Count",      "Number of medium grocery stores within the tract",                                              "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
        ("count_grocery_small",       "Small Grocery Store Count",       "Number of small grocery stores within the tract",                                               "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
        ("count_grocery_any",         "Any Grocery Store Count",         "Total number of grocery stores of any size within the tract",                                   "USDA SNAP / OpenStreetMap", "Count",   "2024-2026"),
        ("count_snap_retailers",      "SNAP-Eligible Retailer Count",    "Number of stores authorized to accept SNAP/EBT benefits within the tract",                     "USDA SNAP",                 "Count",   "2026"),
        ("count_farmers_market",      "Farmers Market Count",            "Number of farmers markets within the tract",                                                    "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_convenience",         "Convenience Store Count",         "Number of convenience stores within the tract",                                                 "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_pharmacy",            "Pharmacy Count",                  "Number of pharmacies within the tract",                                                         "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_hospital",            "Hospital Count",                  "Number of hospitals within the tract",                                                          "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_clinic",              "Clinic Count",                    "Number of clinics and medical offices within the tract",                                        "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_library",             "Library Count",                   "Number of public libraries within the tract",                                                   "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_school",              "School Count",                    "Number of schools within the tract",                                                            "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_community_center",    "Community Center Count",          "Number of community centers within the tract",                                                  "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_social_services",     "Social Services Count",           "Number of social service organizations within the tract",                                       "OpenStreetMap",             "Count",   "2024-2026"),
        ("count_total_civic",         "Total Civic Services Count",      "Total count of all civic and social service locations within the tract",                        "OpenStreetMap",             "Count",   "2024-2026"),
        # Nearest distances
        ("nearest_grocery_full_miles","Nearest Grocery (miles)",         "Distance in miles to the nearest full-service grocery store from the tract centroid",           "USDA SNAP / OpenStreetMap", "Miles",   "2024-2026"),
        ("nearest_pharmacy_miles",    "Nearest Pharmacy (miles)",        "Distance in miles to the nearest pharmacy from the tract centroid",                             "OpenStreetMap",             "Miles",   "2024-2026"),
        ("nearest_hospital_miles",    "Nearest Hospital (miles)",        "Distance in miles to the nearest hospital from the tract centroid",                             "OpenStreetMap",             "Miles",   "2024-2026"),
        ("nearest_clinic_miles",      "Nearest Clinic (miles)",          "Distance in miles to the nearest clinic or medical office from the tract centroid",             "OpenStreetMap",             "Miles",   "2024-2026"),
        ("nearest_library_miles",     "Nearest Library (miles)",         "Distance in miles to the nearest public library from the tract centroid",                       "OpenStreetMap",             "Miles",   "2024-2026"),
        ("nearest_community_center_miles", "Nearest Community Center (miles)", "Distance in miles to the nearest community center from the tract centroid",              "OpenStreetMap",             "Miles",   "2024-2026"),
        ("nearest_social_services_miles",  "Nearest Social Services (miles)",  "Distance in miles to the nearest social services organization from the tract centroid",  "OpenStreetMap",             "Miles",   "2024-2026"),
        # Derived density
        ("food_retail_per_1k",        "Food Retail per 1,000 Residents", "Number of grocery stores of any size per 1,000 residents — a density measure of food retail access", "Derived",          "Rate",    "2023-2026"),
        ("snap_store_per_1k",         "SNAP Stores per 1,000 Residents", "Number of SNAP-authorized retailers per 1,000 residents — measures density of accessible food purchasing options", "Derived", "Rate", "2023-2026"),
    ]
    return pd.DataFrame(rows, columns=["variable", "label", "definition", "source", "unit", "year"])
