"""Merge the selected FIRMS files, build obs_time_utc, map platforms, deduplicate (v1 Step 2, unchanged).

Uses the GLOBAL request per sensor (v1 decision D1). The Spain-only requests are only
loaded to re-check that they are subsets.
Output: processed/firms_merged.csv.gz (global, cropping happens in 02_clean.py).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.helpers import BASE_DIR, PROCESSED  # noqa: E402

# ---- parameters ----
OUT_FILE = PROCESSED / "firms_merged.csv.gz"
USED_REQUESTS = ["817220", "817218", "817219", "817216", "817217"]   # SV, J1V, J2V, MODIS, LS
SUBSET_CHECK = {"817225": "817220", "817223": "817218", "817224": "817219", "817221": "817216"}
DEDUP_ROUND_DECIMALS = 4

PLATFORM_MAP = {"SNPP": "Suomi-NPP", "N": "Suomi-NPP", "N20": "NOAA-20", "N21": "NOAA-21",
                "Terra": "Terra", "T": "Terra", "Aqua": "Aqua", "A": "Aqua",
                "L8": "Landsat-8", "L9": "Landsat-9"}
SENSOR_MAP = {"Suomi-NPP": "VIIRS", "NOAA-20": "VIIRS", "NOAA-21": "VIIRS", "Terra": "MODIS",
              "Aqua": "MODIS", "Landsat-8": "OLI", "Landsat-9": "OLI"}
KEY = ["latitude", "longitude", "acq_date", "acq_time", "satellite"]


def load(request_id):
    csv = next(BASE_DIR.glob(f"DL_FIRE_*_{request_id}/*.csv"))
    df = pd.read_csv(csv, dtype={"acq_time": str, "version": str})
    df["request_id"] = request_id
    df["product"] = "NRT" if "_nrt_" in csv.name else "archive"
    df["source_file"] = f"{csv.parent.name}/{csv.name}"
    return df


# 1. subset check of the unused Spain requests
for small_id, global_id in SUBSET_CHECK.items():
    small, glob = load(small_id), load(global_id)
    missing = (small[KEY].merge(glob[KEY], on=KEY, how="left", indicator=True)["_merge"] == "left_only").sum()
    print(f"subset check {small_id} in {global_id}: {len(small)} rows, {missing} not in global")
    assert missing == 0, "Spain request is not a subset of the global request"

# 2. combine
df = pd.concat([load(r) for r in USED_REQUESTS], ignore_index=True)
print(f"\nrows after concat: {len(df)}")

# 3. obs_time_utc from acq_date + zero-padded HHMM
df["acq_time"] = df["acq_time"].str.zfill(4)
df["obs_time_utc"] = pd.to_datetime(df["acq_date"] + " " + df["acq_time"],
                                    format="%Y-%m-%d %H%M", utc=True, errors="coerce")
print(f"obs_time_utc not parseable: {df['obs_time_utc'].isna().sum()}")

# 4. platform and sensor
print(f"satellite codes found: {df['satellite'].value_counts().to_dict()}")
unknown = set(df["satellite"].unique()) - set(PLATFORM_MAP)
assert not unknown, f"unmapped satellite codes: {unknown}"
df["platform"] = df["satellite"].map(PLATFORM_MAP)
df["sensor"] = df["platform"].map(SENSOR_MAP)

# 5. archive vs NRT overlap per platform (keep archive where both exist)
overlap_drop = pd.Series(False, index=df.index)
for platform, g in df.groupby("platform"):
    if set(g["product"]) == {"archive", "NRT"}:
        arch = g[g["product"] == "archive"]["obs_time_utc"]
        nrt = g["product"] == "NRT"
        overlap_drop[g.index[nrt & g["obs_time_utc"].between(arch.min(), arch.max())]] = True
print(f"NRT rows dropped because archive covers the same time: {overlap_drop.sum()}")
df = df[~overlap_drop]

# 6. duplicates: same platform, same obs_time_utc, same lat/lon rounded
df["lat_r"] = df["latitude"].round(DEDUP_ROUND_DECIMALS)
df["lon_r"] = df["longitude"].round(DEDUP_ROUND_DECIMALS)
dup = df.duplicated(subset=["platform", "obs_time_utc", "lat_r", "lon_r"], keep="first")
print(f"duplicates removed: {dup.sum()}")
df = df[~dup].drop(columns=["lat_r", "lon_r"])

print(f"\nrows after merge and dedup: {len(df)}")
print(df.groupby(["platform", "sensor", "product"]).size().to_string())
df.to_csv(OUT_FILE, index=False)
print(f"written: {OUT_FILE}")
