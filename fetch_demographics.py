"""
fetch_demographics.py
---------------------
Pulls ACS 5-year demographic data for Erie and Crawford County tracts.
Adds population, race/ethnicity, and age variables to support the
Overview tab and services-per-population calculations.

Variables pulled:
  - Total population (B01003)
  - Median age (B01002)
  - Race/ethnicity (B03002 — Hispanic origin by race)

Run: python fetch_demographics.py
Output: data/raw/tract_demographics.csv
Requires: CENSUS_API_KEY in .env
"""

import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("CENSUS_API_KEY")

# ── CONFIG ────────────────────────────────────────────────
OUTPUT_PATH = "data/raw/tract_demographics.csv"
YEARS = [2019, 2020, 2021, 2022, 2023]
STATE_FIPS = "42"
COUNTY_FIPS = ["049", "039"]  # Erie, Crawford

# ── ACS VARIABLES ─────────────────────────────────────────
# B01003: Total population
# B01002: Median age
# B03002: Hispanic or Latino origin by race
#   _001E = total
#   _003E = white alone, not Hispanic
#   _004E = Black or African American alone
#   _006E = Asian alone
#   _012E = Hispanic or Latino

VARIABLES = {
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B03002_001E": "race_total",
    "B03002_003E": "white_non_hispanic",
    "B03002_004E": "black_alone",
    "B03002_006E": "asian_alone",
    "B03002_012E": "hispanic_latino",
    # Additional race groups
    "B03002_005E": "native_american_alone",
    "B03002_007E": "pacific_islander_alone",
    "B03002_008E": "other_race_alone",
    "B03002_009E": "two_or_more_races",
}

BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# ── PULL ──────────────────────────────────────────────────
all_rows = []

for year in YEARS:
    print(f"\nPulling {year}...")
    var_string = ",".join(["NAME"] + list(VARIABLES.keys()))

    for county in COUNTY_FIPS:
        url = BASE_URL.format(year=year)
        params = {
            "get": var_string,
            "for": "tract:*",
            "in": f"state:{STATE_FIPS} county:{county}",
            "key": API_KEY,
        }

        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            headers = data[0]
            rows = data[1:]
            print(f"  County {county}: {len(rows)} tracts")

            for row in rows:
                record = dict(zip(headers, row))
                record["year"] = year
                record["county_fips"] = county
                all_rows.append(record)

        except Exception as e:
            print(f"  Error for {year} county {county}: {e}")

# ── BUILD DATAFRAME ───────────────────────────────────────
df = pd.DataFrame(all_rows)
print(f"\nTotal rows: {len(df):,}")

# ── RENAME COLUMNS ────────────────────────────────────────
df = df.rename(columns=VARIABLES)
df["tract_code"] = df["tract"].astype(str).str.zfill(6)

# ── CONVERT NUMERICS ──────────────────────────────────────
numeric_cols = list(VARIABLES.values())
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ── DERIVED COLUMNS ───────────────────────────────────────
# Percentage breakdowns — only compute where race_total > 0
mask = df["race_total"] > 0

df["pct_white_non_hispanic"] = None
df["pct_black"] = None
df["pct_hispanic"] = None
df["pct_asian"] = None
df["pct_other"] = None

df.loc[mask, "pct_white_non_hispanic"] = (
    df.loc[mask, "white_non_hispanic"] / df.loc[mask, "race_total"] * 100
).round(1)

df.loc[mask, "pct_black"] = (
    df.loc[mask, "black_alone"] / df.loc[mask, "race_total"] * 100
).round(1)

df.loc[mask, "pct_hispanic"] = (
    df.loc[mask, "hispanic_latino"] / df.loc[mask, "race_total"] * 100
).round(1)

df.loc[mask, "pct_asian"] = (
    df.loc[mask, "asian_alone"] / df.loc[mask, "race_total"] * 100
).round(1)

df.loc[mask, "pct_other"] = (
    100
    - df.loc[mask, "pct_white_non_hispanic"].fillna(0)
    - df.loc[mask, "pct_black"].fillna(0)
    - df.loc[mask, "pct_hispanic"].fillna(0)
    - df.loc[mask, "pct_asian"].fillna(0)
).round(1)

# ── KEEP RELEVANT COLUMNS ─────────────────────────────────
keep_cols = [
    "tract_code", "county_fips", "year", "NAME",
    "total_population", "median_age",
    "pct_white_non_hispanic", "pct_black", "pct_hispanic",
    "pct_asian", "pct_other",
    "white_non_hispanic", "black_alone", "hispanic_latino",
    "asian_alone", "race_total",
]
keep_cols = [c for c in keep_cols if c in df.columns]
df = df[keep_cols].copy()

# ── SAVE ──────────────────────────────────────────────────
os.makedirs("data/raw", exist_ok=True)
df.to_csv(OUTPUT_PATH, index=False)
print(f"\nSaved {len(df):,} rows to {OUTPUT_PATH}")
print(f"\nYears: {sorted(df['year'].unique())}")
print(f"Tracts per year: {df.groupby('year')['tract_code'].nunique().to_dict()}")
print("\nSample:")
print(df[["tract_code", "year", "total_population", "median_age",
          "pct_white_non_hispanic", "pct_black", "pct_hispanic"]].head(10).to_string())

print("\nPopulation summary by county and year:")
county_map = {"049": "Erie", "039": "Crawford"}
df["county_name"] = df["county_fips"].map(county_map)
summary = df.groupby(["county_name", "year"])["total_population"].sum().unstack()
print(summary.to_string())