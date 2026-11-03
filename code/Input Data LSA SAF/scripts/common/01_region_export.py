#!/usr/bin/env python3
"""
v2 Step 1: event-agnostic export of LSA SAF FRP-PIXEL detections for one region (v3: any region).

Input: the full-disk conversion lsasaf_frp_pixels_20250808_20250816.csv
(raw / SCALING_FACTOR, verified in v1). No re-download.
Outputs:
  processed/<region_id>/observations_standard.csv   schema v2, region box
  processed/<region_id>/lsasaf_pixels.csv           same rows plus SEVIRI extras (slot time, grid position,
                                        viewing zenith angle, FRP uncertainty) for the event scripts

Run from the "Input Data LSA SAF" folder:
    python scripts/common/01_region_export.py --region <region_id>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.registry import REPO, in_box, iso_z, load_registry, region_arg, region_dir, utc  # noqa: E402
from lib.schema import SCHEMA_V2, check_and_write                  # noqa: E402

# ---------------- constants ----------------
IN_CSV = REPO / "lsasaf_frp_pixels_20250808_20250816.csv"
SLOT_MIN = 15
STATIC_FRACTION = 0.5          # v1 rule: same SEVIRI pixel in more than this share of all slots
CONF_LOW_MAX = 0.5             # < 0.5 low
CONF_NOMINAL_MAX = 0.8         # 0.5 to < 0.8 nominal, >= 0.8 high
# -------------------------------------------

USECOLS = ["slot_time_utc", "acqtime", "abs_line", "abs_pixel", "latitude", "longitude", "frp",
           "frp_uncertainty", "fire_confidence", "pixel_size", "pixel_vza", "source_file"]


def main():
    reg = load_registry()
    start, end = utc(reg["data_window"]["start_utc"]), utc(reg["data_window"]["end_utc"])
    region_id, region = region_arg(reg)
    out_standard = region_dir(region_id) / "observations_standard.csv"
    out_extended = region_dir(region_id) / "lsasaf_pixels.csv"

    df = pd.read_csv(IN_CSV, usecols=USECOLS, parse_dates=["slot_time_utc"],
                     dtype={"fire_confidence": str})
    if "acqtime" not in df or df.acqtime.isna().any():
        raise SystemExit("ACQTIME missing in the full-disk CSV: stop.")
    log = [("input rows (864 files, full MSG disk)", len(df))]

    conf = df.fire_confidence.astype(float)
    valid = (df.frp > 0) & df.latitude.between(-90, 90) & df.longitude.between(-180, 180) & conf.notna()
    df = df[valid.fillna(False)]
    log.append(("after dropping missing / non-positive FRP, invalid coordinates or confidence", len(df)))

    df = df[df.slot_time_utc.between(start, end) & in_box(df.latitude, df.longitude, region["box"])]
    log.append((f"after crop to data window and region box ({region_id})", len(df)))

    df = df.drop_duplicates(subset=["slot_time_utc", "abs_line", "abs_pixel"])
    log.append(("after removing duplicates (same slot, same SEVIRI pixel)", len(df)))

    # acquisition time = slot date + ACQTIME (HHMM, UTC); roll over a day if it wraps past midnight
    acq = df.acqtime.astype(int)
    obs = df.slot_time_utc.dt.normalize() + pd.to_timedelta(acq // 100 * 60 + acq % 100, unit="min")
    wrapped = obs < df.slot_time_utc
    obs[wrapped] += pd.Timedelta(days=1)

    # static: same SEVIRI pixel in more than STATIC_FRACTION of all slots of the window
    n_slots = len(pd.date_range(start, end, freq=f"{SLOT_MIN}min"))
    slots_per_pixel = df.groupby(["abs_line", "abs_pixel"]).slot_time_utc.transform("nunique")
    static = slots_per_pixel / n_slots > STATIC_FRACTION

    conf = df.fire_confidence.astype(float)
    std = pd.DataFrame({
        "source": "LSASAF", "sensor": "SEVIRI", "platform": "MSG", "role": "context",
        "obs_time_utc": iso_z(obs),
        "latitude": df.latitude, "longitude": df.longitude,
        "frp_mw": df.frp,
        "confidence_raw": df.fire_confidence,
        "confidence_class": np.select([conf < CONF_LOW_MAX, conf < CONF_NOMINAL_MAX], ["low", "nominal"], "high"),
        "pixel_size_km": np.sqrt(df.pixel_size).round(3),
        "pixel_area_km2": df.pixel_size,
        "day_night": "",
        "qc_flag": np.where(static, "static", "ok"),
        "static_proxy": "",
    })[SCHEMA_V2]
    order = np.lexsort((df.abs_pixel.values, df.abs_line.values, obs.values))
    std = std.iloc[order]
    check_and_write(std, out_standard, SCHEMA_V2)

    ext = std.copy()
    ext["slot_time_utc"] = iso_z(df.slot_time_utc).iloc[order].values
    ext["acq_minus_slot_min"] = ((obs - df.slot_time_utc).dt.total_seconds() / 60).iloc[order].values
    for col, src in [("abs_line", "abs_line"), ("abs_pixel", "abs_pixel"), ("pixel_vza_deg", "pixel_vza"),
                     ("frp_uncertainty_mw", "frp_uncertainty"), ("source_file", "source_file")]:
        ext[col] = df[src].iloc[order].values
    ext["abs_line"] = ext.abs_line.astype(int)
    ext["abs_pixel"] = ext.abs_pixel.astype(int)
    ext.to_csv(out_extended, index=False)

    # ---- report ----
    print("Row counts:")
    for step, n in log:
        print(f"  {n:8d}  {step}")
    print(f"\nACQTIME minus slot (min): {ext.acq_minus_slot_min.value_counts().sort_index().to_dict()}, "
          f"wrapped past midnight: {int(wrapped.sum())}")
    print(f"obs_time_utc range: {std.obs_time_utc.min()} to {std.obs_time_utc.max()}")
    print(f"Distinct SEVIRI pixels: {df.groupby(['abs_line', 'abs_pixel']).ngroups}, "
          f"max slots for one pixel: {slots_per_pixel.max()} of {n_slots} ({slots_per_pixel.max() / n_slots:.1%})")
    print(f"qc_flag: {std.qc_flag.value_counts().to_dict()}")
    if static.any():
        s = (df[static].groupby(["abs_line", "abs_pixel"])
             .agg(lat=("latitude", "mean"), lon=("longitude", "mean"), slots=("slot_time_utc", "nunique")))
        print("Static pixels:\n" + s.to_string())
    top = (df.assign(n=slots_per_pixel).groupby(["abs_line", "abs_pixel"])
           .agg(lat=("latitude", "mean"), lon=("longitude", "mean"), slots=("n", "first"))
           .sort_values("slots", ascending=False).head(5))
    top["share"] = (top.slots / n_slots).round(3)
    print("Most persistent pixels:\n" + top.to_string())
    print(f"confidence_class: {(std.confidence_class.value_counts(normalize=True) * 100).round(1).to_dict()} %")
    print(f"pixel_size_km: {std.pixel_size_km.min()} to {std.pixel_size_km.max()}")
    print(f"\nWrote {out_standard.relative_to(REPO)} ({len(std)} rows) and {out_extended.relative_to(REPO)}")


if __name__ == "__main__":
    main()
