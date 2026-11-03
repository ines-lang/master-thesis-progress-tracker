"""Crop to data window and the region box, drop invalid rows, add flags, derived columns and fire clusters.

v1 Step 3 logic, unchanged except:
- pixel_size_km is now the SIDE length sqrt(scan x track) (km); the area goes to pixel_area_km2;
- static_proxy is True/False for type_missing rows (NOAA-21) and empty otherwise;
- event-specific columns (in_larouco_box, larouco_fire) moved to scripts/event/.
Flag, do not drop: only rows with invalid coordinates or time are removed.
Usage: python scripts/common/02_clean.py --region <region_id>
Outputs: processed/<region_id>/firms_clean.csv, processed/<region_id>/clusters.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.helpers import KM_PER_DEG_LAT, PROCESSED, PYTHON_DTYPES, dist_km, grid_clusters, in_box, region_dir  # noqa: E402
from lib.registry import load_registry, region_arg, utc  # noqa: E402

# ---- parameters ----
REG = load_registry()
REGION_ID, REGION = region_arg()
IN_FILE = PROCESSED / "firms_merged.csv.gz"
OUT_FILE = region_dir(REGION_ID) / "firms_clean.csv"
CLUSTERS_FILE = region_dir(REGION_ID) / "clusters.csv"
PERIOD_START, PERIOD_END = utc(REG["data_window"]["start_utc"]), utc(REG["data_window"]["end_utc"])
CLUSTER_CELL_KM = REG["conventions"]["firms_cluster_cell_km"]
MODIS_CONF_LOW_MAX = 30       # MODIS confidence < 30 -> low
MODIS_CONF_HIGH_MIN = 80      # MODIS confidence >= 80 -> high, 30 to 79 -> nominal
VIIRS_CONF_MAP = {"l": "low", "n": "nominal", "h": "high"}
LANDSAT_CONF_MAP = {"L": "low", "M": "nominal", "H": "high"}
NOMINAL_PIXEL_KM = {"VIIRS": 0.375, "MODIS": 1.0, "OLI": 0.03}   # side length
SENSORS_WITH_SCAN_TRACK_KM = ["VIIRS", "MODIS"]                   # Landsat scan/track are not km
STATIC_PROXY_DIST_KM = 0.5    # NOAA-21 pixel this close to a type 1/2/3 pixel -> static_proxy

df = pd.read_csv(IN_FILE, dtype=PYTHON_DTYPES)
df["obs_time_utc"] = pd.to_datetime(df["obs_time_utc"], utc=True, errors="coerce")
counts = [("merged input", len(df))]

# 1. crop to data window and the region box
df = df[df["obs_time_utc"].between(PERIOD_START, PERIOD_END)]
counts.append(("1a. inside data window", len(df)))
df = df[in_box(df, REGION["box"])].copy()
counts.append((f"1b. inside region box ({REGION_ID})", len(df)))

# 2. invalid coordinates or time
invalid = (df["latitude"].isna() | df["longitude"].isna() | df["obs_time_utc"].isna()
           | ~df["latitude"].between(-90, 90) | ~df["longitude"].between(-180, 180))
df = df[~invalid].copy()
counts.append(("2. valid coordinates and time", len(df)))

# 3. qc_flag from type (0 vegetation fire, 1 volcano, 2 other static land, 3 offshore)
df["qc_flag"] = np.select([df["type"] == 0, df["type"].isin([1, 2, 3])],
                          ["ok", "non_vegetation"], default="type_missing")

# 4. confidence
df["confidence_raw"] = df["confidence"]
df["confidence_class"] = pd.Series(pd.NA, index=df.index, dtype="object")
viirs, modis, oli = (df["sensor"] == s for s in ["VIIRS", "MODIS", "OLI"])
df.loc[viirs, "confidence_class"] = df.loc[viirs, "confidence"].map(VIIRS_CONF_MAP)
df.loc[oli, "confidence_class"] = df.loc[oli, "confidence"].map(LANDSAT_CONF_MAP)
modis_conf = pd.to_numeric(df.loc[modis, "confidence"], errors="coerce")
df.loc[modis, "confidence_class"] = np.select(
    [modis_conf < MODIS_CONF_LOW_MAX, modis_conf < MODIS_CONF_HIGH_MIN, modis_conf <= 100],
    ["low", "nominal", "high"], default=None)

# 5. pixel size: side length sqrt(scan * track) and area scan * track where scan/track are km, else nominal
has_km = df["sensor"].isin(SENSORS_WITH_SCAN_TRACK_KM) & df["scan"].notna() & df["track"].notna()
nominal = df["sensor"].map(NOMINAL_PIXEL_KM)
df["pixel_area_km2"] = np.where(has_km, df["scan"] * df["track"], nominal ** 2)
df["pixel_size_km"] = np.sqrt(df["pixel_area_km2"])
df["pixel_size_source"] = np.where(has_km, "scan_track", "nominal")

# 6. static_proxy for rows without type (NOAA-21); empty for every other row
#    Same test as v1 (dist_km from each row to every static pixel), computed per latitude strip of
#    width STATIC_PROXY_DIST_KM: a static pixel two or more strips away is always farther than the
#    threshold, so only the row's strip and its two neighbours are compared (fast enough for the globe).
static = df[df["qc_flag"] == "non_vegetation"]
df["static_proxy"] = pd.Series(pd.NA, index=df.index, dtype="object")
strip_deg = STATIC_PROXY_DIST_KM / KM_PER_DEG_LAT
static_strip = np.floor(static["latitude"].to_numpy() / strip_deg).astype(int)
missing = df[df["qc_flag"] == "type_missing"]
for strip, rows in missing.groupby(np.floor(missing["latitude"].to_numpy() / strip_deg).astype(int)):
    near = static[np.abs(static_strip - strip) <= 1]
    s_lat, s_lon = near["latitude"].to_numpy(), near["longitude"].to_numpy()
    for idx, lat, lon in zip(rows.index, rows["latitude"].to_numpy(), rows["longitude"].to_numpy()):
        df.loc[idx, "static_proxy"] = bool((dist_km(lat, lon, s_lat, s_lon) <= STATIC_PROXY_DIST_KM).any())

# 7. fire clusters over the whole region box (1 km grid, 8 neighbours, all times pooled)
df["fire_cluster"] = grid_clusters(df["latitude"].to_numpy(), df["longitude"].to_numpy(), CLUSTER_CELL_KM)

clusters = (df.groupby("fire_cluster")
            .agg(detections=("latitude", "size"), first_detection_utc=("obs_time_utc", "min"),
                 last_detection_utc=("obs_time_utc", "max"), centre_lat=("latitude", "mean"),
                 centre_lon=("longitude", "mean"), lat_min=("latitude", "min"), lat_max=("latitude", "max"),
                 lon_min=("longitude", "min"), lon_max=("longitude", "max"), n_platforms=("platform", "nunique"))
            .reset_index().rename(columns={"fire_cluster": "cluster_id"}))
for col in ["first_detection_utc", "last_detection_utc"]:
    clusters[col] = clusters[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- report ----
print("row counts:")
for name, n in counts:
    print(f"  {name}: {n}")
print("\nrows per platform:\n" + df.groupby(["sensor", "platform"]).size().to_string())
print("\nqc_flag:", df["qc_flag"].value_counts().to_dict())
print("static_proxy:", df["static_proxy"].value_counts(dropna=False).to_dict())
print("\npixel_size_km (side) by sensor:\n" + df.groupby("sensor")["pixel_size_km"].describe().round(3).to_string())
print(f"\nclusters: {len(clusters)}, with >= 100 detections: {(clusters['detections'] >= 100).sum()}, "
      f"single-pixel: {(clusters['detections'] == 1).sum()}")
print(clusters.head(16).round(3).to_string(index=False))

df.to_csv(OUT_FILE, index=False)
clusters.to_csv(CLUSTERS_FILE, index=False)
print(f"\nwritten: {OUT_FILE} ({len(df)} rows), {CLUSTERS_FILE} ({len(clusters)} rows)")
