"""Step 2.4: event-selection figures (PNG, 300 dpi, times in UTC) in figures/.

01_world_complexes.png     complexes passing criteria 1 to 3, coloured by criteria 4 and 5; selected events marked
02_top_by_continent.png    largest complexes per continent by FIRMS area after criteria 1 to 3, coloured by decision,
                           with the official final burned area where known
03_ignition_to_first_detection.png   FIRMS detections per pass (low confidence hollow) and every overpass
                                     (processed/candidate_overpasses.csv) against the reference time;
                                     writes processed/detection_bracket.csv
04_official_vs_firms_area.png        official final burned area against the FIRMS estimate up to the data end, per candidate

Usage: python scripts/04_figures.py
"""
import sys
import textwrap
from pathlib import Path

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ES_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ES_DIR.parent / "Input Data FIRMS" / "scripts"))
from lib.helpers import merc_x, merc_y  # noqa: E402
from lib.plotting import DPI, INK, INK_2, MUTED  # noqa: E402  (rcParams, tile cache)
from lib.registry import load_registry, utc  # noqa: E402

# ---- parameters ----
PROC, FIGS = ES_DIR / "processed", ES_DIR / "figures"
CONTINENTS = ["Europe", "North America", "Africa", "Asia", "South America", "Oceania"]
# validated categorical slots 1 and 2 (dataviz reference palette); greys for the non-selected states
DECISION_STYLE = {"selected": dict(color="#2a78d6", label="Selected"),
                  "alternative": dict(color="#eb6834", label="Alternative"),
                  "not selected": dict(color="#a3a29c", label="Not selected / no official ignition time"),
                  "excluded": dict(color="#e1e0d9", label="Excluded (criteria 4, 5 or not a wildfire)")}
DECISION_GROUP = {"selected": "selected", "alternative": "alternative", "not selected": "not selected",
                  "no ground truth": "not selected", "not examined": "not selected", "excluded": "excluded",
                  "to check": "not selected"}
PASS_COLOR, FAIL_COLOR = "#2a78d6", "#a3a29c"
AFTER_END_COLOR = "#d6d5ce"   # overpass ticks after the FIRMS data end
TIMELINE_EVENTS = ["piodao", "larouco", "molezuelas", "oimbra", "red_canyon", "mount_underwood", "derdara"]
SENSOR_MARKER = {"VIIRS": "o", "MODIS": "D"}
REFERENCE_LABEL = {"official (regional government)": "official ignition", "press (approximate)": "ignition, press",
                   "official discovery": "official discovery", "record creation": "record creation",
                   "press (about 14:00 local)": "ignition, press", "press citing ANEPC": "ignition, press"}
PASS_GAP_MIN = 10                 # detections of one platform within this many minutes = one pass
PASS_MATCH_MIN = 15               # an overpass saw the fire if its platform has a detection this close in time
WORLD_LAT = (-58, 78)
BASEMAP = cx.providers.Esri.WorldGrayCanvas
LABEL_OFFSET = {"larouco": (-58, 10), "molezuelas": (8, 8), "oimbra": (-58, -4), "piodao": (-50, -12),
                "derdara": (8, -10), "red_canyon": (8, 6)}   # points

reg = load_registry()
FIGS.mkdir(exist_ok=True)
complexes = pd.read_csv(PROC / "complexes_criteria.csv")
ranking = pd.read_csv(PROC / "ranking.csv")
gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv")
matches = pd.read_csv(PROC / "candidate_matches.csv")


def label_of(row):
    return row["name"] if isinstance(row["name"], str) else f"{row['lat']:.1f}, {row['lon']:.1f}"


# ---------------- 01 world map ----------------
def fig01_world():
    c = complexes[complexes.c1_vegetation & complexes.c2_onset_in_window & complexes.c3_size]
    ok = c.c4_spreading & c.c5_continent_rule
    fig, ax = plt.subplots(figsize=(11, 5.6))
    x0, x1 = merc_x(-180), merc_x(180)
    y0, y1 = merc_y(WORLD_LAT[0]), merc_y(WORLD_LAT[1])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    cx.add_basemap(ax, source=BASEMAP, zoom=2, attribution_size=5)
    size = np.clip(c.firms_area_ha / 60, 4, 160)
    for mask, color, lab in [(~ok, FAIL_COLOR, "Fails criterion 4 (point source) or 5 (continent rule)"),
                             (ok, PASS_COLOR, "Passes all criteria")]:
        ax.scatter(merc_x(c.lon[mask]), merc_y(c.lat[mask]), s=size[mask], color=color, alpha=0.65, lw=0.3,
                   edgecolor="white", label=lab, zorder=3)
    sel = gt[gt.decision == "selected"].merge(matches[["candidate_id", "lat", "lon"]], on="candidate_id", suffixes=("", "_cl"))
    ax.scatter(merc_x(sel.lon_cl), merc_y(sel.lat_cl), marker="*", s=260, color="#e34948", edgecolor=INK, lw=0.8,
               zorder=5, label="Selected event")
    for r in sel.itertuples():
        ax.annotate(r.name.split(",")[0], (merc_x(r.lon_cl), merc_y(r.lat_cl)), xytext=LABEL_OFFSET.get(r.candidate_id, (6, 6)),
                    textcoords="offset points",
                    fontsize=7.5, color=INK, zorder=6)
    ax.set_axis_off()
    ax.set_title("Fire complexes first detected 9 to 15 Aug 2025 with a FIRMS burned-area estimate of at least 500 ha; "
                 "dot area proportional to that estimate", loc="left", fontsize=9)
    ax.legend(loc="lower left", fontsize=7.5, frameon=True, facecolor="white", edgecolor="none")
    fig.tight_layout()
    fig.savefig(FIGS / "01_world_complexes.png", dpi=DPI)
    plt.close(fig)


# ---------------- 02 top complexes per continent ----------------
def fig02_top():
    fig, axes = plt.subplots(3, 2, figsize=(10, 9.5))
    for ax, cont in zip(axes.flat, CONTINENTS):
        rc = ranking[ranking.continent == cont].sort_values("rank_in_continent")
        named = rc[rc.decision.isin(["selected", "alternative"]) & (rc.rank_in_continent > 8)]
        r = pd.concat([rc.head(8), named]).iloc[::-1]
        groups = r.decision.map(DECISION_GROUP)
        colors = [DECISION_STYLE[g]["color"] for g in groups]
        ax.barh(range(len(r)), r.firms_area_ha, color=colors, edgecolor=[INK_2 if g == "excluded" else "none" for g in groups],
                lw=0.6, height=0.7)
        labels = [f"{int(rk)}. {textwrap.shorten(label_of(row), 30, placeholder='...')}"
                  for rk, (_, row) in zip(r.rank_in_continent, r.iterrows())]
        ax.set_yticks(range(len(r)), labels, fontsize=7)
        ax.grid(axis="y", visible=False)
        ax.set_title(cont, loc="left", fontsize=9)
        ax.scatter(r.official_area_ha, range(len(r)), marker="D", s=22, color=INK, zorder=4)
        ax.set_xlabel("Burned area (ha)", fontsize=7)
        end = np.fmax(r.firms_area_ha.to_numpy(), r.official_area_ha.fillna(0).to_numpy())
        for i, (n, reason, g) in enumerate(zip(end, r.reason, groups)):
            if g in ("excluded", "selected", "alternative"):
                ax.text(n, i, "  " + textwrap.shorten(str(reason), 48, placeholder="..."), va="center", fontsize=6,
                        color=MUTED)
        ax.set_xlim(0, end.max() * 1.9)
    handles = [Patch(facecolor=s["color"], edgecolor=INK_2 if k == "excluded" else "none", label=s["label"])
               for k, s in DECISION_STYLE.items()]
    handles.append(Line2D([], [], marker="D", ls="", color=INK, markersize=5, label="Official final burned area"))
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=7.5)
    fig.suptitle("Largest new fire complexes per continent after criteria 1 to 3. Bars: FIRMS burned-area estimate up to "
                 "15 Aug; diamonds: official final area", x=0.01, ha="left", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    fig.savefig(FIGS / "02_top_by_continent.png", dpi=DPI)
    plt.close(fig)


# ---------------- 03 ignition to first detection ----------------
def passes(det):
    det = det.sort_values(["platform", "obs_time_utc"])
    new = det.groupby("platform")["obs_time_utc"].diff().gt(pd.Timedelta(minutes=PASS_GAP_MIN)) | \
        det["platform"].ne(det["platform"].shift())
    det["pass_id"] = new.cumsum()
    return det.groupby("pass_id").agg(t=("obs_time_utc", "min"), n=("latitude", "size"), kept=("kept", "any"),
                                      sensor=("sensor", "first"), platform=("platform", "first"))


def fig03_timelines():
    det = pd.read_csv(PROC / "candidate_detections.csv", parse_dates=["obs_time_utc"])
    det = det[det["sensor"].isin(SENSOR_MARKER) & ~det["non_vegetation"].astype(bool)]
    ovp = pd.read_csv(PROC / "candidate_overpasses.csv", parse_dates=["pass_utc"])
    firms_end = utc(reg["data_window"]["firms_data_end_utc"])
    ev = gt.set_index("candidate_id").loc[TIMELINE_EVENTS]
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    rows = []
    for y, (cid, row) in enumerate(ev.iloc[::-1].iterrows()):
        ign = pd.Timestamp(row.ignition_utc)
        p = passes(det[det.candidate_id == cid])
        h = (p.t - ign).dt.total_seconds() / 3600
        # every overpass; a pass "saw the fire" if the same platform has a detection within PASS_MATCH_MIN
        o = ovp[ovp.event == cid].copy()
        o["seen"] = [((p.platform == r.platform) & ((p.t - r.pass_utc).abs() <= pd.Timedelta(minutes=PASS_MATCH_MIN))).any()
                     for r in o.itertuples()]
        end_h = (firms_end - ign).total_seconds() / 3600
        # passes after the FIRMS data end cannot show a detection: drawn faded, they carry no information
        after = o.hours_from_reference > end_h
        ax.vlines(o.hours_from_reference[~after], y - 0.16, y + 0.16, color=MUTED, lw=0.6, zorder=1)
        ax.vlines(o.hours_from_reference[after], y - 0.16, y + 0.16, color=AFTER_END_COLOR, lw=0.6, zorder=1)
        # the event starts after the last pass without detection before the reference time; detections before
        # it belong to an earlier fire merged into the same 1 km cluster (Piodao: a fire 7 to 10 km away, -62 to -24 h)
        empty = o.loc[~o.seen, "hours_from_reference"]
        start = empty[empty < 0].max()
        first_any = h[h > start].min()
        first_kept = h[p.kept & (h > start)].min()
        last_clear = empty[empty < first_any].max()
        ax.fill_betweenx([y - 0.28, y + 0.28], last_clear, first_any, color="#f2d5c7", lw=0, zorder=0)
        for sensor, m in SENSOR_MARKER.items():
            for kept in (True, False):
                s = (p.sensor == sensor) & (p.kept == kept)
                c = PASS_COLOR if sensor == "VIIRS" else "#eb6834"
                ax.scatter(h[s], [y] * s.sum(), s=np.clip(p.n[s] * 1.5, 8, 160), marker=m,
                           facecolor=c if kept else "white", edgecolor="white" if kept else c,
                           lw=0.4 if kept else 0.9, alpha=0.85, zorder=3)
        label = f"first detection {first_kept:+.1f} h"
        if first_any < first_kept:
            label += f" (low confidence {first_any:+.1f} h)"
        ax.annotate(label, (first_any, y), xytext=(0, 9), textcoords="offset points", fontsize=6.5, color=INK, ha="left")
        ax.annotate(f"no detection {last_clear:+.1f} h", (last_clear, y), xytext=(-2, 9),
                    textcoords="offset points", fontsize=6, color=INK_2, ha="right")
        ax.plot([end_h] * 2, [y - 0.35, y + 0.35], color=INK_2, lw=1, ls=(0, (2, 1.5)), zorder=2)
        rows.append(dict(event=cid, last_pass_without_detection_h=round(last_clear, 2),
                         first_detection_any_confidence_h=round(first_any, 2), first_kept_detection_h=round(first_kept, 2)))
    pd.DataFrame(rows).to_csv(PROC / "detection_bracket.csv", index=False)
    ax.axvline(0, color="#e34948", lw=1.2, zorder=2)
    ax.text(0, len(ev) - 0.45, " reference time", color="#e34948", fontsize=7, va="bottom")
    labels = [f"{r['name'].split(',')[0]}\n({REFERENCE_LABEL[r.ignition_kind]})" for _, r in ev.iloc[::-1].iterrows()]
    ax.set_yticks(range(len(ev)), labels, fontsize=7)
    ax.set_ylim(-0.6, len(ev) - 0.2)
    ax.set_xlim(-12, 54)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Hours since the reference time (official ignition, official discovery, record creation or press)")
    handles = [Line2D([], [], marker=m, ls="", markerfacecolor=c, markeredgecolor="white", markersize=7, label=f"{s} pass")
               for (s, m), c in zip(SENSOR_MARKER.items(), [PASS_COLOR, "#eb6834"])]
    handles += [Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=PASS_COLOR, markersize=7,
                       label="low confidence only"),
                Line2D([], [], marker="|", ls="", color=MUTED, markersize=8,
                       label="overpass (VIIRS, MODIS); no marker: no FIRMS detection"),
                Patch(color="#f2d5c7", label="last pass without detection to first detection"),
                Line2D([], [], color=INK_2, lw=1, ls=(0, (2, 1.5)), label="FIRMS data end"),
                Line2D([], [], marker="|", ls="", color=AFTER_END_COLOR, markersize=8,
                       label="overpass after the data end (no data)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.13), ncol=3, fontsize=6.5, frameon=False)
    ax.set_title("FIRMS detections per pass (marker area proportional to detections) and every VIIRS / MODIS overpass",
                 loc="left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGS / "03_ignition_to_first_detection.png", dpi=DPI)
    plt.close(fig)


# ---------------- 04 official vs FIRMS area ----------------
def fig04_area():
    r = ranking.dropna(subset=["official_area_ha"])
    groups = r.decision.map(DECISION_GROUP)
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    lim = (300, 1.6 * max(r.official_area_ha.max(), r.firms_area_ha.max()))
    ax.plot(lim, lim, color=MUTED, lw=0.8, ls="--", zorder=1)
    ax.text(lim[1] / 1.15, lim[1] / 1.15, "1:1", fontsize=7, color=MUTED, ha="right", va="bottom")
    for g, st in DECISION_STYLE.items():
        m = groups == g
        if not m.any():
            continue
        ax.scatter(r.firms_area_ha[m], r.official_area_ha[m], s=46, color=st["color"], edgecolor=INK_2, lw=0.5,
                   label=st["label"], zorder=3)
    for _, row in r.iterrows():
        ax.annotate(row["name"].split(",")[0], (row.firms_area_ha, row.official_area_ha), xytext=(5, 3),
                    textcoords="offset points", fontsize=6.5, color=INK)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("FIRMS burned-area estimate up to the data end, 15 Aug (ha)")
    ax.set_ylabel("Official final burned area (ha)")
    ax.set_title("Candidates with an official area: fires still burning after 15 Aug lie above the 1:1 line",
                 loc="left", fontsize=8.5)
    ax.legend(fontsize=6.5, loc="lower right", frameon=True, facecolor="white", edgecolor="none")
    fig.tight_layout()
    fig.savefig(FIGS / "04_official_vs_firms_area.png", dpi=DPI)
    plt.close(fig)


if __name__ == "__main__":
    fig01_world()
    fig02_top()
    fig03_timelines()
    fig04_area()
    print("figures written to", FIGS)
