"""
lib/service_overlays.py
Shared service-overlay helpers used by the Access & Equity and Desert Analysis
tabs. Provides point-scatter pydeck layers for pantries, SNAP stores, health
facilities, civic amenities, and transit stops so both tabs render identically.
"""
import pandas as pd
import pydeck as pdk


PROGRAM_TYPE_COLORS = {
    "Food Pantry":           [34, 197, 94, 220],
    "BackPacks":             [59, 130, 246, 220],
    "School Pantry":         [99, 102, 241, 220],
    "Soup Kitchen":          [251, 146, 60, 220],
    "Produce Express":       [20, 184, 166, 220],
    "Non-Emerg. Meal/Snack": [168, 85, 247, 220],
    "Shelter":               [239, 68, 68, 220],
    "Youth Program":         [245, 158, 11, 220],
    "Just In Time":          [6, 182, 212, 220],
    "Other":                 [156, 163, 175, 200],
}

OVERLAY_COLORS = {
    "snap":         [16, 185, 129, 220],
    "hospitals":    [220, 38, 38, 240],
    "clinics":      [251, 146, 60, 220],
    "pharmacies":   [239, 68, 68, 200],
    "libraries":    [59, 130, 246, 220],
    "comm_centers": [168, 85, 247, 220],
    "social_svc":   [192, 132, 252, 200],
    "transit":      [107, 114, 128, 180],
}

OVERLAY_RADII = {
    "snap":         200,
    "hospitals":    350,
    "clinics":      250,
    "pharmacies":   200,
    "libraries":    250,
    "comm_centers": 250,
    "social_svc":   200,
    "transit":      150,
}


def filter_pois_by_type(pois, primary_category, type_val):
    mask = (pois["primary_category"] == primary_category) & (pois["type"] == type_val)
    return pois[mask].dropna(subset=["lat", "lon"])


def _scatter(points, color, radius):
    return pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position=["lon", "lat"],
        get_radius=radius,
        get_fill_color=color,
        pickable=True,
        opacity=0.9,
    )


def build_service_layers(enabled, pantry_locations=None, pois=None, transit_stops=None):
    """
    Build a list of pydeck ScatterplotLayers for enabled service overlays.

    enabled: dict with any subset of keys:
      pantries, snap, hospitals, clinics, pharmacies,
      libraries, comm_centers, social_svc, transit
    Values are truthy/falsy.
    """
    layers = []

    if enabled.get("pantries") and pantry_locations is not None and len(pantry_locations) > 0:
        pl = pantry_locations.dropna(subset=["lat", "lon"]).copy()
        pl["color"] = pl["program_type"].map(PROGRAM_TYPE_COLORS).apply(
            lambda c: c if isinstance(c, list) else PROGRAM_TYPE_COLORS["Other"]
        )
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=pl,
            get_position=["lon", "lat"],
            get_radius=300,
            get_fill_color="color",
            pickable=True,
            opacity=0.9,
        ))

    if enabled.get("snap") and pois is not None:
        snap_flag = pois.get("snap_eligible", pd.Series(dtype=str)).astype(str).str.lower() == "true"
        if snap_flag.sum() == 0:
            snap_flag = pois.get("geocode_source", pd.Series(dtype=str)) == "usda_snap"
        pts = pois[snap_flag].dropna(subset=["lat", "lon"])
        if len(pts) > 0:
            layers.append(_scatter(pts, OVERLAY_COLORS["snap"], OVERLAY_RADII["snap"]))

    poi_mappings = [
        ("hospitals",    "Health",            "Hospital"),
        ("clinics",      "Health",            "Clinic"),
        ("pharmacies",   "Health",            "Pharmacy"),
        ("libraries",    "Education & Civic", "Library"),
        ("comm_centers", "Civic & Social",    "Community Center"),
        ("social_svc",   "Civic & Social",    "Social Services"),
    ]
    for key, primary_cat, type_val in poi_mappings:
        if enabled.get(key) and pois is not None:
            pts = filter_pois_by_type(pois, primary_cat, type_val)
            if len(pts) > 0:
                layers.append(_scatter(pts, OVERLAY_COLORS[key], OVERLAY_RADII[key]))

    if enabled.get("transit") and transit_stops is not None and len(transit_stops) > 0:
        pts = transit_stops.dropna(subset=["stop_lat", "stop_lon"]).rename(
            columns={"stop_lat": "lat", "stop_lon": "lon"}
        )
        if len(pts) > 0:
            layers.append(_scatter(pts, OVERLAY_COLORS["transit"], OVERLAY_RADII["transit"]))

    return layers
