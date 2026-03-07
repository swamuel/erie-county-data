import pandas as pd
import requests
import time

df = pd.read_csv("data/raw/ErieCountyFoodPantries.csv")

def geocode_address(address, city, state, zip_code):
    url = "https://geocoding.geo.census.gov/geocoder/locations/address"
    params = {
        "street": address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "benchmark": "Public_AR_Current",
        "format": "json"
    }
    try:
        response = requests.get(url, params=params)
        matches = response.json()["result"]["addressMatches"]
        if matches:
            coords = matches[0]["coordinates"]
            return coords["x"], coords["y"]  # x=lon, y=lat
        return None, None
    except:
        return None, None

lats, lons = [], []

for _, row in df.iterrows():
    lon, lat = geocode_address(row["Address"], row["City"], row["State"], row["ZIP"])
    lats.append(lat)
    lons.append(lon)
    print(f"{row['PantryName']}: {lat}, {lon}")
    time.sleep(0.5)  # be polite to the API

df["lat"] = lats
df["lon"] = lons

df.to_csv("data/raw/ErieCountyFoodPantries.csv", index=False)
print("\nDone")
print(df[["PantryName", "lat", "lon"]])