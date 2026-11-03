"""Read FIRMS outputs (read-only) for the EFFIS checks.

Event members come from FIRMS v2 (`events/<id>/processed/event_observations.csv`,
column `event_member`). While FIRMS v2 has not produced them, an event that
already existed in v1 falls back to the frozen FIRMS v1 archive
(`archive_v1/processed/firms_clean.csv`, helper column `<event_id>_fire`).
The source used is always returned so it can be reported.
"""
import pandas as pd

from registry import FIRMS_DIR

FIRMS_V1_CLEAN = FIRMS_DIR / "archive_v1" / "processed" / "firms_clean.csv"
TILE_CACHE_DIR = FIRMS_DIR / "processed" / "tile_cache"
COLS = ["latitude", "longitude", "obs_time_utc", "platform"]


def firms_event_file(event_id, name):
    """FIRMS v2 per-event output: events/<event_id>/processed/<name>."""
    return FIRMS_DIR / "events" / event_id / "processed" / name


def load_event_detections(event_id):
    """FIRMS detections with an `event_member` column, and a label of the source used."""
    v2 = firms_event_file(event_id, "event_observations.csv")
    if v2.exists():
        df = pd.read_csv(v2, usecols=COLS + ["event_member"])
        source = f"FIRMS v2 {v2.relative_to(FIRMS_DIR)}"
    else:
        flag = f"{event_id}_fire"
        header = pd.read_csv(FIRMS_V1_CLEAN, nrows=0).columns
        if flag not in header:
            raise SystemExit(f"no FIRMS members for '{event_id}': {v2} missing and no v1 column '{flag}'. "
                             "Wait for FIRMS v2.")
        df = pd.read_csv(FIRMS_V1_CLEAN, usecols=COLS + [flag]).rename(columns={flag: "event_member"})
        source = f"FIRMS v1 archive (fallback until FIRMS v2): {FIRMS_V1_CLEAN.relative_to(FIRMS_DIR)}, column {flag}"
    df["obs_time_utc"] = pd.to_datetime(df["obs_time_utc"], utc=True)
    df["event_member"] = df["event_member"].astype(str).str.lower().eq("true")
    return df, source


def load_event_passes(event_id):
    """FIRMS v2 passes with at least one event member, or None if not produced yet."""
    path = firms_event_file(event_id, "event_overpasses.csv")
    return (pd.read_csv(path), path) if path.exists() else (None, path)


def firms_overpasses_file(region_id):
    """FIRMS passes over one region: processed/<region_id>/overpasses.csv."""
    return FIRMS_DIR / "processed" / region_id / "overpasses.csv"


def load_overpasses(region_id):
    """All FIRMS passes over one region (event-agnostic)."""
    return pd.read_csv(firms_overpasses_file(region_id), parse_dates=["start_time_utc", "end_time_utc"])
