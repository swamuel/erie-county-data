"""
fetch_osm_pois.py — Pull all community service POIs from OpenStreetMap
for Erie and Crawford County, PA via the Overpass API.

Covers: food retail, pharmacies, libraries, schools, clinics/hospitals,
        community centers, and farmers markets.

Outputs to data/raw/osm_pois_raw.csv for review before use in the app.

Run with: python fetch_osm_pois.py
"""

import requests
import pandas as pd
import time

# ── BOUNDING BOX ──────────────────────────────────────────
# Covers Erie + Crawford County with a small margin
BBOX = "41.49,-80.52,42.27,-79.68"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ── THREE-TIER TAXONOMY ───────────────────────────────────
# primary_category → type → subtype
# Each OSM tag combination maps to this schema.

OSM_TAG_MAP = {
    # ── FOOD & GROCERY ────────────────────────────────────
    ("shop", "supermarket"):      ("Food & Grocery", "Grocery Store",    "Full-Service Grocery"),
    ("shop", "grocery"):          ("Food & Grocery", "Grocery Store",    "Specialty/Independent"),
    ("shop", "greengrocer"):      ("Food & Grocery", "Grocery Store",    "Produce/Specialty"),
    ("shop", "convenience"):      ("Food & Grocery", "Convenience Store","Convenience & Fuel"),
    ("shop", "department_store"): ("Food & Grocery", "Big Box",          "Big Box Retail"),
    ("shop", "wholesale"):        ("Food & Grocery", "Big Box",          "Wholesale"),
    ("amenity", "marketplace"):   ("Food & Grocery", "Farmers Market",   "Farmers Market"),
    ("amenity", "farmers_market"):("Food & Grocery", "Farmers Market",   "Farmers Market"),

    # ── HEALTH ───────────────────────────────────────────
    ("amenity", "pharmacy"):      ("Health", "Pharmacy",        "Retail Pharmacy"),
    ("amenity", "hospital"):      ("Health", "Hospital",        "Acute Care Hospital"),
    ("amenity", "clinic"):        ("Health", "Clinic",          "Outpatient Clinic"),
    ("amenity", "doctors"):       ("Health", "Clinic",          "Medical Office"),
    ("amenity", "dentist"):       ("Health", "Clinic",          "Dental Office"),
    ("amenity", "veterinary"):    ("Health", "Clinic",          "Veterinary"),

    # ── EDUCATION ────────────────────────────────────────
    ("amenity", "library"):       ("Education & Civic", "Library",         "Public Library"),
    ("amenity", "school"):        ("Education & Civic", "School",          "K-12 School"),
    ("amenity", "university"):    ("Education & Civic", "Higher Education","University/College"),
    ("amenity", "college"):       ("Education & Civic", "Higher Education","Community College"),
    ("amenity", "kindergarten"):  ("Education & Civic", "School",          "Early Childhood"),

    # ── CIVIC & SOCIAL SERVICES ───────────────────────────
    ("amenity", "community_centre"): ("Civic & Social", "Community Center", "Community/Rec Center"),
    ("amenity", "social_facility"):  ("Civic & Social", "Social Services",  "Social Services"),
    ("amenity", "place_of_worship"): ("Civic & Social", "Faith Community",  "Place of Worship"),
    ("amenity", "post_office"):      ("Civic & Social", "Government",       "Post Office"),
    ("amenity", "townhall"):         ("Civic & Social", "Government",       "Government Office"),
    ("amenity", "fire_station"):     ("Civic & Social", "Emergency Services","Fire Station"),
    ("amenity", "police"):           ("Civic & Social", "Emergency Services","Police Station"),
    ("amenity", "bank"):             ("Civic & Social", "Financial",        "Bank/Credit Union"),
}

# Map primary_category to a display color [R, G, B]
CATEGORY_COLORS = {
    "Food & Grocery":   (34,  197, 94),
    "Health":           (239, 68,  68),
    "Education & Civic":(59,  130, 246),
    "Civic & Social":   (168, 85,  247),
}

# Food store name → tier (for the food retail layer specifically)
STORE_TIER_MAP = {
    "wegmans":              "premium",
    "erie food co-op":      "premium",
    "westside market":      "premium",
    "giant eagle":          "standard",
    "tops":                 "standard",
    "tops markets":         "standard",
    "aldi":                 "value",
    "save a lot":           "value",
    "serafins":             "specialty",
    "dollar general":       "dollar",
    "dollar tree":          "dollar",
    "family dollar":        "dollar",
    "walmart":              "bigbox",
    "target":               "bigbox",
    "big lots":             "bigbox",
    "country fair":         "convenience",
    "sheetz":               "convenience",
    "speedway":             "convenience",
    "kwikfill":             "convenience",
    "getgo":                "convenience",
    "circle k":             "convenience",
    "crosby's":             "convenience",
    "sunoco":               "convenience",
}

def build_query():
    """Build Overpass QL query for all POI types."""
    tag_pairs = list(OSM_TAG_MAP.keys())

    node_lines = []
    way_lines = []
    for key, val in tag_pairs:
        node_lines.append(f'  node["{key}"="{val}"]({BBOX});')
        way_lines.append(f'  way["{key}"="{val}"]({BBOX});')

    nodes = "\n".join(node_lines)
    ways  = "\n".join(way_lines)

    return f"""
[out:json][timeout:90];
(
{nodes}
{ways}
);
out center body;
"""


def fetch_overpass(query):
    print("Querying Overpass API...")
    r = requests.get(OVERPASS_URL, params={"data": query}, timeout=120)
    r.raise_for_status()
    data = r.json()
    print(f"  {len(data['elements'])} raw elements returned")
    return data["elements"]


def resolve_taxonomy(tags):
    """Map OSM tags to three-tier taxonomy."""
    for (key, val), taxonomy in OSM_TAG_MAP.items():
        if tags.get(key) == val:
            return taxonomy
    return ("Other", "Other", "Other")


def get_food_tier(name):
    if not name:
        return None
    n = name.lower().strip()
    for key, tier in STORE_TIER_MAP.items():
        if key in n:
            return tier
    return None


def parse_elements(elements):
    rows = []
    seen = set()  # dedup by (name_lower, lat_r, lon_r)

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()

        if not name:
            continue

        name_lower = name.lower().strip()

        # Coordinates
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if not lat or not lon:
            continue

        # Dedup
        key = (name_lower, round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)

        # Taxonomy
        primary, type_, subtype = resolve_taxonomy(tags)

        # Color from primary category
        color = CATEGORY_COLORS.get(primary, (100, 100, 100))

        # Food tier (only relevant for food stores)
        food_tier = get_food_tier(name) if primary == "Food & Grocery" else None

        # Address
        addr_parts = []
        for field in ["addr:housenumber", "addr:street", "addr:city",
                      "addr:state", "addr:postcode"]:
            if tags.get(field):
                addr_parts.append(tags[field])
        address = ", ".join(addr_parts) if addr_parts else ""

        rows.append({
            "name":             name,
            "address":          address,
            "primary_category": primary,
            "type":             type_,
            "subtype":          subtype,
            "food_tier":        food_tier or "",
            "lat":              lat,
            "lon":              lon,
            "color_r":          color[0],
            "color_g":          color[1],
            "color_b":          color[2],
            "osm_id":           el.get("id"),
            "osm_type":         el.get("type"),
            "osm_shop":         tags.get("shop", ""),
            "osm_amenity":      tags.get("amenity", ""),
            "brand":            tags.get("brand", ""),
            "opening_hours":    tags.get("opening_hours", ""),
            "website":          tags.get("website", ""),
            "phone":            tags.get("phone", ""),
            "geocode_source":   "openstreetmap",
        })

    return pd.DataFrame(rows)


def print_summary(df):
    print(f"\nTotal POIs: {len(df)}")
    print("\nBy primary category:")
    print(df.groupby("primary_category").size().sort_values(ascending=False).to_string())
    print("\nBy type:")
    print(df.groupby(["primary_category", "type"]).size().to_string())

    food = df[df["primary_category"] == "Food & Grocery"]
    if len(food):
        print(f"\nFood stores with unknown tier: {(food['food_tier'] == '').sum()}")
        print("  These need manual tier assignment before use in the app")
        unknowns = food[food["food_tier"] == ""][["name","subtype","address"]]
        if len(unknowns):
            print(unknowns.to_string(index=False))


def main():
    query = build_query()
    elements = fetch_overpass(query)
    time.sleep(1)

    df = parse_elements(elements)
    print(f"  {len(df)} unique named POIs after deduplication")

    print_summary(df)

    # Sort by category then name for easy review
    df = df.sort_values(["primary_category", "type", "name"]).reset_index(drop=True)

    output = "data/raw/osm_pois_raw.csv"
    df.to_csv(output, index=False)
    print(f"\nSaved to {output}")

    # Also write category-specific files for easier review
    for cat in df["primary_category"].unique():
        cat_df = df[df["primary_category"] == cat]
        safe_name = cat.lower().replace(" ", "_").replace("&", "and")
        path = f"data/raw/osm_{safe_name}_raw.csv"
        cat_df.to_csv(path, index=False)
        print(f"  {path} ({len(cat_df)} rows)")

    print("\nNext steps:")
    print("  1. Review osm_pois_raw.csv — check names, tiers, and categories")
    print("  2. Fix food_tier for any blank rows in Food & Grocery")
    print("  3. Remove anything that doesn't belong (e.g. private clinics, ATMs)")
    print("  4. Use category-specific files to wire layers into the sandbox")


if __name__ == "__main__":
    main()