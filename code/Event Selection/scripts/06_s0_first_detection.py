"""Step 2.6: preliminary S0 first detection of every event, per public source, inside the official final perimeter.

Before the new events are added to the registry and run through the per-event pipelines, this step gives one
comparable number per event and source: the first fire pixel whose centre lies inside the official final perimeter
(buffered by BUFFER_KM) at or after the reference time minus TOLERANCE_H.

Membership by the official perimeter is NOT the FIRMS-cluster rule of the pipelines (registry conventions); it is used
here because it is the same, independent footprint for every source. A perimeter can also contain an earlier,
separate fire (Piodao: Aldeia das Dez); detections in the 24 h before the window are therefore counted and reported.

Perimeters (official final footprints):
    EFFIS burnt areas 2025 (WFS modis.ba.poly.2025)   larouco, molezuelas, oimbra, piodao, derdara
    NIFC WFIGS final perimeter                         red_canyon
    BC Wildfire Service historical fire polygons       mount_underwood
Sources: FIRMS VIIRS + MODIS (kept detections, as in the timeline figure), Sentinel-3 SLSTR (SL_2_FRP NTC),
SEVIRI (LSA SAF FRP-PIXEL, Europe and Africa), GOES-18 and GOES-19 (ABI FDC, North America).

Output: processed/s0_first_detection.csv
Usage: python scripts/06_s0_first_detection.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

# ---- parameters ----
ES_DIR = Path(__file__).resolve().parents[1]
CODE = ES_DIR.parent
PROC = ES_DIR / "processed"
BUFFER_KM = 2.0                 # registry seviri_membership_sensitivity_km; also covers the 1 km to 2 km pixel centres
TOLERANCE_H = 1.0               # detections up to 1 h before the reference count (registry molezuelas tolerance)
EARLIER_H = 24                  # window before that, reported as earlier activity inside the perimeter
EVENTS = ["larouco", "molezuelas", "oimbra", "piodao", "red_canyon", "mount_underwood", "derdara"]
EFFIS_IDS = {"larouco": "278475", "molezuelas": "277940", "oimbra": "278348", "piodao": "278350", "derdara": "278470"}
EFFIS_POLY = CODE / "Input Data EFFIS" / "raw" / "effis_ba_poly_2025_iberia_morocco.geojson"
NORTH_AMERICA = {"red_canyon", "mount_underwood"}   # GOES events; SEVIRI covers the others
OTHER_POLY = {"red_canyon": ES_DIR / "raw" / "perimeters" / "wfigs_red_canyon_2025-WYWBD-000254.geojson",
              "mount_underwood": ES_DIR / "raw" / "perimeters" / "bc_mount_underwood_V71498.geojson"}


def local_km(lat0, lon0):
    k = np.cos(np.radians(lat0))
    return lambda x, y: ((np.asarray(x) - lon0) * 111.32 * k, (np.asarray(y) - lat0) * 110.57)


def perimeters():
    effis = {f["properties"]["id"]: f for f in json.load(open(EFFIS_POLY))["features"]}
    feats = {ev: effis[i] for ev, i in EFFIS_IDS.items()}
    feats |= {ev: json.load(open(p))["features"][0] for ev, p in OTHER_POLY.items()}
    return {ev: shape(f["geometry"]) for ev, f in feats.items()}


def sources():
    """One table per source: event (if already cropped per event), time_utc, lat, lon."""
    f = pd.read_csv(PROC / "candidate_detections.csv", parse_dates=["obs_time_utc"])
    f = f[f.kept.astype(bool) & ~f.non_vegetation.astype(bool)]
    yield "FIRMS VIIRS + MODIS", f.rename(columns={"obs_time_utc": "time_utc", "latitude": "lat", "longitude": "lon"})
    s = pd.read_csv(CODE / "Input Data SLSTR" / "processed" / "slstr_fire_points.csv", parse_dates=["time_utc"])
    yield "Sentinel-3 SLSTR", s.drop(columns="event").drop_duplicates(["time_utc", "lat", "lon"])
    l = pd.read_csv(CODE / "Input Data LSA SAF" / "processed" / "iberia" / "observations_standard.csv",
                    parse_dates=["obs_time_utc"])
    l = l[(l.qc_flag == "ok") & (l.static_proxy != True)]  # noqa: E712  (column is empty or bool)
    yield "SEVIRI (LSA SAF)", l.rename(columns={"obs_time_utc": "time_utc", "latitude": "lat", "longitude": "lon"})
    goes_file = CODE / "Input Data GOES" / "processed" / "goes_fire_pixels.csv"
    if not goes_file.exists():
        print("GOES fire pixels not processed yet: skipped")
        return
    g = pd.read_csv(goes_file, parse_dates=["scan_start_utc"])
    g = g[g.confident].rename(columns={"scan_start_utc": "time_utc"}).drop(columns="event")
    for sat, gs in g.groupby("satellite"):
        yield f"{sat} (ABI FDC)", gs.drop_duplicates(["time_utc", "lat", "lon"])


gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv").set_index("candidate_id")
polys = perimeters()
rows = []
for name, src in sources():
    src = src.copy()
    src["time_utc"] = pd.to_datetime(src["time_utc"], utc=True)
    for ev in EVENTS:
        ref = pd.Timestamp(gt.loc[ev, "ignition_utc"])
        to_km = local_km(gt.loc[ev, "lat"], gt.loc[ev, "lon"])
        zone = shapely.transform(polys[ev], lambda c: np.column_stack(to_km(c[:, 0], c[:, 1]))).buffer(BUFFER_KM)
        if ("GOES" in name and ev not in NORTH_AMERICA) or ("SEVIRI" in name and ev in NORTH_AMERICA):
            continue                                        # outside the disk of that geostationary satellite
        near = src[(src.lat - gt.loc[ev, "lat"]).abs().lt(1) & (src.lon - gt.loc[ev, "lon"]).abs().lt(1.5)]
        x, y = to_km(near.lon.values, near.lat.values)
        inside = near[shapely.contains_xy(zone, x, y)]
        h = (inside.time_utc - ref).dt.total_seconds() / 3600
        after = h[h >= -TOLERANCE_H]
        rows.append(dict(event=ev, source=name, reference_utc=ref,
                         first_detection_utc=inside.time_utc[after.idxmin()] if len(after) else pd.NaT,
                         first_detection_h=round(after.min(), 2) if len(after) else np.nan,
                         n_detections_inside=int(len(after)),
                         n_earlier_inside=int(h.between(-TOLERANCE_H - EARLIER_H, -TOLERANCE_H, inclusive="left").sum())))
out = pd.DataFrame(rows)
out.to_csv(PROC / "s0_first_detection.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
print(out.pivot(index="event", columns="source", values="first_detection_h").loc[EVENTS].to_string())
