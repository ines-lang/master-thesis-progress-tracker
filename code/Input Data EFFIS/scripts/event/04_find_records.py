"""List candidate EFFIS records for an event (report only; the user chooses the set).

Run:
  python scripts/event/04_find_records.py --event <id> --provinces P [P ...]
      --start-from ISO --start-to ISO --communes C [C ...] [--name-parts S [S ...]]

The search parameters are not in the registry yet, so they are passed on the
command line (taken from the strategy file) and printed. Matching is accent- and
case-insensitive; EFFIS names "Rúa, A" are read as "A Rúa".
--communes: exact municipality names. --name-parts: substrings (e.g. a valley
name that is part of several municipality names). No geocoding.
Writes events/<id>/processed/effis_candidates.csv.
"""
import argparse
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from registry import REPO_DIR, event_dir, get_event, utc  # noqa: E402

import pandas as pd

# ---- parameters (script level) ----
EVENTS_FILE = REPO_DIR / "processed" / "effis_events_es.csv"
COINCIDENCE_FILE = REPO_DIR / "processed" / "effis_overpass_coincidence.csv"
LARGE_AREA_QUANTILE = 0.95
LONG_DURATION_DAYS = 7


def norm(name):
    """'Castrocalbón' -> 'castrocalbon'; 'Rúa, A' -> 'a rua'."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().strip()
    if ", " in name:
        base, article = name.rsplit(", ", 1)
        name = f"{article} {base}"
    return name


p = argparse.ArgumentParser()
p.add_argument("--event", required=True)
p.add_argument("--provinces", nargs="+", required=True)
p.add_argument("--start-from", required=True)
p.add_argument("--start-to", required=True)
p.add_argument("--communes", nargs="+", required=True)
p.add_argument("--name-parts", nargs="*", default=[])
a = p.parse_args()
reg, ev = get_event(a.event)
t_from, t_to = utc(a.start_from), utc(a.start_to)
registry_ids = [str(i) for i in (ev.get("effis_ids") or ev.get("effis_candidate_ids") or [])]

es = pd.read_csv(EVENTS_FILE, dtype={"effis_id": str}, parse_dates=["start_date", "last_update"])
coin = pd.read_csv(COINCIDENCE_FILE, dtype={"effis_id": str})
es = es.merge(coin[["effis_id", "gap_to_nearest_pass_min", "platforms_within_window"]], on="effis_id")
area_limit = es["area_ha"].quantile(LARGE_AREA_QUANTILE)

prov_ok = es["province"].map(norm).isin({norm(x) for x in a.provinces})
print(f"provinces in data matching {a.provinces}: {sorted(es.loc[prov_ok, 'province'].unique())}")
in_prov = es[prov_ok].copy()
communes = {norm(c) for c in a.communes}
parts = [norm(s) for s in a.name_parts]
in_prov["commune_norm"] = in_prov["commune"].map(norm)
in_prov["match_commune"] = in_prov["commune_norm"].isin(communes)
in_prov["match_name_part"] = in_prov["commune_norm"].map(lambda c: any(s in c for s in parts))
in_prov["registry_candidate"] = in_prov["effis_id"].isin(registry_ids)
in_prov["in_start_window"] = in_prov["start_date"].between(t_from, t_to)
in_prov["flag_large_area"] = in_prov["area_ha"] > area_limit
in_prov["flag_long_duration"] = in_prov["duration_days"] > LONG_DURATION_DAYS

cand = in_prov[in_prov["in_start_window"]].sort_values("area_ha", ascending=False)
# named-area records outside the start window are shown too, so nothing is missed
named_outside = in_prov[~in_prov["in_start_window"] & (in_prov["match_commune"] | in_prov["match_name_part"]
                                                       | in_prov["registry_candidate"])]

show = ["effis_id", "province", "commune", "start_date", "last_update", "duration_days", "area_ha",
        "registry_candidate", "match_commune", "match_name_part", "flag_large_area", "flag_long_duration",
        "gap_to_nearest_pass_min", "platforms_within_window"]
fmt = {"start_date": lambda t: t.strftime("%m-%dT%H:%MZ"), "last_update": lambda t: t.strftime("%m-%dT%H:%MZ")}
pd.set_option("display.width", 250)
print(f"search: {a.provinces}, start {t_from:%Y-%m-%dT%H:%MZ} to {t_to:%Y-%m-%dT%H:%MZ}, "
      f"communes {a.communes}, name parts {a.name_parts}; registry ids {registry_ids}")
print(f"\nrecords in the provinces: {len(in_prov)}; in the start window: {len(cand)}")
print(cand[show].to_string(index=False, formatters=fmt))
print(f"\nnamed-area or registry records OUTSIDE the start window: {len(named_outside)}")
if len(named_outside):
    print(named_outside[show].to_string(index=False, formatters=fmt))
print(f"\nthresholds: large area > {area_limit:,.0f} ha, long duration > {LONG_DURATION_DAYS} d")

hi = cand[cand["registry_candidate"] | cand["match_commune"] | cand["match_name_part"]]
print(f"\nhighlighted candidates (all attributes): {len(hi)}")
print(hi.drop(columns=["commune_norm"]).set_index("effis_id").T.to_string())

out = pd.concat([cand, named_outside]).drop(columns=["commune_norm"])
out_file = event_dir(a.event, "processed") / "effis_candidates.csv"
out.to_csv(out_file, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
print(f"\nwritten {out_file.relative_to(REPO_DIR)}")
