# Event Selection

Selects one wildfire per continent igniting inside the data window (8 to 16 Aug 2025), for the T0 (first detection)
analysis. Rule: among complexes passing the screen, the largest **official final burned area** with an **official
ignition time** (T0 reference hierarchy: official ignition, otherwise the first geostationary detection).

Run everything: `bash run_event_selection.sh` (add `--query` to re-query WFIGS).

| Step | File | What it does |
|---|---|---|
| input | `../Input Data FIRMS/processed/world/` | Global FIRMS cleaning and 1 km clusters (`02_clean.py --region world`) |
| ground truth | `notes/candidates_ground_truth.csv` | One row per candidate: official ignition time, official area, source, verification level, **decision and reason** (edited by hand) |
| ground truth | `notes/ground_truth.md` | Official sources per continent and the research behind each row |
| 0 | `scripts/00_wfigs_query.py` | Official US discovery times (NIFC WFIGS) -> `processed/wfigs_candidates.csv` |
| 1 | `scripts/01_screen_firms.py` | One row per fire complex, FIRMS burned-area proxy, candidate matching -> `processed/complexes.csv`, `candidate_matches.csv`, `candidate_detections.csv` |
| 2 | `scripts/02_criteria.py` | Criteria 1 to 5, funnel, ranking -> `processed/complexes_criteria.csv`, `criteria_funnel.csv`, `ranking.csv` |
| 3 | `scripts/03_figures.py` | `figures/01` world map, `02` largest complexes per continent, `03` ignition to first detection, `04` official vs FIRMS area |

Criteria: 1 vegetation fire (< 50% flagged volcano / static), 2 onset at least 24 h after the window start,
3 FIRMS area >= 500 ha (filter only), 4 spreading (>= 5 km and >= 20 cells; removes gas flares),
5 northern hemisphere, Asia only Siberia / Russian Far East.

Figures for the report are copied by hand to `Latex/figures/event_selection_*.png`.
