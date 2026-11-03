"""Step 1 (v2): check the per-event inputs of FIRMS and LSA SAF against the shared schema v2.

Usage: python scripts/event/01_check_inputs.py --event <id>
Prints a report; writes nothing.
"""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts/lib")
from registry import event_arg, get_event, load_registry, utc  # noqa: E402

# ---------------- constants ----------------
FIRMS_FILE = "../Input Data FIRMS/events/{event}/processed/event_observations.csv"
SEVIRI_FILE = "../Input Data LSA SAF/events/{event}/processed/event_observations.csv"
SCHEMA_V2 = ["source", "sensor", "platform", "role", "obs_time_utc", "latitude", "longitude",
             "frp_mw", "confidence_raw", "confidence_class", "pixel_size_km", "pixel_area_km2",
             "day_night", "qc_flag", "static_proxy"]
EVENT_COLS = ["event_id", "in_search_box", "event_member", "event_member_sensitivity"]
SIDE_TOL_KM = 0.01          # |pixel_size_km - sqrt(pixel_area_km2)| allowed (rounding)
MARGIN_DEG = 0.5            # rows must lie inside search box + this margin


def check(name, path, event_id, ev, window):
    print(f"\n==================== {name} ({event_id}) ====================")
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    cols = list(raw.columns)
    print("columns = schema v2 + event columns (same order):", cols == SCHEMA_V2 + EVENT_COLS)
    if cols != SCHEMA_V2 + EVENT_COLS:
        print("  missing:", set(SCHEMA_V2 + EVENT_COLS) - set(cols), " extra:", set(cols) - set(SCHEMA_V2 + EVENT_COLS))
    print("all obs_time_utc end with 'Z':", raw.obs_time_utc.str.endswith("Z").all())
    print("event_id values:", raw.event_id.unique().tolist())

    df = pd.read_csv(path, dtype={"confidence_raw": str})
    df["obs_time_utc"] = pd.to_datetime(df.obs_time_utc, utc=True)
    print("rows:", len(df), "| time range:", df.obs_time_utc.min(), "to", df.obs_time_utc.max())
    out_window = ~df.obs_time_utc.between(utc(window["start_utc"]), utc(window["end_utc"]))
    print("rows outside data window:", out_window.sum())

    b = ev["search_box"]
    in_box = (df.latitude.between(b["lat_min"], b["lat_max"])
              & df.longitude.between(b["lon_min"], b["lon_max"]))
    in_margin = (df.latitude.between(b["lat_min"] - MARGIN_DEG, b["lat_max"] + MARGIN_DEG)
                 & df.longitude.between(b["lon_min"] - MARGIN_DEG, b["lon_max"] + MARGIN_DEG))
    print("in_search_box disagreements with registry box:", (in_box != df.in_search_box).sum(),
          "| rows outside box + margin:", (~in_margin).sum())

    side = np.sqrt(df.pixel_area_km2)
    print(f"pixel_size_km is a side length (|side - sqrt(area)| <= {SIDE_TOL_KM}):",
          ((df.pixel_size_km - side).abs() <= SIDE_TOL_KM).all(),
          f"| side km {df.pixel_size_km.min():.3f} to {df.pixel_size_km.max():.3f}")
    print("NaN per column:", df.isna().sum()[df.isna().sum() > 0].to_dict())
    print("duplicates (platform, time, lat, lon):",
          df.duplicated(["platform", "obs_time_utc", "latitude", "longitude"]).sum())

    for col in ["platform", "role", "qc_flag", "confidence_class", "static_proxy",
                "in_search_box", "event_member", "event_member_sensitivity"]:
        print(f"rows per {col}:", df[col].value_counts(dropna=False).to_dict())

    m = df[df.event_member]
    print(f"\nevent members: {len(m)}, {m.obs_time_utc.min()} to {m.obs_time_utc.max()}")
    print("members per platform x qc_flag:")
    print(pd.crosstab(m.platform, m.qc_flag).to_string())
    print("members per confidence_class:", m.confidence_class.value_counts().to_dict())
    if name == "FIRMS":
        n21 = m[m.platform == "NOAA-21"]
        print("NOAA-21 members static_proxy:", n21.static_proxy.value_counts(dropna=False).to_dict())
        print("members outside search box:", (~m.in_search_box).sum())
    sens_only = df.event_member_sensitivity & ~df.event_member
    print("sensitivity-only members:", sens_only.sum(),
          "| primary-only members:", (df.event_member & ~df.event_member_sensitivity).sum())
    ign = utc(ev["ignition_utc"]) - pd.Timedelta(minutes=ev["ignition_tolerance_min"])
    print(f"members before earliest accepted time ({ign}):", (m.obs_time_utc < ign).sum())
    return df


if __name__ == "__main__":
    args = event_arg("Step 1 input check")
    reg = load_registry()
    ev = get_event(args.event, reg)
    f = check("FIRMS", FIRMS_FILE.format(event=args.event), args.event, ev, reg["data_window"])
    s = check("LSA SAF", SEVIRI_FILE.format(event=args.event), args.event, ev, reg["data_window"])
    print("\ndtypes identical:", (f.dtypes == s.dtypes).all())
    diff = pd.DataFrame({"firms": f.dtypes, "seviri": s.dtypes})
    print(diff[diff.firms != diff.seviri].to_string())
