"""
fetch_snap_retailers.py — Pull currently authorized SNAP retailers for
the Second Harvest NW PA 11-county region from the USDA FNS ArcGIS REST API.

No API key required. Data is updated monthly by USDA.

Outputs: data/raw/snap_retailers.csv

Run with: python fetch_snap_retailers.py
"""

import requests
import pandas as pd
import time

# ── USDA SNAP ArcGIS REST endpoint ────────────────────────
# Feature layer: SNAP Retailer Location Data (currently authorized)
BASE_URL = (
    "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/"
    "arcgis/rest/services/snap_retailers/FeatureServer/0/query"
)

# All 11 counties in the Second Harvest NW PA service region
TARGETS = [
    {"State": "PA", "County": "CAMERON"},
    {"State": "PA", "County": "CLARION"},
    {"State": "PA", "County": "CLEARFIELD"},
    {"State": "PA", "County": "CRAWFORD"},
    {"State": "PA", "County": "ELK"},
    {"State": "PA", "County": "ERIE"},
    {"State": "PA", "County": "FOREST"},
    {"State": "PA", "County": "JEFFERSON"},
    {"State": "PA", "County": "MCKEAN"},
    {"State": "PA", "County": "VENANGO"},
    {"State": "PA", "County": "WARREN"},
]

# Store type codes from USDA SNAP authorization categories
# We'll keep all types but map them to readable labels
STORE_TYPE_MAP = {
    "Supermarket":                  ("Full-Service", "standard"),
    "Large Grocery Store":          ("Full-Service", "standard"),
    "Small Grocery Store":          ("Full-Service", "specialty"),
    "Combination Grocery/Other":    ("Full-Service", "specialty"),
    "Convenience Store":            ("Convenience & Fuel", "convenience"),
    "Specialty Food Store":         ("Full-Service", "specialty"),
    "Farmers' Market":              ("Food & Grocery", "farmers_market"),
    "Wholesale Club Stores":        ("Big Box", "bigbox"),
    "Delivery Route":               ("Other", "other"),
    "Pharmacy":                     ("Health", "pharmacy"),
    "Dollar Store":                 ("Discount Variety", "dollar"),
    "Meat/Fish/Poultry Specialty":  ("Full-Service", "specialty"),
    "Bakery":                       ("Full-Service", "specialty"),
    "Produce/Vegetable Specialty":  ("Full-Service", "specialty"),
    "Liquor/Beer/Wine Only":        ("Other", "other"),
    "Military commissary":          ("Other", "other"),
}

def fetch_county(state, county):
    """Fetch all SNAP retailers for a given state/county using pagination."""
    records = []
    offset  = 0
    page    = 1000  # max records per request

    while True:
        params = {
            "where":        f"State='{state}' AND County='{county}'",
            "outFields":    "*",
            "f":            "json",
            "resultOffset": offset,
            "resultRecordCount": page,
        }
        try:
            r = requests.get(BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  Request error at offset {offset}: {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        for feat in features:
            attrs = feat.get("attributes", {})
            geom  = feat.get("geometry", {})
            attrs["lon"] = geom.get("x")
            attrs["lat"] = geom.get("y")
            records.append(attrs)

        print(f"  Fetched {len(records)} records so far...")

        if not data.get("exceededTransferLimit", False):
            break
        offset += page
        time.sleep(0.3)

    return records

def clean_records(records):
    df = pd.DataFrame(records)

    if df.empty:
        return df

    # Normalize column names — ArcGIS returns uppercase
    df.columns = [c.lower() for c in df.columns]

    # Drop records with no coordinates
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"] != 0]

    # Map store type to category/tier
    type_col = None
    for col in ["store_type", "storetype", "type"]:
        if col in df.columns:
            type_col = col
            break

    if type_col:
        df["category"] = df[type_col].map(
            lambda x: STORE_TYPE_MAP.get(str(x), ("Food & Grocery", "unknown"))[0]
        )
        df["tier"] = df[type_col].map(
            lambda x: STORE_TYPE_MAP.get(str(x), ("Food & Grocery", "unknown"))[1]
        )
    else:
        df["category"] = "Food & Grocery"
        df["tier"]     = "unknown"

    # Build clean address string
    addr_parts = []
    for part in ["address", "city", "state", "zip5"]:
        if part in df.columns:
            addr_parts.append(part)

    if addr_parts:
        df["full_address"] = df[addr_parts].fillna("").apply(
            lambda r: ", ".join(str(v) for v in r if str(v).strip()), axis=1
        )
    else:
        df["full_address"] = ""

    # Select and rename key columns
    keep = {
        "store_name":   "name",
        "storename":    "name",
        "full_address": "address",
        "county":       "county",
        "state":        "state",
        "zip5":         "zip",
        "lat":          "lat",
        "lon":          "lon",
        "category":     "category",
        "tier":         "tier",
    }
    if type_col:
        keep[type_col] = "store_type_raw"

    rename = {k: v for k, v in keep.items() if k in df.columns}
    df = df.rename(columns=rename)

    final_cols = ["name", "address", "county", "state", "zip",
                  "lat", "lon", "category", "tier"]
    if "store_type_raw" in df.columns:
        final_cols.append("store_type_raw")

    existing = [c for c in final_cols if c in df.columns]
    df = df[existing].copy()
    df["geocode_source"] = "usda_snap"

    return df.reset_index(drop=True)


def main():
    all_records = []

    for target in TARGETS:
        state  = target["State"]
        county = target["County"]
        print(f"\nFetching {county} County, {state}...")
        records = fetch_county(state, county)
        print(f"  {len(records)} raw records returned")
        all_records.extend(records)
        time.sleep(0.5)

    if not all_records:
        national_csv = "data/raw/snap_retailers_national.csv"
        import os
        if not os.path.exists(national_csv):
            print("\nArcGIS API returned no results. Download the national CSV from")
            print("https://www.fns.usda.gov/snap/retailer-locator, save as")
            print(f"{national_csv}, then re-run this script.")
            return
        print(f"\nArcGIS API returned no results — falling back to {national_csv}...")
        nat = pd.read_csv(national_csv, dtype=str, low_memory=False)
        nat.columns = [c.strip().lower().replace(" ", "_") for c in nat.columns]
        county_names = [t["County"].title() for t in TARGETS]
        nat = nat[
            (nat.get("state", nat.get("st", pd.Series())).str.upper() == "PA") &
            (nat.get("county", pd.Series()).str.upper().isin([t["County"] for t in TARGETS]))
        ].copy()
        nat["lat"] = pd.to_numeric(nat.get("latitude", nat.get("lat")), errors="coerce")
        nat["lon"] = pd.to_numeric(nat.get("longitude", nat.get("lon")), errors="coerce")
        nat["store_type_raw"] = nat.get("store_type", nat.get("storetype", ""))
        nat["category"] = nat["store_type_raw"].map(
            lambda x: STORE_TYPE_MAP.get(str(x).strip(), ("Food & Grocery", "unknown"))[0]
        )
        nat["tier"] = nat["store_type_raw"].map(
            lambda x: STORE_TYPE_MAP.get(str(x).strip(), ("Food & Grocery", "unknown"))[1]
        )
        name_col = next((c for c in ["store_name", "storename", "name"] if c in nat.columns), None)
        if name_col:
            nat = nat.rename(columns={name_col: "name"})
        nat["geocode_source"] = "usda_snap"
        nat["address"] = nat.get("street_number", "").fillna("") + " " + nat.get("street_name", "").fillna("")
        nat["zip"]   = nat.get("zip_code", nat.get("zip5", "")).fillna("")
        keep = [c for c in ["name", "address", "county", "state", "zip",
                             "lat", "lon", "category", "tier", "store_type_raw", "geocode_source"]
                if c in nat.columns]
        df = nat[keep].dropna(subset=["lat", "lon"]).reset_index(drop=True)
        print(f"  {len(df)} records from national CSV for the 11-county region")
    else:
        df = clean_records(all_records)
    print(f"\n{len(df)} clean records after filtering")

    if len(df) == 0:
        print("No records to save.")
        return

    # Summary
    if "store_type_raw" in df.columns:
        print("\nBy store type:")
        print(df["store_type_raw"].value_counts().to_string())

    print("\nBy tier:")
    print(df["tier"].value_counts().to_string())

    print("\nSample:")
    print(df[["name", "address", "tier", "lat", "lon"]].head(10).to_string(index=False))

    out = "data/raw/snap_retailers.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved → {out}")
    print("\nNext step: run process_pois.py to merge SNAP retailers into erie_pois.csv")


if __name__ == "__main__":
    main()