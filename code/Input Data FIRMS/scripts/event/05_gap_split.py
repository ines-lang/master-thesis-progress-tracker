"""Descriptive gap statistics split at a cutoff time, and what the sensing layer saw during long gaps.

Usage: python scripts/event/05_gap_split.py --event <event_id> [--until 2025-08-12T14:57:00Z]
Reads events/<id>/processed/event_overpasses.csv and overpass_times_sensing_layer.csv.
Writes events/<id>/notes/gap_split.txt. Descriptive only; official statistics are computed in the Comparison repo.
"""
import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.event import event_dirs  # noqa: E402

LONG_GAP_H = 6.0

parser = argparse.ArgumentParser()
parser.add_argument("--event", required=True)
parser.add_argument("--until", default=None, help="cutoff (ISO UTC): passes up to and including it form the first phase")
args = parser.parse_args()
dirs = event_dirs(args.event)
ep = pd.read_csv(dirs["processed"] / "event_overpasses.csv", parse_dates=["first_member_utc"])
sl = pd.read_csv(dirs["processed"] / "overpass_times_sensing_layer.csv", parse_dates=["overpass_start_utc"])


def stats(gaps):
    return (f"n={len(gaps)}, median {gaps.median():.2f} h, p90 {np.percentile(gaps, 90):.2f} h, max {gaps.max():.2f} h"
            if len(gaps) else "n=0")


buf = io.StringIO()
with redirect_stdout(buf):
    print(f"event {args.event}: {len(ep)} passes with event members")
    print("all gaps:", stats(ep["gap_to_previous_h"].dropna()))
    if args.until:
        cut = pd.Timestamp(args.until)
        first = ep[ep["first_member_utc"] <= cut]
        print(f"phase 1 (first member to {args.until}, {len(first)} passes):", stats(first["gap_to_previous_h"].dropna()))
        later = ep[ep["first_member_utc"] > cut]
        print(f"after {args.until} ({len(later)} passes): gaps {later['gap_to_previous_h'].round(2).tolist()}")
    print(f"\ngaps > {LONG_GAP_H:g} h and the sensing-layer passes inside them (detections in the search box):")
    for i in ep.index[ep["gap_to_previous_h"] > LONG_GAP_H]:
        a, b = ep.loc[i - 1, "first_member_utc"], ep.loc[i, "first_member_utc"]
        inside = sl[(sl["overpass_start_utc"] > a) & (sl["overpass_start_utc"] < b) & ~sl["event_detected"]]
        print(f"  {ep.loc[i - 1, 'overpass_id']} {a:%Y-%m-%dT%H:%MZ} to {ep.loc[i, 'overpass_id']} {b:%Y-%m-%dT%H:%MZ}: "
              f"{ep.loc[i, 'gap_to_previous_h']:.2f} h; {len(inside)} sensing-layer passes saw other fires in the "
              f"search box but not the event")
    last = ep["first_member_utc"].max()
    after = sl[sl["overpass_start_utc"] > last]
    print(f"\nafter the last event pass ({last:%Y-%m-%dT%H:%MZ}): {len(after)} sensing-layer passes with search-box "
          f"detections, {int(after['event_detected'].sum())} with the event")

report = buf.getvalue()
print(report)
(dirs["notes"] / "gap_split.txt").write_text(report)
