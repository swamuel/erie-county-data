"""
fetch_snap_retailers.py — Build a currently-authorized SNAP retailer file
for the Second Harvest NW PA 11-county region from USDA's published bulk
SNAP Retailer Locator Data (2005-2025 vintage and successors).

Why this script changed (history):
    The original version of this script queried a USDA ArcGIS feature
    service at services1.arcgis.com/RLQu0rK7h4kbsBq5/.../snap_retailers/
    that has since been retired. Worse, when it was live it returned the
    full historical record for the requested counties — every retailer
    ever authorized, not the currently-authorized snapshot. That produced
    1,540 rows for the 11-county NW PA region, of which only 626 were
    actually still authorized as of late 2025.

    USDA's stable, official source is the bulk historical file at
    https://www.fns.usda.gov/sites/default/files/resource-files/
    snap-retailer-locator-data2005-2025.zip. Each row has Authorization
    Date and End Date. End Date is blank (a literal space) for retailers
    still authorized as of the file's compilation. This script downloads
    that file, filters to the 11-county region and to End Date == blank,
    and writes data/raw/snap_retailers.csv with the same schema the map
    scripts expect plus an authorization_date column.

Outputs:
    data/raw/snap_historical/snap_history.csv  (full national archive,
        cached so we don't re-download the 24 MB zip every run)
    data/raw/snap_retailers.csv  (regional active-only working file)

Run with:
    python fetch_snap_retailers.py
"""
from pathlib import Path
import io
import zipfile

import pandas as pd
import requests

HIST_URL = ("https://www.fns.usda.gov/sites/default/files/resource-files/"
            "snap-retailer-locator-data2005-2025.zip")

ROOT = Path(__file__).resolve().parent
HIST_DIR = ROOT / "data" / "raw" / "snap_historical"
HIST_CSV = HIST_DIR / "snap_history.csv"
OUT_CSV  = ROOT / "data" / "raw" / "snap_retailers.csv"

NW_PA_COUNTIES = {
    "CAMERON", "CLARION", "CLEARFIELD", "CRAWFORD", "ELK",
    "ERIE", "FOREST", "JEFFERSON", "MCKEAN", "VENANGO", "WARREN",
}

# Maps USDA's Store Type values to a coarser (category, tier) pair that
# the analytical map scripts use. Same mapping the prior version of this
# script used so existing downstream code keeps working unchanged.
STORE_TYPE_MAP = {
    "Supermarket":                  ("Full-Service",       "standard"),
    "Super Store":                  ("Full-Service",       "standard"),
    "Large Grocery Store":          ("Full-Service",       "standard"),
    "Medium Grocery Store":         ("Full-Service",       "standard"),
    "Small Grocery Store":          ("Full-Service",       "specialty"),
    "Combination Grocery/Other":    ("Full-Service",       "specialty"),
    "Convenience Store":            ("Convenience & Fuel", "convenience"),
    "Farmers' Market":              ("Food & Grocery",     "farmers_market"),
    "Meat/Poultry Specialty":       ("Full-Service",       "specialty"),
    "Bakery Specialty":             ("Full-Service",       "specialty"),
    "Fruits/Veg Specialty":         ("Full-Service",       "specialty"),
    "Seafood Specialty":            ("Full-Service",       "specialty"),
    "Food Buying Co-op":            ("Food & Grocery",     "co_op"),
    "Delivery Route":               ("Other",              "other"),
    "Unknown":                      ("Other",              "unknown"),
}


def download_historical_zip() -> Path:
    """Download and unzip the USDA historical SNAP bulk file. Cached."""
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    if HIST_CSV.exists():
        print(f"Using cached {HIST_CSV} ({HIST_CSV.stat().st_size/1e6:.1f} MB)")
        return HIST_CSV

    print(f"Downloading USDA historical SNAP file from {HIST_URL} ...")
    r = requests.get(HIST_URL, timeout=300)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        members = zf.namelist()
        if not members:
            raise SystemExit("Downloaded ZIP contained no files.")
        # USDA names the inner file with a long human-readable filename.
        with zf.open(members[0]) as src, open(HIST_CSV, "wb") as dst:
            dst.write(src.read())
    print(f"Extracted to {HIST_CSV} ({HIST_CSV.stat().st_size/1e6:.1f} MB)")
    return HIST_CSV


def build_active_csv(hist_path: Path) -> pd.DataFrame:
    df = pd.read_csv(hist_path, low_memory=False, dtype=str)
    df.columns = [c.replace("﻿", "").strip() for c in df.columns]

    region = df[(df["State"] == "PA")
                & (df["County"].str.upper().isin(NW_PA_COUNTIES))].copy()
    print(f"All-time historical records in 11-county region: {len(region):,}")

    # End Date is blank (literally a single space) for retailers whose
    # authorization had not been withdrawn as of the file's compilation.
    region["end_blank"] = region["End Date"].fillna("").str.strip() == ""
    active = region[region["end_blank"]].copy()
    print(f"Currently-authorized retailers: {len(active):,}")

    active["category"] = active["Store Type"].map(
        lambda x: STORE_TYPE_MAP.get(str(x).strip(), ("Food & Grocery", "unknown"))[0]
    )
    active["tier"] = active["Store Type"].map(
        lambda x: STORE_TYPE_MAP.get(str(x).strip(), ("Food & Grocery", "unknown"))[1]
    )
    active["address"] = (
        active["Street Number"].fillna("").astype(str).str.strip()
        + " "
        + active["Street Name"].fillna("").astype(str).str.strip()
    ).str.strip()

    out = pd.DataFrame({
        "name":               active["Store Name"].astype(str).str.strip(),
        "address":            active["address"],
        "county":             active["County"].astype(str).str.upper(),
        "state":              active["State"],
        "zip":                active["Zip Code"].astype(str).str.zfill(5),
        "lat":                pd.to_numeric(active["Latitude"], errors="coerce"),
        "lon":                pd.to_numeric(active["Longitude"], errors="coerce"),
        "category":           active["category"],
        "tier":               active["tier"],
        "store_type_raw":     active["Store Type"],
        "authorization_date": active["Authorization Date"],
        "geocode_source":     "usda_historical_2005_2025",
    })
    out = out.dropna(subset=["lat", "lon"])
    out = out[out["lat"] != 0].reset_index(drop=True)
    return out


def main():
    hist = download_historical_zip()
    active = build_active_csv(hist)

    print(f"\nFinal active-retailer CSV: {len(active):,} rows with valid coords")
    print("\nBy USDA store_type:")
    print(active["store_type_raw"].value_counts().to_string())

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    active.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}  ({OUT_CSV.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
