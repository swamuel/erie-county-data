import pandas as pd

df = pd.read_excel("data/raw/SH_FellowshipData.xlsx")

# Filter to Erie County
df_erie = df[df["County, State"].isin([
    "Erie County, Pennsylvania",
    "Crawford County, Pennsylvania"
])].copy()

# Extract 6-digit tract code from 11-digit FIPS
df_erie["tract_code"] = df_erie["Tract ID"].astype(str).str[-6:].str.zfill(6)

# Keep relevant columns
df_erie = df_erie[[
    "tract_code",
    "Year",
    "Overall Food Insecurity Rate",
    "# of Food Insecure Persons Overall",
    "Unemployment Rate (5 Yr ACS)",
    "Percent Black (all ethnicities) (5 Yr ACS)",
    "Percent Hispanic (any race) (5 Yr ACS)",
    "Homeownership Rate (5 Yr ACS)",
    "Disability Rate (5 Yr ACS)"
]].copy()

# Rename columns
df_erie = df_erie.rename(columns={
    "Year": "year",
    "Overall Food Insecurity Rate": "food_insecurity_rate",
    "# of Food Insecure Persons Overall": "food_insecure_persons",
    "Unemployment Rate (5 Yr ACS)": "unemployment_rate",
    "Percent Black (all ethnicities) (5 Yr ACS)": "percent_black",
    "Percent Hispanic (any race) (5 Yr ACS)": "percent_hispanic",
    "Homeownership Rate (5 Yr ACS)": "homeownership_rate",
    "Disability Rate (5 Yr ACS)": "disability_rate"
})

# Convert rates to percentages
rate_cols = ["food_insecurity_rate", "unemployment_rate", "percent_black",
             "percent_hispanic", "homeownership_rate", "disability_rate"]

for col in rate_cols:
    df_erie[col] = (df_erie[col] * 100).round(1)

print(df_erie.head(10))
print(df_erie.dtypes)
print(f"\n{len(df_erie)} rows")

df_erie.to_csv("data/raw/erie_food_insecurity.csv", index=False)
print("Saved")