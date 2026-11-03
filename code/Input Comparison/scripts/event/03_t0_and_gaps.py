"""Step 2/3 (v2): T0, update gaps and regression check of one event.

T0 (registry): first polar baseline event-member instant at or after ignition - tolerance.
T_END: last baseline event-member instant. Gaps between consecutive distinct instant times in
[T0, T_END] (window "full"); also up to `firms_active_end_utc` if the registry has it (window "active").

Usage: python scripts/event/03_t0_and_gaps.py --event <id>
Outputs: events/<id>/processed/t0_summary.csv, gap_statistics.csv, regression_check.csv
"""

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts/lib")
from gaps import gap_stats, gaps_h, robust_onset  # noqa: E402
from registry import event_arg, get_event, load_registry, utc  # noqa: E402

# ---------------- constants ----------------
EVENT_DIR = "events/{event}/processed"
EFFIS_FILE = "../Input Data EFFIS/events/{event}/processed/effis_reference.csv"
FIRMS_SUMMARY = "../Input Data FIRMS/events/{event}/processed/event_summary.json"
LSASAF_SUMMARY = "../Input Data LSA SAF/events/{event}/processed/seviri_event_summary.json"
BASELINE_PLATFORMS = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"]
SEVIRI_SCOPE = {"event_member": "primary", "event_member_sensitivity": "sensitivity"}
REGRESSION_CONF_MODE = "all"
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"
H = 3600.0


def hours(dt):
    return np.nan if pd.isna(dt) else dt.total_seconds() / H


def gap_groups(d):
    base, sev = d.role == "baseline", d.source == "LSASAF"
    g = {("a", "SEVIRI only"): sev}
    for p in BASELINE_PLATFORMS:
        g[("b", p)] = d.platform == p
    g[("c", "baseline combined")] = base
    g[("d", "baseline + Landsat")] = base | (d.role == "supplementary")
    g[("e", "baseline + SEVIRI")] = base | sev
    return g


def main():
    args = event_arg("T0 and gaps")
    reg = load_registry()
    ev = get_event(args.event, reg)
    conv = reg["conventions"]
    out_dir = EVENT_DIR.format(event=args.event)
    inst = pd.read_csv(f"{out_dir}/observation_instants.csv",
                       parse_dates=["time_utc", "time_end_utc", "slot_time_utc"])
    ignition = utc(ev["ignition_utc"])
    earliest = ignition - pd.Timedelta(minutes=ev["ignition_tolerance_min"])
    active_end = utc(ev.get("firms_active_end_utc"))
    effis = pd.read_csv(EFFIS_FILE.format(event=args.event))
    effis = effis[effis.effis_id.astype(str) != "TOTAL"]

    t0_rows, gap_rows, window_of = [], [], {}
    for mode in conv["conf_modes"]:
        d = inst[inst.conf_mode == mode]
        mem = d[d.scope == "event_member"]
        base = mem[(mem.role == "baseline") & (mem.time_utc >= earliest)]
        t0 = base.time_utc.min()
        t0_platforms = sorted(base[base.time_utc == t0].platform)
        t_end = base.time_utc.max()
        window_of[mode] = (t0, t_end)
        row = dict(conf_mode=mode, ignition_utc=ignition,
                   ignition_tolerance_min=ev["ignition_tolerance_min"], earliest_accepted_utc=earliest,
                   t0_utc=t0, t0_platform=", ".join(t0_platforms), t0_tie=len(t0_platforms) > 1,
                   t0_minus_ignition_h=hours(t0 - ignition), t0_before_ignition=t0 < ignition,
                   t_end_utc=t_end, observable_window_h=hours(t_end - t0),
                   firms_active_end_utc=active_end,
                   passes_with_event=len(base),
                   firms_event_detections=int(mem[mem.source == "FIRMS"].n_pixels.sum()))
        for scope, rule in SEVIRI_SCOPE.items():
            s = d[(d.scope == scope) & (d.source == "LSASAF") & (d.time_utc >= earliest)]
            slot, onset = robust_onset(s.slot_time_utc, s.time_utc)
            g, starts = gaps_h(s.time_utc, t0, t_end)
            row.update({f"seviri_{rule}_first_utc": s.time_utc.min(),
                        f"seviri_{rule}_first_minus_t0_h": hours(s.time_utc.min() - t0),
                        f"seviri_{rule}_first_minus_ignition_h": hours(s.time_utc.min() - ignition),
                        f"seviri_{rule}_robust_onset_utc": onset,
                        f"seviri_{rule}_robust_onset_minus_ignition_h": hours(onset - ignition),
                        f"seviri_{rule}_slots_with_member": len(s)})
        box = d[(d.scope == "search_box") & (d.source == "LSASAF")]
        row["seviri_slots_with_detection_in_search_box"] = len(box)
        landsat = mem[mem.role == "supplementary"]
        row["n_landsat_instants"] = len(landsat)
        e = effis.iloc[0] if len(effis) else None
        row.update(effis_ids=", ".join(effis.effis_id.astype(str)),
                   effis_start_utc=utc(e.start_utc) if e is not None else pd.NaT,
                   effis_start_minus_t0_h=hours(utc(e.start_utc) - t0) if e is not None else np.nan,
                   effis_start_minus_ignition_h=hours(utc(e.start_utc) - ignition) if e is not None else np.nan,
                   effis_last_update_utc=utc(e.last_update_utc) if e is not None else pd.NaT,
                   effis_last_update_minus_t_end_h=hours(utc(e.last_update_utc) - t_end) if e is not None else np.nan,
                   effis_area_ha=effis.area_ha.sum(), official_area_ha=ev.get("official_area_ha"))
        t0_rows.append(row)

        windows = {"full": (t0, t_end)}
        if active_end is not None:
            windows["active"] = (t0, min(active_end, t_end))
        for scope in ["event_member", "event_member_sensitivity", "search_box"]:
            ds = d[d.scope == scope]
            for wname, (w0, w1) in windows.items():
                for (gid, name), mask in gap_groups(ds).items():
                    if scope == "event_member_sensitivity" and gid not in ("a", "e"):
                        continue          # FIRMS is identical to event_member
                    gap_rows.append(dict(conf_mode=mode, scope=scope, window=wname,
                                         main=(scope == conv["main_scope"]) and wname == "full",
                                         group=gid, name=name, window_start_utc=w0, window_end_utc=w1,
                                         **gap_stats(ds.time_utc[mask], w0, w1)))

    t0s, gaps = pd.DataFrame(t0_rows), pd.DataFrame(gap_rows)
    t0s.to_csv(f"{out_dir}/t0_summary.csv", index=False, date_format=DATE_FMT, float_format="%.4f")
    gaps.to_csv(f"{out_dir}/gap_statistics.csv", index=False, date_format=DATE_FMT, float_format="%.4f")

    # ---- regression check against registry and upstream summaries ----
    r = t0s[t0s.conf_mode == REGRESSION_CONF_MODE].iloc[0]
    c = gaps[(gaps.conf_mode == REGRESSION_CONF_MODE) & gaps.main & (gaps.group == "c")].iloc[0]
    obtained = {"firms_event_detections": r.firms_event_detections,
                "t0_utc": r.t0_utc.strftime(DATE_FMT), "t0_platform": r.t0_platform,
                "firms_overpasses_with_event": r.passes_with_event,
                "baseline_gap_median_h": round(c.median_gap_h, 2),
                "baseline_gap_p90_h": round(c.p90_gap_h, 2), "baseline_gap_max_h": round(c.max_gap_h, 2),
                "first_seviri_event_pixel_utc": r.seviri_primary_first_utc.strftime(DATE_FMT),
                "effis_start_utc": r.effis_start_utc.strftime(DATE_FMT) if pd.notna(r.effis_start_utc) else None,
                "lsasaf_slots_with_detection_in_search_box": r.seviri_slots_with_detection_in_search_box}
    fs = json.load(open(FIRMS_SUMMARY.format(event=args.event)))
    ls = json.load(open(LSASAF_SUMMARY.format(event=args.event)))["rules"]
    upstream = {"firms_event_detections": fs["firms_event_detections"], "t0_utc": fs["t0_utc"],
                "t0_platform": fs["t0_platform"], "firms_overpasses_with_event": fs["firms_overpasses_with_event"],
                "baseline_gap_median_h": fs["baseline_gap_median_h"], "baseline_gap_p90_h": fs["baseline_gap_p90_h"],
                "baseline_gap_max_h": fs["baseline_gap_max_h"],
                "first_seviri_event_pixel_utc": ls["primary"]["first_detection_utc"],
                "seviri_robust_onset_primary_utc": ls["primary"]["robust_onset_utc"],
                "seviri_robust_onset_sensitivity_utc": ls["sensitivity"]["robust_onset_utc"],
                "seviri_slots_with_member_primary": ls["primary"]["slots_with_member"],
                "seviri_slots_with_member_sensitivity": ls["sensitivity"]["slots_with_member"]}
    obtained.update({"seviri_robust_onset_primary_utc": r.seviri_primary_robust_onset_utc.strftime(DATE_FMT),
                     "seviri_robust_onset_sensitivity_utc": r.seviri_sensitivity_robust_onset_utc.strftime(DATE_FMT),
                     "seviri_slots_with_member_primary": r.seviri_primary_slots_with_member,
                     "seviri_slots_with_member_sensitivity": r.seviri_sensitivity_slots_with_member})
    expected = ev.get("regression_expected", {}) or {}
    reg_rows = []
    for k, v in obtained.items():
        for src, ref in [("registry", expected), ("upstream", upstream)]:
            if k in ref:
                reg_rows.append(dict(key=k, reference=src, expected=ref[k], obtained=v,
                                     match=str(ref[k]) == str(v) or (isinstance(v, float) and
                                                                     abs(float(ref[k]) - v) < 0.005)))
    regc = pd.DataFrame(reg_rows)
    regc.to_csv(f"{out_dir}/regression_check.csv", index=False)

    pd.set_option("display.width", 250)
    print(t0s.T.to_string())
    show = ["conf_mode", "scope", "window", "main", "group", "name", "n_instants", "median_gap_h",
            "mean_gap_h", "p90_gap_h", "max_gap_h", "longest_gap_start_utc", "longest_gap_end_utc"]
    print(gaps[gaps.conf_mode == REGRESSION_CONF_MODE][show].round(2).to_string(index=False))
    num = ["n_instants", "median_gap_h", "p90_gap_h", "max_gap_h"]
    per_mode = [g[num].round(4).reset_index(drop=True) for _, g in gaps.groupby("conf_mode")]
    print("\nconf modes identical (gap numbers):", all(per_mode[0].equals(x) for x in per_mode[1:]))
    print("\nregression check:\n" + regc.to_string(index=False))
    c_all = inst[(inst.conf_mode == REGRESSION_CONF_MODE) & (inst.scope == "event_member") & (inst.role == "baseline")]
    g, _ = gaps_h(c_all.time_utc, *window_of[REGRESSION_CONF_MODE])
    print("\nmain baseline gaps (h), sorted:", np.round(np.sort(g), 2).tolist())


if __name__ == "__main__":
    main()
