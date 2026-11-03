"""Event-agnostic test: do EFFIS start dates coincide with FIRMS overpasses?

For every EFFIS record: gap (min) between its start date and the nearest FIRMS
pass start or end over the region, and the platform(s) of the passes within the window.
Usage: python scripts/common/03_overpass_coincidence.py --region <region_id> (the region of the EFFIS request)
Records starting after the FIRMS data end, or at exactly 00:00:00 (date-only
entries, assumption A3), are kept in the output but excluded from the share.
Chance level = share of the FIRMS time span within the window of any pass.
Logic unchanged from v1 (scripts/04_footprint_and_check.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from firms import firms_overpasses_file, load_overpasses  # noqa: E402
from registry import REPO_DIR, load_registry, region_arg, utc  # noqa: E402

import numpy as np
import pandas as pd

# ---- parameters ----
EVENTS_FILE = REPO_DIR / "processed" / "effis_events_es.csv"
OUT_FILE = REPO_DIR / "processed" / "effis_overpass_coincidence.csv"

reg = load_registry()
REGION_ID = region_arg()
WINDOW_MIN = reg["conventions"]["overpass_window_min"]
PERIOD_START = utc(reg["data_window"]["start_utc"])
FIRMS_END = utc(reg["data_window"]["firms_data_end_utc"])


def nearest_gap_min(times, ref_times):
    """Minutes from each time to the nearest of the sorted ref_times."""
    idx = np.clip(np.searchsorted(ref_times, times), 1, len(ref_times) - 1)
    return np.minimum(abs(times - ref_times[idx - 1]), abs(ref_times[idx] - times)) / np.timedelta64(1, "m")


ov = load_overpasses(REGION_ID)
ov_t = np.sort(np.concatenate([ov["start_time_utc"].values, ov["end_time_utc"].values]))
ev = pd.read_csv(EVENTS_FILE, dtype={"effis_id": str}, parse_dates=["start_date"])

out = ev[["effis_id", "province", "commune", "start_date", "area_ha"]].copy()
out["gap_to_nearest_pass_min"] = nearest_gap_min(out["start_date"].values, ov_t).round(1)
win = pd.Timedelta(minutes=WINDOW_MIN)
out["platforms_within_window"] = [
    "/".join(sorted(set(ov.loc[(ov["start_time_utc"] - win <= t) & (ov["end_time_utc"] + win >= t), "platform"])))
    for t in out["start_date"]]
out["within_window"] = out["gap_to_nearest_pass_min"] <= WINDOW_MIN
out["excluded_reason"] = np.select(
    [out["start_date"] > FIRMS_END, out["start_date"].dt.strftime("%H:%M:%S") == "00:00:00"],
    ["after_firms_data_end", "midnight_date_only"], default="")
out.to_csv(OUT_FILE, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

# ---- summary ----
used = out[out["excluded_reason"] == ""]
grid = pd.date_range(PERIOD_START, FIRMS_END, freq="1min").values
chance = (nearest_gap_min(grid, ov_t) <= WINDOW_MIN).mean()
print(f"FIRMS passes: {len(ov)} from {firms_overpasses_file(REGION_ID)}; FIRMS data end {FIRMS_END:%Y-%m-%dT%H:%MZ}")
print(f"EFFIS records: {len(out)}; excluded: {out['excluded_reason'].value_counts().drop('', errors='ignore').to_dict()}")
print(f"used n={len(used)}: within +-{WINDOW_MIN} min of a pass {used['within_window'].mean():.0%} "
      f"({used['within_window'].sum()}); chance level {chance:.0%}; "
      f"median gap {used['gap_to_nearest_pass_min'].median():.1f} min")
print("matched platform(s): " + str(used.loc[used["within_window"], "platforms_within_window"]
                                    .value_counts().to_dict()))
print(f"written {OUT_FILE.name}")
