#!/usr/bin/env python3
"""
Download LSA SAF FRP-PIXEL (MSG/SEVIRI) List products for a date range
and convert them into one CSV of fire pixels (comparable to FIRMS).

Setup:
    pip install requests h5py pandas numpy

Usage:
    python lsasaf_frp_download.py --dry-run          # only list matching files
    python lsasaf_frp_download.py                    # download + convert
    python lsasaf_frp_download.py --convert-only     # convert already downloaded files
    python lsasaf_frp_download.py --inspect          # print HDF5 structure of first file
    python lsasaf_frp_download.py --bbox -25 34 45 72  # keep only Europe (lon_min lat_min lon_max lat_max)

Username: env variable LSASAF_USERNAME (exported by the master-thesis venv activate script).
Password: prompted at runtime, or set the env variable LSASAF_PASSWORD.
"""
import argparse
import bz2
import getpass
import gzip
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import h5py
import numpy as np
import pandas as pd
import requests

# ---------------- configuration ----------------
BASE_URL = "https://datalsasaf.lsasvcs.ipma.pt/PRODUCTS/MSG/FRP-PIXEL/HDF5/"
USERNAME = os.environ.get("LSASAF_USERNAME")   # LSA SAF account, never stored in the code
START = datetime(2025, 8, 8, 0, 0)    # UTC, inclusive
END = datetime(2025, 8, 16, 23, 59)   # UTC, inclusive
FILE_PATTERN = "ListProduct"          # FRP-PIXEL List files hold the fire pixels
OUT_DIR = Path("lsasaf_frp_raw")
OUT_CSV = Path("lsasaf_frp_pixels_20250808_20250816.csv")
# ------------------------------------------------

TS_RE = re.compile(r"(20\d{10})")  # YYYYMMDDHHMM inside file names


def file_time(name):
    m = TS_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M")
    except ValueError:
        return None


def list_links(session, url):
    """Return absolute links that are children of url (files and subfolders)."""
    r = session.get(url, timeout=60)
    if r.status_code == 401:
        sys.exit("401 Unauthorized: check username/password and that your account is approved.")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    hrefs = re.findall(r'href="([^"?#]+)"', r.text)
    out = set()
    for h in hrefs:
        full = urljoin(url, h)
        if full.startswith(url) and full != url:
            out.add(full)
    return sorted(out)


def dir_in_range(rel_parts):
    """Prune date folders (YYYY / MM / DD) outside the requested period."""
    nums = [p for p in rel_parts if p.isdigit()]
    if not nums:
        return True
    prefix = "".join(nums)
    if len(prefix) > 8:
        return True
    lo = START.strftime("%Y%m%d")[: len(prefix)]
    hi = END.strftime("%Y%m%d")[: len(prefix)]
    return lo <= prefix <= hi


def crawl(session, url, rel_parts, found):
    for link in list_links(session, url):
        name = link[len(url):]
        if name.endswith("/"):
            part = name.strip("/")
            if dir_in_range(rel_parts + [part]):
                print(f"  scanning {link}")
                crawl(session, link, rel_parts + [part], found)
        else:
            t = file_time(name)
            if FILE_PATTERN in name and t and START <= t <= END:
                found.append((t, link))


def download(session, url, out_dir):
    dest = out_dir / Path(urlparse(url).path).name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_name(dest.name + ".part")
    with session.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    return dest


def open_h5(path):
    raw = path.read_bytes()
    if path.suffix == ".bz2":
        raw = bz2.decompress(raw)
    elif path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return h5py.File(io.BytesIO(raw), "r")


def _scalar(v):
    if v is None:
        return None
    try:
        return float(np.ravel(v)[0])
    except (TypeError, ValueError):
        return None


def read_list_product(path):
    with open_h5(path) as h:
        datasets = {k: v for k, v in h.items() if isinstance(v, h5py.Dataset)}
        n = None
        for k in datasets:
            if k.upper() == "LATITUDE":
                n = datasets[k].shape[0] if datasets[k].ndim >= 1 else 0
        cols = {}
        for key, ds in datasets.items():
            if ds.ndim != 1 or (n is not None and ds.shape[0] != n):
                continue
            try:
                data = ds[()].astype("float64")
            except (TypeError, ValueError):
                continue
            miss = _scalar(ds.attrs.get("MISSING_VALUE"))
            sf = _scalar(ds.attrs.get("SCALING_FACTOR"))
            off = _scalar(ds.attrs.get("OFFSET"))
            if miss is not None:
                data[data == miss] = np.nan
            if sf not in (None, 0.0):
                data = data / sf          # LSA SAF convention: physical = raw / scaling
            if off:
                data = data + off
            cols[key.lower()] = data
    df = pd.DataFrame(cols)
    df.insert(0, "slot_time_utc", file_time(path.name))
    df["source_file"] = path.name
    return df


def inspect(path):
    print(f"\nHDF5 structure of {path.name}:")
    with open_h5(path) as h:
        for key, ds in h.items():
            if isinstance(ds, h5py.Dataset):
                attrs = {a: ds.attrs[a] for a in ds.attrs}
                print(f"  {key:25s} shape={ds.shape} dtype={ds.dtype} attrs={attrs}")


def local_files():
    files = []
    for p in sorted(OUT_DIR.glob(f"*{FILE_PATTERN}*")):
        if p.name.endswith(".part"):
            continue
        t = file_time(p.name)
        if t and START <= t <= END:
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--convert-only", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    if not args.convert_only:
        if not USERNAME:
            sys.exit("LSASAF_USERNAME is not set: activate the master-thesis venv (source .../master-thesis/bin/activate).")
        password = os.environ.get("LSASAF_PASSWORD") or getpass.getpass(f"LSA SAF password for {USERNAME}: ")
        session = requests.Session()
        session.auth = (USERNAME, password)

        print(f"Crawling {BASE_URL}")
        found = []
        crawl(session, BASE_URL, [], found)
        found.sort()
        print(f"\nFound {len(found)} '{FILE_PATTERN}' files between {START} and {END} UTC")
        if found:
            print(f"  first: {found[0][1]}\n  last:  {found[-1][1]}")
        if not found:
            sys.exit("No files matched. Run with --dry-run and check FILE_PATTERN / folder layout.")
        if args.dry_run:
            return

        for i, (_, url) in enumerate(found, 1):
            try:
                download(session, url, OUT_DIR)
            except requests.RequestException as e:
                print(f"  FAILED {url}: {e}")
            if i % 50 == 0 or i == len(found):
                print(f"  downloaded {i}/{len(found)}")

    files = local_files()
    if not files:
        sys.exit(f"No local files in {OUT_DIR} to convert.")
    if args.inspect:
        inspect(files[0])

    frames, bad = [], 0
    for p in files:
        try:
            frames.append(read_list_product(p))
        except Exception as e:  # corrupted or unexpected file
            bad += 1
            print(f"  could not read {p.name}: {e}")
    df = pd.concat(frames, ignore_index=True)

    if "latitude" in df and "longitude" in df:
        lat_ok = df["latitude"].between(-90, 90).mean() if len(df) else 1.0
        if lat_ok < 0.99:
            print("WARNING: latitudes look wrong, scaling convention may differ. Run with --inspect.")
        if args.bbox:
            lon0, lat0, lon1, lat1 = args.bbox
            df = df[df["longitude"].between(lon0, lon1) & df["latitude"].between(lat0, lat1)]

    df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {len(df)} fire pixels from {len(files) - bad} files to {OUT_CSV}")
    print(f"Columns: {list(df.columns)}")


if __name__ == "__main__":
    main()