"""
fetch_food_atlas.py
-------------------
Downloads the USDA Food Access Research Atlas tract-level data,
filters to Erie and Crawford County tracts, and saves to data/raw/.

Source: USDA Economic Research Service
URL: https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data/
File: Excel workbook — tract-level sheet

No API key required. Direct Excel download.

Run: python fetch_food_atlas.py
Output: data/raw/usda_food_atlas.csv

NOTE: If the direct download URL has changed, visit the USDA ERS page above,
download the Excel file manually, place it in data/raw/food_atlas.xlsx,
and set MANUAL_FILE = True below.
"""

import pandas as pd
import os
import requests

# ── CONFIG ────────────────────────────────────────────────
OUTPUT_PATH = "data/raw/usda_food_atlas.csv"
MANUAL_FILE = True
TEMP_XLSX = "data/raw/FoodAccessResearchAtlasData2019.xlsx"

from lib.constants import FIPS_LIST
COUNTY_FIPS = ["42" + f for f in FIPS_LIST]  # All 11 NW PA counties

# USDA direct download URL (may change with new releases)
DOWNLOAD_URL = (
    "https://ers.usda.gov/webdocs/DataFiles/80591/"
    "DataDownload2019.xlsx?v=1754"
)

# Key variables from the Food Atlas
# LILA = Low Income + Low Access (food desert designation)
VARIABLES = [
    "CensusTract",
    "Urban",
    "POP2010",
    "OHU2010",                  # Occupied housing units
    "GroupQuartersFlag",
    "NUMGQTRS",
    "PCTGQTRS",
    "LILATracts_1And10",        # LILA: 1 mile urban / 10 miles rural
    "LILATracts_halfAnd10",     # LILA: 0.5 mile urban / 10 miles rural
    "LILATracts_1And20",        # LILA: 1 mile urban / 20 miles rural
    "LILATracts_Vehicle",       # LILA: vehicle access
    "HUNVFlag",                 # Housing units with no vehicle flag
    "LowIncomeTracts",          # Low income designation
    "PovertyRate",              # Tract poverty rate
    "MedianFamilyIncome",       # Median family income
    "LA1and10",                 # Low access: 1 mile urban / 10 miles rural
    "LAhalfand10",              # Low access: 0.5 mile urban / 10 miles rural
    "LA1and20",                 # Low access: 1 mile / 20 miles
    "LAVehicle",                # Low access by vehicle
    "LAPOP1_10",                # Low access population: 1 & 10
    "LAPOP05_10",               # Low access population: 0.5 & 10
    "LALOWI1_10",               # Low access + low income pop: 1 & 10
    "LALOWI05_10",              # Low access + low income pop: 0.5 & 10
]

# ── DOWNLOAD ──────────────────────────────────────────────
os.makedirs("data/raw", exist_ok=True)

if MANUAL_FILE:
    xlsx_path = TEMP_XLSX
    print(f"Using manual file at {xlsx_path}")
else:
    print("Downloading USDA Food Access Research Atlas...")
    try:
        r = requests.get(DOWNLOAD_URL, timeout=60, stream=True)
        r.raise_for_status()
        with open(TEMP_XLSX, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Downloaded to {TEMP_XLSX}")
        xlsx_path = TEMP_XLSX
    except Exception as e:
        print(f"""
Download failed: {e}

Manual steps:
1. Go to: https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data/
2. Download the Excel file
3. Save it as: data/raw/food_atlas_raw.xlsx
4. Set MANUAL_FILE = True in this script and re-run
""")
        raise

# ── READ EXCEL ────────────────────────────────────────────
print("\nReading Excel file...")
try:
    # Try reading sheet named 'Food Access Research Atlas'
    xl = pd.ExcelFile(xlsx_path)
    print(f"  Sheets available: {xl.sheet_names}")

    # Find the tract-level data sheet
    target_sheet = None
    for sheet in xl.sheet_names:
        if "tract" in sheet.lower() or "food access" in sheet.lower() or "data" in sheet.lower():
            target_sheet = sheet
            break
    if target_sheet is None:
        target_sheet = xl.sheet_names[0]
    print(f"  Using sheet: {target_sheet}")

    df = pd.read_excel(xlsx_path, sheet_name=target_sheet, dtype=str)
    print(f"  {len(df):,} rows, {len(df.columns)} columns")

except Exception as e:
    print(f"Error reading Excel: {e}")
    raise

# ── INSPECT ───────────────────────────────────────────────
print("\nColumns available:")
print(df.columns.tolist())

# ── FIND TRACT COLUMN ─────────────────────────────────────
tract_col = None
for candidate in ["CensusTract", "FIPS", "TractFIPS", "census_tract"]:
    if candidate in df.columns:
        tract_col = candidate
        break
if tract_col is None:
    print("WARNING: Could not find tract FIPS column. Check columns above.")
    raise ValueError("No tract FIPS column found.")

print(f"\nUsing tract column: {tract_col}")

# ── FILTER TO ERIE AND CRAWFORD ───────────────────────────
print(f"Filtering to NW PA 11-county region...")
df[tract_col] = df[tract_col].astype(str).str.zfill(11)
df["county_fips"] = df[tract_col].str[:5]
df = df[df["county_fips"].isin(COUNTY_FIPS)].copy()
print(f"  NW PA region rows: {len(df):,}")

# ── FILTER COLUMNS ────────────────────────────────────────
available_vars = [v for v in VARIABLES if v in df.columns]
missing_vars = [v for v in VARIABLES if v not in df.columns]

if missing_vars:
    print(f"\nWARNING: Variables not found: {missing_vars}")

keep_cols = [c for c in available_vars if c in df.columns]
df = df[keep_cols].copy()

# ── CONVERT NUMERICS ──────────────────────────────────────
numeric_cols = [c for c in df.columns if c != "CensusTract" and c != tract_col]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# ── RENAME FOR CONSISTENCY ────────────────────────────────
df = df.rename(columns={tract_col: "tract_geoid"})
df["tract_geoid"] = df["tract_geoid"].astype(str).str.zfill(11)
df["tract_code"] = df["tract_geoid"].str[-6:]

# Friendly column names
rename_map = {
    "LILATracts_1And10": "food_desert_1_10",
    "LILATracts_halfAnd10": "food_desert_half_10",
    "LowIncomeTracts": "low_income_tract",
    "PovertyRate": "atlas_poverty_rate",
    "MedianFamilyIncome": "atlas_median_income",
    "Urban": "urban_tract",
    "LILATracts_Vehicle": "food_desert_vehicle",
    "LAPOP1_10": "low_access_pop",
    "LALOWI1_10": "low_access_low_income_pop",
}
df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

# ── SAVE ──────────────────────────────────────────────────
df.to_csv(OUTPUT_PATH, index=False)
print(f"\nSaved {len(df):,} rows to {OUTPUT_PATH}")
print("\nSample:")
print(df.head())
print("\nKey food desert columns:")
food_desert_cols = [c for c in df.columns if "food_desert" in c or "low_access" in c]
if food_desert_cols:
    print(df[["tract_code"] + food_desert_cols].head(10).to_string())