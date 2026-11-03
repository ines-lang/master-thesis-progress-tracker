"""Step 4 (v2): cross-event analysis.

1. summary table, 2. common-horizon gap statistics, 3. baseline gaps by UTC start hour,
4. alert latency decomposition. Reads the per-event outputs of scripts/event/.

Usage: python scripts/cross/01_cross_event.py
Outputs in cross_event/processed/: summary_table.csv, common_horizon_gaps.csv,
baseline_gaps_by_hour.csv, instants_by_hour.csv, latency_decomposition.csv
"""

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts/lib")
from gaps import distinct_times, gap_stats, gaps_h  # noqa: E402
from registry import load_registry, utc  # noqa: E402

# ---------------- constants ----------------
EVENT_DIR = "events/{event}/processed"
OUT_DIR = "cross_event/processed"
SENSING_LAYER = "../Input Data FIRMS/events/{event}/processed/overpass_times_sensing_layer.csv"
REGION_PASSES = "../Input Data FIRMS/processed/{region}/overpasses.csv"   # context only, any detection in the region
LSASAF_SUMMARY = "../Input Data LSA SAF/events/{event}/processed/seviri_event_summary.json"
MODE = "all"                 # both conf modes give the same baseline numbers (Steps 2 and 3)
LONG_GAP_H = 6.0             # "worst gap" threshold for the diurnal test
BASELINE = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"]
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"
H = 3600.0


def hours(dt):
    return np.nan if pd.isna(dt) else dt.total_seconds() / H


def load_event(eid):
    d = EVENT_DIR.format(event=eid)
    inst = pd.read_csv(f"{d}/observation_instants.csv", parse_dates=["time_utc", "time_end_utc", "slot_time_utc"])
    t0s = pd.read_csv(f"{d}/t0_summary.csv", parse_dates=["t0_utc", "t_end_utc", "seviri_primary_first_utc",
                                                          "seviri_primary_robust_onset_utc", "effis_start_utc"])
    gaps = pd.read_csv(f"{d}/gap_statistics.csv", parse_dates=["longest_gap_start_utc", "longest_gap_end_utc"])
    inst = inst[(inst.conf_mode == MODE) & (inst.scope == "event_member")]
    return inst, t0s[t0s.conf_mode == MODE].iloc[0], gaps[(gaps.conf_mode == MODE) & gaps.main]


def main():
    reg = load_registry()
    events = list(reg["events"])
    data = {e: load_event(e) for e in events}
    horizon = min(r.t_end_utc - r.t0_utc for _, r, _ in data.values())   # exact Timedelta
    horizon_h = hours(horizon)

    summary, horizon_rows, gap_hour_rows, inst_hour_rows, latency_rows = [], [], [], [], []
    for eid in events:
        ev = reg["events"][eid]
        inst, r, g = data[eid]
        ign = utc(ev["ignition_utc"])
        base = inst[inst.role == "baseline"]
        sev = inst[inst.source == "LSASAF"]
        gc = g[g.group == "c"].iloc[0]
        ge = g[g.group == "e"].iloc[0]
        ga = g[g.group == "a"].iloc[0]
        t_h = r.t0_utc + horizon
        hc, he = gap_stats(base.time_utc, r.t0_utc, t_h), gap_stats(pd.concat([base.time_utc, sev.time_utc]), r.t0_utc, t_h)
        ls = json.load(open(LSASAF_SUMMARY.format(event=eid)))["rules"]["primary"]["blackouts"]
        in_win = [b for b in ls if utc(b["start_slot_utc"]) < r.t_end_utc and utc(b["end_slot_utc"]) > r.t0_utc]
        bmax = max(in_win, key=lambda b: b["hours"]) if in_win else None
        summary.append({
            "event_id": eid, "ignition_utc": ign, "ignition_hour_utc": ign.hour + ign.minute / 60,
            "ignition_tolerance_min": ev["ignition_tolerance_min"],
            "t0_utc": r.t0_utc, "t0_platform": r.t0_platform, "ignition_to_t0_h": r.t0_minus_ignition_h,
            "ignition_to_first_seviri_h": r.seviri_primary_first_minus_ignition_h,
            "ignition_to_seviri_robust_onset_h": r.seviri_primary_robust_onset_minus_ignition_h,
            "first_seviri_minus_t0_h": r.seviri_primary_first_minus_t0_h,
            "effis_start_minus_t0_h": r.effis_start_minus_t0_h,
            "t_end_utc": r.t_end_utc, "observable_window_h": r.observable_window_h,
            "passes_with_event": r.passes_with_event, "firms_event_detections": r.firms_event_detections,
            "baseline_instants": gc.n_instants, "seviri_instants": ga.n_instants,
            "baseline_median_h": gc.median_gap_h, "baseline_p90_h": gc.p90_gap_h, "baseline_max_h": gc.max_gap_h,
            "baseline_longest_gap_start_utc": gc.longest_gap_start_utc,
            "baseline_longest_gap_end_utc": gc.longest_gap_end_utc,
            "all_public_median_h": ge.median_gap_h, "all_public_p90_h": ge.p90_gap_h, "all_public_max_h": ge.max_gap_h,
            "all_public_longest_gap_start_utc": ge.longest_gap_start_utc,
            "all_public_longest_gap_end_utc": ge.longest_gap_end_utc,
            "seviri_longest_gap_h": ga.max_gap_h, "seviri_longest_gap_start_utc": ga.longest_gap_start_utc,
            "seviri_longest_blackout_slots_h": bmax["hours"] if bmax else np.nan,
            "seviri_longest_blackout_start_slot_utc": bmax["start_slot_utc"] if bmax else None,
            "horizon_h": horizon_h,
            "horizon_baseline_median_h": hc["median_gap_h"], "horizon_baseline_p90_h": hc["p90_gap_h"],
            "horizon_baseline_max_h": hc["max_gap_h"], "horizon_baseline_instants": hc["n_instants"],
            "horizon_all_public_median_h": he["median_gap_h"], "horizon_all_public_p90_h": he["p90_gap_h"],
            "horizon_all_public_max_h": he["max_gap_h"],
            "official_area_ha": ev.get("official_area_ha"), "effis_area_ha": r.effis_area_ha,
        })

        # 2. common horizon, every group
        groups = {"a SEVIRI only": sev.time_utc, "c baseline combined": base.time_utc,
                  "e baseline + SEVIRI": pd.concat([base.time_utc, sev.time_utc])}
        groups.update({f"b {p}": base.time_utc[base.platform == p] for p in BASELINE})
        for win, end in [("full", r.t_end_utc), ("common_horizon", t_h)]:
            for name, t in groups.items():
                horizon_rows.append(dict(event_id=eid, window=win, window_end_utc=end, group=name,
                                         **gap_stats(t, r.t0_utc, end)))

        # 3. baseline gaps by UTC start hour; instants by hour
        gh, starts = gaps_h(base.time_utc, r.t0_utc, r.t_end_utc)
        ends = distinct_times(base.time_utc, r.t0_utc, r.t_end_utc)[1:]
        for s, e, h in zip(starts, ends, gh):
            gap_hour_rows.append(dict(event_id=eid, gap_start_utc=s, gap_end_utc=e, gap_h=h,
                                      start_hour_utc=s.hour + s.minute / 60, end_hour_utc=e.hour + e.minute / 60,
                                      hours_since_t0=hours(s - r.t0_utc), long_gap=h >= LONG_GAP_H,
                                      in_common_horizon=s < t_h))
        for _, x in inst[inst.time_utc >= r.t0_utc].iterrows():
            inst_hour_rows.append(dict(event_id=eid, time_utc=x.time_utc, platform=x.platform, role=x.role,
                                       hour_utc=x.time_utc.hour + x.time_utc.minute / 60))

        # 4. alert latency decomposition
        sl = pd.read_csv(SENSING_LAYER.format(event=eid), parse_dates=["overpass_start_utc"])
        after = sl[sl.overpass_start_utc >= ign].sort_values("overpass_start_utc")
        nxt = after.iloc[0]
        miss = after[(after.overpass_start_utc < r.t0_utc) & ~after.event_detected.astype(str).eq("True")]
        ib = pd.read_csv(REGION_PASSES.format(region=ev["region"]), parse_dates=["start_time_utc"])
        ib = ib[(ib.start_time_utc >= ign) & (ib.start_time_utc <= r.t0_utc) & ib.platform.isin(BASELINE)]
        latency_rows.append(dict(
            event_id=eid, ignition_utc=ign, t0_utc=r.t0_utc, ignition_to_t0_h=r.t0_minus_ignition_h,
            next_listed_pass_id=nxt.overpass_id, next_listed_pass_start_utc=nxt.overpass_start_utc,
            next_listed_pass_detected_event=nxt.event_detected,
            waiting_for_pass_h=hours(nxt.overpass_start_utc - ign),
            pass_to_t0_h=hours(r.t0_utc - nxt.overpass_start_utc),
            listed_passes_without_event_before_t0=len(miss),
            listed_passes_without_event_ids=", ".join(miss.overpass_id),
            region_baseline_passes_ignition_to_t0=len(ib),
            region_baseline_passes_ids=", ".join(ib.overpass_id)))

    out = {"summary_table": pd.DataFrame(summary), "common_horizon_gaps": pd.DataFrame(horizon_rows),
           "baseline_gaps_by_hour": pd.DataFrame(gap_hour_rows), "instants_by_hour": pd.DataFrame(inst_hour_rows),
           "latency_decomposition": pd.DataFrame(latency_rows)}
    for name, df in out.items():
        df.to_csv(f"{OUT_DIR}/{name}.csv", index=False, date_format=DATE_FMT, float_format="%.4f")

    # ---------------- report ----------------
    pd.set_option("display.width", 250, "display.max_colwidth", 60)
    print(f"common horizon H = {horizon_h:.2f} h\n")
    print(out["summary_table"].set_index("event_id").T.to_string())
    ch = out["common_horizon_gaps"]
    print("\n" + ch.pivot_table(index="group", columns=["event_id", "window"],
                               values=["median_gap_h", "p90_gap_h", "max_gap_h"]).round(2).to_string())
    gh = out["baseline_gaps_by_hour"]
    print("\nbaseline gaps >= %.0f h:" % LONG_GAP_H)
    print(gh[gh.long_gap][["event_id", "gap_start_utc", "gap_end_utc", "gap_h", "start_hour_utc",
                           "end_hour_utc", "in_common_horizon"]].round(2).to_string(index=False))
    print("\n" + out["latency_decomposition"].T.to_string())


if __name__ == "__main__":
    main()
