# Census ACS 5-Year Estimates, 2023
# Dataset: Median Household Income (B19013_001E)
# Source: https://api.census.gov/data/2023/acs/acs5/variables/B19013_001E.json
# Geography: Erie County, PA census tracts (state: 42, county: 049)

import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("CENSUS_API_KEY")

years = [2019, 2020, 2021, 2022, 2023]
all_years = []

for year in years:
    url = f"https://api.census.gov/data/{year}/acs/acs5"

    params = {
        "get": "NAME,B19013_001E",
        "for": "tract:*",
        "in": "state:42 county:049",
        "key": api_key
    }

    response = requests.get(url, params=params)
    data = response.json()

    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns={
        "NAME": "tract_name",
        "B19013_001E": "median_household_income",
        "state": "state_fips",
        "county": "county_fips",
        "tract": "tract_code"
    })

    df["median_household_income"] = pd.to_numeric(df["median_household_income"], errors="coerce")
    df["median_household_income"] = df["median_household_income"].replace(-666666666, pd.NA)
    df["year"] = year
    df = df[df["tract_code"] != "990000"]

    all_years.append(df)
    print(f"{year} done — {len(df)} tracts")

final_df = pd.concat(all_years, ignore_index=True)
print(f"\nTotal rows: {len(final_df)}")
print(final_df.head())

final_df.to_csv("data/raw/erie_median_income_tracts_multiyear.csv", index=False)