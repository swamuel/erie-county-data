"""
fetch_cdc_places_zcta.py
Pulls CDC PLACES 2023 release health estimates at the ZCTA (ZIP code) level
for Erie and Crawford County ZIP codes.

CDC PLACES ZCTA dataset: https://data.cdc.gov/resource/cwsq-ngmh.csv
Same measures as the tract-level dataset but aggregated to ZIP Code Tabulation Areas.
"""

import pandas as pd

OUTPUT_PATH = "data/raw/cdc_places_zcta.csv"

# Our ZIP codes — same list as fetch_zcta_data.py
ZCTA_LIST = [
    # Crawford County
    "16110", "16111", "16131", "16134", "16314", "16316", "16327", "16328",
    "16335", "16354", "16360", "16403", "16404", "16406", "16422", "16424",
    "16432", "16433", "16434", "16435", "16440",
    # Erie County
    "16401", "16407", "16410", "16411", "16412", "16413", "16415", "16417",
    "16421", "16423", "16426", "16427", "16428", "16430", "16438", "16441",
    "16442", "16443", "16501", "16502", "16503", "16504", "16505", "16506",
    "16507", "16508", "16509", "16510", "16511", "16563",
]

# CDC PLACES ZCTA dataset (2023 release)
url = (
    "https://data.cdc.gov/resource/cwsq-ngmh.csv"
    "?stateabbr=PA"
    "&datavaluetypeid=CrdPrv"
    "&$limit=500000"
)

print("Downloading CDC PLACES 2023 ZCTA data...")
df = pd.read_csv(url, dtype=str, low_memory=False)
print(f"  Downloaded {len(df):,} rows")

# The ZCTA dataset uses 'locationid' as the 5-digit ZIP code
if "locationid" not in df.columns:
    # Some releases use 'locationname' instead
    if "locationname" in df.columns:
        df = df.rename(columns={"locationname": "locationid"})
    else:
        print(f"  ERROR: Could not find location column. Columns: {df.columns.tolist()}")
        raise SystemExit(1)

df["zcta"] = df["locationid"].astype(str).str.zfill(5)
df = df[df["zcta"].isin(ZCTA_LIST)].copy()
print(f"  Erie + Crawford ZCTAs: {len(df):,} rows, {df['zcta'].nunique()} unique ZCTAs")

if len(df) == 0:
    print("  No matching ZCTAs found. Check ZCTA list or dataset availability.")
    raise SystemExit(1)

df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")

# Pivot long → wide (one row per ZCTA)
wide = df.pivot_table(
    index=["zcta"],
    columns="measureid",
    values="data_value",
    aggfunc="first"
).reset_index()
wide.columns.name = None

print(f"  Wide: {len(wide):,} ZCTAs, {len(wide.columns)} columns")

# Rename to friendly column names (same as tract version)
RENAME = {
    "DIABETES":   "diabetes_rate",
    "BPHIGH":     "high_bp_rate",
    "DEPRESSION": "depression_rate",
    "OBESITY":    "obesity_rate",
    "CSMOKING":   "smoking_rate",
    "ACCESS2":    "no_insurance_rate",
    "MHLTH":      "poor_mental_health_rate",
    "PHLTH":      "poor_physical_health_rate",
    "CASTHMA":    "asthma_rate",
    "CHD":        "heart_disease_rate",
    "STROKE":     "stroke_rate",
    "COPD":       "copd_rate",
    "DISABILITY": "any_disability_rate",
    "SLEEP":      "sleep_deprivation_rate",
    "LPA":        "physical_inactivity_rate",
    "BINGE":      "binge_drinking_rate",
    "ARTHRITIS":  "arthritis_rate",
    "HIGHCHOL":   "high_cholesterol_rate",
    "CANCER":     "cancer_rate",
    "GHLTH":      "poor_general_health_rate",
}
wide = wide.rename(columns=RENAME)

keep = ["zcta"] + [v for v in RENAME.values() if v in wide.columns]
wide = wide[keep].copy()

wide.to_csv(OUTPUT_PATH, index=False)
print(f"\nSaved {len(wide):,} ZCTAs, {len(wide.columns)} columns to {OUTPUT_PATH}")
print(f"Health variables available: {[c for c in keep if c != 'zcta']}")
print("\nSample:")
sample_cols = ["zcta", "diabetes_rate", "high_bp_rate", "depression_rate", "obesity_rate"]
sample_cols = [c for c in sample_cols if c in wide.columns]
print(wide[sample_cols].head(10).to_string())
