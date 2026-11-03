"""Group detections into overpass events per platform over the whole region box (v1 Step 4, unchanged).

An overpass starts at the first detection of a platform; every later detection of the
same platform within overpass_window_min of that start belongs to it.
Usage: python scripts/common/03_overpasses.py --region <region_id>
Outputs: overpass_id added to processed/<region_id>/firms_clean.csv; processed/<region_id>/overpasses.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.helpers import extent_km, read_clean, region_dir  # noqa: E402
from lib.registry import load_registry, region_arg  # noqa: E402
from lib.schema import ISO_FMT  # noqa: E402

# ---- parameters ----
REG = load_registry()
REGION_ID, _ = region_arg()
CLEAN_FILE = region_dir(REGION_ID) / "firms_clean.csv"
OUT_FILE = region_dir(REGION_ID) / "overpasses.csv"
OVERPASS_WINDOW_MIN = REG["conventions"]["overpass_window_min"]

df = read_clean(REGION_ID).sort_values(["platform", "obs_time_utc"])

# 1. assign overpass ids, window anchored at the overpass start
window = pd.Timedelta(minutes=OVERPASS_WINDOW_MIN)
overpass_id = np.empty(len(df), dtype=object)
for platform, g in df.groupby("platform"):
    start, n = None, 0
    for idx, t in g["obs_time_utc"].items():
        if start is None or t - start > window:
            start, n = t, n + 1
        overpass_id[df.index.get_loc(idx)] = f"{platform}_{n:03d}"
df["overpass_id"] = overpass_id

# 2. one row per overpass (region-wide; event subsets are computed in scripts/event/)
ov = (df.groupby("overpass_id")
      .agg(platform=("platform", "first"), sensor=("sensor", "first"),
           start_time_utc=("obs_time_utc", "min"), end_time_utc=("obs_time_utc", "max"),
           day_night=("daynight", lambda x: "/".join(sorted(x.dropna().unique()))),
           n_pixels=("latitude", "size"), total_frp_mw=("frp", lambda x: x.sum(min_count=1)))
      .reset_index())
ov["extent_km"] = [extent_km(g["latitude"], g["longitude"]) for _, g in df.groupby("overpass_id")]
ov["duration_min"] = (ov["end_time_utc"] - ov["start_time_utc"]).dt.total_seconds() / 60
ov = ov.sort_values("start_time_utc").reset_index(drop=True)
gaps = df.groupby("platform")["obs_time_utc"].apply(lambda t: t.diff().dt.total_seconds().div(60))
gaps = gaps[gaps > 0]

print(f"detections: {len(df)}   overpasses: {len(ov)}")
print(ov.groupby("platform").size().to_string())
print(f"duration within overpass (min): max {ov['duration_min'].max()}; "
      f"within-platform gaps between 5 and 60 min: {int(((gaps > 5) & (gaps < 60)).sum())}")

for col in ["start_time_utc", "end_time_utc"]:
    ov[col] = ov[col].dt.strftime(ISO_FMT)
ov = ov[["overpass_id", "platform", "sensor", "start_time_utc", "end_time_utc", "duration_min", "day_night",
         "n_pixels", "total_frp_mw", "extent_km"]]
ov.to_csv(OUT_FILE, index=False)
df.to_csv(CLEAN_FILE, index=False)
print(f"written: {OUT_FILE} ({len(ov)} rows); overpass_id added to {CLEAN_FILE.name}")
