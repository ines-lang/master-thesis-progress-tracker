#!/usr/bin/env python3
"""
v2 Step 2.5: per-event SEVIRI figures, one message each.
  01_seviri_detection_strip.png  When did SEVIRI see the event? Member pixels per 15-min slot
                                 (primary rule), blackouts of >= 1 h shaded, ignition and FIRMS T0 marked.
  02_seviri_member_map.png       How coarse is SEVIRI? Member pixels drawn as SEVIRI grid cells
                                 (spacing estimated from the data) over the FIRMS event detections.

Run after 01_event_seviri.py, from the "Input Data LSA SAF" folder:
    python scripts/event/02_event_figures.py --event larouco
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.registry import FIRMS_EVENTS, REPO, get_event, get_region, load_registry, region_dir, utc  # noqa: E402

# ---------------- constants ----------------
SLOT_MIN = 15
DPI = 300
LEAD_H = 6                      # hours shown before ignition
COLOR_MEMBER = "#2a78d6"
COLOR_BLACKOUT = "#e1dfd8"
COLOR_FIRMS = "#0b0b0b"
COLOR_EVENT = "#e34948"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e6e5e0"
KM_PER_DEG_LAT = 111.32
SCALE_BAR_KM = 5
# -------------------------------------------


def clean_axes(ax):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True)
    event_id = ap.parse_args().event
    reg = load_registry()
    ev = get_event(reg, event_id)
    get_region(reg, ev["region"])
    in_extended = region_dir(ev["region"]) / "lsasaf_pixels.csv"
    ev_dir = REPO / "events" / event_id
    fig_dir = ev_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    summ = json.loads((ev_dir / "processed" / "seviri_event_summary.json").read_text())
    p = summ["rules"]["primary"]
    tab = pd.read_csv(ev_dir / "processed" / "seviri_event_slots.csv")
    slots = pd.to_datetime(tab.slot_time_utc).dt.tz_convert(None)
    ignition = utc(ev["ignition_utc"])
    t0 = utc(summ["firms_t0_utc"]) if summ["firms_t0_utc"] else None
    end = utc(reg["data_window"]["end_utc"])
    first = utc(p["first_detection_utc"])
    longest = max(p["blackouts"], key=lambda b: b["hours"]) if p["blackouts"] else None
    short_name = ev["name"].split(" (")[0]

    # ---- figure 01: when did SEVIRI see the event ----
    x0 = ignition - pd.Timedelta(hours=LEAD_H)
    keep = slots >= x0
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for b in p["blackouts"]:
        ax.axvspan(utc(b["start_slot_utc"]), utc(b["end_slot_utc"]), color=COLOR_BLACKOUT, zorder=0, linewidth=0)
    ax.bar(slots[keep], tab.n_member_primary[keep], width=pd.Timedelta(minutes=SLOT_MIN), align="edge",
           color=COLOR_MEMBER, linewidth=0, zorder=2)
    ymax = max(1, tab.n_member_primary.max()) * 1.15
    ax.set_ylim(0, ymax)
    for t, lab, ls in [(ignition, "ignition", "-"), (t0, "FIRMS T0", "--")]:
        if t is not None:
            ax.axvline(t, color=COLOR_EVENT, linewidth=1, linestyle=ls, zorder=3)
    labels = [(ignition, "ignition")] + ([(t0, "FIRMS T0")] if t0 is not None else [])
    for k, (t, lab) in enumerate(sorted(labels)):
        ax.annotate(lab, (t, ymax), xytext=(4, -4 - 12 * k), textcoords="offset points",
                    fontsize=8.5, color=COLOR_EVENT, va="top")
    ax.set_xlim(x0, end + pd.Timedelta(minutes=1))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("SEVIRI fire pixels\non the event")
    ax.grid(axis="y", color=COLOR_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    clean_axes(ax)
    first_min = int(round(p["first_minus_ignition_min"]))
    title = (f"{short_name}: SEVIRI first saw the fire at {first:%d %b %H:%M} UTC, "
             f"{first_min} min after ignition")
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(handles=[Patch(color=COLOR_MEMBER, label="Fire pixels per 15-min image"),
                       Patch(color=COLOR_BLACKOUT, label="No detection for 1 h or more")],
              loc="upper right", frameon=True, facecolor="white", edgecolor="none", framealpha=1, fontsize=8.5)
    note = (f"Longest gap without detection: {longest['hours']:g} h "
            f"({utc(longest['start_slot_utc']):%d %b %H:%M} to {utc(longest['end_slot_utc']):%d %b %H:%M} UTC). "
            if longest else "")
    fig.text(0.01, 0.01, note + "Event pixels = SEVIRI pixels inside the FIRMS event area.",
             fontsize=8, color=COLOR_TEXT_2)
    fig.subplots_adjust(left=0.09, right=0.96, top=0.9, bottom=0.2)
    fig.savefig(fig_dir / "01_seviri_detection_strip.png", dpi=DPI)
    plt.close(fig)

    # ---- figure 02: how coarse is SEVIRI ----
    obs = pd.read_csv(ev_dir / "processed" / "event_observations.csv")
    pix = (obs[obs.event_member].groupby(["latitude", "longitude"])
           .agg(size_km=("pixel_size_km", "mean")).reset_index())
    # SEVIRI grid spacing around the event: degrees per line (north-south) and per column (east-west)
    ext = pd.read_csv(in_extended, usecols=["latitude", "longitude", "abs_line", "abs_pixel"])
    ext = ext[ext.latitude.between(pix.latitude.min() - 0.3, pix.latitude.max() + 0.3)
              & ext.longitude.between(pix.longitude.min() - 0.3, pix.longitude.max() + 0.3)]
    dlat = abs(np.polyfit(ext.abs_line, ext.latitude, 1)[0])
    dlon = abs(np.polyfit(ext.abs_pixel, ext.longitude, 1)[0])
    coslat0 = np.cos(np.radians(pix.latitude.mean()))
    ns_km, ew_km = dlat * KM_PER_DEG_LAT, dlon * KM_PER_DEG_LAT * coslat0
    foot = pd.read_csv(FIRMS_EVENTS / event_id / "processed" / "event_footprint.csv")

    fig, ax = plt.subplots(figsize=(7, 6))
    for _, r in pix.iterrows():
        ax.add_patch(Rectangle((r.longitude - dlon / 2, r.latitude - dlat / 2), dlon, dlat,
                               facecolor="#c9dcf3", edgecolor=COLOR_MEMBER, linewidth=0.8))
    ax.scatter(foot.longitude, foot.latitude, s=2, color=COLOR_FIRMS, zorder=4)
    pad = 0.05
    lat_all = pd.concat([pix.latitude, foot.latitude])
    lon_all = pd.concat([pix.longitude, foot.longitude])
    ax.set_xlim(lon_all.min() - pad, lon_all.max() + pad)
    ax.set_ylim(lat_all.min() - pad, lat_all.max() + pad)
    coslat = np.cos(np.radians(lat_all.mean()))
    ax.set_aspect(1 / coslat)
    # scale bar, bottom left
    bar_deg = SCALE_BAR_KM / (KM_PER_DEG_LAT * coslat)
    bx = lon_all.min() - pad * 0.6
    by = lat_all.min() - pad * 0.6
    ax.plot([bx, bx + bar_deg], [by, by], color=COLOR_FIRMS, linewidth=2)
    ax.text(bx + bar_deg / 2, by + 0.004, f"{SCALE_BAR_KM} km", ha="center", va="bottom", fontsize=8.5)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    clean_axes(ax)
    ax.legend(handles=[Patch(facecolor="#c9dcf3", edgecolor=COLOR_MEMBER,
                             label=f"SEVIRI pixel (about {ew_km:.1f} x {ns_km:.1f} km), {len(pix)} pixels"),
                       plt.Line2D([], [], marker="o", linestyle="", markersize=3, color=COLOR_FIRMS,
                                  label=f"FIRMS detection (0.4 to 1 km), {len(foot)} detections")],
              loc="upper left", fontsize=8.5, frameon=True, framealpha=0.95)
    ax.set_title(f"{short_name}: what SEVIRI sees (cells)\nvs what FIRMS sees (dots)",
                 loc="left", fontsize=10.5)
    fig.text(0.01, 0.01, "Cells = SEVIRI pixel grid around the event (spacing from the data). All days of the event.",
             fontsize=7.5, color=COLOR_TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(fig_dir / "02_seviri_member_map.png", dpi=DPI)
    plt.close(fig)
    print(f"Wrote events/{event_id}/figures/01_seviri_detection_strip.png and 02_seviri_member_map.png")


if __name__ == "__main__":
    main()
