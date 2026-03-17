"""
fetch_cdc_places.py - final version
"""

import pandas as pd
import os

OUTPUT_PATH = "data/raw/cdc_places_tract.csv"
COUNTY_FIPS = ["42049", "42039"]

url = (
    "https://data.cdc.gov/resource/em5e-5hvn.csv"
    "?stateabbr=PA"
    "&$limit=500000"
)

print("Downloading CDC PLACES 2023 release...")
df = pd.read_csv(url, dtype=str, low_memory=False)
print(f"  Downloaded {len(df):,} rows")
print(f"  MeasureIDs: {sorted(df['measureid'].unique())}")

# Filter to crude prevalence only
df = df[df["datavaluetypeid"] == "CrdPrv"].copy()

# Set up geo columns
df["tract_geoid"] = df["locationname"].astype(str).str.zfill(11)
df["county_fips"] = df["tract_geoid"].str[:5]
df["tract_code"] = df["tract_geoid"].str[-6:]
df = df[df["county_fips"].isin(COUNTY_FIPS)].copy()
print(f"  Erie + Crawford rows: {len(df):,}")

df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")

# Pivot long to wide
wide = df.pivot_table(
    index=["tract_geoid", "tract_code", "county_fips", "countyname", "year"],
    columns="measureid",
    values="data_value",
    aggfunc="first"
).reset_index()
wide.columns.name = None

print(f"  Wide: {len(wide):,} rows, {len(wide.columns)} columns")
print(f"  Columns: {wide.columns.tolist()}")

# Check what years are present
print(f"  Years: {wide['year'].unique()}")

# Keep most recent year only
latest_year = wide["year"].max()
wide = wide[wide["year"] == latest_year].copy()
print(f"  Keeping year {latest_year}: {len(wide):,} rows")

# Rename to friendly column names
RENAME = {
    "DIABETES":    "diabetes_rate",
    "BPHIGH":      "high_bp_rate",
    "DEPRESSION":  "depression_rate",
    "OBESITY":     "obesity_rate",
    "CSMOKING":    "smoking_rate",
    "ACCESS2":     "no_insurance_rate",
    "MHLTH":       "poor_mental_health_rate",
    "PHLTH":       "poor_physical_health_rate",
    "CASTHMA":     "asthma_rate",
    "CHD":         "heart_disease_rate",
    "STROKE":      "stroke_rate",
    "COPD":        "copd_rate",
    "DISABILITY":  "any_disability_rate",
    "COGNITION":   "cognitive_disability_rate",
    "MOBILITY":    "mobility_disability_rate",
    "SLEEP":       "sleep_deprivation_rate",
    "LPA":         "physical_inactivity_rate",
    "BINGE":       "binge_drinking_rate",
    "ARTHRITIS":   "arthritis_rate",
    "HIGHCHOL":    "high_cholesterol_rate",
    "KIDNEY":      "kidney_disease_rate",
    "CANCER":      "cancer_rate",
    "HEARING":     "hearing_disability_rate",
    "VISION":      "vision_disability_rate",
    "TEETHLOST":   "teeth_loss_rate",
    "GHLTH":       "poor_general_health_rate",
}
wide = wide.rename(columns=RENAME)

# Keep only the columns we want
keep = ["tract_geoid", "tract_code", "county_fips", "countyname", "year"] + list(RENAME.values())
keep = [c for c in keep if c in wide.columns]
wide = wide[keep].copy()

wide.to_csv(OUTPUT_PATH, index=False)
print(f"\nSaved {len(wide):,} rows, {len(wide.columns)} columns to {OUTPUT_PATH}")
print("\nSample:")
print(wide[["tract_code", "countyname", "diabetes_rate", "high_bp_rate", "depression_rate", "obesity_rate"]].head(10).to_string())