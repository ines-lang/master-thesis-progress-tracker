"""Step 6: NRT latency of the S1 fire products in the study window (8 to 16 August 2025), measured through proxies.

The NRT fire files of August 2025 are no longer online (04_nrt_latency.py), but two products from the same processing
chains are still archived with their creation time in the file name:
  Sentinel-3A/B  SL_2_AOD NR (CDSE): same SLSTR NRT chain and processing centre as SL_2_FRP NR. The offset
                 FRP minus AOD creation is measured on the recent files (same granule) and added.
  VIIRS          NOAA I4 SDR (SVI04, NOAA Open Data on AWS): the calibrated radiances that the fire products start
                 from. FIRMS uses the NASA LANCE products, made later; the offset LANCE online minus the last
                 SDR creation of the same 6-min granule is measured on the recent files (NOAA-20, NOAA-21; Suomi NPP
                 until its end on 2 Nov 2026) and added as a random draw, so the spread is kept.
  MODIS          no archived NRT timing: not measured here (see the EOSDIS weekly metrics of August 2025).
Latency = creation (or online) minus end of observation, in minutes. Day = 8 to 16 Aug 2025 (study window).
Inputs:  processed/nrt_listing_lance.json, processed/nrt_listing_s3.json (04_nrt_latency.py)
Outputs: processed/latency_study_window.csv (one row per satellite), processed/latency_proxy_listing_*.json

Usage: python scripts/05_latency_study_window.py [--offline]
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

CENSUS_DIR = Path(__file__).resolve().parents[1]
PROC = CENSUS_DIR / "processed"
UTC = dt.timezone.utc
CDSE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
WINDOW = [dt.date(2025, 8, 8) + dt.timedelta(days=k) for k in range(9)]
NOAA = {"Suomi NPP": ("noaa-nesdis-snpp-pds", "npp"), "NOAA-20": ("noaa-nesdis-n20-pds", "j01"),
        "NOAA-21": ("noaa-nesdis-n21-pds", "j02")}
LANCE_VIIRS = {"VNP14IMG_NRT": "Suomi NPP", "VJ114IMG_NRT": "NOAA-20", "VJ214IMG_NRT": "NOAA-21"}
NRT_TARGET_MIN = 180
rng = np.random.default_rng(0)


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def cdse_aod(day):
    flt = (f"contains(Name,'SL_2_AOD') and contains(Name,'_NR_') and ContentDate/Start gt {day}T00:00:00.000Z "
           f"and ContentDate/Start lt {day}T23:59:59.999Z")
    q = urllib.parse.urlencode({"$filter": flt, "$top": 1000, "$select": "Name"}, safe="$',:",
                               quote_via=urllib.parse.quote)
    return [x["Name"] for x in json.loads(get(f"{CDSE}?{q}"))["value"]]


def noaa_sdr(sat, day):
    bucket, _ = NOAA[sat]
    keys, token = [], None
    while True:
        q = {"list-type": 2, "prefix": f"VIIRS-I4-SDR/{day:%Y/%m/%d}/"}
        if token:
            q["continuation-token"] = token
        x = get(f"https://{bucket}.s3.amazonaws.com/?{urllib.parse.urlencode(q)}").decode()
        keys += re.findall(r"<Key>([^<]+)</Key>", x)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x)
        if not m:
            return keys
        token = m[1]


def parse_s3(name):
    m = re.match(r"(S3[AB])_SL_2_(FRP|AOD)_+\d{8}T\d{6}_(\d{8}T\d{6})_(\d{8}T\d{6})", name)
    t = lambda s: dt.datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return dict(satellite="Sentinel-3" + m[1][-1], product=m[2], stop=t(m[3]), created=t(m[4]))


def parse_sdr(key):
    m = re.search(r"_d(\d{8})_t(\d{6})\d_e(\d{6})\d_b\d+_c(\d{14})", key)
    start = dt.datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    end = dt.datetime.strptime(m[1] + m[3], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    end += dt.timedelta(days=end < start)
    return dict(start=start, end=end, created=dt.datetime.strptime(m[4], "%Y%m%d%H%M%S").replace(tzinfo=UTC))


def minutes(td):
    return td.dt.total_seconds() / 60


ap = argparse.ArgumentParser()
ap.add_argument("--offline", action="store_true")
a = ap.parse_args()
lance = pd.DataFrame(json.loads((PROC / "nrt_listing_lance.json").read_text()))
recent_days = sorted({dt.datetime.fromtimestamp(t, UTC).date() for t in lance.mtime})
f_aug, f_cal = PROC / "latency_proxy_listing_august.json", PROC / "latency_proxy_listing_recent.json"
if not a.offline:
    jobs = [("aod", None, d) for d in WINDOW] + [(s, s, d) for s in NOAA for d in WINDOW]
    cal = [("aod", None, d) for d in recent_days] + [(s, s, d) for s in NOAA for d in recent_days]
    fetch = lambda j: (j[0], str(j[2]), cdse_aod(j[2]) if j[0] == "aod" else noaa_sdr(j[1], j[2]))
    with ThreadPoolExecutor(6) as ex:
        f_aug.write_text(json.dumps(list(ex.map(fetch, jobs))))
        f_cal.write_text(json.dumps(list(ex.map(fetch, cal))))
aug, recent = json.loads(f_aug.read_text()), json.loads(f_cal.read_text())
rows = []

# ---- Sentinel-3: AOD NR creation in August, plus the FRP minus AOD offset of the recent files ----
s3_aug = pd.DataFrame([parse_s3(n) for k, _, names in aug if k == "aod" for n in names])
s3_rec = pd.DataFrame([parse_s3(n) for k, _, names in recent if k == "aod" for n in names] +
                      [parse_s3(x["name"]) for x in json.loads((PROC / "nrt_listing_s3.json").read_text())])
for sat, g in s3_aug.groupby("satellite"):
    r = s3_rec[s3_rec.satellite == sat]
    frp = r[r["product"] == "FRP"].sort_values("stop")
    aod = r[r["product"] == "AOD"].sort_values("stop")
    pair = pd.merge_asof(frp, aod, on="stop", tolerance=pd.Timedelta("10s"), direction="nearest",
                         suffixes=("_frp", "_aod")).dropna()
    off = minutes(pair.created_frp - pair.created_aod)
    lat = minutes(g.created - g.stop) + off.median()
    rows.append(dict(satellite=sat, proxy="SL_2_AOD NR creation", files=len(g), pairs=len(pair),
                     offset_median_min=round(off.median(), 1), offset_iqr_min=round(off.quantile(.75) - off.quantile(.25), 1),
                     latency_median_min=round(lat.median()), latency_p90_min=round(lat.quantile(.9)),
                     within_3h_pct=round(100 * (lat <= NRT_TARGET_MIN).mean(), 1)))

# ---- VIIRS: NOAA SDR creation in August, plus the LANCE minus SDR offset of the recent files ----
def granules(listing, sat):
    """Last SDR creation within each 6-min LANCE granule (the granule is complete only then)."""
    d = pd.DataFrame([parse_sdr(k) for kind, _, keys in listing if kind == sat for k in keys])
    d["granule"] = d.start.dt.floor("6min")
    return d.groupby("granule").agg(end=("end", "max"), created=("created", "max")).reset_index()

for prod, sat in LANCE_VIIRS.items():
    l = lance[lance["product"] == prod].copy()
    m = l.name.str.extract(r"\.A(\d{7})\.(\d{4})\.")
    l["granule"] = pd.to_datetime(m[0] + m[1], format="%Y%j%H%M", utc=True)
    l["online"] = pd.to_datetime(l.mtime, unit="s", utc=True)
    cal = l.merge(granules(recent, sat), on="granule")
    off = minutes(cal.online - cal.created)
    g = granules(aug, sat)
    base = minutes(g.created - g.end).to_numpy()
    lat = base + rng.choice(off.to_numpy(), size=len(base))
    rows.append(dict(satellite=sat, proxy="NOAA I4 SDR creation + LANCE offset", files=len(g), pairs=len(cal),
                     offset_median_min=round(off.median(), 1), offset_iqr_min=round(off.quantile(.75) - off.quantile(.25), 1),
                     sdr_latency_median_min=round(np.median(base)),
                     latency_median_min=round(np.median(lat)), latency_p90_min=round(np.percentile(lat, 90)),
                     within_3h_pct=round(100 * (lat <= NRT_TARGET_MIN).mean(), 1)))

res = pd.DataFrame(rows)
res.to_csv(PROC / "latency_study_window.csv", index=False)
print(res.to_string(index=False))
print(f"\nwritten: {PROC / 'latency_study_window.csv'}")
