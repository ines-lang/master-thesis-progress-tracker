"""Export the event-agnostic processed/<region_id>/observations_standard.csv in shared schema v2.

Usage: python scripts/common/04_export.py --region <region_id>
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.helpers import read_clean, region_dir  # noqa: E402
from lib.registry import region_arg  # noqa: E402
from lib.schema import SCHEMA_V2, check_and_write, firms_to_schema  # noqa: E402

if __name__ == "__main__":
    region_id, _ = region_arg()
    OUT_FILE = region_dir(region_id) / "observations_standard.csv"
    df = read_clean(region_id)
    obs = firms_to_schema(df).sort_values(["obs_time_utc", "platform", "latitude", "longitude"]).reset_index(drop=True)
    check_and_write(obs, OUT_FILE)
    print(f"{OUT_FILE.name}: {len(obs)} rows, columns = schema v2: {list(obs.columns) == SCHEMA_V2}")
    print(obs.groupby(["sensor", "platform", "role"]).size().to_string())
    print("qc_flag:", obs["qc_flag"].value_counts().to_dict())
    print("static_proxy:", obs["static_proxy"].value_counts().to_dict())
    print(f"time range: {obs['obs_time_utc'].min()} to {obs['obs_time_utc'].max()}")
