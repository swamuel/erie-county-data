# Transit data processing
# Spatially joins EMTA stops to census tracts
# Calculates stop frequency and distance to nearest stop per tract

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import numpy as np

# Load stops
stops = pd.read_csv("data/raw/emta_stops.csv")

# Convert stops to GeoDataFrame
stops_gdf = gpd.GeoDataFrame(
    stops,
    geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]),
    crs="EPSG:4326"
)

# Load tract boundaries
url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_42_tract.zip"
tracts = gpd.read_file(url)
tracts = tracts[tracts["COUNTYFP"] == "049"]
tracts = tracts[tracts["TRACTCE"] != "990000"]

print(f"Tracts loaded: {len(tracts)}")
print(f"Stops loaded: {len(stops_gdf)}")

# Project to a coordinate system that uses meters for distance calculations
# EPSG:32617 is UTM Zone 17N - appropriate for Erie PA
tracts_proj = tracts.to_crs("EPSG:32617")
stops_proj = stops_gdf.to_crs("EPSG:32617")

# Spatial join - which tract does each stop fall in
stops_in_tracts = gpd.sjoin(
    stops_proj,
    tracts_proj[["TRACTCE", "geometry"]],
    how="left",
    predicate="within"
)

print(f"\nStops matched to tracts: {stops_in_tracts['TRACTCE'].notna().sum()}")
print(f"Stops outside tracts: {stops_in_tracts['TRACTCE'].isna().sum()}")

# Calculate per-tract stop statistics
tract_stats = stops_in_tracts.groupby("TRACTCE").agg(
    stop_count=("stop_id", "count"),
    avg_daily_visits=("daily_visits", "mean"),
    total_daily_visits=("daily_visits", "sum"),
    avg_first_service=("first_service", "first"),
    avg_last_service=("last_service", "first")
).reset_index()

tract_stats["avg_daily_visits"] = tract_stats["avg_daily_visits"].round(1)
tract_stats["total_daily_visits"] = tract_stats["total_daily_visits"].round(1)

print(f"\nTracts with at least one stop: {len(tract_stats)}")

# Calculate distance to nearest stop for each tract centroid
tract_centroids = tracts_proj.copy()
tract_centroids["centroid"] = tracts_proj.geometry.centroid

distances = []
for _, tract in tract_centroids.iterrows():
    centroid = tract["centroid"]
    dists = stops_proj.geometry.distance(centroid)
    min_dist = dists.min()
    distances.append({
        "TRACTCE": tract["TRACTCE"],
        "nearest_stop_meters": round(min_dist, 0),
        "nearest_stop_miles": round(min_dist * 0.000621371, 2)
    })

distance_df = pd.DataFrame(distances)

# Merge everything together
result = tracts[["TRACTCE"]].merge(tract_stats, on="TRACTCE", how="left")
result = result.merge(distance_df, on="TRACTCE", how="left")

# Fill tracts with no stops
result["stop_count"] = result["stop_count"].fillna(0).astype(int)
result["total_daily_visits"] = result["total_daily_visits"].fillna(0)
result["avg_daily_visits"] = result["avg_daily_visits"].fillna(0)

print(f"\nFinal tract count: {len(result)}")
print(result.head(10))
print(f"\nTracts with no stops: {(result['stop_count'] == 0).sum()}")
print(f"Max distance to nearest stop: {result['nearest_stop_miles'].max()} miles")
print(f"Min distance to nearest stop: {result['nearest_stop_miles'].min()} miles")

result.to_csv("data/processed/tract_transit_stats.csv", index=False)
print("\nSaved to data/processed/tract_transit_stats.csv")