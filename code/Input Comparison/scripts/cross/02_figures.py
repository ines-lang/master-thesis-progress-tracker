"""Step 4 (v2): cross-event figures.

01_aligned_timelines.png: one panel per event, x = hours since ignition, rows per platform + SEVIRI.
02_gaps_by_hour.png: baseline gaps by UTC start hour (a) and hour of day of each instant (b).

Usage: python scripts/cross/02_figures.py
"""

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, "scripts/lib")
from registry import load_registry, utc  # noqa: E402

# ---------------- constants ----------------
EVENT_DIR = "events/{event}/processed"
CROSS = "cross_event"
DPI = 300
MODE = "all"
X_MIN_H, X_PAD_H = -2, 3
LONG_GAP_H = 6.0
ROLE_COLOR = {"baseline": "#2a78d6", "context": "#eb6834"}
# one style per event in registry order (colour follows the event); validated categorical slots 1 to 5
EVENT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
EVENT_MARKERS = ["o", "s", "^", "D", "v"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
PLATFORMS = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21", "MSG"]
LABEL = {"Terra": "Terra (MODIS)", "Aqua": "Aqua (MODIS)", "Suomi-NPP": "Suomi-NPP (VIIRS)",
         "NOAA-20": "NOAA-20 (VIIRS)", "NOAA-21": "NOAA-21 (VIIRS)", "MSG": "MSG (SEVIRI)"}

plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True})


def since(t, ign):
    return (t - ign).dt.total_seconds() / 3600 if hasattr(t, "dt") else (t - ign).total_seconds() / 3600


def event_styles(reg):
    events = list(reg["events"])
    if len(events) > len(EVENT_COLORS):
        raise SystemExit(f"{len(events)} events but {len(EVENT_COLORS)} validated colours: use small multiples")
    return {eid: dict(color=EVENT_COLORS[i], marker=EVENT_MARKERS[i]) for i, eid in enumerate(events)}


def fig01_aligned(reg, summary):
    events = list(reg["events"])
    horizon = summary.horizon_h.iloc[0]
    x_max = summary.observable_window_h.add(summary.ignition_to_t0_h).max() + X_PAD_H
    fig, axes = plt.subplots(len(events), 1, figsize=(9, 2.7 * len(events)), sharex=True)
    for ax, eid in zip(axes, events):
        ev, s = reg["events"][eid], summary.set_index("event_id").loc[eid]
        ign = utc(ev["ignition_utc"])
        inst = pd.read_csv(f"{EVENT_DIR.format(event=eid)}/observation_instants.csv", parse_dates=["time_utc"])
        inst = inst[(inst.conf_mode == MODE) & (inst.scope == "event_member")]
        for y, p in enumerate(PLATFORMS):
            d = inst[inst.platform == p]
            x = since(d.time_utc, ign)
            if p == "MSG":
                ax.vlines(x, y - 0.3, y + 0.3, color=ROLE_COLOR["context"], lw=0.6)
            else:
                ax.scatter(x, [y] * len(x), s=26, color=ROLE_COLOR["baseline"], edgecolor="white", lw=0.7, zorder=3)
        t0_h = s.ignition_to_t0_h
        ax.axvline(0, color=INK2, ls="--", lw=1)
        ax.axvline(t0_h, color=INK, lw=1.2)
        ax.axvline(t0_h + horizon, color=INK2, ls=":", lw=1)
        gs, ge = since(pd.Timestamp(s.baseline_longest_gap_start_utc), ign), since(pd.Timestamp(s.baseline_longest_gap_end_utc), ign)
        ax.axvspan(gs, ge, color=ROLE_COLOR["baseline"], alpha=0.1, lw=0)
        ax.text((gs + ge) / 2, -0.42, f"longest baseline gap {s.baseline_max_h:.2f} h",
                ha="center", va="center", fontsize=7.5, color=INK, bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
        t_end_h = t0_h + s.observable_window_h
        ax.axvspan(t_end_h, x_max, color=GRID, alpha=0.6, lw=0)
        ax.set_yticks(range(len(PLATFORMS)), [LABEL[p] for p in PLATFORMS])
        ax.set_ylim(len(PLATFORMS) - 0.3, -0.7)
        ax.grid(axis="y", visible=False)
        ax.set_title(f"{ev['name']}: ignition {ign:%d Aug %H:%M} UTC, T0 = ignition + {t0_h:.2f} h",
                     loc="left", fontsize=9, pad=16)
        ax.text(0, -0.65, "ignition ", ha="right", va="bottom", fontsize=7.5, color=INK2)
        ax.text(t0_h, -0.65, " T0", ha="left", va="bottom", fontsize=7.5, color=INK, fontweight="bold")
        ax.text(t0_h + horizon, -0.65, " T0 + common horizon", ha="left", va="bottom", fontsize=7.5, color=INK2)
        ax.text(x_max, len(PLATFORMS) - 0.45, "after T_END ", ha="right", va="center", fontsize=7.5, color=INK2)
    axes[-1].set_xlim(X_MIN_H, x_max)
    axes[-1].set_xticks(np.arange(0, x_max, 12))
    axes[-1].set_xlabel("Hours since stated ignition")
    handles = [plt.Line2D([], [], ls="", marker="o", color=ROLE_COLOR["baseline"], ms=5, label="baseline pass with event pixels"),
               plt.Line2D([], [], color=ROLE_COLOR["context"], lw=1.2, label="SEVIRI slot with event pixels"),
               plt.Rectangle((0, 0), 1, 1, fc=ROLE_COLOR["baseline"], alpha=0.2, label="longest baseline gap (full window)")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(f"Event observations aligned on ignition (common horizon {horizon:.2f} h after T0)",
                 x=0.02, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(f"{CROSS}/figures/01_aligned_timelines.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig02_gaps_by_hour(reg):
    gaps = pd.read_csv(f"{CROSS}/processed/baseline_gaps_by_hour.csv")
    inst = pd.read_csv(f"{CROSS}/processed/instants_by_hour.csv")
    fig, (a, b) = plt.subplots(2, 1, figsize=(8, 7), gridspec_kw={"height_ratios": [1.3, 1]})
    styles = event_styles(reg)
    for eid, st in styles.items():
        g = gaps[gaps.event_id == eid]
        name = reg["events"][eid]["name"].split(" (")[0]
        inside = g[g.in_common_horizon]
        a.scatter(inside.start_hour_utc, inside.gap_h, s=36, color=st["color"], marker=st["marker"],
                  edgecolor="white", lw=0.7, zorder=3, label=f"{name}, within common horizon")
        out = g[~g.in_common_horizon]
        a.scatter(out.start_hour_utc, out.gap_h, s=36, facecolor="white", edgecolor=st["color"],
                  marker=st["marker"], lw=1.2, zorder=3, label=f"{name}, after common horizon")
    a.axhline(LONG_GAP_H, color=INK2, ls="--", lw=0.8)
    a.text(24, LONG_GAP_H, f" {LONG_GAP_H:.0f} h", va="center", fontsize=7.5, color=INK2)
    a.set_xlim(0, 24)
    a.set_xticks(range(0, 25, 3))
    a.set_xlabel("UTC hour at which the gap starts")
    a.set_ylabel("Baseline gap (h)")
    a.set_title("a) Every baseline gap after T0, by the UTC hour at which it starts", loc="left", fontsize=9)
    a.legend(frameon=False, fontsize=7.5, loc="upper right")

    rows = [(eid, p) for eid in styles for p in PLATFORMS]
    for y, (eid, p) in enumerate(rows):
        d = inst[(inst.event_id == eid) & (inst.platform == p)]
        st = styles[eid]
        if p == "MSG":
            b.vlines(d.hour_utc, y - 0.3, y + 0.3, color=st["color"], lw=0.5, alpha=0.6)
        else:
            b.scatter(d.hour_utc, [y] * len(d), s=18, color=st["color"], marker=st["marker"],
                      edgecolor="white", lw=0.5, zorder=3)
    b.set_yticks(range(len(rows)), [f"{e[:4].title()}. {LABEL[p]}" for e, p in rows], fontsize=7.5)
    b.set_ylim(len(rows) - 0.4, -0.6)
    b.grid(axis="y", visible=False)
    b.set_xlim(0, 24)
    b.set_xticks(range(0, 25, 3))
    b.set_xlabel("UTC hour of day of the observation instant")
    b.set_title("b) Hour of day of each event instant after T0 (all days overlaid)", loc="left", fontsize=9)
    fig.tight_layout()
    fig.savefig(f"{CROSS}/figures/02_gaps_by_hour.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    reg = load_registry()
    summary = pd.read_csv(f"{CROSS}/processed/summary_table.csv")
    fig01_aligned(reg, summary)
    fig02_gaps_by_hour(reg)
    print("figures written to", f"{CROSS}/figures")
