"""Event products for one registry event.

Usage: python scripts/event/02_products.py --event <event_id>
Writes to events/<event_id>/processed/:
  event_observations.csv            schema v2 + event columns; detections in search box + 0.5 deg margin, plus all members
  event_overpasses.csv              passes with >= 1 event member
  overpass_times_sensing_layer.csv  all passes of the 5 sensing-layer platforms touching the search box
  event_footprint.csv               event member coordinates, times and pixel size
  event_extent.json                 bounding box of the members
  event_summary.json                key numbers (T0, counts, descriptive gaps) and the regression check
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.event import SENSING_LAYER, event_dirs, parse_event_arg, select_event  # noqa: E402
from lib.helpers import extent_km, in_box  # noqa: E402
from lib.schema import EVENT_COLUMNS, ISO_FMT, SCHEMA_V2, check_and_write, firms_to_schema  # noqa: E402

GAP_PERCENTILE = 90           # descriptive only; official statistics are computed in the Comparison repo


def iso(t):
    return pd.Timestamp(t).strftime(ISO_FMT)


event_id = parse_event_arg()
sel = select_event(event_id)
ev, df, t0 = sel["event"], sel["df"], sel["t0"]
dirs = event_dirs(event_id)
out = dirs["processed"]
members = df[df["event_member"]]

# 1. event_observations.csv
rows = df[in_box(df, sel["row_box"]) | df["event_member"]]
obs = firms_to_schema(rows)
for col in EVENT_COLUMNS:
    obs[col] = rows[col].to_numpy()
obs = obs.sort_values(["obs_time_utc", "platform", "latitude", "longitude"]).reset_index(drop=True)
check_and_write(obs, out / "event_observations.csv", event=True)

# 2. event_overpasses.csv (instant = first event-member detection of the pass)
passes = []
for oid, g in members.groupby("overpass_id"):
    all_in_pass = df[df["overpass_id"] == oid]
    passes.append({
        "overpass_id": oid, "platform": g["platform"].iloc[0], "sensor": g["sensor"].iloc[0],
        "overpass_start_utc": all_in_pass["obs_time_utc"].min(), "first_member_utc": g["obs_time_utc"].min(),
        "day_night": "/".join(sorted(g["daynight"].dropna().unique())), "n_members": len(g),
        "total_frp_mw": g["frp"].sum(min_count=1), "extent_km": extent_km(g["latitude"], g["longitude"]),
    })
ep = pd.DataFrame(passes).sort_values("first_member_utc").reset_index(drop=True)
ep["gap_to_previous_h"] = ep["first_member_utc"].diff().dt.total_seconds() / 3600
gaps = ep["gap_to_previous_h"].dropna()

# 3. overpass_times_sensing_layer.csv (all sensing-layer passes touching the search box)
box_rows = df[df["in_search_box"] & df["platform"].isin(SENSING_LAYER)]
member_passes = set(members["overpass_id"])
#    overpass_start/end = whole pass over the event's region box (as v1); first/last_in_search_box = detections inside the box
pass_times = df.groupby("overpass_id")["obs_time_utc"].agg(overpass_start_utc="min", overpass_end_utc="max")
sl = (box_rows.groupby("overpass_id")
      .agg(platform=("platform", "first"), sensor=("sensor", "first"),
           first_in_search_box_utc=("obs_time_utc", "min"), last_in_search_box_utc=("obs_time_utc", "max"),
           day_night=("daynight", lambda x: "/".join(sorted(x.dropna().unique()))),
           n_pixels_search_box=("latitude", "size"))
      .join(pass_times).reset_index())
sl["event_detected"] = sl["overpass_id"].isin(member_passes)
sl = sl[["overpass_id", "platform", "sensor", "overpass_start_utc", "overpass_end_utc", "first_in_search_box_utc",
         "last_in_search_box_utc", "day_night", "n_pixels_search_box", "event_detected"]]
sl = sl.sort_values(["overpass_start_utc", "platform"]).reset_index(drop=True)

# 4. footprint and extent
fp = members[["obs_time_utc", "platform", "sensor", "overpass_id", "latitude", "longitude",
              "pixel_size_km", "pixel_area_km2", "frp", "qc_flag", "static_proxy"]].sort_values("obs_time_utc")
fp = fp.rename(columns={"frp": "frp_mw"})
extent = {"event_id": event_id, "cluster_id": sel["cluster_id"], "n_members": int(len(members)),
          "lat_min": float(members["latitude"].min()), "lat_max": float(members["latitude"].max()),
          "lon_min": float(members["longitude"].min()), "lon_max": float(members["longitude"].max()),
          "first_member_utc": iso(members["obs_time_utc"].min()), "last_member_utc": iso(members["obs_time_utc"].max()),
          "note": "bounding box of FIRMS event members (pixel centres), whole FIRMS period"}

# write tables with ISO times
for table, cols in [(ep, ["overpass_start_utc", "first_member_utc"]),
                    (sl, ["overpass_start_utc", "overpass_end_utc", "first_in_search_box_utc", "last_in_search_box_utc"]),
                    (fp, ["obs_time_utc"])]:
    for c in cols:
        table[c] = table[c].dt.strftime(ISO_FMT)
ep.to_csv(out / "event_overpasses.csv", index=False)
sl.to_csv(out / "overpass_times_sensing_layer.csv", index=False)
fp.to_csv(out / "event_footprint.csv", index=False)
(out / "event_extent.json").write_text(json.dumps(extent, indent=2))

# 5. summary and regression check
summary = {
    "event_id": event_id, "cluster_id": sel["cluster_id"],
    "seed_utc": iso(sel["seed"]["obs_time_utc"]), "seed_platform": sel["seed"]["platform"],
    "seed_dist_ref_km": round(float(sel["seed"]["dist_ref_km"]), 2),
    "t0_utc": iso(t0["obs_time_utc"]), "t0_platform": t0["platform"],
    "t0_minus_ignition_min": (t0["obs_time_utc"] - sel["ignition"]).total_seconds() / 60,
    "members_before_earliest_accepted": sel["n_members_before_earliest"],
    "firms_event_detections": int(len(members)),
    "members_per_platform": members.groupby("platform").size().to_dict(),
    "firms_overpasses_with_event": int(len(ep)),
    "baseline_gap_median_h": round(float(gaps.median()), 2),
    f"baseline_gap_p{GAP_PERCENTILE}_h": round(float(np.percentile(gaps, GAP_PERCENTILE)), 2),
    "baseline_gap_max_h": round(float(gaps.max()), 2),
    "sensing_layer_passes_touching_search_box": int(len(sl)),
    "sensing_layer_passes_with_event": int(sl["event_detected"].sum()),
    "event_observation_rows": int(len(obs)),
}
expected = ev.get("regression_expected", {})
checks = []
for key, exp in expected.items():
    if key in summary:
        got = summary[key]
        ok = np.isclose(got, exp, atol=0.005) if isinstance(exp, (int, float)) else str(got) == str(exp)
        checks.append({"key": key, "expected": exp, "obtained": got, "match": bool(ok)})
summary["regression_check"] = checks
(out / "event_summary.json").write_text(json.dumps(summary, indent=2, default=str))

print(json.dumps({k: v for k, v in summary.items() if k != "regression_check"}, indent=1, default=str))
if checks:
    print("\nregression check:\n" + pd.DataFrame(checks).to_string(index=False))
    print("keys in regression_expected not produced by FIRMS:", [k for k in expected if k not in summary])
print("\nwritten:", sorted(p.name for p in out.iterdir()))
