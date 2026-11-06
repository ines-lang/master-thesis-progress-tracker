"""Step 1.1: every payload in orbit during the data window (8 to 16 Aug 2025), from Space-Track gp_history.

One query per day (Space-Track discourages one large gp_history query), only the fields needed.
Object types PAYLOAD and UNKNOWN: recently launched satellites are often still catalogued as "OBJECT A, B, ..."
with type UNKNOWN. An object counts as in orbit if it has at least one orbit record with an epoch inside the window.
Output: processed/window_payloads.csv, one row per payload: its last orbit record of the window
(NORAD id, name, country, launch date, epoch, inclination, mean motion, altitudes, orbit family, TLE lines).

Usage: python scripts/00_fetch_window.py
"""
import time

import pandas as pd

from spacetrack import CENSUS_DIR, logout, query, session

# ---- parameters ----
DAYS = pd.date_range("2025-08-08", "2025-08-16", freq="D")        # data window, one query per day
FIELDS = ("NORAD_CAT_ID,OBJECT_NAME,OBJECT_ID,COUNTRY_CODE,LAUNCH_DATE,EPOCH,INCLINATION,MEAN_MOTION,"
          "APOAPSIS,PERIAPSIS,TLE_LINE1,TLE_LINE2")
PAUSE_S = 3                                                         # Space-Track limit: 30 requests per minute
OUT_FILE = CENSUS_DIR / "processed" / "window_payloads.csv"


def orbit_family(incl, mean_motion, apo, peri):
    """Orbit class from the mean elements (screen convention)."""
    if 0.99 <= mean_motion <= 1.01 and incl < 20:
        return "GEO"
    if apo - peri > 2000:
        return "HEO"
    if mean_motion < 11.25:                                          # above about 2000 km
        return "MEO"
    if 95 <= incl <= 105:
        return "LEO polar"
    return "LEO other"


opener = session()
records = []
for day in DAYS:
    span = f"{day:%Y-%m-%d}--{day + pd.Timedelta(days=1):%Y-%m-%d}"
    got = query(opener, f"class/gp_history/OBJECT_TYPE/PAYLOAD,UNKNOWN/EPOCH/{span}/predicates/{FIELDS},OBJECT_TYPE/format/json")
    print(f"{day:%d %b}: {len(got)} orbit records")
    records += got
    time.sleep(PAUSE_S)
logout(opener)

df = pd.DataFrame(records)
df["EPOCH"] = pd.to_datetime(df["EPOCH"], utc=True)
for col in ["INCLINATION", "MEAN_MOTION", "APOAPSIS", "PERIAPSIS"]:
    df[col] = df[col].astype(float)
last = df.sort_values("EPOCH").groupby("NORAD_CAT_ID").tail(1)    # last record of the window per payload
out = pd.DataFrame({
    "norad_id": last["NORAD_CAT_ID"].astype(int), "name": last["OBJECT_NAME"], "object_id": last["OBJECT_ID"],
    "country": last["COUNTRY_CODE"], "launch_date": last["LAUNCH_DATE"], "object_type": last["OBJECT_TYPE"],
    "orbit_family": [orbit_family(*v) for v in zip(last.INCLINATION, last.MEAN_MOTION, last.APOAPSIS, last.PERIAPSIS)],
    "epoch_utc": last["EPOCH"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "records_in_window": last["NORAD_CAT_ID"].map(df.groupby("NORAD_CAT_ID").size()),
    "inclination_deg": last["INCLINATION"], "mean_motion_rev_day": last["MEAN_MOTION"],
    "apoapsis_km": last["APOAPSIS"], "periapsis_km": last["PERIAPSIS"],
    "line1": last["TLE_LINE1"], "line2": last["TLE_LINE2"]}).sort_values("norad_id")
OUT_FILE.parent.mkdir(exist_ok=True)
out.to_csv(OUT_FILE, index=False)
print(f"objects in orbit in the window: {len(out)}")
print(out["object_type"].value_counts().to_string())
print(out["orbit_family"].value_counts().to_string())
print(f"written: {OUT_FILE}")
