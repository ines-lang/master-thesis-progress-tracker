"""Step 1: download the GOES ABI fire product (FDC, CONUS sector, 5 min) for the data window.

The North American counterpart of the LSA SAF FRP-PIXEL product (alert path B of S0, geostationary).
Source: NOAA Open Data Dissemination on AWS (s3://noaa-goes18, s3://noaa-goes19), public, no account.
    GOES-19 (GOES-East, 75.2 W)   ABI-L2-FDCC   CONUS sector
    GOES-18 (GOES-West, 137.2 W)  ABI-L2-FDCC   PACUS sector (the West satellite's "CONUS" scan)
Both see Red Canyon (WY); GOES-18 is the better view of Mount Underwood (BC).

Output: raw/<satellite>/OR_ABI-L2-FDCC-M6_G1x_s<start>_e<end>_c<created>.nc   (raw/ is not published to GitHub)
Already downloaded files are skipped, so the script can be re-run after an interruption.

Usage: python scripts/01_download.py
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Input Data FIRMS" / "scripts"))
from lib.registry import load_registry, utc  # noqa: E402

# ---- parameters ----
GOES_DIR = Path(__file__).resolve().parents[1]
RAW = GOES_DIR / "raw"
SATELLITES = ["goes19", "goes18"]
PRODUCT = "ABI-L2-FDCC"
WORKERS = 8
RETRIES = 4

reg = load_registry()
start, end = utc(reg["data_window"]["start_utc"]), utc(reg["data_window"]["end_utc"])


def list_keys(sat, prefix):
    keys, token = [], None
    while True:
        params = {"list-type": 2, "prefix": prefix} | ({"continuation-token": token} if token else {})
        r = requests.get(f"https://noaa-{sat}.s3.amazonaws.com/", params=params, timeout=60)
        r.raise_for_status()
        keys += pd.Series(r.text.split("<Key>")[1:]).str.split("</Key>").str[0].tolist()
        if "<IsTruncated>true</IsTruncated>" not in r.text:
            return keys
        token = r.text.split("<NextContinuationToken>")[1].split("</NextContinuationToken>")[0]


def fetch(job):
    sat, key = job
    out = RAW / sat / key.split("/")[-1]
    if out.exists():
        return 0
    for attempt in range(RETRIES):                      # NOAA occasionally resets a connection
        try:
            r = requests.get(f"https://noaa-{sat}.s3.amazonaws.com/{key}", timeout=120)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))
    tmp = out.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.rename(out)
    return 1


jobs = []
for sat in SATELLITES:
    (RAW / sat).mkdir(parents=True, exist_ok=True)
    for hour in pd.date_range(start.floor("h"), end, freq="h"):
        jobs += [(sat, k) for k in list_keys(sat, f"{PRODUCT}/{hour:%Y/%j/%H}/")]
    print(f"{sat}: {sum(j[0] == sat for j in jobs)} files listed")
with ThreadPoolExecutor(WORKERS) as ex:
    n = sum(ex.map(fetch, jobs))
print(f"downloaded {n} new files; {len(jobs) - n} already present")
for sat in SATELLITES:
    files = sorted((RAW / sat).glob("*.nc"))
    print(f"{sat}: {len(files)} files, {sum(f.stat().st_size for f in files) / 1e9:.2f} GB")
