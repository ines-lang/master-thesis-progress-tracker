"""EFFIS reference table and consistency checks for one event.

Run: python scripts/event/01_effis_reference.py --event <event_id> [--records ID ...]

Writes events/<id>/processed/effis_reference.csv: one row per EFFIS record of
the event plus a TOTAL row, events/<id>/processed/effis_area_comparison.csv,
and events/<id>/notes/effis_summary.md.
Optional, for values not in the registry (printed, proposed for the registry):
--area-refs "label=ha" ..., --reported-end ISO, --neighbour-provinces P ...
EFFIS never defines a footprint, T0 or ignition; all comparisons are reported only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from firms import load_event_detections, load_event_passes  # noqa: E402
from registry import REPO_DIR, effis_record_ids, event_args, event_dir, get_event, utc  # noqa: E402

import numpy as np
import pandas as pd

# ---- parameters (script level, no event values) ----
EVENTS_FILE = REPO_DIR / "processed" / "effis_events_es.csv"
COINCIDENCE_FILE = REPO_DIR / "processed" / "effis_overpass_coincidence.csv"
LARGE_AREA_QUANTILE = 0.95     # merging flag: area above this quantile of all ES records (v1)
LONG_DURATION_DAYS = 7         # merging flag: start to last update longer than this (v1)
NEIGHBOUR_MIN_AREA_HA = 1000   # other records counted as "large fires active at the same time" (v1)
KM_PER_DEG_LAT = 111.2


def hours(td):
    return round(td.total_seconds() / 3600, 2)


def days(td):
    return round(td.total_seconds() / 86400, 2)


def nearest_event_pass(t):
    """Nearest FIRMS pass WITH event members (v2 event_overpasses.csv), by first member time."""
    if passes is None:
        return {"nearest_event_pass": None, "gap_to_nearest_event_pass_min": None}
    i = (passes["first_member_utc"] - t).abs().idxmin()
    return {"nearest_event_pass": passes.loc[i, "overpass_id"],
            "gap_to_nearest_event_pass_min": round((t - passes.loc[i, "first_member_utc"]).total_seconds() / 60, 1)}


def hull_area_km2(x, y):
    """Convex hull area (monotone chain + shoelace), unchanged from v1."""
    pts = sorted(set(zip(x, y)))

    def half(points):
        h = []
        for p in points:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h[:-1]

    hull = np.array(half(pts) + half(pts[::-1]))
    hx, hy = hull[:, 0], hull[:, 1]
    return 0.5 * abs(np.dot(hx, np.roll(hy, 1)) - np.dot(hy, np.roll(hx, 1)))


args = event_args()
reg, ev = get_event(args.event)
ids, ids_source = effis_record_ids(ev, args.records)
ignition = utc(ev["ignition_utc"])
firms_end = utc(reg["data_window"]["firms_data_end_utc"])
official = ev.get("official_area_ha")

es = pd.read_csv(EVENTS_FILE, dtype={"effis_id": str}, parse_dates=["start_date", "last_update"])
coin = pd.read_csv(COINCIDENCE_FILE, dtype={"effis_id": str})
missing = set(ids) - set(es["effis_id"])
if missing:
    raise SystemExit(f"EFFIS ids not in the delivery: {sorted(missing)}")
rec = es[es["effis_id"].isin(ids)].merge(
    coin[["effis_id", "gap_to_nearest_pass_min", "platforms_within_window", "excluded_reason"]], on="effis_id")

# ---- FIRMS event members ----
det, firms_source = load_event_detections(args.event)
mem = det[det["event_member"] & (det["obs_time_utc"] <= firms_end)]
first = mem.loc[mem["obs_time_utc"].idxmin()]
passes, passes_file = load_event_passes(args.event)
if passes is not None:
    passes["first_member_utc"] = pd.to_datetime(passes["first_member_utc"], utc=True)
    assert passes["first_member_utc"].min() == first["obs_time_utc"], "event_overpasses and members disagree"
reported_end = utc(args.reported_end) if args.reported_end else None
lat0 = mem["latitude"].mean()
x = mem["longitude"].values * KM_PER_DEG_LAT * np.cos(np.radians(lat0))
y = mem["latitude"].values * KM_PER_DEG_LAT
firms_bbox_ha = (x.max() - x.min()) * (y.max() - y.min()) * 100
firms_hull_ha = hull_area_km2(np.round(x, 3), np.round(y, 3)) * 100

# ---- per-record rows ----
area_limit = es["area_ha"].quantile(LARGE_AREA_QUANTILE)
provinces = sorted(rec["province"].unique())
neighbour_provinces = args.neighbour_provinces or provinces
rows = []
for _, r in rec.sort_values("start_date").iterrows():
    neighbours = es[~es["effis_id"].isin(ids) & es["province"].isin(neighbour_provinces)
                    & (es["area_ha"] >= NEIGHBOUR_MIN_AREA_HA)
                    & (es["start_date"] <= r["last_update"]) & (es["last_update"] >= r["start_date"])]
    rows.append({
        "effis_id": r["effis_id"], "province": r["province"], "commune": r["commune"],
        "start_utc": r["start_date"], "last_update_utc": r["last_update"],
        "duration_days": r["duration_days"], "area_ha": r["area_ha"], "map_source": r["map_source"],
        "has_geometry": r["has_geometry"],
        "start_minus_ignition_h": hours(r["start_date"] - ignition),
        "start_minus_firms_first_member_h": hours(r["start_date"] - first["obs_time_utc"]),
        "gap_to_nearest_firms_pass_min": r["gap_to_nearest_pass_min"],
        "platforms_within_window": r["platforms_within_window"],
        **nearest_event_pass(r["start_date"]),
        "coincidence_excluded_reason": r["excluded_reason"],
        "last_update_minus_firms_end_d": round((r["last_update"] - firms_end).total_seconds() / 86400, 2),
        "last_update_minus_reported_end_d": days(r["last_update"] - reported_end) if reported_end else None,
        "area_rank_es": int((es["area_ha"] > r["area_ha"]).sum()) + 1,
        "flag_large_area": bool(r["area_ha"] > area_limit),
        "flag_long_duration": bool(r["duration_days"] > LONG_DURATION_DAYS),
        "n_large_fires_same_provinces_same_time": len(neighbours),
        "large_fires_same_provinces_same_time": "; ".join(
            f"{n.effis_id} {n.commune} {n.area_ha} ha" for n in neighbours.itertuples()),
    })
ref = pd.DataFrame(rows)

total = {
    "effis_id": "TOTAL", "province": "/".join(provinces), "commune": f"{len(ref)} record(s)",
    "start_utc": ref["start_utc"].min(), "last_update_utc": ref["last_update_utc"].max(),
    "area_ha": int(ref["area_ha"].sum()),
    "start_minus_ignition_h": hours(ref["start_utc"].min() - ignition),
    "start_minus_firms_first_member_h": hours(ref["start_utc"].min() - first["obs_time_utc"]),
    "last_update_minus_firms_end_d": round((ref["last_update_utc"].max() - firms_end).total_seconds() / 86400, 2),
    "last_update_minus_reported_end_d": days(ref["last_update_utc"].max() - reported_end) if reported_end else None,
    "official_area_ha": official,
    "area_ratio_effis_to_official": round(ref["area_ha"].sum() / official, 3) if official else None,
    "firms_member_bbox_ha": round(firms_bbox_ha), "firms_member_hull_ha": round(firms_hull_ha),
    "area_ratio_firms_hull_to_effis": round(firms_hull_ha / ref["area_ha"].sum(), 3),
}
ref = pd.concat([ref, pd.DataFrame([total])], ignore_index=True)
ref["record_set_source"] = ids_source
ref["firms_source"] = firms_source
out_file = event_dir(args.event, "processed") / "effis_reference.csv"
ref.to_csv(out_file, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

# ---- report ----
pd.set_option("display.width", 200)
print(f"event {args.event}: records {ids} ({ids_source})")
print(f"FIRMS members: {len(mem)} ({firms_source})")
print(f"  first member {first['obs_time_utc']:%Y-%m-%dT%H:%MZ} ({first['platform']}), "
      f"last {mem['obs_time_utc'].max():%Y-%m-%dT%H:%MZ}")
print(f"ignition {ignition:%Y-%m-%dT%H:%MZ} (tolerance {ev['ignition_tolerance_min']} min); "
      f"first member minus ignition {hours(first['obs_time_utc'] - ignition)} h")
print(ref.drop(columns=["record_set_source", "firms_source"]).T.to_string())
print(f"\nmerging flag thresholds: area > {area_limit:,.0f} ha ({LARGE_AREA_QUANTILE:.0%} quantile), "
      f"duration > {LONG_DURATION_DAYS} d, neighbours >= {NEIGHBOUR_MIN_AREA_HA} ha in {neighbour_provinces}")
print(f"written {out_file.relative_to(REPO_DIR)}")

# ---- area comparison (rough: different methods and times) ----
effis_total = int(ref.iloc[-1]["area_ha"])
areas = [("EFFIS records (sum)", effis_total, "EFFIS burnt area, final record state")]
if official:
    areas.append((f"official ({ev.get('official_area_source', 'registry')})", official, "registry official_area_ha"))
for item in args.area_refs:
    label, value = item.split("=")
    areas.append((label, float(value), "command line --area-refs (not in registry)"))
areas += [("FIRMS members convex hull", round(firms_hull_ha), f"until {firms_end:%Y-%m-%dT%H:%MZ}"),
          ("FIRMS members bounding box", round(firms_bbox_ha), f"until {firms_end:%Y-%m-%dT%H:%MZ}")]
area_cmp = pd.DataFrame(areas, columns=["source", "area_ha", "basis"])
area_cmp["ratio_effis_to_source"] = (effis_total / area_cmp["area_ha"]).round(3)
area_cmp.to_csv(event_dir(args.event, "processed") / "effis_area_comparison.csv", index=False)
print("\narea comparison:")
print(area_cmp.to_string(index=False))
print(f"\nreported end of activity: {reported_end if reported_end else 'not given'}; "
      f"known_context: {ev.get('known_context', [])}")
if passes is not None:
    print(f"FIRMS event passes: {len(passes)} ({passes_file.name}); first member {passes['first_member_utc'].min()}")

# ---- short event note (numbers from this run only) ----
t = ref.iloc[-1]
note = f"""# EFFIS summary: {ev['name']}

Generated by `scripts/event/01_effis_reference.py --event {args.event}`. All numbers come from `effis_reference.csv`.

- Records: {', '.join(ids)} ({ids_source}). No geometry; map_source {', '.join(rec['map_source'].unique())}.
- Start {t['start_utc']:%Y-%m-%dT%H:%MZ}, last update {t['last_update_utc']:%Y-%m-%dT%H:%MZ}, area {t['area_ha']:,} ha.
- Start minus ignition ({ignition:%Y-%m-%dT%H:%MZ}): {t['start_minus_ignition_h']} h. Start minus first FIRMS member ({first['obs_time_utc']:%Y-%m-%dT%H:%MZ}, {first['platform']}): {t['start_minus_firms_first_member_h']} h.
- Last update minus FIRMS data end: {t['last_update_minus_firms_end_d']} d.
- Area: official {official if official else 'not set in registry'} ha, ratio EFFIS/official {t['area_ratio_effis_to_official']}; FIRMS member hull {t['firms_member_hull_ha']:,} ha, bbox {t['firms_member_bbox_ha']:,} ha (until the FIRMS data end, rough only).
- FIRMS members: {firms_source}.
- Caveat: EFFIS start dates coincide with FIRMS passes (see `processed/effis_overpass_coincidence.csv`), so the start-date comparison is circular. Start date and last update are not ignition and extinction.
"""
(event_dir(args.event, "notes") / "effis_summary.md").write_text(note)
