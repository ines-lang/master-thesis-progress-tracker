"""Step 2.2: local solar time of the equator crossings of every LEO layer satellite (S1, S3, S4), from its window TLE.

For a sun-synchronous orbit this is the local time of its daytime and night-time passes everywhere
(at mid latitudes the pass is within about 1 h of it), so it shows how the EO layer covers the day.
Input:  processed/eo_census.csv (role, TLE lines)
Output: processed/overpass_times.csv, figures/01_overpass_times.png

Usage: python scripts/02_overpass_times.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

# ---- parameters ----
CENSUS_DIR = Path(__file__).resolve().parents[1]
PROC, FIGS = CENSUS_DIR / "processed", CENSUS_DIR / "figures"
DAY = (2025, 8, 13)                    # middle of the data window
STEP_S = 20
DPI = 300
GROUP_COLOR = {"S1 EO layer": "#2a78d6", "S3 extended public layer": "#eb6834", "S4 commercial layer": "#1baf7a"}
INK, INK2 = "#0b0b0b", "#52514e"

ts = load.timescale()
census = pd.read_csv(PROC / "eo_census.csv")
layer = census[census["role"].isin(GROUP_COLOR)].copy()
layer["group"] = layer["role"]

seconds = np.arange(0, 86400, STEP_S)
t = ts.utc(*DAY, 0, 0, seconds)
rows = []
for r in layer.itertuples():
    sat = EarthSatellite(r.line1, r.line2, r.mission, ts)
    sub = wgs84.subpoint_of(sat.at(t))
    lat, lon = sub.latitude.degrees, sub.longitude.degrees
    for direction, crossing in [("ascending", (lat[:-1] < 0) & (lat[1:] >= 0)),
                                ("descending", (lat[:-1] > 0) & (lat[1:] <= 0))]:
        i = np.flatnonzero(crossing)
        utc_h = seconds[i] / 3600
        lst = (utc_h + lon[i] / 15) % 24                       # local mean solar time at the crossing
        # circular mean over the day's crossings (sun-synchronous: all nearly equal)
        ang = lst / 24 * 2 * np.pi
        mean = (np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) / (2 * np.pi) * 24) % 24
        rows.append(dict(mission=r.mission, group=r.group, instrument=r.instrument, direction=direction,
                         local_time_h=round(mean, 2), spread_h=round(float(np.ptp(lst)), 2), crossings=len(i)))
ot = pd.DataFrame(rows)
ot.to_csv(PROC / "overpass_times.csv", index=False)

# ---- figure: one row per satellite, both crossings over a 24 h axis ----
order = (ot[ot.direction == "descending"].assign(g=lambda d: d.group.map(list(GROUP_COLOR).index))
         .sort_values(["g", "local_time_h"])["mission"].tolist())
fig, ax = plt.subplots(figsize=(8.5, 0.28 * len(order) + 1.6))
for y, m in enumerate(order[::-1]):
    d = ot[ot.mission == m]
    c = GROUP_COLOR[d.group.iloc[0]]
    for _, x in d.iterrows():
        ax.scatter(x.local_time_h, y, s=34, color=c if x.direction == "descending" else "white",
                   edgecolor=c, lw=1.2, zorder=3)
ax.axvspan(6, 18, color="#fdf6e3", zorder=0)
ax.text(12, len(order) - 0.3, "day (about 06 to 18 local)", ha="center", fontsize=7, color=INK2)
ax.set_yticks(range(len(order)), [f"{m} ({ot[ot.mission == m].instrument.iloc[0]})" for m in order[::-1]],
              fontsize=7)
ax.set_xlim(0, 24)
ax.set_xticks(range(0, 25, 3))
ax.set_xlabel("Local solar time of the equator crossing (h)")
ax.grid(axis="y", visible=False)
ax.grid(axis="x", color="#e1e0d9", lw=0.5)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=g) for g, c in GROUP_COLOR.items()]
handles += [plt.Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=INK2, label="ascending"),
            plt.Line2D([], [], marker="o", ls="", color=INK2, label="descending")]
ax.legend(handles=handles, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False)
ax.set_title(f"LEO fire-capable satellites by layer: local time of their passes ({DAY[2]} Aug 2025 orbits)", loc="left",
             fontsize=9)
fig.tight_layout()
FIGS.mkdir(exist_ok=True)
fig.savefig(FIGS / "01_overpass_times.png", dpi=DPI)
plt.close(fig)

piv = ot.pivot(index=["group", "mission"], columns="direction", values="local_time_h").sort_values(["group", "descending"])
print(piv.round(1).to_string())
print(f"\nwritten: {PROC / 'overpass_times.csv'}, {FIGS / '01_overpass_times.png'}")
