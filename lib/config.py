import pandas as pd
import pydeck as pdk

# ── VARIABLES ─────────────────────────────────────────────
# Everything shown in the app is ACS-verified (see pipeline/verify.py).
all_variables = {
    "Median Household Income": "median_household_income",
    "Poverty Rate": "poverty_rate",
    "Rent Burden Rate": "rent_burden_rate",
    "No Vehicle Rate": "no_vehicle_rate",
    "Bachelor's Degree Rate": "bachelors_rate",
    # Demographics
    "Total Population": "total_population",
    "Median Age": "median_age",
    "% White Non-Hispanic": "pct_white_non_hispanic",
    "% Black": "pct_black",
    "% Hispanic": "pct_hispanic",
    "% Asian": "pct_asian",
}

# Economic variables shown on the Economic tab.
ECONOMIC_VARS = {
    "Median Household Income": "median_household_income",
    "Poverty Rate": "poverty_rate",
    "Rent Burden Rate": "rent_burden_rate",
    "No Vehicle Rate": "no_vehicle_rate",
    "Bachelor's Degree Rate": "bachelors_rate",
}

# Demographic variables shown on the Demographics tab.
DEMOGRAPHIC_VARS = {
    "Total Population":     "total_population",
    "Median Age":          "median_age",
    "% White Non-Hispanic": "pct_white_non_hispanic",
    "% Black":             "pct_black",
    "% Hispanic":          "pct_hispanic",
    "% Asian":             "pct_asian",
}

HIGHER_IS_BETTER = {
    "median_household_income": True,
    "poverty_rate": False,
    "rent_burden_rate": False,
    "no_vehicle_rate": False,
    "bachelors_rate": True,
    "total_population": True,
    "median_age": True,
    "pct_white_non_hispanic": True,
    "pct_black": True,
    "pct_hispanic": True,
    "pct_asian": True,
}

# Bachelor's rate is published at tract level only in this dataset.
TRACT_ONLY_VARS = {"bachelors_rate"}

# ── DATA DICTIONARY ────────────────────────────────────────
data_dictionary = pd.DataFrame([
    {
        "Variable": "Median Household Income",
        "Column": "median_household_income",
        "Plain Language": "The middle income value for all households — half earn more, half earn less.",
        "Technical Definition": "ACS B19013: Median household income in the past 12 months (inflation-adjusted dollars).",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code, County",
        "Years Available": "2020–2023",
        "Caveats": "ACS 5-year estimates represent a rolling average, not a single point in time. Small geographies may have wide margins of error."
    },
    {
        "Variable": "Poverty Rate",
        "Column": "poverty_rate",
        "Plain Language": "Percentage of residents living below the federal poverty line.",
        "Technical Definition": "ACS B17001: Population below poverty level / population for whom poverty status is determined.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code, County",
        "Years Available": "2020–2023",
        "Caveats": "Federal poverty thresholds do not adjust for regional cost of living. May understate hardship in high-cost areas."
    },
    {
        "Variable": "Rent Burden Rate",
        "Column": "rent_burden_rate",
        "Plain Language": "Percentage of renters paying 35% or more of their income on rent.",
        "Technical Definition": "ACS B25070: Gross rent 35% or more of household income / total renter-occupied units.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code, County",
        "Years Available": "2020–2023",
        "Caveats": "Only captures renters. Homeowners with high mortgage costs are not reflected. The 35% threshold is more conservative than the standard 30%."
    },
    {
        "Variable": "No Vehicle Rate",
        "Column": "no_vehicle_rate",
        "Plain Language": "Percentage of households with no access to a personal vehicle.",
        "Technical Definition": "ACS B08201: Households with no vehicle available / total households.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code, County",
        "Years Available": "2020–2023",
        "Caveats": "Does not distinguish between households that chose not to own a vehicle and those who cannot afford one."
    },
    {
        "Variable": "Bachelor's Degree Rate",
        "Column": "bachelors_rate",
        "Plain Language": "Percentage of adults 25 and older with at least a bachelor's degree.",
        "Technical Definition": "ACS B15003: Population 25+ with a bachelor's degree / total population 25+.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract",
        "Years Available": "2020–2023",
        "Caveats": "Educational attainment is a lagging indicator — reflects workforce composition built over decades, not recent trends."
    },
    {
        "Variable": "Total Population",
        "Column": "total_population",
        "Plain Language": "Total number of residents.",
        "Technical Definition": "ACS B01003_001E: Total population.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "ACS 5-year rolling estimate. Group quarters population (college dorms, prisons) is included."
    },
    {
        "Variable": "Median Age",
        "Column": "median_age",
        "Plain Language": "The middle age of residents — half are older, half younger.",
        "Technical Definition": "ACS B01002_001E: Median age.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "A single median can hide bimodal age distributions (e.g. a college town with many young adults and many retirees)."
    },
    {
        "Variable": "Race & Ethnicity (% White / Black / Hispanic / Asian / Other)",
        "Column": "pct_white_non_hispanic, pct_black, pct_hispanic, pct_asian, pct_other",
        "Plain Language": "Share of residents in each race/ethnicity group.",
        "Technical Definition": "ACS B03002: Hispanic or Latino origin by race. Each group / total population.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "'Hispanic or Latino' is an ethnicity that can overlap with any race; categories here follow the Census mutually-exclusive coding (White is non-Hispanic)."
    },
    {
        "Variable": "Unemployment Rate",
        "Column": "unemployment_rate",
        "Plain Language": "Share of the labor force that is unemployed and looking for work.",
        "Technical Definition": "ACS B23025: Unemployed / civilian labor force (population 16+).",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "Counts only people actively seeking work; excludes discouraged workers who have stopped looking. Available in the ZIP-level download; not shown on the maps."
    },
    {
        "Variable": "Homeownership Rate",
        "Column": "homeownership_rate",
        "Plain Language": "Share of occupied homes that are owned rather than rented.",
        "Technical Definition": "ACS B25003: Owner-occupied units / total occupied housing units.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "Reflects occupied units only and says nothing about mortgage burden or housing stability. Available in the ZIP-level download; not shown on the maps."
    },
    {
        "Variable": "SNAP Participation Rate",
        "Column": "snap_participation_rate",
        "Plain Language": "Share of households that received SNAP (food stamp) benefits at some point in the past 12 months.",
        "Technical Definition": "ACS B19058: Households that received Food Stamps/SNAP in the past 12 months / total households.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2020–2023",
        "Caveats": "Counts households receiving SNAP at any point in the year, not average monthly caseload. Small geographies carry wider margins of error. Distinct from the USDA SNAP retailer locations, which are store sites."
    },
    {
        "Variable": "SNAP Retailers",
        "Column": "snap_retailers.csv",
        "Plain Language": "Stores authorized to accept SNAP/EBT benefits.",
        "Technical Definition": "USDA FNS SNAP Retailer Locator — currently authorized retailers with geocoded locations, labeled by USDA's own Store Type (e.g. Supermarket, Convenience Store, Combination Grocery/Other) with no regrouping. Two derived fields are added: an urban/rural flag from the USDA Food Access Research Atlas (used only to size coverage rings — 1 mile urban, 10 miles rural), and the census tract/ZCTA each point falls in (point-in-polygon).",
        "Source": "U.S. Department of Agriculture — Food and Nutrition Service (FNS); urban/rural flag from USDA Food Access Research Atlas",
        "Geography": "Point locations (11-county region)",
        "Years Available": "Current authorization snapshot",
        "Caveats": "Authorization status changes frequently. Being SNAP-authorized does not indicate the quality or quantity of healthy food a store stocks — a convenience store and a supermarket are both eligible. Store types are USDA's verbatim classification, not a food-quality judgement."
    },
])

# ── MAP CONSTANTS ─────────────────────────────────────────
MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
# Centered on the 11-county NW PA region (Erie NW corner, Clearfield SE corner)
VIEW_STATE = pdk.ViewState(latitude=41.5, longitude=-79.2, zoom=7, pitch=0)
TOOLTIP_STYLE = {"backgroundColor": "steelblue", "color": "white",
                 "fontSize": "12px", "padding": "10px"}
