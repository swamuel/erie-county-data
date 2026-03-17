"""
fetch_grocery_stores.py
Geocodes Erie grocery and essential food stores from the 2026 Resource Guide.
Tries Census geocoder first; falls back to pre-verified coordinates if network
is unavailable or a lookup fails.

Run from project root:
    python fetch_grocery_stores.py
Output: data/raw/erie_grocery_stores.csv
"""

import requests
import pandas as pd
import time
import os

OUTPUT = "data/raw/erie_grocery_stores.csv"

# ── STORE LIST ────────────────────────────────────────────
# Addresses from Erie Resources & Data Guide 2026
# Pre-verified lat/lon included as fallback (manually confirmed via Google Maps)
STORES = [
    # name, address, zip, category, tier, lat_fallback, lon_fallback
    ("Wegmans",             "6143 Peach St",       "16509", "Full-Service",       "premium",     42.0435, -80.0513),
    ("Erie Food Co-op",     "1341 W 26th St",      "16508", "Full-Service",       "premium",     42.0891, -80.0947),
    ("Westside Market",     "1119 Powell Ave",     "16505", "Full-Service",       "premium",     42.1132, -80.1201),
    ("Serafins Market",     "601 E 24th St",       "16503", "Full-Service",       "specialty",   42.0924, -80.0683),
    ("Giant Eagle",         "2067 Interchange Rd", "16509", "Full-Service",       "standard",    42.0321, -80.0498),
    ("TOPS Markets",        "712 W 38th St",       "16508", "Full-Service",       "standard",    42.0692, -80.0980),
    ("ALDI",                "2647 W 12th St",      "16505", "Value & Discount",   "value",       42.1208, -80.1203),
    ("Save A Lot",          "1512 Peach St",       "16501", "Value & Discount",   "value",       42.1123, -80.0754),
    ("Dollar General",      "1414 Peach St",       "16501", "Discount Variety",   "dollar",      42.1135, -80.0756),
    ("Dollar Tree",         "3810 Peach St",       "16508", "Discount Variety",   "dollar",      42.0735, -80.0853),
    ("Walmart Supercenter", "2711 Elm St",         "16504", "Big Box",            "bigbox",      42.1019, -80.0702),
    ("Target",              "6700 Peach St",       "16509", "Big Box",            "bigbox",      42.0268, -80.0492),
    ("Country Fair",        "3826 Peach St",       "16508", "Convenience & Fuel", "convenience", 42.0738, -80.0852),
    ("Sheetz",              "2060 Interchange Rd", "16509", "Convenience & Fuel", "convenience", 42.0324, -80.0496),
    ("Speedway",            "1502 W 26th St",      "16508", "Convenience & Fuel", "convenience", 42.0893, -80.0870),
]

# ── COLOR MAP BY TIER ─────────────────────────────────────
# [R, G, B] — used in Pydeck ScatterplotLayer
TIER_COLORS = {
    "premium":     [34,  197, 94],   # green
    "specialty":   [16,  185, 129],  # teal
    "standard":    [59,  130, 246],  # blue
    "value":       [251, 191, 36],   # amber
    "dollar":      [249, 115, 22],   # orange
    "bigbox":      [139, 92,  246],  # purple
    "convenience": [156, 163, 175],  # gray
}

def geocode_census(address, city="Erie", state="PA", zipcode=""):
    """Try Census Geocoder — returns (lat, lon) or None."""
    url = "https://geocoding.geo.census.gov/geocoder/locations/address"
    params = {
        "street": address,
        "city": city,
        "state": state,
        "zip": zipcode,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if matches:
            coords = matches[0]["coordinates"]
            return float(coords["y"]), float(coords["x"])
    except Exception:
        pass
    return None


def build_stores():
    rows = []
    for name, address, zipcode, category, tier, lat_fb, lon_fb in STORES:
        print(f"Geocoding: {name}...", end=" ")
        result = geocode_census(address, zipcode=zipcode)
        if result:
            lat, lon = result
            source = "census_geocoder"
            print(f"OK ({lat:.4f}, {lon:.4f})")
        else:
            lat, lon = lat_fb, lon_fb
            source = "manual_fallback"
            print(f"fallback ({lat:.4f}, {lon:.4f})")

        color = TIER_COLORS.get(tier, [100, 100, 100])
        rows.append({
            "name": name,
            "address": f"{address}, Erie, PA {zipcode}",
            "category": category,
            "tier": tier,
            "lat": lat,
            "lon": lon,
            "color_r": color[0],
            "color_g": color[1],
            "color_b": color[2],
            "geocode_source": source,
        })
        time.sleep(0.5)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    df = build_stores()
    df.to_csv(OUTPUT, index=False)
    print(f"\nSaved {len(df)} stores to {OUTPUT}")
    print(df[["name", "tier", "lat", "lon", "geocode_source"]].to_string(index=False))