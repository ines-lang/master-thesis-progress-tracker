"""Load the shared event registry. Event values come ONLY from here, never from scripts."""

import argparse

import pandas as pd
import yaml

REGISTRY_FILE = "../events_registry.yaml"   # relative to the repo folder, like every path in these scripts


def load_registry(path=REGISTRY_FILE):
    with open(path) as f:
        return yaml.safe_load(f)


def utc(value):
    """Registry time string (ISO, Z) to a UTC Timestamp; None stays None."""
    return None if value is None else pd.Timestamp(value).tz_convert("UTC")


def get_event(event_id, registry=None):
    reg = registry or load_registry()
    if event_id not in reg["events"]:
        raise KeyError(f"event '{event_id}' not in registry: {list(reg['events'])}")
    return reg["events"][event_id]


def event_arg(description):
    """Common --event argument for the per-event scripts."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--event", required=True, help="event id from events_registry.yaml")
    return p.parse_args()
