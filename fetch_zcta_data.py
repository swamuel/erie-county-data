# ZCTA level ACS 5-Year Estimates for the Second Harvest NW PA service region
# ZCTAs are discovered dynamically via TIGER spatial join (cached locally)

import requests
import pandas as pd
import geopandas as gpd
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
api_key = os.getenv("CENSUS_API_KEY")

from lib.constants import FIPS_LIST, FIPS_TO_NAME

ZCTA_CACHE = Path("data/raw/region_zctas.csv")   # zcta, area_name, county_name

# Hand-crafted display names that override Gazetteer lookups.
# Erie city ZIPs get neighborhood labels; Crawford/Erie small towns get their town name.
ZCTA_OVERRIDES = {
    "16501": "Erie Downtown",        "16502": "Erie West",
    "16503": "Erie East",            "16504": "Erie South East",
    "16505": "Erie Frontier/West",   "16506": "Erie Millcreek/West",
    "16507": "Erie Downtown",        "16508": "Erie South Central",
    "16509": "Erie Millcreek/South", "16510": "Erie Harborcreek",
    "16511": "Erie Lawrence Park",   "16563": "Erie Penn State Behrend",
    "16110": "Adamsville",   "16111": "Atlantic",         "16131": "Hartstown",
    "16134": "Jamestown",    "16314": "Cochranton",       "16316": "Conneaut Lake",
    "16327": "Guys Mills",   "16328": "Hydetown",         "16335": "Meadville",
    "16354": "Titusville",   "16360": "Townville",        "16403": "Cambridge Springs",
    "16404": "Centerville",  "16406": "Conneautville",    "16422": "Harmonsburg",
    "16424": "Linesville",   "16432": "Riceville",        "16433": "Saegertown",
    "16434": "Spartansburg", "16435": "Springboro",       "16440": "Venango",
    "16401": "Albion",       "16407": "Corry",            "16410": "Cranesville",
    "16411": "East Springfield", "16412": "Edinboro",     "16413": "Elgin",
    "16415": "Fairview",     "16417": "Girard",           "16421": "Lake City",
    "16423": "Lowville/Wattsburg", "16426": "McKean",     "16427": "Mill Village",
    "16428": "North East",   "16430": "Platea",           "16438": "Union City",
    "16441": "Waterford",    "16442": "Wattsburg",        "16443": "West Springfield",
}


def discover_region_zctas(force=False):
    """
    Find all ZCTAs that intersect the 11-county NW PA region using TIGER
    boundary files. Results are cached to data/raw/region_zctas.csv.

    Returns a DataFrame with columns: zcta, area_name, county_name
    """
    if ZCTA_CACHE.exists() and not force:
        print(f"Using cached ZCTA list from {ZCTA_CACHE}")
        return pd.read_csv(ZCTA_CACHE, dtype={"zcta": str})

    print("Discovering ZCTAs via TIGER spatial join...")
    import warnings
    warnings.filterwarnings("ignore")

    county_url = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
    zcta_url   = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"

    print("  Loading county boundaries...")
    counties = gpd.read_file(county_url)
    counties = counties[
        (counties["STATEFP"] == "42") &
        (counties["COUNTYFP"].isin(FIPS_LIST))
    ].copy()
    counties = counties.to_crs("EPSG:4326")
    print(f"  {len(counties)} counties loaded")

    print("  Loading ZCTA boundaries (large file, may take a moment)...")
    zctas = gpd.read_file(zcta_url)
    # Pre-filter to rough PA bounding box before spatial join
    zctas = zctas.cx[-80.6:-77.7, 40.7:42.3].copy()
    zctas = zctas.to_crs("EPSG:4326")
    print(f"  {len(zctas)} ZCTAs in PA bounding box")

    print("  Spatial join ZCTAs -> counties...")
    joined = gpd.sjoin(zctas, counties[["COUNTYFP", "NAME", "geometry"]], how="inner", predicate="intersects")
    joined = joined.rename(columns={"ZCTA5CE20": "zcta", "NAME": "county_name"})
    joined["zcta"] = joined["zcta"].astype(str).str.zfill(5)
    joined["county_name"] = joined["county_name"].str.strip()

    # Keep one row per ZCTA (some ZCTAs span county lines — assign to the county with most overlap)
    result = (
        joined.groupby("zcta")
        .agg(county_name=("county_name", "first"))
        .reset_index()
    )

    # Drop border ZCTAs that are actually in neighboring states (NY 14xxx, OH 43-44xxx).
    # PA ZIPs are in the 15000–19999 range.
    result = result[result["zcta"].str.match(r"^1[5-9]")].copy()
    print(f"  {len(result)} PA ZCTAs after filtering out out-of-state border ZCTAs")

    # Get city/place names from Census Gazetteer file
    print("  Fetching ZIP code place names from Census Gazetteer...")
    try:
        gaz_url = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_zcta_national.zip"
        gaz = pd.read_csv(gaz_url, sep="\t", dtype={"GEOID": str}, usecols=["GEOID", "NAME"])
        gaz["zcta"] = gaz["GEOID"].str.zfill(5)
        gaz_map = dict(zip(gaz["zcta"], gaz["NAME"]))
        result["area_name"] = result["zcta"].map(gaz_map).fillna(result["zcta"])
        print(f"  Got names for {result['area_name'].notna().sum()} ZCTAs")
    except Exception as e:
        print(f"  Could not load Gazetteer ({e}), using ZIP as name")
        result["area_name"] = result["zcta"]

    # Apply hand-crafted overrides (neighborhood names for Erie city ZIPs, named towns)
    result["area_name"] = result["zcta"].map(ZCTA_OVERRIDES).fillna(result["area_name"])

    ZCTA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(ZCTA_CACHE, index=False)
    print(f"  Discovered {len(result)} ZCTAs, saved to {ZCTA_CACHE}")
    print(f"  By county:\n{result['county_name'].value_counts().to_string()}")
    return result


# ── Load ZCTA list ────────────────────────────────────────────────────────────
zcta_df   = discover_region_zctas()
ZCTA_LIST = zcta_df["zcta"].tolist()
AREA_NAME = dict(zip(zcta_df["zcta"], zcta_df["area_name"]))
COUNTY_LOOKUP = dict(zip(zcta_df["zcta"], zcta_df["county_name"]))

print(f"\nFetching ACS data for {len(ZCTA_LIST)} ZCTAs...")

# ── ACS variables ─────────────────────────────────────────────────────────────
variables = {
    # Economic
    "B19013_001E": "median_household_income",
    "B17001_002E": "poverty_population",
    "B17001_001E": "poverty_total",
    "B15003_022E": "bachelors_degree",
    "B15003_001E": "education_total",
    "B25070_010E": "rent_burdened",
    "B25070_001E": "rent_total",
    "B08201_002E": "no_vehicle_households",
    "B08201_001E": "vehicle_total",
    # Demographics
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B03002_003E": "white_non_hispanic",
    "B03002_001E": "race_total",
    "B02001_003E": "black_alone",
    "B03003_003E": "hispanic_latino",
    "B02001_005E": "asian_alone",
    # Employment
    "B23025_005E": "unemployed",
    "B23025_003E": "labor_force",
    # Homeownership
    "B25003_002E": "owner_occupied",
    "B25003_001E": "housing_units",
}

get_vars = "NAME," + ",".join(variables.keys())
years = [2019, 2020, 2021, 2022, 2023]
all_years = []

for year in years:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": get_vars, "for": "zip code tabulation area:*", "key": api_key}
    if year < 2020:
        params["in"] = "state:42"

    response = requests.get(url, params=params)
    if response.status_code != 200 or not response.text.strip():
        print(f"{year} failed — status {response.status_code}: {response.text[:200]}")
        continue

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns=variables)
    df = df.rename(columns={"zip code tabulation area": "zcta"})
    df["zcta"] = df["zcta"].astype(str).str.zfill(5)

    # Filter to discovered region ZCTAs
    df = df[df["zcta"].isin(ZCTA_LIST)].copy()

    for col in variables.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].replace(-666666666, pd.NA)

    # Derived rates — economic
    df["poverty_rate"]      = (df["poverty_population"] / df["poverty_total"] * 100).round(1)
    df["bachelors_rate"]    = (df["bachelors_degree"] / df["education_total"] * 100).round(1)
    df["rent_burden_rate"]  = (df["rent_burdened"] / df["rent_total"] * 100).round(1)
    df["no_vehicle_rate"]   = (df["no_vehicle_households"] / df["vehicle_total"] * 100).round(1)

    # Derived rates — demographics
    df["pct_white_non_hispanic"] = (df["white_non_hispanic"] / df["total_population"] * 100).round(1)
    df["pct_black"]              = (df["black_alone"]        / df["total_population"] * 100).round(1)
    df["pct_hispanic"]           = (df["hispanic_latino"]    / df["total_population"] * 100).round(1)
    df["pct_asian"]              = (df["asian_alone"]        / df["total_population"] * 100).round(1)
    df["pct_other"]              = (
        100 - df["pct_white_non_hispanic"] - df["pct_black"]
            - df["pct_hispanic"] - df["pct_asian"]
    ).round(1).clip(lower=0)

    # Derived rates — employment & housing
    df["unemployment_rate"]  = (df["unemployed"]     / df["labor_force"]   * 100).round(1)
    df["homeownership_rate"] = (df["owner_occupied"] / df["housing_units"] * 100).round(1)

    drop_cols = [
        "poverty_population", "poverty_total", "bachelors_degree", "education_total",
        "rent_burdened", "rent_total", "no_vehicle_households", "vehicle_total",
        "white_non_hispanic", "race_total", "black_alone", "hispanic_latino", "asian_alone",
        "unemployed", "labor_force", "owner_occupied", "housing_units", "NAME",
    ]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    df["year"]        = year
    df["area_name"]   = df["zcta"].map(AREA_NAME)
    df["county_name"] = df["zcta"].map(COUNTY_LOOKUP)
    df["state"]       = "PA"

    all_years.append(df)
    print(f"{year} done -- {len(df)} ZCTAs, {len(df.columns)} columns")

final = pd.concat(all_years, ignore_index=True)
final["zcta"] = final["zcta"].astype(str).str.zfill(5)

print(f"\nTotal rows: {len(final)}")
print(f"Columns: {final.columns.tolist()}")
print(final.groupby(["county_name", "year"]).size())

final.to_csv("data/raw/zcta_data.csv", index=False)
print("\nSaved to data/raw/zcta_data.csv")
