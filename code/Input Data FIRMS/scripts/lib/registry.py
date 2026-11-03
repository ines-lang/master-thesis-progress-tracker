"""Read-only access to the shared event registry (events_registry.yaml).

Event parameters come only from the registry; scripts never hard-code them.
"""
import argparse
from pathlib import Path

import pandas as pd
import yaml

REGISTRY_FILE = Path(__file__).resolve().parents[3] / "events_registry.yaml"   # .../code/events_registry.yaml


def load_registry(path=REGISTRY_FILE):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def utc(value):
    """Registry time string ("2025-08-13T16:55:00Z") to a UTC pandas Timestamp."""
    return pd.Timestamp(value).tz_convert("UTC") if pd.Timestamp(value).tzinfo else pd.Timestamp(value, tz="UTC")


def get_event(event_id, registry=None):
    registry = registry or load_registry()
    if event_id not in registry["events"]:
        raise KeyError(f"event '{event_id}' not in registry; available: {list(registry['events'])}")
    return registry["events"][event_id]


def region_arg():
    """--region (id from the registry `regions`) for scripts/common/*.py; returns (region_id, region entry)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, help="region id from events_registry.yaml")
    region_id = parser.parse_args().region
    regions = load_registry()["regions"]
    if region_id not in regions:
        raise KeyError(f"region '{region_id}' not in registry; available: {list(regions)}")
    return region_id, regions[region_id]


if __name__ == "__main__":
    reg = load_registry()
    print(f"registry: {REGISTRY_FILE} (schema_version {reg['schema_version']})")
    print("\ndata_window:", reg["data_window"])
    print("regions:", reg["regions"])
    print("\nconventions:")
    for k, v in reg["conventions"].items():
        print(f"  {k}: {v}")
    for eid, ev in reg["events"].items():
        print(f"\nevent '{eid}': {ev['name']} [{ev['status']}]")
        for k in ["region", "t0_reference", "ignition_utc", "ignition_tolerance_min", "reference_point",
                  "seed_radius_km", "search_box"]:
            print(f"  {k}: {ev[k]}")
        if "regression_expected" in ev:
            print("  regression_expected:", ev["regression_expected"])
        if "known_context" in ev:
            print("  known_context:")
            for c in ev["known_context"]:
                print(f"    - {c}")
