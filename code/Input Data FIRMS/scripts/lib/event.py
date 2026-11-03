"""Event selection shared by the scripts in scripts/event/.

Rule (registry conventions, v1 Larouco method):
1. seed = first detection at or after (ignition_utc - ignition_tolerance_min) within seed_radius_km
   of reference_point (ties at the same minute: closest to the reference point);
2. event = the seed's FIRMS fire cluster (event_member);
3. T0 = first VIIRS/MODIS event member at or after (ignition_utc - ignition_tolerance_min).
"""
import argparse

import pandas as pd

from lib.helpers import EVENTS_DIR, dist_km, grow_box, in_box, read_clean
from lib.registry import get_event, load_registry, utc

ROW_MARGIN_DEG = 0.5          # event_observations rows: search box plus this margin (strategy v2.1)
BASELINE_SENSORS = ["VIIRS", "MODIS"]
SENSING_LAYER = ["Suomi-NPP", "NOAA-20", "NOAA-21", "Terra", "Aqua"]


def parse_event_arg():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, help="event_id from events_registry.yaml")
    return parser.parse_args().event


def event_dirs(event_id):
    base = EVENTS_DIR / event_id
    dirs = {k: base / k for k in ["processed", "figures", "notes"]}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def select_event(event_id, df=None, cluster_col="fire_cluster"):
    """Return a dict with the registry entry, the clean table with event columns, seed and T0."""
    reg = load_registry()
    ev = get_event(event_id, reg)
    df = read_clean(ev["region"]) if df is None else df.copy()
    ignition = utc(ev["ignition_utc"])
    earliest = ignition - pd.Timedelta(minutes=ev["ignition_tolerance_min"])
    ref = ev["reference_point"]

    df["dist_ref_km"] = dist_km(ref["lat"], ref["lon"], df["latitude"].to_numpy(), df["longitude"].to_numpy())
    cand = df[(df["obs_time_utc"] >= earliest) & (df["dist_ref_km"] <= ev["seed_radius_km"])]
    if cand.empty:
        raise ValueError(f"{event_id}: no detection within {ev['seed_radius_km']} km after {earliest}")
    seed = cand.sort_values(["obs_time_utc", "dist_ref_km"]).iloc[0]
    cluster_id = int(seed[cluster_col])

    df["event_id"] = event_id
    df["in_search_box"] = in_box(df, ev["search_box"])
    df["event_member"] = df[cluster_col] == cluster_id
    df["event_member_sensitivity"] = df["event_member"]          # FIRMS: identical to event_member
    members = df[df["event_member"]]
    t0_rows = members[(members["obs_time_utc"] >= earliest) & members["sensor"].isin(BASELINE_SENSORS)]
    t0 = t0_rows.sort_values(["obs_time_utc", "dist_ref_km"]).iloc[0]
    return {"registry": reg, "event": ev, "df": df, "seed": seed, "cluster_id": cluster_id,
            "ignition": ignition, "earliest": earliest, "t0": t0,
            "n_members_before_earliest": int((members["obs_time_utc"] < earliest).sum()),
            "row_box": grow_box(ev["search_box"], ROW_MARGIN_DEG)}
