"""Shared helpers: paths, geometry, clustering, map projection.

The geometry and clustering functions are copied unchanged from v1
(archive_v1/scripts/03_clean.py and 04_overpasses.py) so results reproduce.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]            # .../code/Input Data FIRMS
PROCESSED = BASE_DIR / "processed"
EVENTS_DIR = BASE_DIR / "events"
ARCHIVE_V1 = BASE_DIR / "archive_v1"
PYTHON_DTYPES = {"acq_time": str, "version": str, "request_id": str, "confidence": str, "confidence_raw": str}
KM_PER_DEG_LAT = 111.2
EARTH_RADIUS_M = 6378137.0    # Web Mercator sphere


def in_box(df, box):
    return (df["latitude"].between(box["lat_min"], box["lat_max"])
            & df["longitude"].between(box["lon_min"], box["lon_max"]))


def grow_box(box, margin_deg):
    return {"lat_min": box["lat_min"] - margin_deg, "lat_max": box["lat_max"] + margin_deg,
            "lon_min": box["lon_min"] - margin_deg, "lon_max": box["lon_max"] + margin_deg}


def dist_km(lat, lon, lats, lons):
    """Equirectangular distance in km from one point to arrays of points (fine at fire scale)."""
    dy = (lats - lat) * KM_PER_DEG_LAT
    dx = (lons - lon) * KM_PER_DEG_LAT * np.cos(np.radians(lat))
    return np.hypot(dx, dy)


def extent_km(lats, lons):
    """Diagonal of the bounding box of the detections, in km (equirectangular)."""
    dy = (lats.max() - lats.min()) * KM_PER_DEG_LAT
    dx = (lons.max() - lons.min()) * KM_PER_DEG_LAT * np.cos(np.radians(lats.mean()))
    return float(np.hypot(dx, dy))


def grid_clusters(lats, lons, cell_km):
    """Put detections on a grid of about cell_km x cell_km and label connected groups of
    occupied cells (8 neighbours). All times pooled: a cluster is the footprint of one
    fire (or of fires that touched) over the whole period. Labels 1, 2, ... by size."""
    ci = np.floor(lats * KM_PER_DEG_LAT / cell_km).astype(int)
    cj = np.floor(lons * KM_PER_DEG_LAT * np.cos(np.radians(lats)) / cell_km).astype(int)
    cells = set(zip(ci, cj))
    cell_label, n = {}, 0
    for start in cells:
        if start in cell_label:
            continue
        n += 1
        cell_label[start] = n
        stack = [start]
        while stack:
            i, j = stack.pop()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nb = (i + di, j + dj)
                    if nb in cells and nb not in cell_label:
                        cell_label[nb] = n
                        stack.append(nb)
    labels = np.array([cell_label[c] for c in zip(ci, cj)])
    by_size = pd.Series(labels).value_counts().index          # relabel: 1 = most detections
    return pd.Series(labels).map({old: new for new, old in enumerate(by_size, start=1)}).to_numpy()


def merc_x(lon):
    """Longitude (deg) to Web Mercator x (m), the projection of the map tiles."""
    return EARTH_RADIUS_M * np.radians(lon)


def merc_y(lat):
    return EARTH_RADIUS_M * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def region_dir(region_id):
    """processed/<region_id>/ for region-level outputs, created if missing."""
    d = PROCESSED / region_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_clean(region_id):
    df = pd.read_csv(region_dir(region_id) / "firms_clean.csv", dtype={**PYTHON_DTYPES, "static_proxy": str})
    df["obs_time_utc"] = pd.to_datetime(df["obs_time_utc"], utc=True)
    # static_proxy: True/False for type_missing rows, empty otherwise (read as text, never bool("False"))
    df["static_proxy"] = df["static_proxy"].map({"True": True, "False": False}).astype("object")
    return df
