"""Step 4: downlink latency of the S1 EO layer over the selected events, per ground-station set.

For every S1 satellite, every pass with the event inside the instrument swath (reference time to +24 h) is found;
for each pass, the time to the first contact (elevation >= MIN_ELEVATION_DEG) with a station of each set is
computed. Zero means a station sees the satellite while it observes the fire (direct readout possible).
Inputs:  processed/eo_census.csv (S1 TLEs), notes/ground_stations.csv (station sets; column satellites = the
         satellites a station serves, "all" for every satellite),
         ../Event Selection/notes/candidates_ground_truth.csv (event location and reference time)
Outputs: processed/ground_contacts.csv (one row per pass and station set), figures/02_downlink_latency.png

Usage: python scripts/03_ground_contacts.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

# ---- parameters ----
CENSUS_DIR = Path(__file__).resolve().parents[1]
PROC, FIGS = CENSUS_DIR / "processed", CENSUS_DIR / "figures"
EVENTS = ["larouco", "molezuelas", "oimbra", "piodao", "red_canyon", "derdara"]
HALF_SWATH_KM = {"VIIRS": 3040 / 2, "MODIS": 2330 / 2, "SLSTR": 1400 / 2, "MERSI-II": 2900 / 2}  # Month 2 Table; MERSI-II OSCAR
HORIZON_H = 24                      # passes from the reference time to +24 h
LOOKAHEAD_H = 6                     # search window for the next ground contact after a pass
STEP_S = 30
MIN_ELEVATION_DEG = 10              # Month 2 mask
RELAY = {"Terra"}                   # downlinks through TDRSS relays: not representable with direct-view stations
EARTH_RADIUS_KM = 6371.0
DPI = 300

ts = load.timescale()
census = pd.read_csv(PROC / "eo_census.csv")
s1 = census[(census["role"] == "S1 EO layer") & ~census["mission"].isin(RELAY)]
stations = pd.read_csv(CENSUS_DIR / "notes" / "ground_stations.csv")
gt = pd.read_csv(CENSUS_DIR.parent / "Event Selection" / "notes" / "candidates_ground_truth.csv").set_index("candidate_id")


def ground_distance_km(lat1, lon1, lat2, lon2):
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
    return EARTH_RADIUS_KM * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1))


rows = []
for ev in EVENTS:
    e = gt.loc[ev]
    t_ref = pd.Timestamp(e["ignition_utc"])
    secs = np.arange(0, (HORIZON_H + LOOKAHEAD_H) * 3600, STEP_S)
    t = ts.from_datetimes((t_ref + pd.to_timedelta(secs, unit="s")).to_pydatetime())
    for sat_row in s1.itertuples():
        sat = EarthSatellite(sat_row.line1, sat_row.line2, sat_row.mission, ts)
        sub = wgs84.subpoint_of(sat.at(t))
        d = ground_distance_km(e["lat"], e["lon"], sub.latitude.degrees, sub.longitude.degrees)
        inside = (d <= HALF_SWATH_KM[sat_row.instrument]) & (secs <= HORIZON_H * 3600)
        if not inside.any():
            continue
        # passes = runs of consecutive samples inside the swath; observation = closest approach of the run
        run_id = np.cumsum(np.diff(np.r_[0, inside.astype(int)]) == 1) * inside
        elev = {st.station: (sat - wgs84.latlon(st.lat, st.lon)).at(t).altaz()[0].degrees
                for st in stations.drop_duplicates("station").itertuples()}
        for r in np.unique(run_id[run_id > 0]):
            idx = np.flatnonzero(run_id == r)
            i_obs = idx[np.argmin(d[idx])]
            for set_name, members in stations.groupby("station_set", sort=False):
                serves = members["satellites"].eq("all") | members["satellites"].str.split(";").apply(
                    lambda sats: sat_row.mission in sats)
                best = None
                for st in members.loc[serves, "station"]:
                    vis = np.flatnonzero(elev[st][i_obs:] >= MIN_ELEVATION_DEG)
                    if vis.size and (best is None or vis[0] < best[0]):
                        best = (vis[0], st)
                rows.append(dict(event=ev, satellite=sat_row.mission, instrument=sat_row.instrument,
                                 obs_utc=t_ref + pd.Timedelta(seconds=int(secs[i_obs])),
                                 hours_after_reference=round(secs[i_obs] / 3600, 2),
                                 off_track_km=round(float(d[i_obs]), 0), station_set=set_name,
                                 first_station=best[1] if best else None,
                                 latency_min=round(best[0] * STEP_S / 60, 1) if best else np.nan))
gc = pd.DataFrame(rows)
gc.to_csv(PROC / "ground_contacts.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

# ---- report: per event and set, first observation and its latency, and the median over all passes ----
first = gc.sort_values("hours_after_reference").groupby(["event", "station_set"]).first()
summ = gc.groupby(["event", "station_set"])["latency_min"].agg(passes="size", median="median", max="max")
print(f"not modelled (relay downlink): {sorted(RELAY)}")
print(first[["satellite", "hours_after_reference", "latency_min", "first_station"]].join(summ).round(1).to_string())

# ---- figure: downlink latency of every pass, per event and station set ----
sets = list(stations["station_set"].unique())
fig_w = 9
fig, ax = plt.subplots(figsize=(fig_w, 3.8))
colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
for k, s in enumerate(sets):
    for j, ev in enumerate(EVENTS):
        v = gc[(gc.event == ev) & (gc.station_set == s)]["latency_min"].dropna()
        x = j + (k - (len(sets) - 1) / 2) * 0.25
        ax.scatter(np.full(len(v), x), v, s=12, color=colors[k], alpha=0.7, label=s if j == 0 else None)
        ax.plot([x - 0.08, x + 0.08], [v.median()] * 2, color=colors[k], lw=2)
ax.set_xticks(range(len(EVENTS)), [gt.loc[e, "name"].split(",")[0] for e in EVENTS], fontsize=7)
ax.set_ylabel("Observation to first\nground contact (min)")
ax.set_title(f"S1 passes over each event (reference to +{HORIZON_H} h, Terra excluded: TDRSS relay): downlink latency "
             f"per station set (elevation >= {MIN_ELEVATION_DEG} deg; line = median)", loc="left", fontsize=8)
ax.legend(fontsize=7, frameon=False)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
fig.tight_layout()
FIGS.mkdir(exist_ok=True)
fig.savefig(FIGS / "02_downlink_latency.png", dpi=DPI)
plt.close(fig)
print(f"\nwritten: {PROC / 'ground_contacts.csv'}, {FIGS / '02_downlink_latency.png'}")
