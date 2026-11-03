"""Registry loader and repo paths. Event parameters come only from events_registry.yaml."""
import argparse
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]            # .../Input Data LSA SAF
THESIS = REPO.parent                                   # .../code
REGISTRY_PATH = THESIS / "events_registry.yaml"
FIRMS_EVENTS = THESIS / "Input Data FIRMS" / "events"
GEO_SOURCE = "lsasaf_msg0"                             # the registry geo_source this repo provides


def load_registry():
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def get_event(reg, event_id):
    if event_id not in reg["events"]:
        raise SystemExit(f"Event '{event_id}' not in registry. Known: {list(reg['events'])}")
    return reg["events"][event_id]


def get_region(reg, region_id):
    """Region entry; stops if the region does not use this repo's GEO source (SEVIRI, Meteosat 0 deg)."""
    if region_id not in reg["regions"]:
        raise SystemExit(f"Region '{region_id}' not in registry. Known: {list(reg['regions'])}")
    region = reg["regions"][region_id]
    if region["geo_source"] != GEO_SOURCE:
        raise SystemExit(f"Region '{region_id}' uses geo_source '{region['geo_source']}', not {GEO_SOURCE}: "
                         "not covered by this repo.")
    return region


def region_arg(reg):
    """--region for scripts/common/*.py; returns (region_id, region entry)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="region id from events_registry.yaml")
    region_id = ap.parse_args().region
    return region_id, get_region(reg, region_id)


def region_dir(region_id):
    """processed/<region_id>/ for region-level outputs, created if missing."""
    d = REPO / "processed" / region_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def utc(s):
    """Registry time string ('...Z') to a naive UTC pandas Timestamp."""
    return pd.Timestamp(s).tz_convert(None) if pd.Timestamp(s).tzinfo else pd.Timestamp(s)


def in_box(lat, lon, box, margin=0.0):
    return (lat.between(box["lat_min"] - margin, box["lat_max"] + margin)
            & lon.between(box["lon_min"] - margin, box["lon_max"] + margin))


def iso_z(ts):
    """Series of naive UTC timestamps to ISO 8601 strings with Z."""
    return ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
