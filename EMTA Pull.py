# EMTA GTFS Route Data
# Source: Erie Metropolitan Transit Authority
# Reproduced with permission granted by Erie Metropolitan Transit Authority (EMTA)
# Feed: https://emta.availtec.com/InfoPoint/gtfs-zip.ashx

import requests
import zipfile
import io
import pandas as pd

url = "https://emta.availtec.com/InfoPoint/gtfs-zip.ashx"

response = requests.get(url)
z = zipfile.ZipFile(io.BytesIO(response.content))

routes = pd.read_csv(z.open("routes.txt"))
shapes = pd.read_csv(z.open("shapes.txt"))
trips = pd.read_csv(z.open("trips.txt"))

# Connect shapes to routes via trips
# Each trip has a route_id and shape_id
shape_to_route = trips[["route_id", "shape_id"]].drop_duplicates()

# Join route info to shapes
shapes = shapes.merge(shape_to_route, on="shape_id", how="left")
shapes = shapes.merge(routes[["route_id", "route_short_name",
                               "route_long_name", "route_color"]],
                      on="route_id", how="left")

# Sort so lines draw correctly
shapes = shapes.sort_values(["shape_id", "shape_pt_sequence"])

stops = pd.read_csv(z.open("stops.txt"))

stop_times = pd.read_csv(z.open("stop_times.txt"))

# Count daily visits per stop (frequency)
frequency = stop_times.groupby("stop_id").size().reset_index(name="daily_visits")
def time_to_minutes(t):
    try:
        h, m, s = str(t).split(":")
        return int(h) * 60 + int(m) + int(s) / 60
    except:
        return None

stop_times["arrival_minutes"] = stop_times["arrival_time"].apply(time_to_minutes)

service_hours = stop_times.groupby("stop_id")["arrival_minutes"].agg(
    first_service_minutes="min",
    last_service_minutes="max"
).reset_index()

# Convert minutes back to readable time
def minutes_to_time(m):
    if pd.isna(m):
        return None
    h = int(m // 60)
    mins = int(m % 60)
    period = "AM" if h < 12 else "PM"
    h = h if h <= 12 else h - 12
    h = 12 if h == 0 else h
    return f"{h}:{mins:02d} {period}"

service_hours["first_service"] = service_hours["first_service_minutes"].apply(minutes_to_time)
service_hours["last_service"] = service_hours["last_service_minutes"].apply(minutes_to_time)
service_hours = service_hours.drop(columns=["first_service_minutes", "last_service_minutes"])

# Join everything together
stops = stops.merge(frequency, on="stop_id", how="left")
stops = stops.merge(service_hours, on="stop_id", how="left")

print(stops[["stop_name", "daily_visits", "first_service", "last_service"]].head(10))
print(f"\nFrequency range: {stops['daily_visits'].min()} - {stops['daily_visits'].max()}")

stops.to_csv("data/raw/emta_stops.csv", index=False)
print("Stops saved")

#print(stops.head())
#print(stops.columns.tolist())
#print(f"\n{len(stops)} stops")
#print(shapes.head(10))
#print(f"\nUnique routes in shapes: {shapes['route_short_name'].nunique()}")

# Save to raw
shapes.to_csv("data/raw/emta_shapes.csv", index=False)
routes.to_csv("data/raw/emta_routes.csv", index=False)
print("Saved")

stops.to_csv("data/raw/emta_stops.csv", index=False)
print("Stops saved")

stop_times = pd.read_csv(z.open("stop_times.txt"))
#print(f"Stop times rows: {len(stop_times)}")
#print(stop_times.head())
#print(stop_times.columns.tolist())