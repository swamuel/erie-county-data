# Benchmark data from Census ACS 5-Year Estimates
# Pulls national, state, and Erie County averages for 2019-2023
# Erie County is kept as a named benchmark option in the app

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

def pull_geography(geography_params, label):
    all_years = []
    for year in years:
        url = f"https://api.census.gov/data/{year}/acs/acs5"
        params = {"get": get_vars, "key": api_key}
        params.update(geography_params)

        response = requests.get(url, params=params)
        data = response.json()

        df = pd.DataFrame(data[1:], columns=data[0])
        df = df.rename(columns=variables)

        for col in variables.values():
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].replace(-666666666, pd.NA)

        df = calculate_rates(df)
        df["year"] = year
        all_years.append(df)
        print(f"{label} {year} done")

    return pd.concat(all_years, ignore_index=True)

# National
national = pull_geography({"for": "us:1"}, "National")
national["geography"] = "national"
national["name"] = "United States"
national.to_csv("data/raw/benchmarks_national.csv", index=False)
print("National saved\n")

# Pennsylvania
pennsylvania = pull_geography({"for": "state:42"}, "Pennsylvania")
pennsylvania["geography"] = "state"
pennsylvania["name"] = "Pennsylvania"
pennsylvania.to_csv("data/raw/benchmarks_pennsylvania.csv", index=False)
print("Pennsylvania saved\n")

# Erie County
erie = pull_geography({"for": "county:049", "in": "state:42"}, "Erie County")
erie["geography"] = "county"
erie["name"] = "Erie County"
erie.to_csv("data/raw/benchmarks_erie.csv", index=False)
print("Erie County saved\n")

print("All benchmarks complete")