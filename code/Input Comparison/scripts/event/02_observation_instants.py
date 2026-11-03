"""Step 2/3 (v2): observation instants of one event.

FIRMS: passes per platform (consecutive detections less than overpass_window_min apart);
instant time = first detection of the pass inside the scope.
SEVIRI: one instant per 15-min slot with at least SEVIRI_MIN_PIXELS pixels in the scope;
instant time = earliest per-pixel acquisition time (ACQTIME) in the slot.

Scopes: event_member (main; SEVIRI primary rule), event_member_sensitivity (SEVIRI 2 km rule;
FIRMS identical to event_member), search_box (reported alongside, never main).
Filters (registry): qc_flag in qc_keep; rows with static_proxy True excluded; conf_modes.

Usage: python scripts/event/02_observation_instants.py --event <id>
Output: events/<id>/processed/observation_instants.csv, events/<id>/processed/filter_counts.csv
"""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts/lib")
from registry import event_arg, get_event, load_registry  # noqa: E402

# ---------------- constants ----------------
FIRMS_FILE = "../Input Data FIRMS/events/{event}/processed/event_observations.csv"
SEVIRI_FILE = "../Input Data LSA SAF/events/{event}/processed/event_observations.csv"
OUT_DIR = "events/{event}/processed"
SEVIRI_SLOT_MIN = 15
SEVIRI_MIN_PIXELS = 1
KM_PER_DEG = 111.2
SCOPES = {"event_member": "event_member",
          "event_member_sensitivity": "event_member_sensitivity",
          "search_box": "in_search_box"}
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"


def extent_km(lat, lon):
    """Diagonal of the bounding box of the detections (equirectangular, km)."""
    dy = (lat.max() - lat.min()) * KM_PER_DEG
    dx = (lon.max() - lon.min()) * KM_PER_DEG * np.cos(np.radians(lat.mean()))
    return float(np.hypot(dx, dy))


def summarise(g, **extra):
    return dict(time_utc=g.obs_time_utc.min(), time_end_utc=g.obs_time_utc.max(),
                source=g.source.iloc[0], sensor=g.sensor.iloc[0], platform=g.platform.iloc[0],
                role=g.role.iloc[0], n_pixels=len(g), total_frp_mw=g.frp_mw.sum(),
                extent_km=extent_km(g.latitude, g.longitude),
                day_night=g.day_night.iloc[0] if g.day_night.notna().any() else "", **extra)


def firms_passes(df, window_min):
    rows = []
    for _, d in df.sort_values("obs_time_utc").groupby("platform"):
        new = d.obs_time_utc.diff() > pd.Timedelta(minutes=window_min)
        for _, g in d.groupby(new.cumsum()):
            rows.append(summarise(g, slot_time_utc=pd.NaT))
    return rows


def seviri_slots(df):
    df = df.assign(slot=df.obs_time_utc.dt.floor(f"{SEVIRI_SLOT_MIN}min"))
    return [summarise(g, slot_time_utc=slot) for slot, g in df.groupby("slot")
            if len(g) >= SEVIRI_MIN_PIXELS]


def load(path):
    df = pd.read_csv(path, dtype={"confidence_raw": str, "static_proxy": str, "day_night": str})
    df["obs_time_utc"] = pd.to_datetime(df.obs_time_utc, utc=True)
    # static_proxy is text "True"/"False" or empty (FIRMS F10): map explicitly
    df["static_proxy"] = df.static_proxy.map({"True": True, "False": False})
    return df


if __name__ == "__main__":
    args = event_arg("observation instants")
    reg = load_registry()
    conv = reg["conventions"]
    obs = pd.concat([load(FIRMS_FILE.format(event=args.event)),
                     load(SEVIRI_FILE.format(event=args.event))], ignore_index=True)

    # ---- filters, counted per scope and source ----
    counts = []
    qc_ok = obs.qc_flag.isin(conv["qc_keep"])
    not_static = obs.static_proxy.ne(True)
    for scope, col in SCOPES.items():
        for src, d in obs[obs[col]].groupby("source"):
            m_qc, m_st = qc_ok[d.index], not_static[d.index]
            row = dict(scope=scope, source=src, rows=len(d),
                       removed_qc=int((~m_qc).sum()),
                       removed_static_proxy=int((m_qc & ~m_st).sum()))
            for mode, classes in conv["conf_modes"].items():
                row[f"removed_conf_{mode}"] = int((m_qc & m_st & ~d.confidence_class.isin(classes)).sum())
            counts.append(row)
    counts = pd.DataFrame(counts)
    excluded_qc = obs[obs.in_search_box & ~qc_ok].groupby(["source", "qc_flag", "platform"]).size()
    obs = obs[qc_ok & not_static]

    instants = []
    for mode, classes in conv["conf_modes"].items():
        d = obs[obs.confidence_class.isin(classes)]
        for scope, col in SCOPES.items():
            ds = d[d[col]]
            rows = (firms_passes(ds[ds.source == "FIRMS"], conv["overpass_window_min"])
                    + seviri_slots(ds[ds.source == "LSASAF"]))
            instants.append(pd.DataFrame(rows).assign(conf_mode=mode, scope=scope))
    out = pd.concat(instants, ignore_index=True).sort_values(["conf_mode", "scope", "time_utc", "platform"])
    cols = ["conf_mode", "scope", "time_utc", "time_end_utc", "slot_time_utc", "source", "sensor",
            "platform", "role", "day_night", "n_pixels", "total_frp_mw", "extent_km"]
    out_dir = OUT_DIR.format(event=args.event)
    out[cols].to_csv(f"{out_dir}/observation_instants.csv", index=False, date_format=DATE_FMT)
    counts.to_csv(f"{out_dir}/filter_counts.csv", index=False)

    # ---------------- report ----------------
    pd.set_option("display.width", 200)
    print(f"event {args.event}: {len(out)} instants written")
    print("\nfilter counts per scope and source:\n" + counts.to_string(index=False))
    print("\nexcluded by qc in search box (source, qc_flag, platform):\n" + excluded_qc.to_string())
    print("\ninstants per conf_mode, scope and platform:")
    print(out.groupby(["conf_mode", "scope", "platform"]).size().unstack(fill_value=0).to_string())
    print("\nmax pass duration (min):",
          ((out.time_end_utc - out.time_utc).dt.total_seconds() / 60)
          .groupby(out.source).max().to_dict())
