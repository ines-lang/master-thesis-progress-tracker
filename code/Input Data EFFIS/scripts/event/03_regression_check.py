"""Regression check: v2 outputs versus v1 / registry expected values.

Run: python scripts/event/03_regression_check.py --event <event_id>

Expected values come from (1) registry `regression_expected` keys about EFFIS,
(2) the frozen v1 reference table archive_v1/processed/<event_id>_reference.csv
if it exists, (3) the v1 repo-level overpass coincidence share (V1_COINCIDENCE).
Writes events/<id>/processed/regression_check.csv.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from registry import REPO_DIR, event_args, event_dir, get_event, utc  # noqa: E402

import pandas as pd

# ---- parameters (script level) ----
V1_ARCHIVE = REPO_DIR / "archive_v1" / "processed"
COINCIDENCE_FILE = REPO_DIR / "processed" / "effis_overpass_coincidence.csv"
# v1 repo-level result (archive_v1/notes/effis_log.md, Step 4): 117 of 122 records, rounded 96 %
V1_COINCIDENCE = {"n_used": 122, "n_within": 117}

args = event_args()
reg, ev = get_event(args.event)
ref = pd.read_csv(event_dir(args.event, "processed") / "effis_reference.csv", dtype={"effis_id": str})
recs = ref[ref["effis_id"] != "TOTAL"]
total = ref[ref["effis_id"] == "TOTAL"].iloc[0]
rows = []


def check(item, expected, obtained, source):
    rows.append({"item": item, "expected": expected, "obtained": obtained,
                 "match": str(expected) == str(obtained), "expected_source": source})


# (1) registry
for key, value in ev.get("regression_expected", {}).items():
    if key == "effis_start_utc":
        check(key, value, total["start_utc"], "registry regression_expected")

# (2) frozen v1 reference table
v1_file = V1_ARCHIVE / f"{args.event}_reference.csv"
if v1_file.exists():
    v1 = pd.read_csv(v1_file, dtype={"effis_id": str}, parse_dates=["start_date", "last_update"]).iloc[0]
    src = f"archive_v1/processed/{v1_file.name}"
    check("effis_id", v1["effis_id"], ";".join(recs["effis_id"]), src)
    check("province / commune", f"{v1['province']} / {v1['commune']}",
          f"{recs['province'].iloc[0]} / {recs['commune'].iloc[0]}", src)
    check("start_utc", f"{v1['start_date']:%Y-%m-%dT%H:%M:%SZ}", total["start_utc"], src)
    check("last_update_utc", f"{v1['last_update']:%Y-%m-%dT%H:%M:%SZ}", total["last_update_utc"], src)
    check("area_ha", int(v1["area_ha"]), int(total["area_ha"]), src)
    check("has_geometry", bool(v1["has_geometry"]), bool(recs["has_geometry"].iloc[0]), src)

# (3) repo-level overpass coincidence
coin = pd.read_csv(COINCIDENCE_FILE)
coin = coin[coin["country"] == "ES"]   # v1 covered Spain only; PT and MA were added on 7 Nov 2026
used = coin[coin["excluded_reason"].isna()]
check("overpass coincidence (n within / n used)",
      f"{V1_COINCIDENCE['n_within']} / {V1_COINCIDENCE['n_used']}",
      f"{int(used['within_window'].sum())} / {len(used)}", "v1 log, Step 4")
check("overpass coincidence share (rounded %)",
      round(100 * V1_COINCIDENCE["n_within"] / V1_COINCIDENCE["n_used"]),
      round(100 * used["within_window"].mean()), "v1 log, Step 4")

out = pd.DataFrame(rows)
out_file = event_dir(args.event, "processed") / "regression_check.csv"
out.to_csv(out_file, index=False)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
print(f"\nall match: {out['match'].all()}  ({out['match'].sum()} of {len(out)})")
print(f"written {out_file.relative_to(REPO_DIR)}")
