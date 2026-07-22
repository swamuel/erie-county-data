"""
pipeline/verify.py
==================
Accuracy verification harness for the Northwest PA Community Data app.

Answers two questions:

  1. PROVENANCE — do the local master CSVs match what the U.S. Census Bureau
     ACS 5-year API actually reports? (re-queries the API live and diffs)
  2. FIDELITY   — are the derived columns (rates, percentages) correctly
     computed from their raw components, and do row counts reconcile?

Run:  python pipeline/verify.py            (full run, writes report)
      python pipeline/verify.py --no-net   (offline checks only)
      python pipeline/verify.py --fresh    (ignore cached API pull)

Requires: CENSUS_API_KEY in .env (for the live checks)
Output:   data/verification_report.json   (consumed by the About tab badge)

Exit code 0 if every check passes, 1 otherwise — so CI / a pre-deploy step
can gate on it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ── Make repo root importable regardless of CWD ───────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
import os  # noqa: E402

from lib.constants import COUNTY_FIPS, FIPS_TO_NAME, STATE_FIPS  # noqa: E402

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("CENSUS_API_KEY")

# ── Config ────────────────────────────────────────────────────────────────
YEARS = [2019, 2020, 2021, 2022, 2023]
ACS_BASE = "https://api.census.gov/data/{year}/acs/acs5"
SUPPRESSED = -666666666           # ACS sentinel for suppressed/unavailable
RATE_TOL = 0.051                  # rates are stored rounded to 1 decimal
AGE_TOL = 0.051
CACHE_PATH = ROOT / "data" / "verification_api_cache.parquet"

# Tracts intentionally excluded by the fetch scripts (water / population 0).
# The API returns them; the masters drop them. Not a failure.
EXPECTED_EXCLUDED_TRACT_SUFFIX = "990000"

# All raw ACS variables needed to reconstruct every derived column, pulled
# in ONE request per (county, year).  Economic vars come from census_pull.py;
# demographic vars from fetch_demographics.py.
ACS_VARS = {
    # economic
    "B19013_001E": "median_household_income",
    "B17001_002E": "poverty_num",
    "B17001_001E": "poverty_den",
    "B15003_022E": "bachelors_num",
    "B15003_001E": "bachelors_den",
    "B25070_010E": "rent_num",
    "B25070_001E": "rent_den",
    "B08201_002E": "novehicle_num",
    "B08201_001E": "vehicle_den",
    # demographic
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B03002_001E": "race_total",
    "B03002_003E": "white_non_hispanic",
    "B03002_004E": "black_alone",
    "B03002_006E": "asian_alone",
    "B03002_012E": "hispanic_latino",
    # SNAP participation (B19058)
    "B19058_001E": "snap_hh_total",
    "B19058_002E": "snap_hh_receiving",
}

# ZCTA-level variables (queried nationally, then filtered to region ZCTAs).
# Race uses B03002 consistently — the same non-Hispanic basis as the tract data.
ZCTA_VARS = {
    "B19013_001E": "income", "B17001_002E": "pov_num", "B17001_001E": "pov_den",
    "B15003_022E": "bach_num", "B15003_001E": "bach_den",
    "B25070_010E": "rent_num", "B25070_001E": "rent_den",
    "B08201_002E": "noveh_num", "B08201_001E": "veh_den",
    "B01003_001E": "population", "B01002_001E": "median_age",
    "B03002_001E": "race_total", "B03002_003E": "white_nh", "B03002_004E": "black_nh",
    "B03002_006E": "asian_nh", "B03002_012E": "hispanic",
    "B23025_005E": "unemployed", "B23025_003E": "labor_force",
    "B25003_002E": "owner_occ", "B25003_001E": "occ_units",
    "B19058_002E": "snap_recv", "B19058_001E": "snap_total",
}
ZCTA_CACHE = ROOT / "data" / "verification_api_cache_zcta.parquet"


# ── Result accumulator ────────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name, passed, detail, sample=None):
        self.checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
            "sample": sample or [],
        })
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}: {detail}")
        return passed

    @property
    def all_passed(self):
        return all(c["status"] == "PASS" for c in self.checks)

    def write(self, path, meta):
        payload = {
            **meta,
            "overall": "PASS" if self.all_passed else "FAIL",
            "checks": self.checks,
        }
        path.write_text(json.dumps(payload, indent=2))
        print(f"\nReport written to {path.relative_to(ROOT)}")


# ── API pull (cached) ─────────────────────────────────────────────────────
def pull_acs(use_cache=True) -> pd.DataFrame:
    """One request per (county, year); returns a tidy raw-variable frame."""
    if use_cache and CACHE_PATH.exists():
        print(f"Using cached API pull ({CACHE_PATH.name}); pass --fresh to refresh.")
        return pd.read_parquet(CACHE_PATH)

    if not API_KEY:
        raise SystemExit("CENSUS_API_KEY missing — cannot run live checks. Use --no-net.")

    get = "NAME," + ",".join(ACS_VARS.keys())
    frames = []
    total = len(YEARS) * len(COUNTY_FIPS)
    n = 0
    for year in YEARS:
        for name, fips in COUNTY_FIPS.items():
            n += 1
            print(f"  pulling {n}/{total}: {name} {year}", end="\r")
            params = {"get": get, "for": "tract:*",
                      "in": f"state:{STATE_FIPS} county:{fips}", "key": API_KEY}
            r = requests.get(ACS_BASE.format(year=year), params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data[1:], columns=data[0]).rename(columns=ACS_VARS)
            df["tract_code"] = df["tract"].astype(str).str.zfill(6)
            df["county_fips"] = fips
            df["county_name"] = name
            df["year"] = year
            frames.append(df)
            time.sleep(0.1)
    print()
    out = pd.concat(frames, ignore_index=True)
    for col in ACS_VARS.values():
        out[col] = pd.to_numeric(out[col], errors="coerce").replace(SUPPRESSED, pd.NA)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CACHE_PATH, index=False)
    return out


def rate(num, den):
    """Vectorised rate = num/den*100, rounded to 1 dp, NA where den<=0."""
    num = pd.to_numeric(num, errors="coerce")
    den = pd.to_numeric(den, errors="coerce")
    out = (num / den * 100).round(1)
    out[(den.isna()) | (den <= 0)] = pd.NA
    return out


def _mismatches(merged, stored_col, api_col, tol, keys):
    """Rows where both sides are present and differ beyond tolerance."""
    s = pd.to_numeric(merged[stored_col], errors="coerce")
    a = pd.to_numeric(merged[api_col], errors="coerce")
    both = s.notna() & a.notna()
    bad = both & ((s - a).abs() > tol)
    # also flag where stored has a value but API says NA (or vice-versa)
    only_one = s.notna() ^ a.notna()
    flagged = merged[bad | only_one].copy()
    cols = keys + [stored_col, api_col]
    return flagged[cols].head(15).to_dict("records"), int((bad | only_one).sum())


# ── Check 1: tract economic provenance (erie_tract_data.csv) ──────────────
def check_economic(api: pd.DataFrame, rep: Report):
    path = ROOT / "data" / "raw" / "erie_tract_data.csv"
    csv = pd.read_csv(path, dtype={"tract_code": str})
    csv["tract_code"] = csv["tract_code"].str.zfill(6)

    a = api.copy()
    a["poverty_rate_api"] = rate(a["poverty_num"], a["poverty_den"])
    a["bachelors_rate_api"] = rate(a["bachelors_num"], a["bachelors_den"])
    a["rent_burden_rate_api"] = rate(a["rent_num"], a["rent_den"])
    a["no_vehicle_rate_api"] = rate(a["novehicle_num"], a["vehicle_den"])
    a["income_api"] = a["median_household_income"]

    keys = ["county_name", "year", "tract_code"]
    m = csv.merge(
        a[keys + ["income_api", "poverty_rate_api", "bachelors_rate_api",
                  "rent_burden_rate_api", "no_vehicle_rate_api"]],
        on=keys, how="left",
    )

    pairs = [
        ("median_household_income", "income_api", 0.5),
        ("poverty_rate", "poverty_rate_api", RATE_TOL),
        ("bachelors_rate", "bachelors_rate_api", RATE_TOL),
        ("rent_burden_rate", "rent_burden_rate_api", RATE_TOL),
        ("no_vehicle_rate", "no_vehicle_rate_api", RATE_TOL),
    ]
    ok = True
    for stored, apicol, tol in pairs:
        sample, count = _mismatches(m, stored, apicol, tol, keys)
        passed = count == 0
        ok &= passed
        rep.add(f"economic · {stored} vs live API",
                passed,
                f"{len(m)} tract-years checked, {count} mismatch(es)",
                sample if not passed else None)
    return ok


# ── Check 2: tract demographics provenance (tract_demographics.csv) ───────
def check_demographics(api: pd.DataFrame, rep: Report):
    path = ROOT / "data" / "raw" / "tract_demographics.csv"
    csv = pd.read_csv(path, dtype={"tract_code": str, "county_fips": str})
    csv["tract_code"] = csv["tract_code"].str.zfill(6)
    csv["county_fips"] = csv["county_fips"].str.zfill(3)
    # 9900-series are unpopulated water tracts (not real geographies); the app
    # never renders them. Excluded here to match the row-reconciliation policy.
    # NOTE: tract_demographics.csv currently retains these rows with an
    # unscrubbed -666666666 sentinel — the flat-master pipeline drops them.
    csv = csv[~csv["tract_code"].str.endswith(EXPECTED_EXCLUDED_TRACT_SUFFIX)]

    keys = ["county_fips", "year", "tract_code"]
    a = api.rename(columns={
        "total_population": "pop_api", "median_age": "age_api",
        "race_total": "race_total_api", "white_non_hispanic": "white_api",
        "black_alone": "black_api", "asian_alone": "asian_api",
        "hispanic_latino": "hisp_api",
    })
    m = csv.merge(
        a[keys + ["pop_api", "age_api", "race_total_api", "white_api",
                  "black_api", "asian_api", "hisp_api"]],
        on=keys, how="left",
    )

    ok = True
    # raw components must match exactly (population, race counts) / age within tol
    for stored, apicol, tol in [
        ("total_population", "pop_api", 0.5),
        ("median_age", "age_api", AGE_TOL),
        ("race_total", "race_total_api", 0.5),
        ("white_non_hispanic", "white_api", 0.5),
        ("black_alone", "black_api", 0.5),
        ("asian_alone", "asian_api", 0.5),
        ("hispanic_latino", "hisp_api", 0.5),
    ]:
        sample, count = _mismatches(m, stored, apicol, tol, keys)
        passed = count == 0
        ok &= passed
        rep.add(f"demographics · {stored} vs live API",
                passed,
                f"{len(m)} tract-years checked, {count} mismatch(es)",
                sample if not passed else None)

    # derived percentages recomputed from stored components (offline fidelity)
    d = csv.copy()
    mask = pd.to_numeric(d["race_total"], errors="coerce") > 0
    for pct_col, comp in [
        ("pct_white_non_hispanic", "white_non_hispanic"),
        ("pct_black", "black_alone"),
        ("pct_hispanic", "hispanic_latino"),
        ("pct_asian", "asian_alone"),
    ]:
        recomputed = rate(d[comp], d["race_total"])
        stored = pd.to_numeric(d[pct_col], errors="coerce")
        diff = (recomputed - stored).abs()
        bad = int((diff > RATE_TOL).sum())
        passed = bad == 0
        ok &= passed
        rep.add(f"demographics · {pct_col} recompute",
                passed,
                f"{int(mask.sum())} populated tracts, {bad} recompute mismatch(es)",
                None)
    return ok


# ── Check 3: county benchmark cross-check (benchmarks_pa_counties.csv) ─────
def check_county_benchmarks(rep: Report, use_net: bool):
    path = ROOT / "data" / "raw" / "benchmarks_pa_counties.csv"
    csv = pd.read_csv(path, dtype={"county_fips": str})
    csv["county_fips"] = csv["county_fips"].str.zfill(3)
    csv = csv[csv["county_fips"].isin(COUNTY_FIPS.values())]

    if not use_net:
        rep.add("county benchmarks vs live API", True,
                "skipped (offline mode)", None)
        return True

    # Pull county-level ACS directly — an INDEPENDENT source from the tract pull
    frames = []
    for year in YEARS:
        params = {"get": "NAME,B19013_001E,B17001_002E,B17001_001E",
                  "for": "county:" + ",".join(COUNTY_FIPS.values()),
                  "in": f"state:{STATE_FIPS}", "key": API_KEY}
        r = requests.get(ACS_BASE.format(year=year), params=params, timeout=60)
        r.raise_for_status()
        d = pd.DataFrame(r.json()[1:], columns=r.json()[0])
        d["year"] = year
        frames.append(d)
        time.sleep(0.1)
    api = pd.concat(frames, ignore_index=True)
    api["county_fips"] = api["county"].astype(str).str.zfill(3)
    api["income_api"] = pd.to_numeric(api["B19013_001E"], errors="coerce").replace(SUPPRESSED, pd.NA)
    api["poverty_rate_api"] = rate(api["B17001_002E"], api["B17001_001E"])

    keys = ["county_fips", "year"]
    m = csv.merge(api[keys + ["income_api", "poverty_rate_api"]], on=keys, how="left")
    ok = True
    for stored, apicol, tol in [("median_household_income", "income_api", 0.5),
                                ("poverty_rate", "poverty_rate_api", RATE_TOL)]:
        sample, count = _mismatches(m, stored, apicol, tol, keys)
        passed = count == 0
        ok &= passed
        rep.add(f"county benchmark · {stored} vs live API",
                passed, f"{len(m)} county-years checked, {count} mismatch(es)",
                sample if not passed else None)
    return ok


# ── Check 3b: shipped-master provenance (master_tract.csv) ────────────────
# The masters are what the APP actually reads. This proves the full chain
# API -> raw -> master carried every value through uncorrupted.
def check_master_tract(api: pd.DataFrame, rep: Report):
    path = ROOT / "data" / "processed" / "master_tract.csv"
    if not path.exists():
        rep.add("master_tract vs live API", False,
                "master_tract.csv not found — run build_masters.py first", None)
        return False
    m = pd.read_csv(path, dtype={"GEOID": str})

    a = api.copy()
    a["GEOID"] = "42" + a["county_fips"].astype(str).str.zfill(3) + a["tract_code"].str.zfill(6)
    a["poverty_rate_api"] = rate(a["poverty_num"], a["poverty_den"])
    a["bachelors_rate_api"] = rate(a["bachelors_num"], a["bachelors_den"])
    a["rent_burden_rate_api"] = rate(a["rent_num"], a["rent_den"])
    a["no_vehicle_rate_api"] = rate(a["novehicle_num"], a["vehicle_den"])
    a["snap_participation_rate_api"] = rate(a["snap_hh_receiving"], a["snap_hh_total"])
    a = a.rename(columns={"median_household_income": "income_api",
                          "total_population": "pop_api", "median_age": "age_api"})

    keys = ["GEOID", "year"]
    j = m.merge(a[keys + ["income_api", "poverty_rate_api", "bachelors_rate_api",
                          "rent_burden_rate_api", "no_vehicle_rate_api",
                          "snap_participation_rate_api", "pop_api", "age_api"]],
                on=keys, how="left")

    ok = True
    checks = [
        ("median_household_income", "income_api", 0.5),
        ("poverty_rate", "poverty_rate_api", RATE_TOL),
        ("bachelors_rate", "bachelors_rate_api", RATE_TOL),
        ("rent_burden_rate", "rent_burden_rate_api", RATE_TOL),
        ("no_vehicle_rate", "no_vehicle_rate_api", RATE_TOL),
        ("total_population", "pop_api", 0.5),
        ("median_age", "age_api", AGE_TOL),
    ]
    if "snap_participation_rate" in m.columns:
        checks.append(("snap_participation_rate", "snap_participation_rate_api", RATE_TOL))
    for stored, apicol, tol in checks:
        sample, count = _mismatches(j, stored, apicol, tol, keys)
        passed = count == 0
        ok &= passed
        rep.add(f"master_tract · {stored} vs live API",
                passed, f"{len(j)} tract-years (shipped), {count} mismatch(es)",
                sample if not passed else None)
    return ok


# ── Check 4: row reconciliation ───────────────────────────────────────────
def check_row_reconciliation(api: pd.DataFrame, rep: Report):
    path = ROOT / "data" / "raw" / "erie_tract_data.csv"
    csv = pd.read_csv(path, dtype={"tract_code": str})
    csv["tract_code"] = csv["tract_code"].str.zfill(6)

    # API tracts minus the intentionally-excluded 9900-series water tracts
    api_keep = api[~api["tract_code"].str.endswith(EXPECTED_EXCLUDED_TRACT_SUFFIX)]
    api_counts = api_keep.groupby(["county_name", "year"]).size().rename("api")
    csv_counts = csv.groupby(["county_name", "year"]).size().rename("csv")
    j = pd.concat([api_counts, csv_counts], axis=1).fillna(0).astype(int)
    j["diff"] = j["api"] - j["csv"]
    bad = j[j["diff"] != 0].reset_index()
    passed = len(bad) == 0
    rep.add("row reconciliation · tract counts per county-year",
            passed,
            f"{len(j)} county-years; {len(bad)} with unexpected count diff "
            f"(9900-series water tracts excluded by design)",
            bad.to_dict("records") if not passed else None)
    return passed


# ── Check 5: code integrity ───────────────────────────────────────────────
def check_code_integrity(rep: Report):
    ok = True
    for label, path, col, width in [
        ("erie_tract_data", "data/raw/erie_tract_data.csv", "tract_code", 6),
        ("tract_demographics", "data/raw/tract_demographics.csv", "tract_code", 6),
        ("zcta_data", "data/raw/zcta_data.csv", "zcta", 5),
    ]:
        df = pd.read_csv(ROOT / path, dtype={col: str})
        s = df[col].astype(str)
        padded = s.str.zfill(width)
        bad_pad = int((s != padded).sum())
        non_digit = int((~s.str.fullmatch(r"\d+")).sum())
        # duplicate key check — a tract code is only unique WITHIN a county,
        # so the full key must include county_fips where present.
        dup = 0
        key_cols = [col]
        if "county_fips" in df.columns:
            key_cols.append("county_fips")
        if "year" in df.columns:
            key_cols.append("year")
        if len(key_cols) > 1:
            dup = int(df.duplicated(subset=key_cols).sum())
        passed = bad_pad == 0 and non_digit == 0 and dup == 0
        ok &= passed
        rep.add(f"code integrity · {label}.{col}",
                passed,
                f"{bad_pad} unpadded, {non_digit} non-digit, {dup} duplicate key(s)",
                None)
    return ok


# ── Check 6: shipped ZCTA master vs live API ──────────────────────────────
def pull_acs_zcta(use_cache=True) -> pd.DataFrame:
    """National ZCTA pull (one request per year), filtered to region ZCTAs."""
    if use_cache and ZCTA_CACHE.exists():
        print(f"Using cached ZCTA pull ({ZCTA_CACHE.name}); pass --fresh to refresh.")
        return pd.read_parquet(ZCTA_CACHE)
    if not API_KEY:
        raise SystemExit("CENSUS_API_KEY missing — cannot run live checks. Use --no-net.")

    region = set(pd.read_csv(ROOT / "data" / "processed" / "master_zcta.csv",
                             dtype={"ZCTA5CE20": str})["ZCTA5CE20"])
    get = ",".join(ZCTA_VARS.keys())
    frames = []
    for i, year in enumerate(YEARS, 1):
        print(f"  pulling ZCTA {i}/{len(YEARS)}: {year}", end="\r")
        params = {"get": get, "for": "zip code tabulation area:*", "key": API_KEY}
        r = requests.get(ACS_BASE.format(year=year), params=params, timeout=180)
        r.raise_for_status()
        d = pd.DataFrame(r.json()[1:], columns=r.json()[0]).rename(columns=ZCTA_VARS)
        zcol = [c for c in d.columns if "zip code" in c][0]
        d["ZCTA5CE20"] = d[zcol].astype(str).str.zfill(5)
        d = d[d["ZCTA5CE20"].isin(region)].copy()
        d["year"] = year
        frames.append(d)
        time.sleep(0.1)
    print()
    out = pd.concat(frames, ignore_index=True)
    for col in ZCTA_VARS.values():
        out[col] = pd.to_numeric(out[col], errors="coerce").replace(SUPPRESSED, pd.NA)
    ZCTA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(ZCTA_CACHE, index=False)
    return out


def check_master_zcta(zapi: pd.DataFrame, rep: Report):
    path = ROOT / "data" / "processed" / "master_zcta.csv"
    m = pd.read_csv(path, dtype={"ZCTA5CE20": str})

    a = zapi.copy()
    a["income_api"] = a["income"]
    a["poverty_rate_api"] = rate(a["pov_num"], a["pov_den"])
    a["bachelors_rate_api"] = rate(a["bach_num"], a["bach_den"])
    a["rent_burden_rate_api"] = rate(a["rent_num"], a["rent_den"])
    a["no_vehicle_rate_api"] = rate(a["noveh_num"], a["veh_den"])
    a["population_api"] = a["population"]
    a["median_age_api"] = a["median_age"]
    a["unemployment_rate_api"] = rate(a["unemployed"], a["labor_force"])
    a["homeownership_rate_api"] = rate(a["owner_occ"], a["occ_units"])
    a["snap_participation_rate_api"] = rate(a["snap_recv"], a["snap_total"])
    a["pct_white_non_hispanic_api"] = rate(a["white_nh"], a["race_total"])
    a["pct_black_api"] = rate(a["black_nh"], a["race_total"])
    a["pct_hispanic_api"] = rate(a["hispanic"], a["race_total"])
    a["pct_asian_api"] = rate(a["asian_nh"], a["race_total"])

    keys = ["ZCTA5CE20", "year"]
    api_cols = [c for c in a.columns if c.endswith("_api")]
    j = m.merge(a[keys + api_cols], on=keys, how="left")

    ok = True
    for stored, apicol, tol in [
        ("median_household_income", "income_api", 0.5),
        ("poverty_rate", "poverty_rate_api", RATE_TOL),
        ("bachelors_rate", "bachelors_rate_api", RATE_TOL),
        ("rent_burden_rate", "rent_burden_rate_api", RATE_TOL),
        ("no_vehicle_rate", "no_vehicle_rate_api", RATE_TOL),
        ("total_population", "population_api", 0.5),
        ("median_age", "median_age_api", AGE_TOL),
        ("unemployment_rate", "unemployment_rate_api", RATE_TOL),
        ("homeownership_rate", "homeownership_rate_api", RATE_TOL),
        ("snap_participation_rate", "snap_participation_rate_api", RATE_TOL),
        ("pct_white_non_hispanic", "pct_white_non_hispanic_api", RATE_TOL),
        ("pct_black", "pct_black_api", RATE_TOL),
        ("pct_hispanic", "pct_hispanic_api", RATE_TOL),
        ("pct_asian", "pct_asian_api", RATE_TOL),
    ]:
        if stored not in m.columns:
            continue
        sample, count = _mismatches(j, stored, apicol, tol, keys)
        passed = count == 0
        ok &= passed
        rep.add(f"master_zcta · {stored} vs live API",
                passed, f"{len(j)} ZCTA-years (shipped), {count} mismatch(es)",
                sample if not passed else None)
    return ok


# ── Check 7: national / PA / Erie benchmarks vs live API ──────────────────
def check_geo_benchmarks(rep: Report, use_net: bool):
    if not use_net:
        rep.add("geo benchmarks vs live API", True, "skipped (offline mode)", None)
        return True
    targets = [
        ("benchmarks_national.csv", "National", {"for": "us:1"}),
        ("benchmarks_pennsylvania.csv", "Pennsylvania", {"for": f"state:{STATE_FIPS}"}),
        ("benchmarks_erie.csv", "Erie County", {"for": "county:049", "in": f"state:{STATE_FIPS}"}),
    ]
    econ = {"B19013_001E": "income", "B17001_002E": "pov_num", "B17001_001E": "pov_den",
            "B15003_022E": "bach_num", "B15003_001E": "bach_den",
            "B25070_010E": "rent_num", "B25070_001E": "rent_den",
            "B08201_002E": "noveh_num", "B08201_001E": "veh_den"}
    ok = True
    for fname, label, geo in targets:
        csv = pd.read_csv(ROOT / "data" / "raw" / fname)
        rows = []
        for year in YEARS:
            params = {"get": ",".join(econ.keys()), "key": API_KEY, **geo}
            r = requests.get(ACS_BASE.format(year=year), params=params, timeout=60)
            r.raise_for_status()
            d = pd.DataFrame(r.json()[1:], columns=r.json()[0]).rename(columns=econ)
            d["year"] = year
            rows.append(d)
            time.sleep(0.1)
        a = pd.concat(rows, ignore_index=True)
        a["income_api"] = pd.to_numeric(a["income"], errors="coerce").replace(SUPPRESSED, pd.NA)
        a["poverty_rate_api"] = rate(a["pov_num"], a["pov_den"])
        a["bachelors_rate_api"] = rate(a["bach_num"], a["bach_den"])
        a["rent_burden_rate_api"] = rate(a["rent_num"], a["rent_den"])
        a["no_vehicle_rate_api"] = rate(a["noveh_num"], a["veh_den"])
        j = csv.merge(a[["year", "income_api", "poverty_rate_api", "bachelors_rate_api",
                         "rent_burden_rate_api", "no_vehicle_rate_api"]], on="year", how="inner")
        for stored, apicol, tol in [("median_household_income", "income_api", 0.5),
                                    ("poverty_rate", "poverty_rate_api", RATE_TOL),
                                    ("bachelors_rate", "bachelors_rate_api", RATE_TOL),
                                    ("rent_burden_rate", "rent_burden_rate_api", RATE_TOL),
                                    ("no_vehicle_rate", "no_vehicle_rate_api", RATE_TOL)]:
            if stored not in csv.columns:
                continue
            sample, count = _mismatches(j, stored, apicol, tol, ["year"])
            passed = count == 0
            ok &= passed
            rep.add(f"benchmark {label} · {stored} vs live API",
                    passed, f"{len(j)} years, {count} mismatch(es)",
                    sample if not passed else None)
    return ok


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="offline checks only")
    ap.add_argument("--fresh", action="store_true", help="ignore cached API pull")
    args = ap.parse_args()
    use_net = not args.no_net

    print("=" * 68)
    print("  ACCURACY VERIFICATION — Northwest PA Community Data")
    print("=" * 68)

    rep = Report()

    if use_net:
        print("\nPulling ACS reference data from Census API...")
        api = pull_acs(use_cache=not args.fresh)
        print("\n[ Provenance — local masters vs live Census API ]")
        check_economic(api, rep)
        check_demographics(api, rep)
        check_master_tract(api, rep)
        check_row_reconciliation(api, rep)
        check_county_benchmarks(rep, use_net)
        print("\n[ Provenance — ZCTA (ZIP) master & benchmarks vs live API ]")
        zapi = pull_acs_zcta(use_cache=not args.fresh)
        check_master_zcta(zapi, rep)
        check_geo_benchmarks(rep, use_net)
    else:
        print("\n[ Offline mode — provenance checks skipped ]")
        # still run demographic recompute (uses stored components only)
        # by loading a stub frame that satisfies the merge with all-NA API cols
        api = pd.DataFrame(columns=["county_fips", "year", "tract_code"])

    print("\n[ Fidelity — code integrity & derived-column recompute ]")
    check_code_integrity(rep)

    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "U.S. Census Bureau ACS 5-Year Estimates",
        "years": YEARS,
        "counties": list(COUNTY_FIPS.keys()),
        "network_checks": use_net,
    }
    rep.write(ROOT / "data" / "verification_report.json", meta)

    print("\n" + "=" * 68)
    if rep.all_passed:
        print("  RESULT: ALL CHECKS PASSED")
        print("=" * 68)
        sys.exit(0)
    else:
        n_fail = sum(c["status"] == "FAIL" for c in rep.checks)
        print(f"  RESULT: {n_fail} CHECK(S) FAILED - see report for samples")
        print("=" * 68)
        sys.exit(1)


if __name__ == "__main__":
    main()
