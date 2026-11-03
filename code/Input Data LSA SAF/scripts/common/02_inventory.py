#!/usr/bin/env python3
"""
Step 2: inventory of the raw LSA SAF FRP-PIXEL ListProduct files.
Checks files per day, missing 15-min slots, unreadable and empty files,
and draws figures/<region_id>/01_data_availability.png.

v2: same logic as v1, period and region box read from events_registry.yaml.

Run from the "Input Data LSA SAF" folder:
    python scripts/common/02_inventory.py --region <region_id>
"""
import re
import sys
from datetime import datetime
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.registry import REPO, load_registry, region_arg, region_dir, utc  # noqa: E402

# ---------------- parameters ----------------
RAW_DIR = REPO / "lsasaf_frp_raw"
FILE_PATTERN = "ListProduct"
SLOT_MIN = 15
DPI = 300
# --------------------------------------------

TS_RE = re.compile(r"(20\d{10})")
_REG = load_registry()
PERIOD_START = utc(_REG["data_window"]["start_utc"])
PERIOD_END = utc(_REG["data_window"]["end_utc"])


def read_counts(path, b):
    """Return (n_pixels_disk, n_pixels_region) for region box b, or raise if unreadable."""
    with h5py.File(path, "r") as h:
        lat = h["LATITUDE"][()] / h["LATITUDE"].attrs["SCALING_FACTOR"]
        lon = h["LONGITUDE"][()] / h["LONGITUDE"].attrs["SCALING_FACTOR"]
    in_ib = (lat >= b["lat_min"]) & (lat <= b["lat_max"]) & (lon >= b["lon_min"]) & (lon <= b["lon_max"])
    return len(lat), int(in_ib.sum())


def main():
    region_id, region = region_arg(_REG)
    out_table = region_dir(region_id) / "inventory.csv"
    out_fig = REPO / "figures" / region_id / "01_data_availability.png"
    slots = pd.date_range(PERIOD_START, PERIOD_END, freq=f"{SLOT_MIN}min")
    files = {}
    for p in sorted(RAW_DIR.glob(f"*{FILE_PATTERN}*")):
        m = TS_RE.search(p.name)
        if m:
            files[pd.Timestamp(datetime.strptime(m.group(1), "%Y%m%d%H%M"))] = p

    rows = []
    for t in slots:
        p = files.get(t)
        row = dict(slot_time_utc=t, file=p.name if p else "", status="missing",
                   size_bytes=np.nan, n_pixels_disk=np.nan, n_pixels_region=np.nan)
        if p:
            row["size_bytes"] = p.stat().st_size
            try:
                n_disk, n_ib = read_counts(p, region["box"])
                row.update(n_pixels_disk=n_disk, n_pixels_region=n_ib,
                           status="ok" if n_disk > 0 else "empty")
            except Exception as e:
                row["status"] = f"unreadable: {e}"
        rows.append(row)
    inv = pd.DataFrame(rows)
    extra = sorted(set(files) - set(slots))

    inv.to_csv(out_table, index=False)

    # ---- console summary ----
    inv["date"] = inv.slot_time_utc.dt.date
    per_day = inv.groupby("date").agg(
        files=("file", lambda s: (s != "").sum()),
        ok=("status", lambda s: (s == "ok").sum()),
        pixels_disk=("n_pixels_disk", "sum"),
        pixels_region=("n_pixels_region", "sum"))
    print(f"Expected slots: {len(slots)}, files found: {len(files)}, files outside period: {len(extra)}")
    print(inv.status.str.split(":").str[0].value_counts().to_string())
    print("\nPer day:")
    print(per_day.astype(int).to_string())
    bad = inv[inv.status != "ok"]
    if len(bad):
        print("\nNot ok:")
        print(bad[["slot_time_utc", "file", "status"]].to_string(index=False))
    print(f"\nPixels per file (disk): min {inv.n_pixels_disk.min():.0f}, "
          f"median {inv.n_pixels_disk.median():.0f}, max {inv.n_pixels_disk.max():.0f}")
    print(f"File size: min {inv.size_bytes.min():.0f} B, max {inv.size_bytes.max():.0f} B")

    # ---- figure: day x slot grid, coloured by fire pixels in the region box ----
    days = sorted(inv.date.unique())
    grid = np.full((len(days), 24 * 60 // SLOT_MIN), np.nan)
    missing = np.zeros_like(grid, dtype=bool)
    for _, r in inv.iterrows():
        i = days.index(r.date)
        j = (r.slot_time_utc.hour * 60 + r.slot_time_utc.minute) // SLOT_MIN
        if r.status == "ok":
            grid[i, j] = r.n_pixels_region
        else:
            missing[i, j] = True

    fig, ax = plt.subplots(figsize=(11, 4.2))
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#f1f0ec")                       # file present, 0 pixels in the region box
    shown = np.where(grid > 0, grid, np.nan)
    im = ax.imshow(shown, aspect="auto", cmap=cmap, norm=LogNorm(vmin=1, vmax=max(1, np.nanmax(grid))),
                   extent=(0, 24, len(days) - 0.5, -0.5), interpolation="nearest")
    for i, j in zip(*np.where(missing)):
        ax.add_patch(plt.Rectangle((j * SLOT_MIN / 60, i - 0.5), SLOT_MIN / 60, 1,
                                   facecolor="#e34948", edgecolor="none"))
    ax.set_yticks(range(len(days)), [d.strftime("%d %b") for d in days])
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Time of day (UTC, h)")
    ax.set_ylabel("Date (2025)")
    n_missing = int(missing.sum())
    ax.set_title(f"LSA SAF FRP-PIXEL file availability: {len(slots) - n_missing} of {len(slots)} "
                 f"15-min slots present ({n_missing} missing or unreadable)", loc="left", fontsize=11)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label(f"Fire pixels in {region_id} box per slot")
    cb.outline.set_visible(False)
    fig.text(0.01, 0.01, f"Light grey: file present, no fire pixel in {region_id} box. "
             "Red: file missing or unreadable.", fontsize=8, color="#52514e")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_fig.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_fig, dpi=DPI)
    print(f"\nWrote {out_table} and {out_fig}")


if __name__ == "__main__":
    main()
