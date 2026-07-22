# Northwest PA Community Data

A public Streamlit app for exploring economic, demographic, and food-access data
across the 11-county Second Harvest Food Bank of Northwest PA service region.

Every census figure shown is a U.S. Census Bureau ACS 5-Year Estimate (2020–2023)
and is **verified against the live Census API** before release — see the About tab
and `pipeline/verify.py`.

## Tabs

| Tab | What it shows |
|-----|---------------|
| **About** | Overview, data sources, limitations, regional population snapshot, data-verification badge |
| **Demographics** | Population, median age, and race/ethnicity by tract or ZIP, with a choropleth map |
| **Economic** | Income, poverty, rent burden, no-vehicle, and education — snapshot maps, change-over-time, and household income stratification |
| **SNAP Retailers** | USDA-authorized SNAP/EBT stores with coverage rings (1 mi urban / 10 mi rural), an address + radius search, and an optional poverty-rate context layer |
| **Download** | CSV downloads of every dataset the app uses |
| **Data Dictionary** | Definitions, sources, and caveats for every variable |

## Running locally

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app reads only the pre-built, verified data in `data/processed/` and the
boundary/benchmark files in `data/raw/` — no network or API key required at runtime.

## Data pipeline

All data preparation happens offline in `pipeline/`, so the app itself does exactly
one join per geography (attributes → boundary) on the collision-safe 11-digit GEOID.

```bash
# 1. Fetch raw source data (needs CENSUS_API_KEY in .env)
python census_pull.py            # ACS economic variables  -> data/raw/erie_tract_data.csv
python fetch_demographics.py     # ACS demographics        -> data/raw/tract_demographics.csv
python fetch_zcta_data.py        # ACS ZIP-level           -> data/raw/zcta_data.csv
python fetch_benchmarks.py       # national/state/Erie benchmarks
python fetch_county_benchmarks.py
python fetch_boundaries.py       # TIGER/Line boundaries (2020 vintage)
python fetch_snap_retailers.py   # USDA FNS SNAP retailers

# 2. Build the flat master files the app reads
python pipeline/build_masters.py   # -> data/processed/master_{tract,zcta,county}.csv
python pipeline/build_snap.py      # -> data/processed/snap_retailers.csv (with urban/rural flag)

# 3. Verify every value against the live Census API
python pipeline/verify.py          # -> data/verification_report.json  (exit 1 on any mismatch)
```

### Accuracy verification

`pipeline/verify.py` re-queries the Census ACS API and confirms, cell by cell, that
the shipped master files match the source. It also recomputes derived rates,
reconciles row counts, and checks code integrity. Run it after any data refresh; the
About tab surfaces the pass/fail badge from `data/verification_report.json`.

## Notes

- **Years:** 2020–2023. 2019 is excluded because it predates the 2020 tract
  boundaries used for mapping (11 tracts were renumbered in the 2020 redistricting).
- Large raw pipeline inputs (national SNAP file, USDA atlas workbook) are gitignored;
  they are only needed to regenerate data, not to run the app.
