"""Step 2.1: global FIRMS screen. One row per fire complex (FIRMS 1 km cluster), with continent.

Input: FIRMS processed/world/firms_clean.csv (FIRMS 02_clean.py --region world): same cleaning,
type flags, NOAA-21 static proxy and 1 km clustering as for the Spanish events.
Outputs (processed/):
  complexes.csv               one row per cluster with >= 1 kept detection
  candidate_matches.csv       each candidate of notes/candidates_ground_truth.csv and its cluster
  candidate_detections.csv    all detections of the matched clusters, column kept = passes the keep rule
                              (the timelines also show the low-confidence ones)

Usage: python scripts/01_screen_firms.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ES_DIR = Path(__file__).resolve().parents[1]
FIRMS_DIR = ES_DIR.parent / "Input Data FIRMS"
sys.path.insert(0, str(FIRMS_DIR / "scripts"))
from lib.helpers import dist_km, extent_km, read_clean  # noqa: E402
from lib.registry import load_registry  # noqa: E402

# ---- parameters ----
REGION_ID = "world"
CONF_KEEP = ["nominal", "high"]            # registry conventions.conf_modes.nominal_high
MATCH_KM = 5.0                             # candidate point to the nearest kept detection of a cluster
VIIRS_CELL_KM = 0.375                      # FIRMS area proxy: distinct VIIRS-size cells with a kept VIIRS detection
GROUND_TRUTH = ES_DIR / "notes" / "candidates_ground_truth.csv"
OUT = ES_DIR / "processed"


def continent(lat, lon):
    """Approximate continent of a cluster centre (screen convention, boxes in degrees)."""
    if (lon >= 112 and lat <= -10) or (lon >= 141 and lat < 0) or lon <= -150:
        return "Oceania"
    if -82 <= lon <= -34 and lat < 13:
        return "South America"
    if lon < -34:
        return "North America"
    if -18 <= lon <= 52 and -35 <= lat < 35.95 and not (lon > 32 and lat > 29.5) and not (lon > 34.5 and lat > 12):
        return "Africa"
    if (-25 <= lon <= 60 and lat >= 42) or (-25 <= lon <= 26 and lat >= 35.95):
        return "Europe"
    return "Asia"


reg = load_registry()
conv = reg["conventions"]
df = read_clean(REGION_ID)
n_all = len(df)
df["non_vegetation"] = (df["qc_flag"] == "non_vegetation") | (df["static_proxy"] == True)  # noqa: E712
keep = (df["qc_flag"].isin(conv["qc_keep"]) & ~df["non_vegetation"] & df["confidence_class"].isin(CONF_KEEP)
        & df["sensor"].isin(["VIIRS", "MODIS"]))

# 1. one row per cluster: kept detections only, plus the share of non-vegetation flags among all its detections
share_nonveg = df.groupby("fire_cluster")["non_vegetation"].mean().rename("share_non_vegetation")
k = df[keep]
cx = (k.groupby("fire_cluster")
      .agg(detections=("latitude", "size"), viirs=("sensor", lambda s: int((s == "VIIRS").sum())),
           frp_sum_mw=("frp", "sum"), first_utc=("obs_time_utc", "min"), last_utc=("obs_time_utc", "max"),
           lat=("latitude", "mean"), lon=("longitude", "mean"), lat_min=("latitude", "min"),
           lat_max=("latitude", "max"), lon_min=("longitude", "min"), lon_max=("longitude", "max"))
      .join(share_nonveg).reset_index().rename(columns={"fire_cluster": "cluster_id"}))
cells = k.assign(ci=(k["latitude"] * 100).round(), cj=(k["longitude"] * 100).round())
cx["cells"] = cx["cluster_id"].map(cells.groupby("fire_cluster")[["ci", "cj"]].apply(lambda g: len(g.drop_duplicates())))
cx["active_days"] = cx["cluster_id"].map(k.groupby("fire_cluster")["obs_time_utc"].apply(lambda t: t.dt.date.nunique()))
# burned-area proxy: distinct 375 m cells (VIIRS I-band size) with a kept VIIRS detection, times the cell area.
# Same measure on every continent; it misses burning after the FIRMS data end and unburnt gaps inside a cell.
v = k[k["sensor"] == "VIIRS"]
vi = np.floor(v["latitude"] * 111.2 / VIIRS_CELL_KM)
vj = np.floor(v["longitude"] * 111.2 * np.cos(np.radians(v["latitude"])) / VIIRS_CELL_KM)
n_cells = pd.DataFrame({"c": v["fire_cluster"], "i": vi, "j": vj}).drop_duplicates().groupby("c").size()
cx["firms_area_ha"] = (cx["cluster_id"].map(n_cells).fillna(0) * VIIRS_CELL_KM ** 2 * 100).round(0)
cx["extent_km"] = [extent_km(pd.Series([a, b]), pd.Series([c, d]))
                   for a, b, c, d in zip(cx.lat_min, cx.lat_max, cx.lon_min, cx.lon_max)]
cx["continent"] = [continent(a, b) for a, b in zip(cx.lat, cx.lon)]
OUT.mkdir(exist_ok=True)
cx.to_csv(OUT / "complexes.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ", float_format="%.4f")

# 2. match each candidate to the largest cluster with a kept detection within MATCH_KM of its point
gt = pd.read_csv(GROUND_TRUTH)
rows, members = [], []
for c in gt.itertuples():
    d = dist_km(c.lat, c.lon, k["latitude"].to_numpy(), k["longitude"].to_numpy())
    near = k[d <= MATCH_KM]
    if near.empty:
        rows.append(dict(candidate_id=c.candidate_id, cluster_id=np.nan, nearest_detection_km=round(float(d.min()), 1)))
        continue
    cl = near["fire_cluster"].value_counts().index[0]
    rows.append(dict(candidate_id=c.candidate_id, cluster_id=int(cl), nearest_detection_km=round(float(d.min()), 1)))
    members.append(df[df["fire_cluster"] == cl].assign(candidate_id=c.candidate_id, kept=keep[df["fire_cluster"] == cl]))
matches = pd.DataFrame(rows).merge(cx, on="cluster_id", how="left")
matches.to_csv(OUT / "candidate_matches.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ", float_format="%.4f")
cols = ["candidate_id", "fire_cluster", "obs_time_utc", "platform", "sensor", "latitude", "longitude", "frp",
        "confidence_class", "non_vegetation", "kept"]
pd.concat(members)[cols].to_csv(OUT / "candidate_detections.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

# ---- report ----
print(f"detections: {n_all}, kept (vegetation, {'/'.join(CONF_KEEP)}, VIIRS + MODIS): {int(keep.sum())}")
print(f"complexes: {len(cx)}")
print(cx.groupby("continent").agg(complexes=("cluster_id", "size"), detections=("detections", "sum")).to_string())
print("\ncandidate matches:")
print(matches[["candidate_id", "cluster_id", "nearest_detection_km", "detections", "firms_area_ha", "first_utc",
               "share_non_vegetation", "continent"]].to_string(index=False))
