"""Load the shared event registry. Event values come ONLY from here, never from scripts.

Run directly to print the registry content used by the EFFIS repo:
    python scripts/lib/registry.py
"""
import argparse
from pathlib import Path

import pandas as pd
import yaml

# ---- paths ----
REPO_DIR = Path(__file__).resolve().parents[2]            # .../code/Input Data EFFIS
REGISTRY_FILE = REPO_DIR.parent / "events_registry.yaml"
FIRMS_DIR = REPO_DIR.parent / "Input Data FIRMS"


def load_registry():
    with open(REGISTRY_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def utc(value):
    """Registry time string ('...Z') to a UTC pandas Timestamp; None stays None."""
    return None if value is None else pd.Timestamp(value).tz_convert("UTC")


def get_event(event_id):
    reg = load_registry()
    if event_id not in reg["events"]:
        raise SystemExit(f"event '{event_id}' not in registry; known: {list(reg['events'])}")
    return reg, reg["events"][event_id]


def region_arg():
    """--region (id from the registry `regions`) for scripts/common/*.py; returns the region id."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    region_id = parser.parse_args().region
    if region_id not in load_registry()["regions"]:
        raise SystemExit(f"region '{region_id}' not in registry; known: {list(load_registry()['regions'])}")
    return region_id


def event_args():
    """Parse --event (required) and --records (user-confirmed EFFIS ids, only for events
    whose registry entry has no `effis_ids` yet) for scripts/event/*.py."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--records", nargs="+", default=None)
    # values not (yet) in the registry; passed explicitly, printed and proposed for the registry
    parser.add_argument("--area-refs", nargs="*", default=[], help='e.g. "Junta provisional=31500"')
    parser.add_argument("--reported-end", default=None, help="reported end of activity, ISO UTC")
    parser.add_argument("--neighbour-provinces", nargs="*", default=None)
    return parser.parse_args()


def effis_record_ids(ev, records_arg):
    """Registry `effis_ids` if present; otherwise the user-confirmed --records."""
    if ev.get("effis_ids"):
        if records_arg and sorted(records_arg) != sorted(map(str, ev["effis_ids"])):
            raise SystemExit(f"--records {records_arg} differs from registry effis_ids {ev['effis_ids']}")
        return [str(i) for i in ev["effis_ids"]], "registry effis_ids"
    if not records_arg:
        raise SystemExit(f"registry has no effis_ids (candidates: {ev.get('effis_candidate_ids')}); "
                         "pass the user-confirmed set with --records")
    return [str(i) for i in records_arg], "user-confirmed --records (registry has candidates only)"


def event_dir(event_id, sub):
    """events/<event_id>/<sub>/, created if missing."""
    d = REPO_DIR / "events" / event_id / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


if __name__ == "__main__":
    reg = load_registry()
    print(f"registry: {REGISTRY_FILE} (schema_version {reg['schema_version']})")
    print(f"data_window: {reg['data_window']}")
    print(f"regions: {reg['regions']}")
    print(f"overpass_window_min: {reg['conventions']['overpass_window_min']}")
    for eid, ev in reg["events"].items():
        print(f"\n[{eid}] {ev['name']}  status: {ev['status']}")
        for key in ["region", "t0_reference", "ignition_utc", "ignition_source", "ignition_tolerance_min", "reference_point",
                    "search_box", "effis_ids", "effis_candidate_ids", "official_area_ha", "official_area_source"]:
            if key in ev:
                print(f"  {key}: {ev[key]}")
        effis_keys = {k: v for k, v in ev.get("regression_expected", {}).items() if "effis" in k}
        if effis_keys:
            print(f"  regression_expected (EFFIS): {effis_keys}")
        for line in ev.get("known_context", []):
            print(f"  context: {line}")
