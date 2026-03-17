"""
process_snap_csv.py — Filter the USDA SNAP national retailer CSV to
Erie and Crawford County, PA. Keeps only currently authorized retailers
(blank End Date). Outputs data/raw/snap_retailers.csv.

Run with: python process_snap_csv.py

The national CSV file should be saved somewhere accessible.
Update INPUT_PATH below if needed.
"""

import pandas as pd

# ── CONFIG ────────────────────────────────────────────────
# Update this path to wherever you saved the downloaded CSV
INPUT_PATH = r"C:\Users\samro\PycharmProjects\ErieCensusData\data\raw\snap_retailers_national.csv"

OUTPUT_PATH = "data/raw/snap_retailers.csv"

TARGET_STATE   = "PA"
TARGET_COUNTIES = {"ERIE", "CRAWFORD"}

# USDA store type → (category label, tier)
STORE_TYPE_MAP = {
    # Full-service grocery
    "Supermarket":                  ("Food & Grocery", "Supermarket"),
    "Super Store":                  ("Food & Grocery", "Supermarket"),
    "Large Grocery Store":          ("Food & Grocery", "Large Grocery Store"),
    "Medium Grocery Store":         ("Food & Grocery", "Medium Grocery Store"),
    "Small Grocery Store":          ("Food & Grocery", "Small Grocery Store"),
    # Combination / mixed retail (Dollar General, Dollar Tree, etc.)
    "Combination Grocery/Other":    ("Food & Grocery", "Combination Grocery/Other"),
    # Specialty food
    "Specialty Food Store":         ("Food & Grocery", "Specialty Food Store"),
    "Meat/Fish/Poultry Specialty":  ("Food & Grocery", "Meat/Poultry Specialty"),
    "Meat/Poultry Specialty":       ("Food & Grocery", "Meat/Poultry Specialty"),
    "Bakery":                       ("Food & Grocery", "Bakery Specialty"),
    "Bakery Specialty":             ("Food & Grocery", "Bakery Specialty"),
    "Produce/Vegetable Specialty":  ("Food & Grocery", "Fruits/Veg Specialty"),
    "Fruits/Veg Specialty":         ("Food & Grocery", "Fruits/Veg Specialty"),
    # Farmers market
    "Farmers' Market":              ("Food & Grocery", "Farmers' Market"),
    # Convenience
    "Convenience Store":            ("Food & Grocery", "Convenience Store"),
    # Big box / wholesale
    "Wholesale Club Stores":        ("Food & Grocery", "Wholesale Club Stores"),
    # Dollar stores
    "Dollar Store":                 ("Food & Grocery", "Dollar Store"),
    # Other authorized retailers
    "Pharmacy":                     ("Food & Grocery", "Pharmacy"),
    "Delivery Route":               ("Food & Grocery", "Delivery Route"),
    "Liquor/Beer/Wine Only":        ("Food & Grocery", "Liquor/Beer/Wine"),
    "Military commissary":          ("Food & Grocery", "Military Commissary"),
}

# ── LOAD ──────────────────────────────────────────────────
print(f"Loading {INPUT_PATH}...")
try:
    df = pd.read_csv(INPUT_PATH, dtype=str, low_memory=False)
except FileNotFoundError:
    # Try alternate common filename
    alt = "data/raw/snap_retailers_national.csv"
    print(f"  Not found at primary path, trying {alt}...")
    df = pd.read_csv(alt, dtype=str, low_memory=False)

print(f"  {len(df):,} total records nationwide")
print(f"  Columns: {list(df.columns)}")

# Normalize column names
df.columns = df.columns.str.strip()

# ── FILTER: STATE ─────────────────────────────────────────
df_pa = df[df["State"].str.strip().str.upper() == TARGET_STATE].copy()
print(f"  {len(df_pa):,} Pennsylvania records")

# ── FILTER: COUNTY ────────────────────────────────────────
df_pa["County_upper"] = df_pa["County"].str.strip().str.upper()
df_local = df_pa[df_pa["County_upper"].isin(TARGET_COUNTIES)].copy()
print(f"  {len(df_local):,} Erie + Crawford County records (including expired)")

# ── FILTER: CURRENTLY AUTHORIZED ──────────────────────────
# End Date blank = still authorized
df_local["End Date"] = df_local["End Date"].fillna("").str.strip()
df_active = df_local[df_local["End Date"] == ""].copy()
print(f"  {len(df_active):,} currently authorized (blank End Date)")

# ── FILTER: VALID COORDINATES ─────────────────────────────
df_active["Latitude"]  = pd.to_numeric(df_active["Latitude"],  errors="coerce")
df_active["Longitude"] = pd.to_numeric(df_active["Longitude"], errors="coerce")
df_active = df_active[
    df_active["Latitude"].notna()  & (df_active["Latitude"]  != 0) &
    df_active["Longitude"].notna() & (df_active["Longitude"] != 0)
].copy()
print(f"  {len(df_active):,} records with valid coordinates")

# ── DEDUPLICATE ───────────────────────────────────────────
# Same store can appear multiple times if re-authorized — keep most recent
df_active["Authorization Date"] = pd.to_datetime(
    df_active["Authorization Date"], errors="coerce"
)
df_active = df_active.sort_values("Authorization Date", ascending=False)
df_active = df_active.drop_duplicates(
    subset=["Store Name", "Latitude", "Longitude"], keep="first"
)
print(f"  {len(df_active):,} after deduplication")

# ── BUILD OUTPUT ──────────────────────────────────────────
out = df_active.copy()

# Full address
out["address"] = (
    out["Street Number"].fillna("").str.strip() + " " +
    out["Street Name"].fillna("").str.strip() + ", " +
    out["City"].fillna("").str.strip() + ", " +
    out["State"].fillna("").str.strip() + " " +
    out["Zip Code"].fillna("").str.strip()
).str.strip(", ")

# Map store type to category / tier
out["category"] = "Food & Grocery"
out["store_type"] = out["Store Type"].str.strip().map(
    lambda x: STORE_TYPE_MAP.get(str(x), ("Food & Grocery", x))[1]
)

# Final columns
result = out.rename(columns={
    "Store Name":  "name",
    "Store Type":  "store_type_raw",
    "County":      "county",
    "State":       "state",
    "Zip Code":    "zip",
    "Latitude":    "lat",
    "Longitude":   "lon",
})[["name", "address", "store_type_raw", "store_type", "county", "state", "zip",
    "lat", "lon", "category"]].copy()

result["name"]          = result["name"].str.strip().str.title()
result["geocode_source"] = "usda_snap"

# ── SUMMARY ───────────────────────────────────────────────
print("\nBy store type:")
print(result["store_type_raw"].value_counts().to_string())

print("\nBy store type (mapped):")
print(result["store_type"].value_counts().to_string())

print("\nBy county:")
print(result["county"].value_counts().to_string())

print(f"\nSample:")
print(result[["name", "store_type_raw", "store_type", "county", "lat", "lon"]].head(15).to_string(index=False))

# ── SAVE ──────────────────────────────────────────────────
result.to_csv(OUTPUT_PATH, index=False)
print(f"\nSaved {len(result)} records → {OUTPUT_PATH}")
print("\nNext step: merge into erie_pois.csv via process_pois.py")