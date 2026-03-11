# ZCTA level ACS 5-Year Estimates for Erie and Crawford County zip codes
# Filters to meaningful residential ZCTAs only

import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("CENSUS_API_KEY")

# All ZCTAs for Erie and Crawford counties
# PO Box and institutional ZCTAs excluded
ZCTA_LIST = {
    # Crawford County
    "16110": "Adamsville", "16111": "Atlantic", "16131": "Hartstown",
    "16134": "Jamestown", "16314": "Cochranton", "16316": "Conneaut Lake",
    "16327": "Guys Mills", "16328": "Hydetown", "16335": "Meadville",
    "16354": "Titusville", "16360": "Townville", "16403": "Cambridge Springs",
    "16404": "Centerville", "16406": "Conneautville", "16422": "Harmonsburg",
    "16424": "Linesville", "16432": "Riceville", "16433": "Saegertown",
    "16434": "Spartansburg", "16435": "Springboro", "16440": "Venango",
    # Erie County
    "16401": "Albion", "16407": "Corry", "16410": "Cranesville",
    "16411": "East Springfield", "16412": "Edinboro", "16413": "Elgin",
    "16415": "Fairview", "16417": "Girard", "16421": "Lake City",
    "16423": "Lowville/Wattsburg", "16426": "McKean", "16427": "Mill Village",
    "16428": "North East", "16430": "Platea", "16438": "Union City",
    "16441": "Waterford", "16442": "Wattsburg", "16443": "West Springfield",
    "16501": "Erie Downtown", "16502": "Erie West", "16503": "Erie East",
    "16504": "Erie South East", "16505": "Erie Frontier/West",
    "16506": "Erie Millcreek/West", "16507": "Erie Downtown",
    "16508": "Erie South Central", "16509": "Erie Millcreek/South",
    "16510": "Erie Harborcreek", "16511": "Erie Lawrence Park",
    "16563": "Erie Penn State Behrend"
}

COUNTY_LOOKUP = {
    "16110": "Crawford", "16111": "Crawford", "16131": "Crawford",
    "16134": "Crawford", "16314": "Crawford", "16316": "Crawford",
    "16327": "Crawford", "16328": "Crawford", "16335": "Crawford",
    "16354": "Crawford", "16360": "Crawford", "16403": "Crawford",
    "16404": "Crawford", "16406": "Crawford", "16422": "Crawford",
    "16424": "Crawford", "16432": "Crawford", "16433": "Crawford",
    "16434": "Crawford", "16435": "Crawford", "16440": "Crawford",
    "16401": "Erie", "16407": "Erie", "16410": "Erie",
    "16411": "Erie", "16412": "Erie", "16413": "Erie",
    "16415": "Erie", "16417": "Erie", "16421": "Erie",
    "16423": "Erie", "16426": "Erie", "16427": "Erie",
    "16428": "Erie", "16430": "Erie", "16438": "Erie",
    "16441": "Erie", "16442": "Erie", "16443": "Erie",
    "16501": "Erie", "16502": "Erie", "16503": "Erie",
    "16504": "Erie", "16505": "Erie", "16506": "Erie",
    "16507": "Erie", "16508": "Erie", "16509": "Erie",
    "16510": "Erie", "16511": "Erie", "16563": "Erie"
}

variables = {
    "B19013_001E": "median_household_income",
    "B17001_002E": "poverty_population",
    "B17001_001E": "poverty_total",
    "B15003_022E": "bachelors_degree",
    "B15003_001E": "education_total",
    "B25070_010E": "rent_burdened",
    "B25070_001E": "rent_total",
    "B08201_002E": "no_vehicle_households",
    "B08201_001E": "vehicle_total"
}

get_vars = "NAME," + ",".join(variables.keys())

years = [2019, 2020, 2021, 2022, 2023]
all_years = []

for year in years:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    if year >= 2020:
        params = {
            "get": get_vars,
            "for": "zip code tabulation area:*",
            "key": api_key
        }
    else:
        params = {
            "get": get_vars,
            "for": "zip code tabulation area:*",
            "in": "state:42",
            "key": api_key
        }
    response = requests.get(url, params=params)

    if response.status_code != 200 or not response.text.strip():
        print(f"{year} failed — status {response.status_code}: {response.text[:200]}")
        continue

    data = response.json()

    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns=variables)
    df = df.rename(columns={"zip code tabulation area": "zcta"})

    # Filter to our ZCTAs only
    df = df[df["zcta"].isin(ZCTA_LIST.keys())].copy()

    for col in variables.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].replace(-666666666, pd.NA)

    df["poverty_rate"] = (df["poverty_population"] / df["poverty_total"] * 100).round(1)
    df["bachelors_rate"] = (df["bachelors_degree"] / df["education_total"] * 100).round(1)
    df["rent_burden_rate"] = (df["rent_burdened"] / df["rent_total"] * 100).round(1)
    df["no_vehicle_rate"] = (df["no_vehicle_households"] / df["vehicle_total"] * 100).round(1)

    df = df.drop(columns=["poverty_population", "poverty_total",
                           "bachelors_degree", "education_total",
                           "rent_burdened", "rent_total",
                           "no_vehicle_households", "vehicle_total"])

    df["year"] = year
    df["area_name"] = df["zcta"].map(ZCTA_LIST)
    df["county_name"] = df["zcta"].map(COUNTY_LOOKUP)

    all_years.append(df)
    print(f"{year} done — {len(df)} ZCTAs")

final = pd.concat(all_years, ignore_index=True)
final["zcta"] = final["zcta"].astype(str).str.zfill(5)

print(f"\nTotal rows: {len(final)}")
print(final.groupby(["county_name", "year"]).size())
print(final[["zcta", "area_name", "county_name", "year", "median_household_income", "poverty_rate"]].head(10))

final.to_csv("data/raw/zcta_data.csv", index=False)
print("\nSaved to data/raw/zcta_data.csv")