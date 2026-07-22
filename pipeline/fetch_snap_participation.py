"""
pipeline/fetch_snap_participation.py
====================================
Pulls ACS table B19058 (Receipt of Food Stamps/SNAP in the past 12 months)
for tracts and ZCTAs across the region, and computes a SNAP participation rate
(households receiving SNAP / total households).

This is "SNAP usage" context for the SNAP Retailers tab.

Output:
    data/raw/snap_participation_tract.csv   (GEOID, year, snap_participation_rate, ...)
    data/raw/snap_participation_zcta.csv    (ZCTA5CE20, year, snap_participation_rate, ...)

Run:  python pipeline/fetch_snap_participation.py   (needs CENSUS_API_KEY in .env)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from lib.constants import COUNTY_FIPS, STATE_FIPS  # noqa: E402

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("CENSUS_API_KEY")
YEARS = [2020, 2021, 2022, 2023]
BASE = "https://api.census.gov/data/{year}/acs/acs5"
TOTAL, SNAP = "B19058_001E", "B19058_002E"      # total households, receiving SNAP
SUPPRESSED = -666666666


def _rate(df):
    total = pd.to_numeric(df[TOTAL], errors="coerce").replace(SUPPRESSED, pd.NA)
    snap = pd.to_numeric(df[SNAP], errors="coerce").replace(SUPPRESSED, pd.NA)
    rate = (snap / total * 100).round(1)
    rate[(total.isna()) | (total <= 0)] = pd.NA
    return total, snap, rate


def fetch_tracts():
    frames = []
    for year in YEARS:
        for name, fips in COUNTY_FIPS.items():
            params = {"get": f"NAME,{TOTAL},{SNAP}", "for": "tract:*",
                      "in": f"state:{STATE_FIPS} county:{fips}", "key": API_KEY}
            r = requests.get(BASE.format(year=year), params=params, timeout=60)
            r.raise_for_status()
            d = pd.DataFrame(r.json()[1:], columns=r.json()[0])
            d["GEOID"] = STATE_FIPS + fips + d["tract"].astype(str).str.zfill(6)
            d["year"] = year
            frames.append(d)
            time.sleep(0.1)
    df = pd.concat(frames, ignore_index=True)
    _, _, df["snap_participation_rate"] = _rate(df)
    out = df[["GEOID", "year", "snap_participation_rate"]].copy()
    out.to_csv(ROOT / "data" / "raw" / "snap_participation_tract.csv", index=False)
    print(f"[OK] snap_participation_tract.csv — {len(out)} rows")


def fetch_zctas():
    frames = []
    for year in YEARS:
        params = {"get": f"{TOTAL},{SNAP}", "for": "zip code tabulation area:*", "key": API_KEY}
        r = requests.get(BASE.format(year=year), params=params, timeout=120)
        r.raise_for_status()
        d = pd.DataFrame(r.json()[1:], columns=r.json()[0])
        zcol = [c for c in d.columns if "zip code" in c][0]
        d["ZCTA5CE20"] = d[zcol].astype(str).str.zfill(5)
        d["year"] = year
        frames.append(d)
        time.sleep(0.1)
    df = pd.concat(frames, ignore_index=True)
    _, _, df["snap_participation_rate"] = _rate(df)
    out = df[["ZCTA5CE20", "year", "snap_participation_rate"]].copy()
    out.to_csv(ROOT / "data" / "raw" / "snap_participation_zcta.csv", index=False)
    print(f"[OK] snap_participation_zcta.csv — {len(out)} rows (national; filtered at build time)")


def main():
    if not API_KEY:
        raise SystemExit("CENSUS_API_KEY missing in .env")
    print("Fetching ACS B19058 (SNAP receipt)...")
    fetch_tracts()
    fetch_zctas()


if __name__ == "__main__":
    main()
