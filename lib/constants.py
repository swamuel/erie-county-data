# lib/constants.py
# Central source of truth for all county-level constants.
# Import from here — never hardcode county FIPS elsewhere.

# All counties in the Second Harvest Food Bank of Northwest PA service region
COUNTY_FIPS = {
    "Cameron County":    "023",
    "Clarion County":    "031",
    "Clearfield County": "033",
    "Crawford County":   "039",
    "Elk County":        "047",
    "Erie County":       "049",
    "Forest County":     "053",
    "Jefferson County":  "065",
    "McKean County":     "083",
    "Venango County":    "121",
    "Warren County":     "123",
}

# Convenience lists
FIPS_LIST    = list(COUNTY_FIPS.values())   # ["023", "031", ...]
COUNTY_NAMES = list(COUNTY_FIPS.keys())     # ["Cameron County", ...]

# Reverse lookup: FIPS -> county name
FIPS_TO_NAME = {v: k for k, v in COUNTY_FIPS.items()}

# Counties with very small populations — ACS estimates may be suppressed
# Cameron ~4,500 residents, Forest ~7,000
SMALL_COUNTIES = {"Cameron County", "Forest County"}

# App identity
APP_TITLE  = "Northwest PA Community Data"
APP_REGION = "Second Harvest Food Bank of Northwest PA service region"
STATE_FIPS = "42"
