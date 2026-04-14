import pandas as pd
import pydeck as pdk

# ── VARIABLES ─────────────────────────────────────────────
all_variables = {
    "Median Household Income": "median_household_income",
    "Poverty Rate": "poverty_rate",
    "Rent Burden Rate": "rent_burden_rate",
    "No Vehicle Rate": "no_vehicle_rate",
    "Food Insecurity Rate": "food_insecurity_rate",
    "Unemployment Rate": "unemployment_rate",
    "Disability Rate": "disability_rate",
    "Bachelor's Degree Rate": "bachelors_rate",
    "Homeownership Rate": "homeownership_rate",
    # Health — CDC PLACES
    "Diabetes Rate": "diabetes_rate",
    "High Blood Pressure": "high_bp_rate",
    "Depression Rate": "depression_rate",
    "Obesity Rate": "obesity_rate",
    "Smoking Rate": "smoking_rate",
    "No Health Insurance": "no_insurance_rate",
    "Poor Mental Health": "poor_mental_health_rate",
    "Poor Physical Health": "poor_physical_health_rate",
    "Asthma Rate": "asthma_rate",
    "Heart Disease Rate": "heart_disease_rate",
    "Stroke Rate": "stroke_rate",
    "COPD Rate": "copd_rate",
    "Physical Inactivity": "physical_inactivity_rate",
    "Sleep Deprivation": "sleep_deprivation_rate",
    # Food Access — USDA
    "Food Desert (1mi/10mi)": "food_desert_1_10",
    "Food Desert (Vehicle)": "food_desert_vehicle",
    "Low Income Tract": "low_income_tract",
    # Demographics
    "Total Population": "total_population",
    "Median Age": "median_age",
    "% White Non-Hispanic": "pct_white_non_hispanic",
    "% Black": "pct_black",
    "% Hispanic": "pct_hispanic",
    "% Asian": "pct_asian",
}

HIGHER_IS_BETTER = {
    "median_household_income": True,
    "poverty_rate": False,
    "rent_burden_rate": False,
    "no_vehicle_rate": False,
    "food_insecurity_rate": False,
    "unemployment_rate": False,
    "disability_rate": False,
    "bachelors_rate": True,
    "homeownership_rate": True,
    "diabetes_rate": False,
    "high_bp_rate": False,
    "depression_rate": False,
    "obesity_rate": False,
    "smoking_rate": False,
    "no_insurance_rate": False,
    "poor_mental_health_rate": False,
    "poor_physical_health_rate": False,
    "asthma_rate": False,
    "heart_disease_rate": False,
    "stroke_rate": False,
    "copd_rate": False,
    "physical_inactivity_rate": False,
    "sleep_deprivation_rate": False,
    "food_desert_1_10": False,
    "food_desert_vehicle": False,
    "low_income_tract": False,
    "total_population": True,
    "median_age": True,
    "pct_white_non_hispanic": True,
    "pct_black": True,
    "pct_hispanic": True,
    "pct_asian": True,
}

TRACT_ONLY_VARS = {
    "food_insecurity_rate", "unemployment_rate", "disability_rate",
    "homeownership_rate", "stop_count", "total_daily_visits", "nearest_stop_miles",
    "diabetes_rate", "high_bp_rate", "depression_rate", "obesity_rate",
    "smoking_rate", "no_insurance_rate", "poor_mental_health_rate",
    "poor_physical_health_rate", "asthma_rate", "heart_disease_rate",
    "stroke_rate", "copd_rate", "physical_inactivity_rate", "sleep_deprivation_rate",
    "food_desert_1_10", "food_desert_vehicle", "low_income_tract",
    "low_access_pop", "low_access_low_income_pop",
    "total_population", "median_age",
    "pct_white_non_hispanic", "pct_black", "pct_hispanic", "pct_asian",
}

# ── DATA DICTIONARY ────────────────────────────────────────
data_dictionary = pd.DataFrame([
    {
        "Variable": "Median Household Income",
        "Column": "median_household_income",
        "Plain Language": "The middle income value for all households — half earn more, half earn less.",
        "Technical Definition": "ACS B19013: Median household income in the past 12 months (inflation-adjusted dollars).",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "ACS 5-year estimates represent a rolling average, not a single point in time. Small geographies may have wide margins of error."
    },
    {
        "Variable": "Poverty Rate",
        "Column": "poverty_rate",
        "Plain Language": "Percentage of residents living below the federal poverty line.",
        "Technical Definition": "ACS B17001: Population for whom poverty status is determined, below poverty level / total.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Federal poverty thresholds do not adjust for regional cost of living. May understate hardship in high-cost areas."
    },
    {
        "Variable": "Rent Burden Rate",
        "Column": "rent_burden_rate",
        "Plain Language": "Percentage of renters paying 35% or more of their income on rent.",
        "Technical Definition": "ACS B25070: Gross rent as a percentage of household income — 35% or more / total renter-occupied units.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Only captures renters. Homeowners with high mortgage costs are not reflected. Threshold of 35% is more conservative than the standard 30%."
    },
    {
        "Variable": "No Vehicle Rate",
        "Column": "no_vehicle_rate",
        "Plain Language": "Percentage of households with no access to a personal vehicle.",
        "Technical Definition": "ACS B08201: Households with no vehicle available / total households.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract, ZIP Code",
        "Years Available": "2019–2023",
        "Caveats": "Does not distinguish between households that chose not to own a vehicle and those who cannot afford one."
    },
    {
        "Variable": "Food Insecurity Rate",
        "Column": "food_insecurity_rate",
        "Plain Language": "Estimated percentage of residents who lack reliable access to enough food.",
        "Technical Definition": "Modeled tract-level food insecurity estimates from Feeding America / Second Harvest North Central PA.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "These are modeled estimates, not direct measurements. Methodology uses poverty, unemployment, and demographic variables to estimate food insecurity. Should not be interpreted as a precise count."
    },
    {
        "Variable": "Unemployment Rate",
        "Column": "unemployment_rate",
        "Plain Language": "Percentage of the labor force that is unemployed.",
        "Technical Definition": "Derived from Second Harvest source data. Unemployed civilians / civilian labor force.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "Does not include discouraged workers or those who have left the labor force. Tract-level estimates may have higher variability than county-level BLS data."
    },
    {
        "Variable": "Disability Rate",
        "Column": "disability_rate",
        "Plain Language": "Percentage of residents with any disability.",
        "Technical Definition": "Derived from Second Harvest source data. Population with a disability / total civilian noninstitutionalized population.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "Disability is self-reported and covers a broad range of conditions. Does not distinguish severity or type of disability."
    },
    {
        "Variable": "Bachelor's Degree Rate",
        "Column": "bachelors_rate",
        "Plain Language": "Percentage of adults 25 and older with at least a bachelor's degree.",
        "Technical Definition": "ACS B15003: Population 25 years and over with bachelor's degree / total population 25 and over.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract only",
        "Years Available": "2019–2023",
        "Caveats": "Educational attainment is a lagging indicator — reflects workforce composition built over decades, not recent trends."
    },
    {
        "Variable": "Homeownership Rate",
        "Column": "homeownership_rate",
        "Plain Language": "Percentage of housing units that are owner-occupied.",
        "Technical Definition": "Derived from Second Harvest source data. Owner-occupied units / total occupied housing units.",
        "Source": "Second Harvest North Central PA / Feeding America Map the Meal Gap",
        "Geography": "Tract only",
        "Years Available": "2020–2023",
        "Caveats": "High homeownership does not necessarily indicate housing stability. Does not capture mortgage distress or property tax burden."
    },
    {
        "Variable": "Diabetes Rate",
        "Column": "diabetes_rate",
        "Plain Language": "Percentage of adults diagnosed with diabetes.",
        "Technical Definition": "CDC PLACES model-based estimate. Crude prevalence of diagnosed diabetes among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Model-based estimates, not direct survey counts. Based on Behavioral Risk Factor Surveillance System data modeled down to tract level. Should not be compared to clinical data."
    },
    {
        "Variable": "High Blood Pressure",
        "Column": "high_bp_rate",
        "Plain Language": "Percentage of adults with high blood pressure.",
        "Technical Definition": "CDC PLACES crude prevalence of high blood pressure among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Model-based estimate. BRFSS data for blood pressure collected every other year."
    },
    {
        "Variable": "Depression Rate",
        "Column": "depression_rate",
        "Plain Language": "Percentage of adults who have ever been told they have a depressive disorder.",
        "Technical Definition": "CDC PLACES crude prevalence of depression among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Self-reported diagnosis. Likely undercounts true prevalence due to underdiagnosis, especially in rural areas."
    },
    {
        "Variable": "Obesity Rate",
        "Column": "obesity_rate",
        "Plain Language": "Percentage of adults with a BMI of 30 or higher.",
        "Technical Definition": "CDC PLACES crude prevalence of obesity (BMI >= 30) among adults aged 18+.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Based on self-reported height and weight. BMI is a limited measure of health and does not account for body composition."
    },
    {
        "Variable": "No Health Insurance",
        "Column": "no_insurance_rate",
        "Plain Language": "Percentage of adults under 65 without health insurance.",
        "Technical Definition": "CDC PLACES crude prevalence of no health insurance among adults aged 18-64.",
        "Source": "CDC PLACES Local Data for Better Health — 2023 release (2021 BRFSS data)",
        "Geography": "Tract only",
        "Years Available": "2021 (single year)",
        "Caveats": "Excludes adults 65+ who are generally covered by Medicare. Model-based estimate."
    },
    {
        "Variable": "Food Desert (1mi/10mi)",
        "Column": "food_desert_1_10",
        "Plain Language": "Tract designated as a food desert — low income and low access to a grocery store.",
        "Technical Definition": "USDA LILA designation: low income tract where a significant share of residents are more than 1 mile (urban) or 10 miles (rural) from a supermarket or large grocery store.",
        "Source": "USDA Economic Research Service — Food Access Research Atlas 2019",
        "Geography": "Tract only",
        "Years Available": "2019 (single year)",
        "Caveats": "Based on 2019 store locations. Does not account for stores opened or closed since then. Dollar stores and convenience stores are not counted as grocery stores."
    },
    {
        "Variable": "Total Population",
        "Column": "total_population",
        "Plain Language": "Total number of residents in the tract.",
        "Technical Definition": "ACS B01003_001E: Total population.",
        "Source": "U.S. Census Bureau — American Community Survey 5-Year Estimates",
        "Geography": "Tract only",
        "Years Available": "2019–2023",
        "Caveats": "ACS 5-year rolling estimate. Group quarters population (college dorms, prisons) is included."
    },
])

# ── SERVICES LAYER CONFIG ─────────────────────────────────
LAYER_CONFIG = {
    "Food & Grocery": {
        "Supermarkets":            {"primary_category":"Food & Grocery","type":"Supermarket","default_on":True,"color":[34,197,94,220],"subtypes":None},
        "Large Grocery Stores":    {"primary_category":"Food & Grocery","type":"Large Grocery Store","default_on":True,"color":[52,211,153,220],"subtypes":None},
        "Medium Grocery Stores":   {"primary_category":"Food & Grocery","type":"Medium Grocery Store","default_on":True,"color":[110,231,183,220],"subtypes":None},
        "Small Grocery Stores":    {"primary_category":"Food & Grocery","type":"Small Grocery Store","default_on":False,"color":[167,243,208,220],"subtypes":None},
        "Combination / Mixed Retail":{"primary_category":"Food & Grocery","type":"Combination Grocery/Other","default_on":False,"color":[251,191,36,220],"subtypes":None},
        "Specialty Food":          {"primary_category":"Food & Grocery","type":"Specialty Food Store","default_on":False,"color":[16,185,129,220],"subtypes":{
            "Meat / Poultry":{"value":"Meat/Poultry Specialty","default_on":True,"color":[239,68,68,200]},
            "Bakery":        {"value":"Bakery Specialty",       "default_on":True,"color":[251,146,60,200]},
            "Fruits / Veg":  {"value":"Fruits/Veg Specialty",  "default_on":True,"color":[34,197,94,200]},
        }},
        "Farmers Markets":         {"primary_category":"Food & Grocery","type":"Farmers' Market","default_on":True,"color":[5,150,105,220],"subtypes":None},
        "Convenience Stores":      {"primary_category":"Food & Grocery","type":"Convenience Store","default_on":False,"color":[156,163,175,200],"subtypes":None},
    },
    "Health": {
        "Hospitals":               {"primary_category":"Health","type":"Hospital","default_on":True,"color":[220,38,38,240],"subtypes":None},
        "Pharmacies":              {"primary_category":"Health","type":"Pharmacy","default_on":True,"color":[239,68,68,220],"subtypes":None},
        "Clinics & Care":          {"primary_category":"Health","type":"Clinic","default_on":True,"color":[251,146,60,200],"subtypes":{
            "Outpatient Clinic":{"value":"Outpatient Clinic","default_on":True, "color":[251,146,60,220]},
            "Medical Office":   {"value":"Medical Office",   "default_on":False,"color":[253,186,116,200]},
            "Dental Office":    {"value":"Dental Office",    "default_on":False,"color":[251,191,36,200]},
            "Veterinary":       {"value":"Veterinary",       "default_on":False,"color":[100,180,100,200]},
        }},
    },
    "Civic & Social": {
        "Libraries":               {"primary_category":"Education & Civic","type":"Library","default_on":True,"color":[59,130,246,220],"subtypes":None},
        "Schools":                 {"primary_category":"Education & Civic","type":"School","default_on":False,"color":[99,102,241,200],"subtypes":{
            "K-12 Schools":    {"value":"K-12 School",    "default_on":True, "color":[99,102,241,200]},
            "Early Childhood": {"value":"Early Childhood","default_on":False,"color":[129,140,248,200]},
        }},
        "Higher Education":        {"primary_category":"Education & Civic","type":"Higher Education","default_on":True,"color":[67,56,202,220],"subtypes":None},
        "Community Centers":       {"primary_category":"Civic & Social","type":"Community Center","default_on":True,"color":[168,85,247,220],"subtypes":None},
        "Social Services":         {"primary_category":"Civic & Social","type":"Social Services","default_on":True,"color":[192,132,252,200],"subtypes":None},
        "Financial":               {"primary_category":"Civic & Social","type":"Financial","default_on":False,"color":[100,100,180,200],"subtypes":None},
        "Government":              {"primary_category":"Civic & Social","type":"Government","default_on":False,"color":[107,114,128,200],"subtypes":{
            "Government Offices":{"value":"Government Office","default_on":True, "color":[107,114,128,220]},
            "Post Offices":      {"value":"Post Office",      "default_on":False,"color":[156,163,175,200]},
        }},
        "Emergency Services":      {"primary_category":"Civic & Social","type":"Emergency Services","default_on":False,"color":[239,68,68,200],"subtypes":{
            "Fire Stations":   {"value":"Fire Station",   "default_on":True,"color":[239,68,68,220]},
            "Police Stations": {"value":"Police Station", "default_on":True,"color":[59,130,246,220]},
        }},
        "Faith Communities":       {"primary_category":"Civic & Social","type":"Faith Community","default_on":False,"color":[180,140,200,180],"subtypes":None},
    },
}

# ── MAP CONSTANTS ─────────────────────────────────────────
MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
VIEW_STATE = pdk.ViewState(latitude=41.95, longitude=-80.15, zoom=8.5, pitch=0)
TOOLTIP_STYLE = {"backgroundColor": "steelblue", "color": "white",
                 "fontSize": "12px", "padding": "10px"}
