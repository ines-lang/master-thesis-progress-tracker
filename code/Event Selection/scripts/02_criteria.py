"""Step 2.2: apply the selection criteria in order and rank the remaining complexes per continent.

Criteria (Strategy v3.0, decisions of 3 Nov 2026):
  1. vegetation fire: less than MAX_NON_VEGETATION of the cluster's detections flagged volcano / static / flare
  2. onset inside the window: first kept detection at least ONSET_MARGIN_H after the data window start
  3. size: FIRMS burned-area proxy of at least MIN_AREA_HA (the Spanish GIF threshold); a filter only, since the
     proxy misses burning after the FIRMS data end
  4. spreading fire, not a point source (gas flares): extent >= MIN_EXTENT_KM and >= MIN_CELLS cells of 0.01 deg
  5. hemisphere and continent rule: every complex south of the equator excluded (austral winter: dry-season
     clearing, agricultural or prescribed burning; no officially recorded wildfire in South America or Oceania);
     Asia restricted to Siberia / Russian Far East (ASIA_BOX)
The complexes are listed by FIRMS area and joined with notes/candidates_ground_truth.csv; the selection itself
(made in the ground-truth file) is the largest OFFICIAL final burned area among candidates with an official ignition time.

Outputs (processed/): complexes_criteria.csv (all complexes with one flag per criterion), criteria_funnel.csv, ranking.csv (top TOP_N per continent after criteria 1 to 4)
Usage: python scripts/02_criteria.py
"""
import sys
from pathlib import Path

import pandas as pd

ES_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ES_DIR.parent / "Input Data FIRMS" / "scripts"))
from lib.registry import load_registry, utc  # noqa: E402

# ---- parameters ----
MAX_NON_VEGETATION = 0.5
ONSET_MARGIN_H = 24
MIN_AREA_HA = 500
MIN_EXTENT_KM = 5.0
MIN_CELLS = 20
TOP_N = 8
SOUTH_REASON = "southern hemisphere (austral winter)"
ASIA_BOX = {"lat_min": 50.0, "lon_min": 60.0}          # Siberia / Russian Far East (decision 1)
CONTINENTS = ["Europe", "North America", "Africa", "Asia", "South America", "Oceania"]
OUT = ES_DIR / "processed"

reg = load_registry()
start = utc(reg["data_window"]["start_utc"])
firms_end = utc(reg["data_window"]["firms_data_end_utc"])
cx = pd.read_csv(OUT / "complexes.csv", parse_dates=["first_utc", "last_utc"])
gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv")
matches = pd.read_csv(OUT / "candidate_matches.csv")[["candidate_id", "cluster_id"]].dropna()

# 1 to 4: flags, one per criterion
cx["c1_vegetation"] = cx["share_non_vegetation"] < MAX_NON_VEGETATION
cx["c2_onset_in_window"] = cx["first_utc"] >= start + pd.Timedelta(hours=ONSET_MARGIN_H)
cx["c3_size"] = cx["firms_area_ha"] >= MIN_AREA_HA
cx["c4_spreading"] = (cx["extent_km"] >= MIN_EXTENT_KM) & (cx["cells"] >= MIN_CELLS)
cx["c5_continent_rule"] = (cx["lat"] >= 0) & (
    (cx["continent"] != "Asia") | ((cx["lat"] >= ASIA_BOX["lat_min"]) & (cx["lon"] >= ASIA_BOX["lon_min"])))

cx.to_csv(OUT / "complexes_criteria.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ", float_format="%.4f")

steps = [("all complexes", None), ("1. vegetation fire", "c1_vegetation"),
         ("2. onset inside the window", "c2_onset_in_window"), ("3. size", "c3_size"),
         ("4. spreading fire", "c4_spreading"), ("5. northern hemisphere; Asia: Siberia / Far East", "c5_continent_rule")]
funnel, mask = [], pd.Series(True, index=cx.index)
for label, col in steps:
    if col:
        mask &= cx[col]
    funnel.append({"step": label, **cx[mask].groupby("continent").size().reindex(CONTINENTS, fill_value=0).to_dict()})
funnel = pd.DataFrame(funnel)
funnel.to_csv(OUT / "criteria_funnel.csv", index=False)

# ranking after criteria 1 to 3; complexes that also pass criteria 4 and 5 come first, so excluded
# continents stay visible and Asia shows its Siberian complexes first
ok = cx[cx["c1_vegetation"] & cx["c2_onset_in_window"] & cx["c3_size"]].copy()
ok["passes_all"] = ok["c4_spreading"] & ok["c5_continent_rule"]
ok = ok.sort_values(["c5_continent_rule", "c4_spreading", "firms_area_ha"], ascending=False)
ok["rank_in_continent"] = ok.groupby("continent").cumcount() + 1
top = ok[ok["rank_in_continent"] <= TOP_N]
named = ok.merge(matches, on="cluster_id")                           # candidates outside the top N are kept too
top = pd.concat([top, named.drop(columns="candidate_id")]).drop_duplicates("cluster_id")
top = top.merge(matches, on="cluster_id", how="left").merge(
    gt[["candidate_id", "name", "ignition_utc", "ignition_kind", "size_ha", "level", "decision", "reason"]], on="candidate_id",
    how="left").rename(columns={"size_ha": "official_area_ha"})
top["decision"] = top["decision"].fillna("no ground truth")
top.loc[~top["c5_continent_rule"] & (top["decision"] == "no ground truth"), "decision"] = "excluded"
point = ~top["c4_spreading"] & top["decision"].isin(["no ground truth", "to check"])
top.loc[point, "decision"] = "excluded"
top.loc[point, "reason"] = "point source (likely gas flare)"
top.loc[(top["lat"] < 0) & top["reason"].isna(), "reason"] = SOUTH_REASON
top.loc[(top["continent"] == "Asia") & ~top["c5_continent_rule"] & top["reason"].isna(), "reason"] = "outside Siberia / Far East"
top["reason"] = top["reason"].fillna("no official ignition record found")
top["hours_after_window_start"] = ((top["first_utc"] - start).dt.total_seconds() / 3600).round(1)
top = top.sort_values(["continent", "rank_in_continent"])
cols = ["continent", "rank_in_continent", "cluster_id", "name", "firms_area_ha", "official_area_ha", "detections", "viirs",
        "frp_sum_mw", "extent_km",
        "cells", "active_days", "first_utc", "last_utc", "lat", "lon", "c4_spreading", "c5_continent_rule", "ignition_utc", "ignition_kind", "level",
        "decision", "reason"]
top[cols].to_csv(OUT / "ranking.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ", float_format="%.2f")

# ---- report ----
print(f"window start {start:%Y-%m-%dT%H:%MZ}, onset from {start + pd.Timedelta(hours=ONSET_MARGIN_H):%Y-%m-%dT%H:%MZ}, "
      f"FIRMS end {firms_end:%Y-%m-%dT%H:%MZ}")
print("\ncriteria funnel (complexes per continent):\n" + funnel.to_string(index=False))
pd.set_option("display.width", 220)
print("\n" + top[["continent", "rank_in_continent", "name", "firms_area_ha", "official_area_ha", "first_utc", "lat", "lon",
                   "decision"]]
      .to_string(index=False))
