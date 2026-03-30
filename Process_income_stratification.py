import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW = Path("data/raw/income_stratification.csv")
OUT = Path("data/processed/income_stratification.csv")
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Band definitions ──────────────────────────────────────────────────────────
# All 16 income bands from B19001
BANDS = [
    "under_10k",
    "10k_15k",
    "15k_20k",
    "20k_25k",
    "25k_30k",
    "30k_35k",
    "35k_40k",
    "40k_45k",
    "45k_50k",
    "50k_60k",
    "60k_75k",
    "75k_100k",
    "100k_125k",
    "125k_150k",
    "150k_200k",
    "200k_plus",
]

# Tier assignments — fixed thresholds
BOTTOM_BANDS = ["under_10k", "10k_15k", "15k_20k", "20k_25k", "25k_30k", "30k_35k"]       # < $35k
MIDDLE_BANDS = ["35k_40k", "40k_45k", "45k_50k", "50k_60k", "60k_75k"]                     # $35k–$75k
TOP_BANDS    = ["75k_100k", "100k_125k", "125k_150k", "150k_200k", "200k_plus"]             # $75k+

# Human-readable band labels for charting
BAND_LABELS = {
    "under_10k":   "Under $10k",
    "10k_15k":     "$10k–$15k",
    "15k_20k":     "$15k–$20k",
    "20k_25k":     "$20k–$25k",
    "25k_30k":     "$25k–$30k",
    "30k_35k":     "$30k–$35k",
    "35k_40k":     "$35k–$40k",
    "40k_45k":     "$40k–$45k",
    "45k_50k":     "$45k–$50k",
    "50k_60k":     "$50k–$60k",
    "60k_75k":     "$60k–$75k",
    "75k_100k":    "$75k–$100k",
    "100k_125k":   "$100k–$125k",
    "125k_150k":   "$125k–$150k",
    "150k_200k":   "$150k–$200k",
    "200k_plus":   "$200k+",
}

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_csv(RAW)

# ── Coerce band columns to numeric ────────────────────────────────────────────
for col in BANDS + ["total_households"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Drop any tracts with missing or zero total
df = df.dropna(subset=["total_households"])
df = df[df["total_households"] > 0].copy()

# ── Derive tier household counts ──────────────────────────────────────────────
df["hh_bottom"] = df[BOTTOM_BANDS].sum(axis=1)
df["hh_middle"] = df[MIDDLE_BANDS].sum(axis=1)
df["hh_top"]    = df[TOP_BANDS].sum(axis=1)

# ── Derive tier shares (0–100) ────────────────────────────────────────────────
df["share_bottom"] = (df["hh_bottom"] / df["total_households"] * 100).round(2)
df["share_middle"] = (df["hh_middle"] / df["total_households"] * 100).round(2)
df["share_top"]    = (df["hh_top"]    / df["total_households"] * 100).round(2)

# ── Derive individual band shares ─────────────────────────────────────────────
for band in BANDS:
    df[f"share_{band}"] = (df[band] / df["total_households"] * 100).round(2)

# ── Column ordering ───────────────────────────────────────────────────────────
# Identity columns
id_cols = ["geoid", "county", "year", "NAME", "total_households"]

# Tier summary columns
tier_cols = [
    "hh_bottom", "hh_middle", "hh_top",
    "share_bottom", "share_middle", "share_top",
]

# Original band raw counts
band_raw_cols = BANDS

# Original band shares
band_share_cols = [f"share_{b}" for b in BANDS]

final_cols = id_cols + tier_cols + band_raw_cols + band_share_cols
df = df[final_cols].sort_values(["county", "geoid", "year"]).reset_index(drop=True)

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_csv(OUT, index=False)

print(f"✓ income_stratification.csv — {len(df):,} rows → {OUT}")
print()
print("Sample — Erie tract 2023 tier shares:")
sample = df[(df["county"] == "Erie") & (df["year"] == 2023)][
    ["NAME", "share_bottom", "share_middle", "share_top"]
].head(5)
print(sample.to_string(index=False))
print()
print("County averages by year:")
avg = df.groupby(["county", "year"])[["share_bottom", "share_middle", "share_top"]].mean().round(1)
print(avg.to_string())
print()
print(f"Tier thresholds:")
print(f"  Bottom: under $35k  ({len(BOTTOM_BANDS)} bands)")
print(f"  Middle: $35k–$75k   ({len(MIDDLE_BANDS)} bands)")
print(f"  Top:    $75k+        ({len(TOP_BANDS)} bands)")