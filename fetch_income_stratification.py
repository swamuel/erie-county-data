from pathlib import Path
import time
import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
# ── Config ────────────────────────────────────────────────────────────────────
API_KEY   = os.getenv("CENSUS_API_KEY")
OUT       = Path("data/raw/income_stratification.csv")
YEARS     = [2019, 2020, 2021, 2022, 2023]
STATE     = "42"       # Pennsylvania
from lib.constants import FIPS_LIST, FIPS_TO_NAME
COUNTIES  = FIPS_LIST  # All 11 NW PA counties

# ── B19001 variables — household income brackets ──────────────────────────────
# B19001_001E = Total households
# B19001_002E = Less than $10,000
# B19001_003E = $10,000 to $14,999
# B19001_004E = $15,000 to $19,999
# B19001_005E = $20,000 to $24,999
# B19001_006E = $25,000 to $29,999
# B19001_007E = $30,000 to $34,999
# B19001_008E = $35,000 to $39,999
# B19001_009E = $40,000 to $44,999
# B19001_010E = $45,000 to $49,999
# B19001_011E = $50,000 to $59,999
# B19001_012E = $60,000 to $74,999
# B19001_013E = $75,000 to $99,999
# B19001_014E = $100,000 to $124,999
# B19001_015E = $125,000 to $149,999
# B19001_016E = $150,000 to $199,999
# B19001_017E = $200,000 or more

BAND_VARS = {
    "B19001_001E": "total_households",
    "B19001_002E": "under_10k",
    "B19001_003E": "10k_15k",
    "B19001_004E": "15k_20k",
    "B19001_005E": "20k_25k",
    "B19001_006E": "25k_30k",
    "B19001_007E": "30k_35k",
    "B19001_008E": "35k_40k",
    "B19001_009E": "40k_45k",
    "B19001_010E": "45k_50k",
    "B19001_011E": "50k_60k",
    "B19001_012E": "60k_75k",
    "B19001_013E": "75k_100k",
    "B19001_014E": "100k_125k",
    "B19001_015E": "125k_150k",
    "B19001_016E": "150k_200k",
    "B19001_017E": "200k_plus",
}

VARS_STR = ",".join(BAND_VARS.keys())

# ── Fetch ─────────────────────────────────────────────────────────────────────
all_rows = []

for year in YEARS:
    for county in COUNTIES:
        url = (
            f"https://api.census.gov/data/{year}/acs/acs5"
            f"?get=NAME,{VARS_STR}"
            f"&for=tract:*"
            f"&in=state:{STATE}+county:{county}"
            f"&key={API_KEY}"
        )
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"  ✗ {year} county {county} — HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")
            continue

        # Add this temporarily to see what's coming back before parsing
        print(f"  Raw response preview: {resp.text[:300]}")

        data = resp.json()
        headers = data[0]
        rows    = data[1:]
        for row in rows:
            record = dict(zip(headers, row))
            record["year"]   = year
            record["county_fips"] = county
            all_rows.append(record)

        county_name = FIPS_TO_NAME.get(county, county)
        print(f"  {year} {county_name} -- {len(rows)} tracts")
        time.sleep(0.1)

# ── Build DataFrame ───────────────────────────────────────────────────────────
df = pd.DataFrame(all_rows)

# Rename band columns
df = df.rename(columns=BAND_VARS)

# Build GEOID
df["geoid"] = STATE + df["county_fips"] + df["tract"]

# Add county name
df["county"] = df["county_fips"].map(FIPS_TO_NAME)

# Cast band columns to numeric
band_cols = list(BAND_VARS.values())
for col in band_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Drop rows with missing total
df = df.dropna(subset=["total_households"])
df = df[df["total_households"] > 0]

# Keep only needed columns
keep = ["geoid", "county", "year", "NAME"] + band_cols
df = df[keep].copy()

df = df.sort_values(["county", "geoid", "year"]).reset_index(drop=True)

# ── Save ──────────────────────────────────────────────────────────────────────
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)

print(f"\nDone: Saved {len(df):,} rows to {OUT}")
print(f"  Years: {sorted(df['year'].unique().tolist())}")
print(f"  Tracts per county:")
print(df.groupby(["county", "year"])["geoid"].count().unstack().to_string())
