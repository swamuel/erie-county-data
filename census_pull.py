# Census ACS 5-Year Estimates, 2019-2023
# Geography: Erie County, PA census tracts (state: 42, county: 049)

import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("CENSUS_API_KEY")

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
counties = {
    "049": "Erie County",
    "039": "Crawford County"
}

all_years = []

for year in years:
    for county_fips, county_name in counties.items():
        url = f"https://api.census.gov/data/{year}/acs/acs5"

        params = {
            "get": get_vars,
            "for": "tract:*",
            "in": f"state:42 county:{county_fips}",
            "key": api_key
        }

        response = requests.get(url, params=params)
        data = response.json()

        df = pd.DataFrame(data[1:], columns=data[0])
        df = df.rename(columns={"NAME": "tract_name", "state": "state_fips",
                                 "county": "county_fips", "tract": "tract_code"})
        df = df.rename(columns=variables)

        numeric_cols = list(variables.values())
        for col in numeric_cols:
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
        df["county_name"] = county_name
        df = df[df["tract_code"] != "990000"]

        all_years.append(df)
        print(f"{year} {county_name} done — {len(df)} tracts")

final_df = pd.concat(all_years, ignore_index=True)
final_df["tract_code"] = final_df["tract_code"].astype(str).str.zfill(6)
final_df["median_household_income"] = pd.to_numeric(final_df["median_household_income"], errors="coerce")

print(f"\nTotal rows: {len(final_df)}")
print(final_df.groupby(["county_name", "year"]).size())

final_df.to_csv("data/raw/erie_tract_data.csv", index=False)
print("Saved")