"""Step 2.3: overpasses of the FIRMS satellites over each timeline event, before and after the reference time.

FIRMS lists detections only, so a pass that saw no fire leaves no trace. Without it, the timelines cannot show
when each event was last observed without a fire. This step computes every pass with the event inside the
instrument swath from PRE_H hours before to POST_H hours after the reference time.

Input:   ../EO Census/processed/eo_census.csv (S1 TLEs, epoch 16 Aug 2025), notes/candidates_ground_truth.csv
Output:  processed/candidate_overpasses.csv   one row per pass: event, platform (FIRMS name), sensor,
                                              closest approach (UTC, hours from reference, off-track km)

TLE accuracy: one TLE per satellite, propagated back up to 6 days; SGP4 error stays at a few km per day, far
below the swath half-widths, and the pass times agree with the FIRMS acquisition times to within minutes.

Usage: python scripts/03_overpasses.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

# ---- parameters ----
ES_DIR = Path(__file__).resolve().parents[1]
PROC = ES_DIR / "processed"
CENSUS = ES_DIR.parent / "EO Census" / "processed" / "eo_census.csv"
EVENTS = ["piodao", "larouco", "molezuelas", "oimbra", "red_canyon", "mount_underwood", "derdara"]
FIRMS_PLATFORM = {"Suomi NPP": "Suomi-NPP", "NOAA-20": "NOAA-20", "NOAA-21": "NOAA-21",
                  "Terra": "Terra", "Aqua": "Aqua"}      # census name -> FIRMS platform name (Sentinel-3 not in FIRMS)
HALF_SWATH_KM = {"VIIRS": 3040 / 2, "MODIS": 2330 / 2}  # Month 2 Table, as in EO Census/03_ground_contacts.py
PRE_H, POST_H = 24, 54                                   # same span as the timeline figure, plus one day before
STEP_S = 20
EARTH_RADIUS_KM = 6371.0


def ground_distance_km(lat1, lon1, lat2, lon2):
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
    return EARTH_RADIUS_KM * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1))


ts = load.timescale()
census = pd.read_csv(CENSUS)
sats = census[census["mission"].isin(FIRMS_PLATFORM)]
gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv").set_index("candidate_id")

rows = []
for ev in EVENTS:
    e = gt.loc[ev]
    t_ref = pd.Timestamp(e["ignition_utc"])
    secs = np.arange(-PRE_H * 3600, POST_H * 3600, STEP_S)
    t = ts.from_datetimes((t_ref + pd.to_timedelta(secs, unit="s")).to_pydatetime())
    for s in sats.itertuples():
        sub = wgs84.subpoint_of(EarthSatellite(s.line1, s.line2, s.mission, ts).at(t))
        d = ground_distance_km(e["lat"], e["lon"], sub.latitude.degrees, sub.longitude.degrees)
        inside = d <= HALF_SWATH_KM[s.instrument]
        run_id = np.cumsum(np.diff(np.r_[0, inside.astype(int)]) == 1) * inside   # one run per pass
        for r in np.unique(run_id[run_id > 0]):
            idx = np.flatnonzero(run_id == r)
            i = idx[np.argmin(d[idx])]                                            # closest approach
            rows.append(dict(event=ev, platform=FIRMS_PLATFORM[s.mission], sensor=s.instrument,
                             pass_utc=t_ref + pd.Timedelta(seconds=int(secs[i])),
                             hours_from_reference=round(secs[i] / 3600, 3), off_track_km=int(round(d[i]))))

out = pd.DataFrame(rows).sort_values(["event", "pass_utc"])
out.to_csv(PROC / "candidate_overpasses.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

# ---- report: the last pass before each reference time ----
pre = out[out["hours_from_reference"] < 0].groupby("event").tail(1).set_index("event").loc[EVENTS]
print("last FIRMS-satellite pass before the reference time:")
print(pre[["platform", "pass_utc", "hours_from_reference", "off_track_km"]].to_string())
