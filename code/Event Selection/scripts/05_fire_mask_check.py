"""Step 2.5: why did the overpasses before each first detection see nothing?

FIRMS lists fire pixels only. An overpass without a FIRMS detection can mean no fire, a fire below the detection
limit, cloud or smoke, or missing data. The Level-2 fire products behind FIRMS keep a per-pixel fire mask that
separates these cases. This step reads it at the event location for every empty overpass shown in the timeline
figure (from PRE_H hours before the reference time up to the first detection).

Products (fire: LP DAAC, geolocation: LAADS):  fire mask   geolocation
    Suomi-NPP  VIIRS                      VNP14IMG           VNP03IMG
    NOAA-20    VIIRS                      VJ114IMG           VJ103IMG
    NOAA-21    VIIRS                      VJ214IMG           VJ203IMG
    Terra      MODIS                      MOD14              MOD03
    Aqua       MODIS                      MYD14              MYD03

Fire mask classes (VIIRS and MODIS use the same numbering): 0 to 2 not processed / missing, 3 water, 4 cloud,
5 clear land without fire, 6 unknown, 7 to 9 fire (low, nominal, high confidence). VIIRS also uses 1 for bow-tie
deletion and 2 for sun glint.

Stages:
    catalog   (no login) CMR search: does each empty pass have a fire and a geolocation granule over the event?
              Output: processed/fire_mask_granules.csv
    read      (NASA Earthdata login) download each granule pair to raw/l2_fire_mask/, take every pixel within
              RADIUS_KM of the event point, count its fire-mask classes and classify the pass; geolocation files are
              deleted after reading (VIIRS: about 160 MB each). Output: processed/fire_mask_check.csv

Earthdata account: the Level-2 granules are only served to logged-in users (FIRMS and the CMR catalogue are not).
An account was created on 2026-11-06 for this step only. Credentials are read from EARTHDATA_USERNAME and
EARTHDATA_PASSWORD in the .env file of the master-thesis venv and are never printed or written elsewhere.

Usage: python scripts/05_fire_mask_check.py catalog|read
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# ---- parameters ----
ES_DIR = Path(__file__).resolve().parents[1]
PROC = ES_DIR / "processed"
PRE_H = 12                      # same left edge as the timeline figure
GRANULE_SLACK_MIN = 8           # pass_utc is the closest approach; granules are 5 (MODIS) or 6 (VIIRS) min long
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
RAW = ES_DIR / "raw" / "l2_fire_mask"
ENV_FILE = ES_DIR.parents[2] / "master-thesis" / ".env"
RADIUS_KM = 2.0                 # event points are official or press ignition points, accurate to about 1 to 2 km
EARTH_RADIUS_KM = 6371.0
CLASS = {0: "missing", 1: "missing", 2: "missing", 3: "water", 4: "cloud", 5: "clear", 6: "unknown",
         7: "fire", 8: "fire", 9: "fire"}   # VIIRS 1 = bow-tie deletion, 2 = sun glint: not observed, counted as missing
# (fire short name, fire version at LP DAAC, geolocation short name, geolocation version at LAADS)
PRODUCTS = {"Suomi-NPP": ("VNP14IMG", "002", "VNP03IMG", "2"), "NOAA-20": ("VJ114IMG", "002", "VJ103IMG", "2.1"),
            "NOAA-21": ("VJ214IMG", "002", "VJ203IMG", "2.1"), "Terra": ("MOD14", "061", "MOD03", "6.1"),
            "Aqua": ("MYD14", "061", "MYD03", "6.1")}


def empty_passes():
    o = pd.read_csv(PROC / "candidate_overpasses.csv", parse_dates=["pass_utc"])
    first = pd.read_csv(PROC / "detection_bracket.csv").set_index("event")["first_detection_any_confidence_h"]
    o = o[(o.hours_from_reference >= -PRE_H) & (o.hours_from_reference < o.event.map(first))]
    gt = pd.read_csv(ES_DIR / "notes" / "candidates_ground_truth.csv").set_index("candidate_id")
    return o.join(gt[["lat", "lon"]], on="event").reset_index(drop=True)


def cmr_granules(short_name, version, t, lat, lon):
    dt = pd.Timedelta(minutes=GRANULE_SLACK_MIN)
    r = requests.get(CMR, params={"short_name": short_name, "version": version, "point": f"{lon},{lat}",
                                  "temporal": f"{(t - dt):%Y-%m-%dT%H:%M:%SZ},{(t + dt):%Y-%m-%dT%H:%M:%SZ}",
                                  "page_size": 10}, timeout=60)
    r.raise_for_status()
    out = []
    for e in r.json()["feed"]["entry"]:
        url = next((l["href"] for l in e.get("links", []) if l.get("rel", "").endswith("/data#")
                    and l["href"].startswith("https")), None)
        out.append(dict(id=e["producer_granule_id"] if "producer_granule_id" in e else e["title"],
                        start=e["time_start"], size_mb=float(e.get("granule_size", "nan")), url=url))
    return out


def catalog():
    rows = []
    for p in empty_passes().itertuples():
        fire, fver, geo, gver = PRODUCTS[p.platform]
        f, g = (cmr_granules(fire, fver, p.pass_utc, p.lat, p.lon), cmr_granules(geo, gver, p.pass_utc, p.lat, p.lon))
        rows.append(dict(event=p.event, platform=p.platform, pass_utc=p.pass_utc, hours_from_reference=p.hours_from_reference,
                         off_track_km=p.off_track_km, lat=p.lat, lon=p.lon,
                         n_fire_granules=len(f), n_geo_granules=len(g),
                         fire_granule=";".join(x["id"] for x in f), geo_granule=";".join(x["id"] for x in g),
                         fire_url=";".join(x["url"] or "" for x in f), geo_url=";".join(x["url"] or "" for x in g),
                         download_mb=round(sum(x["size_mb"] for x in f + g), 1)))
        print(f"{p.event:16s} {p.platform:9s} {p.hours_from_reference:+6.2f} h  fire {len(f)}  geo {len(g)}")
    out = pd.DataFrame(rows)
    out.to_csv(PROC / "fire_mask_granules.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{len(out)} empty passes; without fire granule: {(out.n_fire_granules == 0).sum()}; "
          f"total download {out.download_mb.sum() / 1024:.1f} GB")


# ---------------- read stage ----------------
def earthdata_session():
    env = {}
    for line in open(ENV_FILE):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

    class Session(requests.Session):   # keep the login only for the redirects to and from the Earthdata login host
        def rebuild_auth(self, prep, resp):
            new, old = requests.utils.urlparse(prep.url).hostname, requests.utils.urlparse(resp.request.url).hostname
            if "Authorization" in prep.headers and new != old and "urs.earthdata.nasa.gov" not in (new, old):
                del prep.headers["Authorization"]

    s = Session()
    s.auth = (env["EARTHDATA_USERNAME"], env["EARTHDATA_PASSWORD"])
    return s


def download(session, url):
    out = RAW / url.split("/")[-1]
    if not out.exists():
        r = session.get(url, stream=True, timeout=600)
        if r.status_code == 401:
            sys.exit("Earthdata login refused (HTTP 401): check the account and the .env credentials")
        r.raise_for_status()
        tmp = out.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(out)
    return out


def read_arrays(fire_file, geo_file):
    """Fire mask, latitude, longitude on the same pixel grid."""
    if fire_file.suffix == ".nc":                                   # VIIRS, netCDF4
        import h5py
        with h5py.File(fire_file) as f:
            mask = f["fire mask"][:]
        with h5py.File(geo_file) as g:
            lat, lon = g["geolocation_data/latitude"][:], g["geolocation_data/longitude"][:]
    else:                                                           # MODIS, HDF4
        from pyhdf.SD import SD
        mask = SD(str(fire_file)).select("fire mask")[:]
        g = SD(str(geo_file))
        lat, lon = g.select("Latitude")[:], g.select("Longitude")[:]
    if mask.shape != lat.shape:
        raise ValueError(f"grid mismatch {fire_file.name}: mask {mask.shape}, geolocation {lat.shape}")
    return mask, lat, lon


def classify(counts):
    if counts.get("fire", 0):
        return "fire in mask"           # fire pixel that FIRMS did not list (or outside its 15 min match)
    if counts.get("cloud", 0):
        return "cloud" if counts.get("clear", 0) == 0 else "partly cloud"
    if counts.get("clear", 0):
        return "clear, no fire"
    return "missing" if counts.get("missing", 0) else "other"


def read():
    RAW.mkdir(parents=True, exist_ok=True)
    session = earthdata_session()
    g = pd.read_csv(PROC / "fire_mask_granules.csv")
    rows = []
    for p in g.itertuples():
        base = dict(event=p.event, platform=p.platform, pass_utc=p.pass_utc,
                    hours_from_reference=p.hours_from_reference, off_track_km=p.off_track_km)
        if p.n_fire_granules == 0:
            rows.append(base | dict(result="not in granule footprint"))
            continue
        geo_urls = str(p.geo_url).split(";")
        best = None
        for fu in p.fire_url.split(";"):
            key = fu.split("/")[-1].split(".")[1:3]                 # A2025225, 1430: same granule time
            gu = next((u for u in geo_urls if u.split("/")[-1].split(".")[1:3] == key), None)
            if gu is None:
                continue
            ff, gf = download(session, fu), download(session, gu)
            mask, lat, lon = read_arrays(ff, gf)
            gf.unlink()                                             # geolocation is large and re-downloadable
            ok = np.isfinite(lat) & (np.abs(lat) <= 90)
            p1, p2 = np.radians(p.lat), np.radians(np.where(ok, lat, 0))
            d = EARTH_RADIUS_KM * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2)
                                                    * np.cos(np.radians(np.where(ok, lon, 0) - p.lon)), -1, 1))
            d[~ok] = np.inf
            near = d <= RADIUS_KM
            if not near.any() or (best is not None and d.min() >= best["nearest_pixel_km"]):
                continue
            classes = pd.Series([CLASS.get(int(v), "other") for v in mask[near]]).value_counts().to_dict()
            best = dict(granule=ff.name, nearest_pixel_km=round(float(d.min()), 2), n_pixels=int(near.sum()),
                        **{f"n_{c}": classes.get(c, 0) for c in ["clear", "cloud", "fire", "missing", "water", "unknown"]},
                        result=classify(classes))
        rows.append(base | (best or dict(result="no pixel within radius")))
        print(f"{p.event:16s} {p.platform:9s} {p.hours_from_reference:+6.2f} h  {rows[-1]['result']}")
    out = pd.DataFrame(rows)
    out.to_csv(PROC / "fire_mask_check.csv", index=False)
    print("\n" + out.groupby(["event", "result"]).size().to_string())


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "catalog"
    if stage == "catalog":
        catalog()
    elif stage == "read":
        read()
    else:
        sys.exit(__doc__)
