"""
process_agency_list.py
Filters, normalizes, and geocodes the Second Harvest AgencyList.csv.

Run:   python process_agency_list.py
Output: data/processed/pantry_locations.csv
"""
import pandas as pd
import requests
import time
from pathlib import Path

INPUT_PATH  = "data/raw/AgencyList.csv"
OUTPUT_PATH = "data/processed/pantry_locations.csv"

TARGET_COUNTIES = {
    "CAMERON", "CLARION", "CLEARFIELD", "CRAWFORD", "ELK",
    "ERIE", "FOREST", "JEFFERSON", "MCKEAN", "VENANGO", "WARREN"
}

AGENCY_TYPE_MAP = {
    "Food Pantry- Agency":      "Food Pantry",
    "Backpack- Agency":         "BackPacks",
    "School Pantry - Agency":   "School Pantry",
    "Soup Kitchen- Agency":     "Soup Kitchen",
    "Produce Express -Agency":  "Produce Express",
    "Non-Emergency- Agency":    "Non-Emerg. Meal/Snack",
    "Shelter -Agency":          "Shelter",
    "Youth Program - Agency":   "Youth Program",
    "Just In Time - Agency":    "Just In Time",
}

TEST_REF_CODES = {"99999", "7357"}


def census_geocode(street, city, state, zip_code):
    url = "https://geocoding.geo.census.gov/geocoder/locations/address"
    params = {
        "street":    street,
        "city":      city,
        "state":     state,
        "zip":       zip_code,
        "benchmark": "Public_AR_Current",
        "format":    "json",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        matches = r.json()["result"]["addressMatches"]
        if matches:
            c = matches[0]["coordinates"]
            return c["x"], c["y"]   # lon, lat
    except Exception:
        pass
    return None, None


def main():
    df = pd.read_csv(INPUT_PATH)
    df.columns = df.columns.str.strip()
    print(f"Loaded {len(df)} agencies from {INPUT_PATH}")

    # ── Filters ───────────────────────────────────────────────
    df = df[~df["Is Suspended"].astype(str).str.strip().str.upper().eq("TRUE")]
    print(f"  After removing suspended: {len(df)}")

    df = df[~df["Agency Name"].str.contains("TEST", case=False, na=False)]
    df = df[~df["Agency - Reference Code"].astype(str).str.strip().isin(TEST_REF_CODES)]
    print(f"  After removing test agencies: {len(df)}")

    df = df[~df["Agency Type"].astype(str).str.contains("Affiliated Food Bank", na=False)]
    print(f"  After removing affiliated food banks: {len(df)}")

    df = df[df["Address Line1"].notna() & df["Address Line1"].astype(str).str.strip().ne("")]
    print(f"  After removing blank addresses: {len(df)}")

    df["County"] = df["County"].astype(str).str.strip()
    df = df[df["County"].isin(TARGET_COUNTIES)]
    print(f"  After filtering to 11 target counties: {len(df)}")

    # ── Normalization ─────────────────────────────────────────
    df["county"] = df["County"].str.title()
    df["Agency Type"] = df["Agency Type"].astype(str).str.strip()
    df["program_type"] = df["Agency Type"].map(AGENCY_TYPE_MAP).fillna("Other")

    def build_address(row):
        addr = str(row["Address Line1"]).strip()
        addr2 = str(row.get("Address Line2", "")).strip()
        if addr2 and addr2.lower() != "nan":
            addr = addr + " " + addr2
        return addr

    df["address"] = df.apply(build_address, axis=1)
    df["city"]    = df["City"].astype(str).str.strip()
    df["postal_code"] = df["Postal Code"].astype(str).str.strip()

    # ── Geocoding ─────────────────────────────────────────────
    lats, lons, sources = [], [], []
    failed = []
    total  = len(df)
    print(f"\nGeocoding {total} agencies via Census Bureau geocoder...")

    for i, (_, row) in enumerate(df.iterrows(), 1):
        lon, lat = census_geocode(row["address"], row["city"], "PA", row["postal_code"])
        lats.append(lat)
        lons.append(lon)
        if lat is not None:
            sources.append("census")
        else:
            sources.append("failed")
            failed.append({
                "agency_name": row["Agency Name"],
                "county":      row["county"],
                "address":     f"{row['address']}, {row['city']}, PA {row['postal_code']}",
            })

        if i % 20 == 0 or i == total:
            print(f"  {i}/{total}  ({len(failed)} failures so far)")
        time.sleep(0.35)

    df["lat"]           = lats
    df["lon"]           = lons
    df["geocode_source"] = sources

    if failed:
        print(f"\nWARNING: {len(failed)} agencies could not be geocoded:")
        for f in failed:
            print(f"  [{f['county']}] {f['agency_name']} — {f['address']}")

    # ── Output ────────────────────────────────────────────────
    output = df.rename(columns={
        "Agency Name":             "agency_name",
        "Agency - Reference Code": "agency_ref",
        "Is Agency Pickup":        "is_pickup",
    })

    output = output[[
        "agency_ref", "agency_name", "program_type", "county",
        "address", "city", "postal_code",
        "lat", "lon", "is_pickup", "geocode_source",
    ]]

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(output)} agencies → {OUTPUT_PATH}")
    print(f"  Geocoded: {(output['geocode_source'] == 'census').sum()}")
    print(f"  Failed:   {(output['geocode_source'] == 'failed').sum()}")
    print(f"\nProgram type breakdown:")
    print(output["program_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
