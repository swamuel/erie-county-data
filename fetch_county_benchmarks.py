# All Pennsylvania county averages from Census ACS 5-Year Estimates
# Used for county comparison feature in the app

import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("CENSUS_API_KEY")

years = [2019, 2020, 2021, 2022, 2023]

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

def calculate_rates(df):
    df["poverty_rate"] = (df["poverty_population"] / df["poverty_total"] * 100).round(1)
    df["bachelors_rate"] = (df["bachelors_degree"] / df["education_total"] * 100).round(1)
    df["rent_burden_rate"] = (df["rent_burdened"] / df["rent_total"] * 100).round(1)
    df["no_vehicle_rate"] = (df["no_vehicle_households"] / df["vehicle_total"] * 100).round(1)
    df = df.drop(columns=["poverty_population", "poverty_total",
                           "bachelors_degree", "education_total",
                           "rent_burdened", "rent_total",
                           "no_vehicle_households", "vehicle_total"])
    return df

all_years = []

for year in years:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {
        "get": get_vars,
        "for": "county:*",
        "in": "state:42",
        "key": api_key
    }

    response = requests.get(url, params=params)
    data = response.json()

    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns=variables)

    for col in variables.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].replace(-666666666, pd.NA)

    df = calculate_rates(df)
    df["year"] = year

    # Clean up county name - remove ", Pennsylvania" suffix
    df["name"] = df["NAME"].str.replace(", Pennsylvania", "", regex=False)
    df["county_fips"] = df["county"]
    df = df.drop(columns=["NAME", "state", "county"])

    all_years.append(df)
    print(f"{year} done — {len(df)} counties")

final = pd.concat(all_years, ignore_index=True)
print(f"\nTotal rows: {len(final)}")
print(final[["name", "year", "median_household_income", "poverty_rate"]].head(10))

print("Crawford County saved\n")
final.to_csv("data/raw/benchmarks_pa_counties.csv", index=False)
print("Saved")