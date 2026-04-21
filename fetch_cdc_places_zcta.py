"""
fetch_cdc_places_zcta.py
Pulls CDC PLACES 2023 release health estimates at the ZCTA (ZIP code) level
for the Second Harvest NW PA service region (11 counties).

Uses the GIS-friendly wide format dataset (one row per ZCTA):
  https://data.cdc.gov/resource/c7b2-4ecy.json

ZCTAs are discovered dynamically via fetch_zcta_data.discover_region_zctas().
Run fetch_zcta_data.py first if data/raw/region_zctas.csv doesn't exist.
"""

import requests
import pandas as pd
from pathlib import Path

OUTPUT_PATH = "data/raw/cdc_places_zcta.csv"

# Load ZCTA list from cache (created by fetch_zcta_data.py)
ZCTA_CACHE = Path("data/raw/region_zctas.csv")
if ZCTA_CACHE.exists():
    _zcta_df  = pd.read_csv(ZCTA_CACHE, dtype={"zcta": str})
    ZCTA_LIST = _zcta_df["zcta"].str.zfill(5).tolist()
    print(f"Using {len(ZCTA_LIST)} ZCTAs from {ZCTA_CACHE}")
else:
    print("WARNING: region_zctas.csv not found. Run fetch_zcta_data.py first.")
    print("Falling back to Erie+Crawford hardcoded list.")
    ZCTA_LIST = [
        "16110","16111","16131","16134","16314","16316","16327","16328",
        "16335","16354","16360","16403","16404","16406","16422","16424",
        "16432","16433","16434","16435","16440","16401","16407","16410",
        "16411","16412","16413","16415","16417","16421","16423","16426",
        "16427","16428","16430","16438","16441","16442","16443","16501",
        "16502","16503","16504","16505","16506","16507","16508","16509",
        "16510","16511","16563",
    ]

# Column renames: GIS-friendly _crudeprev names → app-friendly names
RENAME = {
    "diabetes_crudeprev":    "diabetes_rate",
    "bphigh_crudeprev":      "high_bp_rate",
    "depression_crudeprev":  "depression_rate",
    "obesity_crudeprev":     "obesity_rate",
    "csmoking_crudeprev":    "smoking_rate",
    "access2_crudeprev":     "no_insurance_rate",
    "mhlth_crudeprev":       "poor_mental_health_rate",
    "phlth_crudeprev":       "poor_physical_health_rate",
    "casthma_crudeprev":     "asthma_rate",
    "chd_crudeprev":         "heart_disease_rate",
    "stroke_crudeprev":      "stroke_rate",
    "copd_crudeprev":        "copd_rate",
    "disability_crudeprev":  "any_disability_rate",
    "sleep_crudeprev":       "sleep_deprivation_rate",
    "lpa_crudeprev":         "physical_inactivity_rate",
    "binge_crudeprev":       "binge_drinking_rate",
    "arthritis_crudeprev":   "arthritis_rate",
    "highchol_crudeprev":    "high_cholesterol_rate",
    "cancer_crudeprev":      "cancer_rate",
    "ghlth_crudeprev":       "poor_general_health_rate",
}

print("Downloading CDC PLACES 2023 ZCTA data (GIS-friendly format)...")

all_rows = []
offset = 0
limit = 1000

while True:
    r = requests.get(
        "https://data.cdc.gov/resource/c7b2-4ecy.json",
        params={"$limit": limit, "$offset": offset}
    )
    r.raise_for_status()
    batch = r.json()
    if not batch:
        break
    all_rows.extend(batch)
    offset += limit
    if len(batch) < limit:
        break

df = pd.DataFrame(all_rows)
print(f"  Downloaded {len(df):,} ZCTAs total")

df["zcta"] = df["zcta5"].astype(str).str.zfill(5)
df = df[df["zcta"].isin(ZCTA_LIST)].copy()
print(f"  Erie + Crawford ZCTAs: {len(df):,} rows")

if len(df) == 0:
    print("  ERROR: No matching ZCTAs found.")
    raise SystemExit(1)

# Convert numeric columns
for col in RENAME:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.rename(columns=RENAME)
keep = ["zcta"] + [v for v in RENAME.values() if v in df.columns]
df = df[keep].reset_index(drop=True)

df.to_csv(OUTPUT_PATH, index=False)
print(f"Saved {len(df):,} ZCTAs, {len(df.columns)} columns to {OUTPUT_PATH}")
print(f"Health variables: {[c for c in df.columns if c != 'zcta']}")
print("\nSample:")
sample_cols = ["zcta", "diabetes_rate", "high_bp_rate", "depression_rate", "obesity_rate"]
sample_cols = [c for c in sample_cols if c in df.columns]
print(df[sample_cols].to_string())
