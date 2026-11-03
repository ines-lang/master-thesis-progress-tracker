"""Step 3 (v2): figures 01 to 04 of one event (PNG, 300 dpi, times in UTC).

Usage: python scripts/event/04_plots.py --event <id>
Uses conf_mode PLOT_MODE; scope event_member is main, search_box shown for context.
"""

import json
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle

sys.path.insert(0, "scripts/lib")
from registry import event_arg, get_event, load_registry, utc  # noqa: E402

# ---------------- constants ----------------
EVENT_DIR = "events/{event}"
FIRMS_FILE = "../Input Data FIRMS/events/{event}/processed/event_observations.csv"
SEVIRI_FILE = "../Input Data LSA SAF/events/{event}/processed/event_observations.csv"
EXTENT_FILE = "../Input Data FIRMS/events/{event}/processed/event_extent.json"
DPI = 300
PLOT_MODE = "all"
PAD_BEFORE_IGNITION = pd.Timedelta("4h")
PAD_AFTER_T_END = pd.Timedelta("2h")
AXIS_ROUND = "6h"
ZOOM_PAD_DEG = 0.06
KM_PER_DEG = 111.2

# validated categorical slots 1 to 3 (dataviz reference palette), one per role
ROLE_COLOR = {"baseline": "#2a78d6", "context": "#eb6834", "supplementary": "#1baf7a"}
INK, INK2, GRID, OTHER = "#0b0b0b", "#52514e", "#e4e3df", "#a3a29c"
PLATFORMS = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21", "Landsat-8/9", "MSG"]
LABEL = {"Terra": "Terra (MODIS)", "Aqua": "Aqua (MODIS)", "Suomi-NPP": "Suomi-NPP (VIIRS)",
         "NOAA-20": "NOAA-20 (VIIRS)", "NOAA-21": "NOAA-21 (VIIRS)",
         "Landsat-8/9": "Landsat-8/9 (OLI): not shown\n(supplementary)", "MSG": "MSG (SEVIRI)"}

plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True})


class Ctx:
    """Everything the figures need for one event."""

    def __init__(self, event_id):
        reg = load_registry()
        self.id, self.ev = event_id, get_event(event_id, reg)
        self.name = self.ev["name"]
        d = EVENT_DIR.format(event=event_id)
        self.fig_dir = f"{d}/figures"
        inst = pd.read_csv(f"{d}/processed/observation_instants.csv",
                           parse_dates=["time_utc", "time_end_utc", "slot_time_utc"])
        self.inst = inst[inst.conf_mode == PLOT_MODE]
        t0s = pd.read_csv(f"{d}/processed/t0_summary.csv", parse_dates=["t0_utc", "t_end_utc"])
        r = t0s[t0s.conf_mode == PLOT_MODE].iloc[0]
        self.t0, self.t_end = r.t0_utc, r.t_end_utc
        self.gaps = pd.read_csv(f"{d}/processed/gap_statistics.csv",
                                parse_dates=["longest_gap_start_utc", "longest_gap_end_utc"])
        self.gaps = self.gaps[(self.gaps.conf_mode == PLOT_MODE) & (self.gaps.window == "full")]
        self.ignition = utc(self.ev["ignition_utc"])
        self.firms_end = utc(reg["data_window"]["firms_data_end_utc"])
        self.start = (self.ignition - PAD_BEFORE_IGNITION).floor(AXIS_ROUND)
        self.end = (self.t_end + PAD_AFTER_T_END).ceil(AXIS_ROUND)
        self.extent = json.load(open(EXTENT_FILE.format(event=event_id)))

    def gap(self, scope, group):
        return self.gaps[(self.gaps.scope == scope) & (self.gaps.group == group)].iloc[0]


def time_axis(ax, c):
    ax.set_xlim(c.start, c.end)
    span_h = (c.end - c.start).total_seconds() / 3600
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12] if span_h <= 96 else [0]))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 3 if span_h <= 96 else 6)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d Aug\n%H:%M"))


def event_lines(ax, c, label=True):
    ax.axvline(c.ignition, color=INK2, ls="--", lw=1)
    ax.axvline(c.t0, color=INK, lw=1.2)
    if c.firms_end < c.end:
        ax.axvspan(c.firms_end, c.end, color=GRID, alpha=0.6, lw=0)
    if label:
        y = ax.get_ylim()[1]
        ax.text(c.ignition, y, "ignition ", color=INK2, va="bottom", ha="right", fontsize=8)
        ax.text(c.t0, y, " T0", color=INK, va="bottom", fontsize=8, fontweight="bold")


def fig01_timeline(c):
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    mem = c.inst[c.inst.scope == "event_member"]
    box = c.inst[c.inst.scope == "search_box"]
    for y, p in enumerate(PLATFORMS):
        if p == "Landsat-8/9":
            continue
        m, b = mem[mem.platform == p], box[box.platform == p]
        # box-only pass: no member instant inside [box start, box end] (+- 1 min)
        tol = pd.Timedelta("1min")
        has_member = [((m.time_utc >= t0 - tol) & (m.time_utc <= t1 + tol)).any()
                      for t0, t1 in zip(b.time_utc, b.time_end_utc)]
        b_only = b[~np.array(has_member, dtype=bool)]
        if p == "MSG":
            color = ROLE_COLOR["context"]
            ax.vlines(b_only.time_utc, y - 0.15, y + 0.15, color=color, lw=0.5, alpha=0.4)
            ax.vlines(m.time_utc, y - 0.32, y + 0.32, color=color, lw=0.7)
        else:
            color = ROLE_COLOR["baseline"]
            ax.scatter(b_only.time_utc, [y] * len(b_only), s=34, facecolor="white",
                       edgecolor=color, linewidth=1.1, zorder=3)
            ax.scatter(m.time_utc, [y] * len(m), s=34, color=color, edgecolor="white",
                       linewidth=0.8, zorder=4)
    ax.set_yticks(range(len(PLATFORMS)), [LABEL[p] for p in PLATFORMS])
    ax.set_ylim(len(PLATFORMS) - 0.4, -0.6)
    ax.grid(axis="y", visible=False)
    time_axis(ax, c)

    # longest gaps: c (baseline, main) shaded; e (all public) as arrow
    gc, ge = c.gap("event_member", "c"), c.gap("event_member", "e")
    ax.axvspan(gc.longest_gap_start_utc, gc.longest_gap_end_utc, color=ROLE_COLOR["baseline"],
               alpha=0.08, lw=0)
    same = (gc.longest_gap_start_utc == ge.longest_gap_start_utc) and (gc.longest_gap_end_utc == ge.longest_gap_end_utc)
    mid = lambda g: g.longest_gap_start_utc + (g.longest_gap_end_utc - g.longest_gap_start_utc) / 2
    label_c = (f"longest baseline gap {gc.max_gap_h:.2f} h,\nalso no public update at all" if same
               else f"longest baseline gap\n{gc.max_gap_h:.2f} h")
    ax.text(mid(gc), 5.0, label_c, ha="center", va="center", fontsize=7.5, color=INK,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    if not same:
        ax.annotate("", xy=(ge.longest_gap_end_utc, 5.55), xytext=(ge.longest_gap_start_utc, 5.55),
                    arrowprops=dict(arrowstyle="<->", color=INK, lw=0.9))
        ax.text(mid(ge), 5.4, f"{ge.max_gap_h:.2f} h without\nany public update", ha="center",
                va="bottom", fontsize=7.5, color=INK, bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    event_lines(ax, c)
    if c.firms_end < c.end:
        ax.text(c.firms_end, -0.55, " FIRMS\n data end", color=INK2, fontsize=7, va="top")
    ax.set_xlabel("Time (UTC)")
    handles = [
        plt.Line2D([], [], ls="", marker="o", color=ROLE_COLOR["baseline"], ms=6,
                   label="baseline pass with event pixels"),
        plt.Line2D([], [], ls="", marker="o", mfc="white", mec=ROLE_COLOR["baseline"], ms=6,
                   label="baseline pass, other fires in search box only"),
        plt.Line2D([], [], color=ROLE_COLOR["context"], lw=1.2,
                   label="SEVIRI slot: tall = event pixels, short = other fires only"),
        Rectangle((0, 0), 1, 1, fc=ROLE_COLOR["baseline"], alpha=0.15, label="longest baseline gap"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2,
              frameon=False, fontsize=7.5)
    ax.set_title(f"{c.name}: observation instants after ignition", loc="left", fontsize=10, pad=14)
    fig.savefig(f"{c.fig_dir}/01_observation_timeline.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig02_gaps(c):
    from gaps import gaps_h  # noqa: E402
    groups = [("a", "a) SEVIRI only", lambda d: d.source == "LSASAF", "context"),
              ("c", "c) Baseline combined (VIIRS + MODIS)", lambda d: d.role == "baseline", "baseline"),
              ("e", "e) Baseline + SEVIRI", lambda d: (d.role == "baseline") | (d.source == "LSASAF"),
               "baseline")]
    all_g = []
    for scope in ["event_member", "search_box"]:
        d = c.inst[c.inst.scope == scope]
        for gid, _, sel, _ in groups:
            all_g.append(gaps_h(d.time_utc[sel(d)], c.t0, c.t_end)[0])
    xmax = np.ceil(max(g.max() for g in all_g if len(g)) + 0.5)
    bins = np.arange(0, xmax + 0.01, 0.5)
    fig, axes = plt.subplots(3, 1, figsize=(7, 6.2), sharex=True)
    for ax, (gid, title, sel, role) in zip(axes, groups):
        for scope, filled in [("event_member", True), ("search_box", False)]:
            d = c.inst[c.inst.scope == scope]
            g = gaps_h(d.time_utc[sel(d)], c.t0, c.t_end)[0]
            st = c.gap(scope, gid)
            lab = (f"{'event pixels (main)' if filled else 'whole search box'}: n = {len(g)}, "
                   f"median {st.median_gap_h:.2f} h, p90 {st.p90_gap_h:.2f} h, max {st.max_gap_h:.2f} h")
            if filled:
                ax.hist(g, bins=bins, color=ROLE_COLOR[role], alpha=0.85, edgecolor="white", lw=0.8, label=lab)
            else:
                ax.hist(g, bins=bins, histtype="step", color=INK, lw=1.2, label=lab)
        ax.set_yscale("symlog", linthresh=10)
        ax.set_ylabel("Number of gaps")
        ax.set_title(title, loc="left", fontsize=9)
        ax.legend(frameon=False, fontsize=7.2, loc="upper right")
    axes[-1].set_xlabel("Gap between consecutive observation instants (h)")
    axes[-1].set_xticks(np.arange(0, xmax + 1, 1 if xmax <= 16 else 2))
    fig.suptitle(f"{c.name}:\nupdate gaps from T0 ({c.t0:%d Aug %H:%M} UTC) to T_END "
                 f"({c.t_end:%d Aug %H:%M} UTC)", x=0.02, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(f"{c.fig_dir}/02_gap_histograms.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def fig03_growth(c):
    d = c.inst[(c.inst.scope == "event_member") & (c.inst.time_utc >= c.start)]
    f, s = d[d.source == "FIRMS"], d[d.source == "LSASAF"]
    panels = [(f, "total_frp_mw", "FIRMS FRP\nper pass (MW)", "baseline"),
              (s, "total_frp_mw", "SEVIRI FRP\nper slot (MW)", "context"),
              (f, "extent_km", "FIRMS extent\nper pass (km)", "baseline"),
              (s, "extent_km", "SEVIRI extent\nper slot (km)", "context")]
    fig, axes = plt.subplots(4, 1, figsize=(8.5, 6.8), sharex=True)
    for i, (ax, (df, col, ylab, role)) in enumerate(zip(axes, panels)):
        if role == "baseline":
            ax.scatter(df.time_utc, df[col], s=28, color=ROLE_COLOR[role], edgecolor="white", lw=0.8, zorder=3)
        else:
            ax.plot(df.time_utc, df[col], ls="", marker="o", ms=2.3, color=ROLE_COLOR[role])
        ax.set_ylabel(ylab)
        ax.set_ylim(bottom=0)
        time_axis(ax, c)
        event_lines(ax, c, label=(i == 0))
    axes[-1].set_xlabel("Time (UTC)")
    fig.suptitle(f"{c.name}:\ngrowth proxy from event pixels (magnitudes not comparable between sensors)",
                 x=0.02, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(f"{c.fig_dir}/03_growth_proxy.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def footprints(df):
    """One square patch per detection; pixel_size_km is the side length (schema v2)."""
    dlat = df.pixel_size_km / KM_PER_DEG
    dlon = df.pixel_size_km / (KM_PER_DEG * np.cos(np.radians(df.latitude)))
    return [Rectangle((lo - w / 2, la - h / 2), w, h)
            for la, lo, h, w in zip(df.latitude, df.longitude, dlat, dlon)]


def fig04_map(c):
    reg = load_registry()
    keep = lambda d: d[d.in_search_box & d.qc_flag.isin(reg["conventions"]["qc_keep"])
                       & (d.static_proxy.astype(str) != "True")
                       & (pd.to_datetime(d.obs_time_utc, utc=True) >= c.ignition
                          - pd.Timedelta(minutes=c.ev["ignition_tolerance_min"]))]
    f = keep(pd.read_csv(FIRMS_FILE.format(event=c.id), dtype={"static_proxy": str}))
    s = keep(pd.read_csv(SEVIRI_FILE.format(event=c.id), dtype={"static_proxy": str}))
    b, e = c.ev["search_box"], c.extent
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1, 1, 0.9]})
    aspect = 1 / np.cos(np.radians((b["lat_min"] + b["lat_max"]) / 2))
    for ax, df, role, title in [(axes[0], f, "baseline", "FIRMS VIIRS + MODIS"),
                                (axes[1], s, "context", "LSA SAF SEVIRI")]:
        mem = df.event_member
        ax.add_collection(PatchCollection(footprints(df[~mem]), facecolor=OTHER, edgecolor="none", alpha=0.25))
        ax.add_collection(PatchCollection(footprints(df[mem]), facecolor=ROLE_COLOR[role],
                                          edgecolor="none", alpha=0.35))
        ax.set_xlim(b["lon_min"], b["lon_max"])
        ax.set_ylim(b["lat_min"], b["lat_max"])
        ax.add_patch(Rectangle((e["lon_min"], e["lat_min"]), e["lon_max"] - e["lon_min"],
                               e["lat_max"] - e["lat_min"], fill=False, ec=INK, lw=1))
        ax.set_title(f"{title}: {mem.sum()} event / {(~mem).sum()} other detections", loc="left", fontsize=8.5)
    z = axes[2]
    zb = dict(lat_min=e["lat_min"] - ZOOM_PAD_DEG, lat_max=e["lat_max"] + ZOOM_PAD_DEG,
              lon_min=e["lon_min"] - ZOOM_PAD_DEG, lon_max=e["lon_max"] + ZOOM_PAD_DEG)
    inz = lambda d: (d.latitude.between(zb["lat_min"], zb["lat_max"])
                     & d.longitude.between(zb["lon_min"], zb["lon_max"]) & d.event_member)
    sz = s[inz(s)].drop_duplicates(["latitude", "longitude"])
    z.add_collection(PatchCollection(footprints(sz), facecolor="none", edgecolor=ROLE_COLOR["context"], lw=0.8))
    z.add_collection(PatchCollection(footprints(f[inz(f)]), facecolor=ROLE_COLOR["baseline"],
                                     edgecolor="none", alpha=0.35))
    z.add_patch(Rectangle((e["lon_min"], e["lat_min"]), e["lon_max"] - e["lon_min"],
                          e["lat_max"] - e["lat_min"], fill=False, ec=INK, lw=1, ls="--"))
    z.set_xlim(zb["lon_min"], zb["lon_max"])
    z.set_ylim(zb["lat_min"], zb["lat_max"])
    z.set_title("Zoom: FIRMS event bounding box (dashed)", loc="left", fontsize=8.5)
    for ax in axes:
        ax.set_aspect(aspect)
        ax.set_xlabel("Longitude (deg E)")
        ax.grid(alpha=0.5)
    axes[0].set_ylabel("Latitude (deg N)")
    handles = [Rectangle((0, 0), 1, 1, fc=ROLE_COLOR["baseline"], alpha=0.5,
                         label=f"FIRMS event pixel (side {f.pixel_size_km.min():.1f} to {f.pixel_size_km.max():.1f} km)"),
               Rectangle((0, 0), 1, 1, fc=ROLE_COLOR["context"], alpha=0.5,
                         label=f"SEVIRI event pixel (side {s.pixel_size_km.min():.1f} to {s.pixel_size_km.max():.1f} km)"),
               Rectangle((0, 0), 1, 1, fc=OTHER, alpha=0.5, label="other fires in search box"),
               Rectangle((0, 0), 1, 1, fc="none", ec=INK, label="FIRMS event bounding box")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle(f"{c.name}:\ndetections in the search box from the earliest accepted time to end of data "
                 "(equal-area square footprints)", x=0.02, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(f"{c.fig_dir}/04_map.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    args = event_arg("event figures")
    c = Ctx(args.event)
    fig01_timeline(c)
    fig02_gaps(c)
    fig03_growth(c)
    fig04_map(c)
    print("figures written to", c.fig_dir)
