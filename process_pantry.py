import pandas as pd
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
RAW = Path("data/raw/PantryData.csv")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

# ── Load ─────────────────────────────────────────────────────────────────────
df = pd.read_csv(RAW)

# Normalize column names
df.columns = [c.replace("Content.", "").strip() for c in df.columns]
# Expected cols: Agency Name, Agency Ref, Effective Date, Value, County,
#                Statistic Name, Statistic Group, Name

# ── Filter to Erie + Crawford ─────────────────────────────────────────────────
df = df[df["County"].str.upper().isin(["ERIE", "CRAWFORD"])].copy()

# ── Parse date ───────────────────────────────────────────────────────────────
df["date"] = pd.to_datetime(df["Effective Date"], format="%m/%d/%Y")

# ── Clean up key fields ───────────────────────────────────────────────────────
df["agency_name"] = df["Agency Name"].str.strip()
df["agency_ref"] = df["Agency Ref"].astype(str).str.strip()
df["county"] = df["County"].str.title()
df["program_type"] = df["Statistic Group"].str.strip()
df["statistic"] = df["Statistic Name"].str.strip()
df["value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0)

# ── Map statistics to metric columns ─────────────────────────────────────────
# We want: total_individuals, children, adults, seniors
# Using "Unique" counts as the primary metric (unduplicated persons)
STAT_MAP = {
    "F. Number of Unique Individuals":              "total_individuals",
    "D. Number of Unique Children (0 - 17 years)":  "children",
    "C. Number of Unique Adults (18 - 59 years)":   "adults",
    "E. Number of Unique Seniors (60+ years)":      "seniors",
    "L. Total New Households":                      "new_households",
    "Onsites: Total Number of Unduplicated Persons Served This Month": "total_individuals",
}
df_filtered = df[df["statistic"].isin(STAT_MAP.keys())].copy()
df_filtered["metric"] = df_filtered["statistic"].map(STAT_MAP)

# ── Pivot to wide format ──────────────────────────────────────────────────────
# Group key: agency + county + program_type + date + metric
# Some agencies report under multiple program types — keep them separate
agg = (
    df_filtered
    .groupby(["agency_name", "agency_ref", "county", "program_type", "date", "metric"])["value"]
    .sum()
    .reset_index()
)

monthly = agg.pivot_table(
    index=["agency_name", "agency_ref", "county", "program_type", "date"],
    columns="metric",
    values="value",
    aggfunc="sum"
).reset_index()

monthly.columns.name = None

# Ensure all metric columns exist even if some agencies don't report all stats
for col in ["total_individuals", "children", "adults", "seniors", "new_households"]:
    if col not in monthly.columns:
        monthly[col] = 0

monthly = monthly.fillna(0)
monthly = monthly.sort_values(["agency_name", "program_type", "date"])

# ── Agency index (one row per agency + program type) ─────────────────────────
index = (
    monthly
    .groupby(["agency_name", "agency_ref", "county", "program_type"])
    .agg(
        first_month=("date", "min"),
        last_month=("date", "max"),
        total_individuals_served=("total_individuals", "sum"),
        months_reported=("date", "count"),
    )
    .reset_index()
    .sort_values(["county", "agency_name"])
)

# ── Save ──────────────────────────────────────────────────────────────────────
monthly_path = OUT / "pantry_agency_monthly.csv"
index_path   = OUT / "pantry_agency_index.csv"

monthly.to_csv(monthly_path, index=False)
index.to_csv(index_path, index=False)

print(f"✓ pantry_agency_monthly.csv  — {len(monthly):,} rows")
print(f"✓ pantry_agency_index.csv    — {len(index):,} agencies")
print()
print("County breakdown:")
print(index.groupby("county")["agency_name"].count().to_string())
print()
print("Program types found:")
print(index["program_type"].value_counts().to_string())