"""Gap statistics and onset helpers shared by the per-event and cross-event scripts."""

import numpy as np
import pandas as pd

GAP_PERCENTILE = 90


def distinct_times(times, start=None, end=None):
    """Sorted distinct instant times inside [start, end] (None = open)."""
    t = pd.Series(pd.to_datetime(times, utc=True))
    if start is not None:
        t = t[t >= start]
    if end is not None:
        t = t[t <= end]
    return pd.DatetimeIndex(np.sort(t.unique()))


def gaps_h(times, start=None, end=None):
    """Gaps (h) between consecutive distinct times, and the times they start at."""
    t = distinct_times(times, start, end)
    g = np.diff(t.values).astype("timedelta64[s]").astype(float) / 3600 if len(t) > 1 else np.array([])
    return g, t[:-1]


def gap_stats(times, start=None, end=None):
    """Median, mean, p90, max and the longest gap of the distinct times in [start, end]."""
    t = distinct_times(times, start, end)
    g, _ = gaps_h(t)
    out = dict(n_instants=len(t), first_instant_utc=t.min() if len(t) else pd.NaT,
               last_instant_utc=t.max() if len(t) else pd.NaT, n_gaps=len(g))
    if len(g) == 0:
        return {**out, "median_gap_h": np.nan, "mean_gap_h": np.nan, "p90_gap_h": np.nan,
                "max_gap_h": np.nan, "longest_gap_start_utc": pd.NaT, "longest_gap_end_utc": pd.NaT}
    i = int(np.argmax(g))
    return {**out, "median_gap_h": float(np.median(g)), "mean_gap_h": float(g.mean()),
            "p90_gap_h": float(np.percentile(g, GAP_PERCENTILE)), "max_gap_h": float(g[i]),
            "longest_gap_start_utc": t[i], "longest_gap_end_utc": t[i + 1]}


def robust_onset(slot_times, instant_times, slot_min=15, n_consecutive=2):
    """First instant of the first run of >= n_consecutive consecutive slots (registry convention)."""
    s = pd.DataFrame({"slot": pd.to_datetime(slot_times, utc=True),
                      "instant": pd.to_datetime(instant_times, utc=True)}).sort_values("slot")
    s = s.drop_duplicates("slot")
    new_run = s.slot.diff() != pd.Timedelta(minutes=slot_min)
    run_id = new_run.cumsum()
    run_len = s.groupby(run_id).slot.transform("size")
    ok = s[run_len >= n_consecutive]
    if ok.empty:
        return pd.NaT, pd.NaT
    first = ok.iloc[0]
    return first.slot, first.instant
