"""Event figures (PNG, 300 dpi, UTC) in events/<event_id>/figures/.

Usage: python scripts/event/03_figures.py --event <event_id>
01 map: Esri background, event members by sensor, other detections grey, search box drawn
02 overpass timeline: sensing-layer passes touching the search box, one row per platform, filled = event detected
03 growth proxy: total FRP and extent of event members per pass, by platform
Reads the products of 02_products.py.
"""
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.event import event_dirs, parse_event_arg  # noqa: E402
from lib.helpers import grow_box, merc_x, merc_y  # noqa: E402
from lib.plotting import (DPI, INK, INK_2, MUTED, NO_DATA, OTHER_COLOR, PLATFORM_MARKER, PLATFORM_SENSOR,  # noqa: E402
                          PLATFORMS, SENSOR_COLOR, add_basemap, box_patch_merc, credit, degree_ticks, halo_text,
                          time_axis)
from lib.registry import get_event, load_registry, utc  # noqa: E402

MAP_PAD_DEG = 0.1             # map extent = search box and member bbox, plus this pad
GROWTH_LEAD_H = 12            # figure 03 starts this long before the ignition or first member

event_id = parse_event_arg()
reg = load_registry()
ev = get_event(event_id, reg)
dirs = event_dirs(event_id)
proc, figs = dirs["processed"], dirs["figures"]
ignition = utc(ev["ignition_utc"])
win_start, win_end = utc(reg["data_window"]["start_utc"]), utc(reg["data_window"]["end_utc"])
firms_end = utc(reg["data_window"]["firms_data_end_utc"])
summary = json.loads((proc / "event_summary.json").read_text())
extent = json.loads((proc / "event_extent.json").read_text())
obs = pd.read_csv(proc / "event_observations.csv", dtype={"confidence_raw": str, "static_proxy": str})
ep = pd.read_csv(proc / "event_overpasses.csv", parse_dates=["first_member_utc", "overpass_start_utc"])
sl = pd.read_csv(proc / "overpass_times_sensing_layer.csv", parse_dates=["overpass_start_utc"])
name = ev["name"]

# ---------------- 01 map ----------------
sb = ev["search_box"]
box = grow_box({"lat_min": min(sb["lat_min"], extent["lat_min"]), "lat_max": max(sb["lat_max"], extent["lat_max"]),
                "lon_min": min(sb["lon_min"], extent["lon_min"]), "lon_max": max(sb["lon_max"], extent["lon_max"])},
               MAP_PAD_DEG)
obs["mx"], obs["my"] = merc_x(obs["longitude"]), merc_y(obs["latitude"])
mem = obs["event_member"]
fig, ax = plt.subplots(figsize=(7.0, 6.2))
add_basemap(ax, box)
ax.scatter(obs.loc[~mem, "mx"], obs.loc[~mem, "my"], s=5, c=OTHER_COLOR, edgecolors=INK, linewidths=0.15, zorder=2)
for sensor in ["MODIS", "VIIRS"]:
    sel = mem & (obs["sensor"] == sensor)
    ax.scatter(obs.loc[sel, "mx"], obs.loc[sel, "my"], s=7 if sensor == "VIIRS" else 14, c=SENSOR_COLOR[sensor],
               edgecolors="white", linewidths=0.25, zorder=3)
ax.add_patch(box_patch_merc(sb, ec="white", lw=1.0, ls="--", zorder=4))
halo_text(ax, merc_x(sb["lon_min"]), merc_y(sb["lat_max"]), " search box (crop, not the event)", va="bottom")
ref = ev["reference_point"]
ax.scatter(merc_x(ref["lon"]), merc_y(ref["lat"]), marker="+", s=60, c="white", linewidths=1.2, zorder=5)
halo_text(ax, merc_x(ref["lon"]), merc_y(ref["lat"]), "  reference point", va="center")
degree_ticks(ax, box)
ax.set_xlabel("Longitude (°E)")
ax.set_ylabel("Latitude (°N)")
handles = [Line2D([], [], ls="", marker="o", ms=5, mfc=SENSOR_COLOR[s], mec="none",
                  label=f"event member, {s} ({(mem & (obs['sensor'] == s)).sum():,})") for s in ["VIIRS", "MODIS"]]
handles += [Line2D([], [], ls="", marker="o", ms=5, mfc=OTHER_COLOR, mec=INK, mew=0.3,
                   label=f"other FIRMS detections ({(~mem).sum():,})"),
            Line2D([], [], ls="", marker="+", ms=7, mec=INK_2, label="registry reference point (approximate)")]
fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.01, 0.0), ncol=1, fontsize=7)
credit(fig, width=60)
at_end = " (= FIRMS data end)" if utc(extent["last_member_utc"]) == firms_end else ""
ax.set_title(f"{name}\nFIRMS event cluster {summary['cluster_id']}, {summary['firms_event_detections']:,} detections\n"
             f"first to last member: {extent['first_member_utc']} to {extent['last_member_utc']}{at_end}",
             loc="left", fontsize=8)
fig.tight_layout(rect=(0, 0.1, 1, 1))
fig.savefig(figs / "01_map_event.png", dpi=DPI)
plt.close(fig)

# ---------------- 02 overpass timeline ----------------
fig, ax = plt.subplots(figsize=(7.5, 3.2))
ax.axvspan(firms_end, win_end, color=NO_DATA, zorder=0, lw=0)
for row, platform in enumerate(PLATFORMS):
    y = len(PLATFORMS) - 1 - row
    sensor = PLATFORM_SENSOR[platform]
    if sensor == "OLI":
        ax.axhspan(y - 0.35, y + 0.35, color=SENSOR_COLOR["OLI"], alpha=0.12, lw=0, hatch="////")
        ax.text(win_start + pd.Timedelta(hours=3), y, "Landsat not shown (supplementary; FIRMS Landsat "
                "covers the US and Canada only)", va="center", fontsize=6.5, color=INK_2)
        continue
    g = sl[sl["platform"] == platform]
    hit = g["event_detected"]
    ax.scatter(g.loc[~hit, "overpass_start_utc"], [y] * (~hit).sum(), marker=PLATFORM_MARKER[platform], s=26,
               facecolors="white", edgecolors=SENSOR_COLOR[sensor], linewidths=1.0, zorder=3)
    ax.scatter(g.loc[hit, "overpass_start_utc"], [y] * hit.sum(), marker=PLATFORM_MARKER[platform], s=26,
               c=SENSOR_COLOR[sensor], edgecolors="white", linewidths=0.5, zorder=3)
ax.axvline(ignition, color=INK, lw=0.8, ls="--", zorder=2)
ax.text(ignition, len(PLATFORMS) - 0.45, " ignition (registry)", fontsize=6.5, color=INK, va="bottom")
ax.text(firms_end + pd.Timedelta(hours=2), len(PLATFORMS) - 0.45, "no FIRMS data", fontsize=6.5, color=MUTED, va="bottom")
ax.set_yticks(range(len(PLATFORMS)))
ax.set_yticklabels([f"{p} ({PLATFORM_SENSOR[p]})" for p in reversed(PLATFORMS)])
ax.set_ylim(-0.6, len(PLATFORMS) - 0.1)
ax.grid(axis="y", visible=False)
time_axis(ax, win_start, win_end)
ax.set_xlabel("Overpass start time (UTC)")
handles = [Line2D([], [], ls="", marker="o", ms=5, mfc=INK_2, mec="white", label="event detected"),
           Line2D([], [], ls="", marker="o", ms=5, mfc="white", mec=INK_2, label="search box only (other fires)")]
ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.22), ncol=2, fontsize=7)
ax.set_title(f"{name}\nsensing-layer passes with a detection in the search box: {len(sl)}, "
             f"{int(sl['event_detected'].sum())} detected the event", loc="left", fontsize=8.5)
fig.tight_layout()
fig.savefig(figs / "02_overpass_timeline.png", dpi=DPI)
plt.close(fig)

# ---------------- 03 growth proxy ----------------
fig, axes = plt.subplots(2, 1, figsize=(7.0, 4.8), sharex=True)
growth_start = min(ep["first_member_utc"].min(), ignition) - pd.Timedelta(hours=GROWTH_LEAD_H)
for ax, (var, label) in zip(axes, [("total_frp_mw", "Total FRP (MW)"), ("extent_km", "Extent (km)")]):
    ax.axvspan(firms_end, win_end, color=NO_DATA, zorder=0, lw=0)
    gv = ep[ep[var] > 0] if var == "total_frp_mw" else ep      # log axis: passes with FRP = 0 not drawn
    ax.plot(gv["first_member_utc"], gv[var], color="#e1e0d9", lw=0.8, zorder=2)
    for platform, g in gv.groupby("platform"):
        ax.scatter(g["first_member_utc"], g[var], marker=PLATFORM_MARKER[platform], s=22,
                   c=SENSOR_COLOR[PLATFORM_SENSOR[platform]], edgecolors="white", linewidths=0.4, zorder=3)
    ax.axvline(ignition, color=INK, lw=0.7, ls="--", zorder=1)
    ax.set_ylabel(label)
    time_axis(ax, growth_start, win_end)
axes[0].set_yscale("log")
axes[1].set_ylim(bottom=0)
axes[1].set_xlabel("First event-member detection of the pass (UTC)")
handles = [Line2D([], [], ls="", marker=PLATFORM_MARKER[p], ms=5, mfc=SENSOR_COLOR[PLATFORM_SENSOR[p]], mec="white",
                  label=f"{p} ({PLATFORM_SENSOR[p]})") for p in PLATFORMS[:5]]
handles.append(Line2D([], [], color=INK, lw=0.7, ls="--", label="ignition (registry)"))
fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=7, bbox_to_anchor=(0.5, 0.0))
axes[0].set_title(f"{name}\ngrowth proxy per pass, event members only ({len(ep)} passes): total FRP (log) and "
                  f"bounding-box diagonal", loc="left", fontsize=8.5)
fig.tight_layout(rect=(0, 0.09, 1, 1))
fig.savefig(figs / "03_growth_proxy.png", dpi=DPI)
plt.close(fig)
print("written:", sorted(p.name for p in figs.glob("*.png")))
