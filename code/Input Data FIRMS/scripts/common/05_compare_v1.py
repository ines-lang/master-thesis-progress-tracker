"""Regression check of the v2 common pipeline against archive_v1/ (read-only).

Row counts and unchanged columns must be identical; only the convention fixes may differ:
pixel_size_km (now side length), pixel_area_km2 (new), static_proxy (empty instead of False
for rows with a type), and the event-specific v1 columns moved to scripts/event/.
v1 covered Iberia only: python scripts/common/05_compare_v1.py --region iberia
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.helpers import ARCHIVE_V1, PROCESSED, PYTHON_DTYPES, read_clean, region_dir  # noqa: E402
from lib.registry import region_arg  # noqa: E402

REGION_ID, _ = region_arg()

KEY = ["platform", "obs_time_utc", "latitude", "longitude"]
UNCHANGED = ["sensor", "frp", "confidence_raw", "confidence_class", "daynight", "qc_flag", "type",
             "scan", "track", "fire_cluster", "overpass_id", "pixel_size_source"]

rows = []
v1_merged = pd.read_csv(ARCHIVE_V1 / "processed" / "firms_merged.csv.gz", usecols=["platform"])
v2_merged = pd.read_csv(PROCESSED / "firms_merged.csv.gz", usecols=["platform"])
rows.append(("firms_merged.csv.gz rows", len(v1_merged), len(v2_merged)))

v1 = pd.read_csv(ARCHIVE_V1 / "processed" / "firms_clean.csv", dtype=PYTHON_DTYPES)
v1["obs_time_utc"] = pd.to_datetime(v1["obs_time_utc"], utc=True)
v2 = read_clean(REGION_ID)
rows.append(("firms_clean.csv rows", len(v1), len(v2)))
for p in sorted(v2["platform"].unique()):
    rows.append((f"  rows {p}", (v1["platform"] == p).sum(), (v2["platform"] == p).sum()))
for f in ["ok", "non_vegetation", "type_missing"]:
    rows.append((f"  qc_flag {f}", (v1["qc_flag"] == f).sum(), (v2["qc_flag"] == f).sum()))
rows.append(("  static_proxy True", int(v1["static_proxy"].astype(str).eq("True").sum()),
             int((v2["static_proxy"] == True).sum())))  # noqa: E712
rows.append(("  fire clusters", v1["fire_cluster"].nunique(), v2["fire_cluster"].nunique()))
rows.append(("  overpasses", v1["overpass_id"].nunique(), v2["overpass_id"].nunique()))

# row-by-row comparison of unchanged columns
m = v1.merge(v2, on=KEY, how="outer", suffixes=("_v1", "_v2"), indicator=True)
rows.append(("  rows matched on platform, time, lat, lon", (m["_merge"] == "both").sum(), len(v2)))
both = m[m["_merge"] == "both"]
for col in UNCHANGED:
    a, b = both[f"{col}_v1"], both[f"{col}_v2"]
    same = (a == b) | (a.isna() & b.isna())
    rows.append((f"  identical values: {col}", len(both), int(same.sum())))

# changed conventions
side = np.sqrt(both["pixel_size_km_v1"])
rows.append(("  pixel_area_km2 (v2) == pixel_size_km (v1)", len(both),
             int(np.isclose(both["pixel_area_km2"], both["pixel_size_km_v1"]).sum())))
rows.append(("  pixel_size_km (v2) == sqrt(pixel_size_km v1)", len(both),
             int(np.isclose(both["pixel_size_km_v2"], side).sum())))

v1_obs = pd.read_csv(ARCHIVE_V1 / "processed" / "observations_standard.csv")
v2_obs = pd.read_csv(region_dir(REGION_ID) / "observations_standard.csv", dtype={"static_proxy": str})
rows.append(("observations_standard.csv rows", len(v1_obs), len(v2_obs)))
v1_ov = pd.read_csv(ARCHIVE_V1 / "processed" / "overpasses_iberia.csv")
v2_ov = pd.read_csv(region_dir(REGION_ID) / "overpasses.csv")
rows.append(("overpasses_iberia.csv rows", len(v1_ov), len(v2_ov)))
cols = ["overpass_id", "start_time_utc", "n_pixels", "total_frp_mw", "extent_km"]
mo = v1_ov[cols].merge(v2_ov[cols], on="overpass_id", suffixes=("_v1", "_v2"))
same_ov = ((mo["start_time_utc_v1"] == mo["start_time_utc_v2"]) & (mo["n_pixels_v1"] == mo["n_pixels_v2"])
           & np.isclose(mo["total_frp_mw_v1"], mo["total_frp_mw_v2"]) & np.isclose(mo["extent_km_v1"], mo["extent_km_v2"]))
rows.append(("  overpasses identical (start, n, FRP, extent)", len(v1_ov), int(same_ov.sum())))

out = pd.DataFrame(rows, columns=["check", "v1", "v2"])
out["match"] = np.where(out["v1"] == out["v2"], "yes", "NO")
print(out.to_string(index=False))
print("\ncolumns only in v1 clean:", sorted(set(v1.columns) - set(v2.columns)))
print("columns only in v2 clean:", sorted(set(v2.columns) - set(v1.columns)))
print("observations_standard columns only in v1:", sorted(set(v1_obs.columns) - set(v2_obs.columns)))
print("observations_standard columns only in v2:", sorted(set(v2_obs.columns) - set(v1_obs.columns)))
