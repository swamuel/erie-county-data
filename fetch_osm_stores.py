"""
fetch_osm_stores.py — Pull food retail locations from OpenStreetMap
for the Second Harvest NW PA 11-county region via the Overpass API.

Outputs to data/raw/osm_stores_raw.csv for review before merging
with erie_grocery_stores.csv.

Run with: python fetch_osm_stores.py
"""

import requests
import pandas as pd
import time

# ── BOUNDING BOX ──────────────────────────────────────────
# Covers all 11 NW PA counties (Cameron east edge to Erie/Crawford west edge,
# Clearfield south edge to Erie north edge)
BBOX = "40.85,-80.52,42.27,-77.45"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ── TIER MAPPING ──────────────────────────────────────────
# Maps known store names to your existing tier system.
# Add to this as you find new stores.
NAME_TO_TIER = {
    # Premium / Full-Service
    "wegmans":           ("Full-Service", "premium"),
    "erie food co-op":   ("Full-Service", "premium"),
    "westside market":   ("Full-Service", "premium"),
    # Standard
    "giant eagle":       ("Full-Service", "standard"),
    "tops":              ("Full-Service", "standard"),
    "tops markets":      ("Full-Service", "standard"),
    # Specialty
    "serafins":          ("Full-Service", "specialty"),
    "serafin":           ("Full-Service", "specialty"),
    # Value & Discount
    "aldi":              ("Value & Discount", "value"),
    "save a lot":        ("Value & Discount", "value"),
    "save-a-lot":        ("Value & Discount", "value"),
    # Big Box
    "walmart":           ("Big Box", "bigbox"),
    "walmart supercenter":("Big Box", "bigbox"),
    "target":            ("Big Box", "bigbox"),
    "meijer":            ("Big Box", "bigbox"),
    # Dollar
    "dollar general":    ("Discount Variety", "dollar"),
    "dollar tree":       ("Discount Variety", "dollar"),
    "family dollar":     ("Discount Variety", "dollar"),
    # Convenience
    "country fair":      ("Convenience & Fuel", "convenience"),
    "sheetz":            ("Convenience & Fuel", "convenience"),
    "speedway":          ("Convenience & Fuel", "convenience"),
    "kwikfill":          ("Convenience & Fuel", "convenience"),
    "kwick fill":        ("Convenience & Fuel", "convenience"),
    "getgo":             ("Convenience & Fuel", "convenience"),
    "sunoco":            ("Convenience & Fuel", "convenience"),
    "cumberland farms":  ("Convenience & Fuel", "convenience"),
    "7-eleven":          ("Convenience & Fuel", "convenience"),
    # Meadville / Crawford specific
    "meadville":         ("Full-Service", "standard"),
}

# Tier color mapping — matches erie_grocery_stores.csv
TIER_COLORS = {
    "premium":     (34,  197, 94),
    "specialty":   (16,  185, 129),
    "standard":    (59,  130, 246),
    "value":       (251, 191, 36),
    "dollar":      (249, 115, 22),
    "bigbox":      (139, 92,  246),
    "convenience": (156, 163, 175),
    "unknown":     (100, 100, 100),
}

OSM_TAG_DEFAULTS = {
    "supermarket": ("Full-Service", "standard"),
    "grocery":     ("Full-Service", "specialty"),
    "greengrocer": ("Full-Service", "specialty"),
    "convenience": ("Convenience & Fuel", "convenience"),
    "marketplace": ("Full-Service", "specialty"),
    "department_store": ("Big Box", "bigbox"),
    "wholesale":   ("Big Box", "bigbox"),
}

def get_tier(name, shop_tag):
    """Resolve tier from store name, falling back to OSM shop tag."""
    if name:
        name_lower = name.lower().strip()
        for key, tier_info in NAME_TO_TIER.items():
            if key in name_lower:
                return tier_info
    return OSM_TAG_DEFAULTS.get(shop_tag, ("Full-Service", "unknown"))


def build_query():
    shop_types = [
        "supermarket", "grocery", "convenience",
        "greengrocer", "department_store", "wholesale"
    ]
    node_queries = "\n  ".join(
        f'node["shop"="{s}"]({BBOX});' for s in shop_types
    )
    way_queries = "\n  ".join(
        f'way["shop"="{s}"]({BBOX});' for s in shop_types
    )
    return f"""
[out:json][timeout:180][maxsize:536870912];
(
  {node_queries}
  {way_queries}
);
out center body;
"""


def fetch_osm():
    query = build_query()
    for attempt in range(1, 4):
        print(f"Querying Overpass API (attempt {attempt})...")
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, timeout=240)
            response.raise_for_status()
        except Exception as e:
            if attempt < 3:
                print(f"  Error: {e} — retrying in 30s...")
                time.sleep(30)
                continue
            raise
        break
    data = response.json()
    print(f"  {len(data['elements'])} elements returned")
    return data["elements"]


def parse_elements(elements):
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()

        # Skip unnamed elements — not useful without a name
        if not name:
            continue

        # Coordinates — nodes have lat/lon directly, ways have center
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if not lat or not lon:
            continue

        shop_tag = tags.get("shop", "")
        category, tier = get_tier(name, shop_tag)
        color = TIER_COLORS.get(tier, TIER_COLORS["unknown"])

        # Build address from OSM tags if available
        addr_parts = []
        if tags.get("addr:housenumber"):
            addr_parts.append(tags["addr:housenumber"])
        if tags.get("addr:street"):
            addr_parts.append(tags["addr:street"])
        if tags.get("addr:city"):
            addr_parts.append(tags["addr:city"])
        if tags.get("addr:state"):
            addr_parts.append(tags["addr:state"])
        if tags.get("addr:postcode"):
            addr_parts.append(tags["addr:postcode"])
        address = ", ".join(addr_parts) if addr_parts else ""

        rows.append({
            "name":          name,
            "address":       address,
            "category":      category,
            "tier":          tier,
            "lat":           lat,
            "lon":           lon,
            "color_r":       color[0],
            "color_g":       color[1],
            "color_b":       color[2],
            "osm_id":        el.get("id"),
            "osm_type":      el.get("type"),
            "shop_tag":      shop_tag,
            "brand":         tags.get("brand", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "geocode_source": "openstreetmap",
        })

    return pd.DataFrame(rows)


def deduplicate(df):
    """
    Remove obvious duplicates — same name within ~100m.
    Uses rounded coordinates as a proxy for proximity.
    """
    df["lat_r"] = df["lat"].round(3)
    df["lon_r"] = df["lon"].round(3)
    df["name_lower"] = df["name"].str.lower().str.strip()
    before = len(df)
    df = df.drop_duplicates(subset=["name_lower", "lat_r", "lon_r"])
    df = df.drop(columns=["lat_r", "lon_r", "name_lower"])
    after = len(df)
    if before != after:
        print(f"  Removed {before - after} duplicates")
    return df


def flag_existing(df, existing_path="data/raw/erie_grocery_stores.csv"):
    """Mark stores that already exist in erie_grocery_stores.csv."""
    try:
        existing = pd.read_csv(existing_path)
        existing["name_lower"] = existing["name"].str.lower().str.strip()
        df["name_lower"] = df["name"].str.lower().str.strip()
        df["already_in_app"] = df["name_lower"].isin(existing["name_lower"])
        df = df.drop(columns=["name_lower"])
        in_app = df["already_in_app"].sum()
        new = (~df["already_in_app"]).sum()
        print(f"  {in_app} stores already in erie_grocery_stores.csv")
        print(f"  {new} new stores not yet in the app")
    except FileNotFoundError:
        print("  erie_grocery_stores.csv not found — skipping duplicate check")
        df["already_in_app"] = False
    return df


def main():
    elements = fetch_osm()
    time.sleep(1)  # Be polite to the API

    df = parse_elements(elements)
    print(f"  {len(df)} named stores parsed")

    df = deduplicate(df)
    df = flag_existing(df)

    # Sort — new stores first, then alphabetically
    df = df.sort_values(["already_in_app", "name"]).reset_index(drop=True)

    output_path = "data/raw/osm_stores_raw.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} stores to {output_path}")
    print("\nPreview:")
    print(df[["name", "category", "tier", "lat", "lon", "already_in_app"]].to_string(index=False))

    # Summary by tier
    print("\nBy tier:")
    print(df.groupby("tier").size().sort_values(ascending=False).to_string())

    print("\nNext steps:")
    print("  1. Review osm_stores_raw.csv")
    print("  2. Check 'already_in_app=False' rows for new additions")
    print("  3. Verify tier assignments — especially 'unknown' tier rows")
    print("  4. Copy approved rows into erie_grocery_stores.csv")


if __name__ == "__main__":
    main()