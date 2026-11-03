#!/usr/bin/env python3
"""
v2 Step 2: per-event SEVIRI pipeline.

1. Extract search box + 0.5 deg margin from the export of the event's region.
2. Membership, only for acquisitions at or after (ignition - tolerance):
   event_member              pixel centre inside the FIRMS event bounding box (event_extent.json)
   event_member_sensitivity  pixel centre within 2 km of any FIRMS event detection (event_footprint.csv)
3. Per 15-min slot: detections in the search box, member pixels, total member FRP.
4. First member detection, robust onset (first of >= 2 consecutive member slots),
   blackouts (runs of >= 1 h without member pixel after the robust onset), for both rules.

Run from the "Input Data LSA SAF" folder:
    python scripts/event/01_event_seviri.py --event larouco
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.registry import FIRMS_EVENTS, REPO, get_event, get_region, in_box, iso_z, load_registry, region_dir, utc  # noqa: E402
from lib.schema import EVENT_COLUMNS, SCHEMA_V2, check_and_write                         # noqa: E402

# ---------------- constants ----------------
MARGIN_DEG = 0.5
SLOT_MIN = 15
BLACKOUT_MIN_H = 1.0
ONSET_CONSECUTIVE = 2
EARTH_RADIUS_KM = 6371.0088
# -------------------------------------------

RULES = {"primary": "event_member", "sensitivity": "event_member_sensitivity"}


def min_distance_km(lat, lon, ref_lat, ref_lon, chunk=2000):
    """Haversine distance from every (lat, lon) to the nearest reference point."""
    lat1, lon1 = np.radians(lat)[:, None], np.radians(lon)[:, None]
    lat2, lon2 = np.radians(ref_lat)[None, :], np.radians(ref_lon)[None, :]
    out = np.empty(len(lat))
    for i in range(0, len(lat), chunk):
        a, b = lat1[i:i + chunk], lon1[i:i + chunk]
        h = np.sin((lat2 - a) / 2) ** 2 + np.cos(a) * np.cos(lat2) * np.sin((lon2 - b) / 2) ** 2
        out[i:i + chunk] = (2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h))).min(axis=1)
    return out


def runs(mask):
    """Start/end index pairs of True runs in a boolean array."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def timeline_stats(slots, member_slots, first_instant, onset_slot_instant):
    """First detection, robust onset and blackouts for one membership rule."""
    has = slots.isin(member_slots)
    out = {"first_detection_utc": first_instant, "slots_with_member": int(has.sum())}
    onset_idx = next((i for i in range(len(slots) - ONSET_CONSECUTIVE + 1)
                      if has[i:i + ONSET_CONSECUTIVE].all()), None)
    out["robust_onset_slot_utc"] = slots[onset_idx] if onset_idx is not None else None
    out["robust_onset_utc"] = onset_slot_instant.get(slots[onset_idx]) if onset_idx is not None else None
    blackouts = []
    if onset_idx is not None:
        tail = ~has[onset_idx:]
        for s, e in runs(np.asarray(tail)):
            n = e - s
            if n * SLOT_MIN / 60 >= BLACKOUT_MIN_H:
                start = slots[onset_idx + s]
                open_end = onset_idx + e >= len(slots)
                end = slots[onset_idx + e] if not open_end else slots[-1] + pd.Timedelta(minutes=SLOT_MIN)
                blackouts.append({"start_slot_utc": start, "end_slot_utc": end, "n_slots": int(n),
                                  "hours": n * SLOT_MIN / 60, "open_until_data_end": bool(open_end)})
    out["blackouts"] = blackouts
    return out


def fmt(t):
    return None if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True)
    event_id = ap.parse_args().event

    reg = load_registry()
    ev = get_event(reg, event_id)
    get_region(reg, ev["region"])
    in_extended = region_dir(ev["region"]) / "lsasaf_pixels.csv"
    box = ev["search_box"]
    start, end = utc(reg["data_window"]["start_utc"]), utc(reg["data_window"]["end_utc"])
    ignition = utc(ev["ignition_utc"])
    earliest = ignition - pd.Timedelta(minutes=ev["ignition_tolerance_min"])
    sens_km = reg["conventions"]["seviri_membership_sensitivity_km"]

    firms_dir = FIRMS_EVENTS / event_id / "processed"
    extent = json.loads((firms_dir / "event_extent.json").read_text())
    foot = pd.read_csv(firms_dir / "event_footprint.csv")
    firms_t0 = json.loads((firms_dir / "event_summary.json").read_text()).get("t0_utc")

    out_dir = REPO / "events" / event_id / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. extract search box + margin
    df = pd.read_csv(in_extended, dtype={"confidence_raw": str, "day_night": str, "static_proxy": str},
                     keep_default_na=False, na_values={"frp_mw": [""]})
    df = df[in_box(df.latitude, df.longitude, box, MARGIN_DEG)].copy()
    obs = pd.to_datetime(df.obs_time_utc).dt.tz_convert(None)
    df["slot"] = pd.to_datetime(df.slot_time_utc).dt.tz_convert(None)

    # 2. membership
    df["event_id"] = event_id
    df["in_search_box"] = in_box(df.latitude, df.longitude, box)
    after = obs >= earliest
    inside_bbox = (df.latitude.between(extent["lat_min"], extent["lat_max"])
                   & df.longitude.between(extent["lon_min"], extent["lon_max"]))
    df["dist_firms_km"] = min_distance_km(df.latitude.values, df.longitude.values,
                                          foot.latitude.values, foot.longitude.values)
    df["event_member"] = after & inside_bbox
    df["event_member_sensitivity"] = after & (df.dist_firms_km <= sens_km)

    event_obs = df[SCHEMA_V2 + EVENT_COLUMNS]
    check_and_write(event_obs, out_dir / "event_observations.csv", SCHEMA_V2 + EVENT_COLUMNS)

    # 3. per slot table over the whole data window
    slots = pd.date_range(start, end, freq=f"{SLOT_MIN}min")
    df["obs"] = obs
    sb = df[df.in_search_box]
    tab = pd.DataFrame(index=slots)
    tab["n_search_box"] = sb.groupby("slot").size()
    for rule, col in RULES.items():
        m = df[df[col]]
        g = m.groupby("slot")
        tab[f"n_member_{rule}"] = g.size()
        tab[f"frp_member_{rule}_mw"] = g.frp_mw.sum()
        tab[f"instant_{rule}_utc"] = g.obs.min()          # earliest ACQTIME in the slot
    tab = tab.fillna({c: 0 for c in tab.columns if c.startswith(("n_", "frp_"))})
    for c in [c for c in tab.columns if c.startswith("n_")]:
        tab[c] = tab[c].astype(int)
    vza = df[df.event_member].groupby("slot").pixel_vza_deg.agg(["min", "max"])
    tab["vza_member_min_deg"], tab["vza_member_max_deg"] = vza["min"], vza["max"]
    tab_out = tab.copy()
    for c in [c for c in tab_out.columns if c.startswith("instant_")]:
        tab_out[c] = tab_out[c].map(fmt)
    tab_out.insert(0, "slot_time_utc", [fmt(t) for t in tab_out.index])
    tab_out.to_csv(out_dir / "seviri_event_slots.csv", index=False)

    # 4. first detection, robust onset, blackouts
    summary = {"event_id": event_id, "ignition_utc": fmt(ignition), "earliest_accepted_utc": fmt(earliest),
               "firms_t0_utc": firms_t0, "firms_bbox": {k: extent[k] for k in ["lat_min", "lat_max", "lon_min", "lon_max"]},
               "sensitivity_km": sens_km,
               "rows_search_box_plus_margin": int(len(df)), "rows_in_search_box": int(df.in_search_box.sum()),
               "slots_with_detection_in_search_box": int((tab.n_search_box > 0).sum()),
               "rows_before_earliest_in_bbox": int((~after & inside_bbox).sum()),
               "rules": {}}
    for rule, col in RULES.items():
        m = df[df[col]]
        inst = tab[f"instant_{rule}_utc"].dropna().to_dict()
        st = timeline_stats(slots, set(m.slot), m.obs.min() if len(m) else None, inst)
        first = m[m.obs == m.obs.min()]
        st.update({
            "member_rows": int(len(m)),
            "distinct_pixels": int(m.groupby(["abs_line", "abs_pixel"]).ngroups),
            "first_detection_pixels": first[["latitude", "longitude", "frp_mw", "confidence_raw",
                                             "dist_firms_km"]].round(3).to_dict("records"),
            "first_minus_ignition_min": (m.obs.min() - ignition).total_seconds() / 60 if len(m) else None,
            "vza_deg": [float(m.pixel_vza_deg.min()), float(m.pixel_vza_deg.max())] if len(m) else None,
            "pixel_size_km": [float(m.pixel_size_km.min()), float(m.pixel_size_km.max())] if len(m) else None,
            "last_detection_utc": m.obs.max() if len(m) else None,
        })
        if st["robust_onset_utc"] is not None:
            st["robust_onset_minus_ignition_min"] = (st["robust_onset_utc"] - ignition).total_seconds() / 60
        summary["rules"][rule] = st

    def to_json(o):
        if isinstance(o, (pd.Timestamp,)):
            return fmt(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(type(o))

    (out_dir / "seviri_event_summary.json").write_text(json.dumps(summary, indent=2, default=to_json))
    print(json.dumps(summary, indent=2, default=to_json))
    print(f"\nWrote events/{event_id}/processed/: event_observations.csv ({len(event_obs)} rows), "
          f"seviri_event_slots.csv ({len(tab)} slots), seviri_event_summary.json")

    # regression check against the registry
    exp = ev.get("regression_expected", {})
    checks = []
    if "lsasaf_slots_with_detection_in_search_box" in exp:
        checks.append(("lsasaf_slots_with_detection_in_search_box", exp["lsasaf_slots_with_detection_in_search_box"],
                       summary["slots_with_detection_in_search_box"]))
    if "first_seviri_event_pixel_utc" in exp:
        checks.append(("first_seviri_event_pixel_utc", exp["first_seviri_event_pixel_utc"],
                       fmt(summary["rules"]["primary"]["first_detection_utc"])))
    for k, e, o in checks:
        print(f"REGRESSION {k}: expected {e}, obtained {o}, match {str(e) == str(o)}")


if __name__ == "__main__":
    main()
