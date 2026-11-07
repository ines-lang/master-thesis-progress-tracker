"""Step 5: measured near-real-time (NRT) latency of the S1 fire products, split into downlink wait and processing.

The NRT files of the S1 fire products are kept online only for days (LANCE about 7 days, CDSE Sentinel-3 NR about
two weeks), so the August 2025 files are gone. The latency is therefore measured on the files online at run time and
used as an estimate for August 2025.
  LANCE (FIRMS source): MOD14 (Terra), MYD14 (Aqua), VNP14IMG_NRT (Suomi NPP), VJ114IMG_NRT (NOAA-20),
      VJ214IMG_NRT (NOAA-21). Latency = file mtime (UTC, online on LANCE) minus end of granule (MODIS 5 min,
      VIIRS 6 min). The production stamp in the file name is US Eastern local time, so it is not used.
  CDSE: SL_2_FRP NR (Sentinel-3A/B). Latency = PublicationDate minus sensing stop (also: creation minus sensing stop).
The downlink wait is the orbit average of the time from an observation to the first stored-data contact of the real
station set (ground_stations.csv, 10 deg mask, every 30 s over one day, 13 Aug 2025 orbits); Terra: fixed relay wait.
Processing = median measured latency minus median downlink wait (an approximation: medians do not subtract exactly).
Outputs: processed/nrt_listing_lance.json, processed/nrt_listing_s3.json (raw listings, as fetched),
         processed/nrt_latency.csv (one row per satellite)

Usage: python scripts/04_nrt_latency.py [--days 14] [--offline]   (--offline: reuse the saved listings)
"""
import argparse
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

CENSUS_DIR = Path(__file__).resolve().parents[1]
PROC = CENSUS_DIR / "processed"
UTC = dt.timezone.utc
LANCE = "https://nrt3.modaps.eosdis.nasa.gov/api/v2/content/details/allData"
CDSE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
PRODUCTS = {  # product: (LANCE collection, satellite, granule minutes)
    "MOD14": ("61", "Terra", 5), "MYD14": ("61", "Aqua", 5),
    "VNP14IMG_NRT": ("5200", "Suomi NPP", 6), "VJ114IMG_NRT": ("5200", "NOAA-20", 6),
    "VJ214IMG_NRT": ("5200", "NOAA-21", 6)}
MIN_ELEVATION_DEG, STEP_S = 10, 30
RELAY_WAIT_MIN = 25                  # Terra via TDRSS, as in 03_ground_contacts.py
NRT_TARGET_MIN = 180                 # LANCE and Sentinel-3 NRT: within 3 h


def get_json(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def fetch_lance(days):
    today = dt.datetime.now(UTC).date()
    jobs = [(p, today - dt.timedelta(days=k)) for p in PRODUCTS for k in range(days + 1)]

    def one(job):
        prod, d = job
        url = f"{LANCE}/{PRODUCTS[prod][0]}/{prod}/{d.year}/{d.timetuple().tm_yday:03d}?fields=all&format=json"
        try:
            return [dict(product=prod, name=x["name"], mtime=x["mtime"]) for x in get_json(url).get("content", [])]
        except Exception:
            return []                # day no longer (or not yet) online
    with ThreadPoolExecutor(8) as ex:
        return [r for rows in ex.map(one, jobs) for r in rows]


def fetch_s3(days):
    today = dt.datetime.now(UTC).date()
    rows = []
    for k in range(1, days + 1):     # one query per day (at most 1000 products; about 960 per day)
        d = today - dt.timedelta(days=k)
        flt = (f"contains(Name,'SL_2_FRP') and contains(Name,'_NR_') and ContentDate/Start gt {d}T00:00:00.000Z "
               f"and ContentDate/Start lt {d}T23:59:59.999Z")
        q = urllib.parse.urlencode({"$filter": flt, "$top": 1000, "$select": "Name,PublicationDate"},
                                   safe="$',:", quote_via=urllib.parse.quote)
        rows += get_json(f"{CDSE}?{q}").get("value", [])
    return [dict(name=x["Name"], published=x["PublicationDate"]) for x in rows]


def measured(lance, s3):
    out = []
    for r in lance:
        m = re.search(r"\.A(\d{7})\.(\d{4})\.", r["name"])
        _, sat, dur = PRODUCTS[r["product"]]
        end = dt.datetime.strptime(m[1] + m[2], "%Y%j%H%M").replace(tzinfo=UTC) + dt.timedelta(minutes=dur)
        out.append(dict(satellite=sat, product=r["product"], obs_end=end,
                        latency_min=(dt.datetime.fromtimestamp(r["mtime"], UTC) - end).total_seconds() / 60))
    for r in s3:
        m = re.match(r"(S3[AB])_SL_2_FRP____\d{8}T\d{6}_(\d{8}T\d{6})_(\d{8}T\d{6})", r["name"])
        stop = dt.datetime.strptime(m[2], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        pub = dt.datetime.fromisoformat(r["published"].replace("Z", "+00:00"))
        out.append(dict(satellite="Sentinel-3" + m[1][-1], product="SL_2_FRP NR", obs_end=stop,
                        latency_min=(pub - stop).total_seconds() / 60))
    return pd.DataFrame(out)


def orbit_wait():
    """Median and 90th percentile of the wait from an observation to the first stored-data contact, per satellite."""
    ts = load.timescale()
    census = pd.read_csv(PROC / "eo_census.csv")
    st = pd.read_csv(CENSUS_DIR / "notes" / "ground_stations.csv")
    st = st[(st.station_set == "real") & (st.link == "stored")]
    secs = np.arange(0, 2 * 86400, STEP_S)
    t = ts.utc(2025, 8, 13, 0, 0, secs)
    res = {"Terra": (RELAY_WAIT_MIN, RELAY_WAIT_MIN)}
    for r in census[(census.role == "S1 EO layer") & (census.mission != "Terra")].itertuples():
        sat = EarthSatellite(r.line1, r.line2, r.mission, ts)
        vis = np.zeros(len(secs), bool)
        for s in st[st.satellites.str.split(";").apply(lambda x: r.mission in x)].itertuples():
            vis |= (sat - wgs84.latlon(s.lat, s.lon)).at(t).altaz()[0].degrees >= MIN_ELEVATION_DEG
        idx = np.flatnonzero(vis)
        i = np.arange(len(secs) // 2)                # observations over the first day; contacts over two
        w = (idx[np.searchsorted(idx, i)] - i) * STEP_S / 60
        res[r.mission] = (float(np.median(w)), float(np.percentile(w, 90)))
    return res


ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=14)
ap.add_argument("--offline", action="store_true")
a = ap.parse_args()
f_l, f_s = PROC / "nrt_listing_lance.json", PROC / "nrt_listing_s3.json"
if not a.offline:
    f_l.write_text(json.dumps(fetch_lance(a.days)))
    f_s.write_text(json.dumps(fetch_s3(a.days)))
m = measured(json.loads(f_l.read_text()), json.loads(f_s.read_text()))
wait = orbit_wait()
rows = []
for sat, g in m.groupby("satellite", sort=False):
    v = g.latency_min
    w_med, w_p90 = wait[sat]
    rows.append(dict(satellite=sat, product=g["product"].iloc[0], files=len(v),
                     first_obs=g.obs_end.min().date(), last_obs=g.obs_end.max().date(),
                     latency_median_min=round(v.median()), latency_p90_min=round(v.quantile(.9)),
                     within_3h_pct=round(100 * (v <= NRT_TARGET_MIN).mean(), 1),
                     downlink_wait_median_min=round(w_med), downlink_wait_p90_min=round(w_p90),
                     processing_median_min=round(v.median() - w_med)))
res = pd.DataFrame(rows)
res.to_csv(PROC / "nrt_latency.csv", index=False)
print(res.to_string(index=False))
print(f"\nwritten: {PROC / 'nrt_latency.csv'}")
