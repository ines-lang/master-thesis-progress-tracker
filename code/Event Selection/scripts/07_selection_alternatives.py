"""Step 2.7: two alternative figures for the event selection (to replace 02_top_by_continent.png, choice pending).

alt_B_candidates_official_area.png   vertical bars: every candidate with an official final area, grouped by continent
                                      and sorted by it (the selection rule); tick: FIRMS estimate up to 15 Aug
alt_C_selection_funnel.png           flow from all FIRMS fire complexes to the seven events, with the number removed
                                      and the reason at every step
Counts come from processed/complexes_criteria.csv, processed/ranking.csv and notes/candidates_ground_truth.csv.

Usage: python scripts/07_selection_alternatives.py
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch

ES_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ES_DIR.parent / "Input Data FIRMS" / "scripts"))
from lib.plotting import DPI, INK, INK_2, MUTED  # noqa: E402

PROC, FIGS = ES_DIR / "processed", ES_DIR / "figures"
COLOR = {"selected": "#2a78d6", "alternative": "#eb6834", "not selected": "#c9c8c1"}
GROUPS = [("Europe", "four largest"), ("North America", "largest"), ("Africa", "only candidate")]
SHORT = {"Molezuelas de la Carballeda, Zamora": "Molezuelas, Zamora", "Oimbra - A Granxa, Ourense": "Oimbra, Ourense",
         "Orallo - Genestoso, Leon": "Orallo, Leon", "Barniedo de la Reina, Leon": "Barniedo, Leon",
         "Anllares del Sil, Leon": "Anllares, Leon"}

ranking = pd.read_csv(PROC / "ranking.csv")
complexes = pd.read_csv(PROC / "complexes_criteria.csv")
gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv")


# ---------------- B: candidates by official area ----------------
def alt_b():
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    x, ticks, labels = 0, [], []
    for cont, rule in GROUPS:
        r = ranking[(ranking.continent == cont) & ranking.official_area_ha.notna()]
        r = r.sort_values("official_area_ha", ascending=False)
        x0 = x
        for row in r.itertuples():
            ax.bar(x, row.official_area_ha, width=0.75, color=COLOR[row.decision], zorder=2)
            ax.plot([x - 0.38, x + 0.38], [row.firms_area_ha] * 2, color=INK, lw=1.4, zorder=3)
            ticks.append(x)
            labels.append(SHORT.get(row.name, row.name))
            x += 1
        mid = (x0 + x - 1) / 2
        ax.annotate(f"{cont}\nkeeps the {rule}" if rule != "only candidate" else f"{cont}\nonly candidate",
                    (mid, 1.0), xycoords=("data", "axes fraction"), ha="center", va="bottom", fontsize=7.5, color=INK)
        if cont != GROUPS[-1][0]:
            ax.axvline(x - 0.5 + 0.5, color=MUTED, lw=0.6, ls=(0, (2, 2)))
        x += 1
    ax.set_xticks(ticks, labels, rotation=55, ha="right", fontsize=6.5)
    ax.set_ylabel("Burned area (ha)")
    ax.grid(axis="x", visible=False)
    ax.set_xlim(-0.8, x - 1.2)
    handles = [Patch(color=COLOR[k], label=k.capitalize()) for k in COLOR]
    handles.append(Line2D([], [], color=INK, lw=1.4, label="FIRMS estimate up to 15 Aug"))
    ax.legend(handles=handles, loc="upper right", fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(FIGS / "alt_B_candidates_official_area.png", dpi=DPI)
    plt.close(fig)


# ---------------- C: selection funnel ----------------
def alt_c():
    c = complexes
    m1 = c.c1_vegetation
    m2 = m1 & c.c2_onset_in_window
    m3 = m2 & c.c3_size
    m4 = m3 & c.c4_spreading
    m5 = m4 & c.c5_continent_rule
    examined = gt[~gt.decision.eq("excluded")]                  # candidates checked against official sources
    official = examined[examined.ignition_utc.notna()]
    chosen = official[official.decision.isin(["selected", "alternative"])]
    steps = [  # (box text, number left, removed text)
        ("1.69 M FIRMS detections, 8 to 15 Aug 2025\ngrouped into 1 km fire complexes", len(c), None),
        ("1  Vegetation fire", m1.sum(), "volcano or static source"),
        ("2  Onset inside the window (from 9 Aug)", m2.sum(), "burning before the window"),
        ("3  FIRMS area of at least 500 ha", m3.sum(), "smaller fires"),
        ("4  Spreading fire (5 km, 20 cells)", m4.sum(), "point sources, e.g. gas flares"),
        ("5  Northern hemisphere; Asia: Siberia / Far East", m5.sum(),
         "austral winter (S. America, S. Africa, Oceania);\nAsia outside Siberia"),
        ("Largest per continent checked against official sources", len(examined), "smaller, not checked"),
        ("Official ignition time and final area", len(official), "no official record (Balkans, Greece, NWT)"),
        ("Ranked by official final area per continent:\nEurope 4, North America 1 (+1 alternative), Africa 1",
         len(chosen), "smaller official area (e.g. Jarilla, Sleeper Ranch)"),
    ]
    fig, ax = plt.subplots(figsize=(9.5, 7.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.6, len(steps) - 0.2)
    ax.axis("off")
    prev = None
    for i, (text, n, removed) in enumerate(steps):
        y = len(steps) - 1 - i
        last = i == len(steps) - 1
        ax.add_patch(FancyBboxPatch((0.2, y - 0.32), 5.4, 0.64, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    facecolor="#2a78d6" if last else "#f3f2ee", edgecolor="none"))
        ax.text(0.4, y, text, va="center", fontsize=7.5, color="white" if last else INK)
        ax.text(5.45, y, f"{n:,}", va="center", ha="right", fontsize=9, fontweight="bold",
                color="white" if last else INK)
        if prev is not None:
            ax.annotate("", (2.9, y + 0.33), (2.9, y + 0.67), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=0.8))
            ax.annotate("", (6.0, y + 0.5), (5.65, y + 0.5), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=0.8))
            ax.text(6.1, y + 0.5, f"−{prev - n:,}  {removed}", va="center", fontsize=7, color=INK_2)
        prev = n
    ax.set_title("From all FIRMS fire complexes to the seven events: number left after each step and reason for "
                 "the rest", loc="left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGS / "alt_C_selection_funnel.png", dpi=DPI)
    plt.close(fig)
    return steps


alt_b()
for text, n, removed in alt_c():
    print(f"{n:>8,}  {text.splitlines()[0]}")
