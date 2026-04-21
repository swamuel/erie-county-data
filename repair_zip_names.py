"""
One-time repair script: restores descriptive area_name values for all ZCTAs.
  - Uses hand-crafted names for original Erie/Crawford ZIPs
  - Looks up USPS city names via zippopotam.us for remaining ZIPs
  - Updates region_zctas.csv and backfills zcta_data.csv
"""

import time
import requests
import pandas as pd

ZCTA_OVERRIDES = {
    # Erie city neighborhoods
    "16501": "Erie Downtown",       "16502": "Erie West",
    "16503": "Erie East",           "16504": "Erie South East",
    "16505": "Erie Frontier/West",  "16506": "Erie Millcreek/West",
    "16507": "Erie Downtown",       "16508": "Erie South Central",
    "16509": "Erie Millcreek/South","16510": "Erie Harborcreek",
    "16511": "Erie Lawrence Park",  "16563": "Erie Penn State Behrend",
    # Crawford County towns
    "16110": "Adamsville",      "16111": "Atlantic",         "16131": "Hartstown",
    "16134": "Jamestown",       "16314": "Cochranton",       "16316": "Conneaut Lake",
    "16327": "Guys Mills",      "16328": "Hydetown",         "16335": "Meadville",
    "16354": "Titusville",      "16360": "Townville",        "16403": "Cambridge Springs",
    "16404": "Centerville",     "16406": "Conneautville",    "16422": "Harmonsburg",
    "16424": "Linesville",      "16432": "Riceville",        "16433": "Saegertown",
    "16434": "Spartansburg",    "16435": "Springboro",       "16440": "Venango",
    # Erie County small towns
    "16401": "Albion",          "16407": "Corry",            "16410": "Cranesville",
    "16411": "East Springfield","16412": "Edinboro",         "16413": "Elgin",
    "16415": "Fairview",        "16417": "Girard",           "16421": "Lake City",
    "16423": "Lowville/Wattsburg","16426": "McKean",         "16427": "Mill Village",
    "16428": "North East",      "16430": "Platea",           "16438": "Union City",
    "16441": "Waterford",       "16442": "Wattsburg",        "16443": "West Springfield",
}


def lookup_city(zip_code):
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data["places"][0]["place name"]
    except Exception:
        pass
    return None


def main():
    zctas = pd.read_csv("data/raw/region_zctas.csv", dtype={"zcta": str})
    print(f"Loaded {len(zctas)} ZCTAs from region_zctas.csv")

    # Apply hand-crafted overrides first
    zctas["area_name"] = zctas["zcta"].map(ZCTA_OVERRIDES)

    # For ZIPs not in overrides, look up via API
    need_lookup = zctas[zctas["area_name"].isna()]["zcta"].tolist()
    print(f"{len(need_lookup)} ZIPs need API lookup...")

    api_names = {}
    for i, z in enumerate(need_lookup):
        name = lookup_city(z)
        api_names[z] = name if name else z
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(need_lookup)} done")
        time.sleep(0.1)  # be polite to the API

    zctas["area_name"] = zctas["area_name"].fillna(zctas["zcta"].map(api_names))
    # Final fallback: use county name
    zctas["area_name"] = zctas["area_name"].fillna(zctas["county_name"])

    zctas.to_csv("data/raw/region_zctas.csv", index=False)
    print(f"Saved updated region_zctas.csv")

    # Backfill zcta_data.csv
    zcta_data = pd.read_csv("data/raw/zcta_data.csv", dtype={"zcta": str})
    name_map = dict(zip(zctas["zcta"], zctas["area_name"]))
    zcta_data["area_name"] = zcta_data["zcta"].map(name_map).fillna(zcta_data["area_name"])
    zcta_data.to_csv("data/raw/zcta_data.csv", index=False)
    print(f"Backfilled area_name in zcta_data.csv ({len(zcta_data)} rows)")

    # Preview
    print("\nSample labels:")
    for _, row in zctas.sample(min(10, len(zctas))).iterrows():
        print(f"  {row['zcta']} → {row['area_name']} ({row['county_name']})")


if __name__ == "__main__":
    main()
