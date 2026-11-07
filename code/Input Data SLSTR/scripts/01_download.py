"""Step 1: download the Sentinel-3 SLSTR fire product (SL_2_FRP) over every event of the data window.

S0 counterpart of the Sentinel-3A/B satellites in the S1 EO layer. Source: Copernicus Data Space Ecosystem (CDSE).
The catalogue search is open; the download needs a CDSE account (created 7 Nov 2026 for this step). Credentials are
read from CDSE_USERNAME and CDSE_PASSWORD in the .env file of the master-thesis venv and are never printed.

Only the NTC (non-time-critical, about 1 to 2 days after sensing) products are still in the archive for August 2025;
the NRT products that were public during the fires have been removed. Acquisition times are the same, but the NTC fire
list is a reprocessing and may differ slightly from what was available in near real time.

Only the three fire files of each product are fetched (FRP_in.nc: 1 km MWIR fire list and per-pixel flags;
FRP_an.nc, FRP_bn.nc: 500 m SWIR fire lists), about 1 MB instead of about 75 MB for the full product.

Output: raw/<product name>/FRP_{in,an,bn}.nc   (raw/ is not published to GitHub)
        processed/slstr_products.csv           one row per product and event it covers
Usage: python scripts/01_download.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Input Data FIRMS" / "scripts"))
from lib.registry import load_registry, utc  # noqa: E402

# ---- parameters ----
SL_DIR = Path(__file__).resolve().parents[1]
RAW, PROC = SL_DIR / "raw", SL_DIR / "processed"
ENV_FILE = SL_DIR.parents[2] / "master-thesis" / ".env"
EVENTS_FILE = SL_DIR.parent / "Event Selection" / "notes" / "candidates_ground_truth.csv"
EVENTS = ["larouco", "molezuelas", "oimbra", "piodao", "red_canyon", "mount_underwood", "derdara"]
FILES = ["FRP_in.nc", "FRP_an.nc", "FRP_bn.nc"]
CATALOGUE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
TOKEN_LIFETIME_S = 500          # CDSE access tokens last 600 s

reg = load_registry()
start, end = utc(reg["data_window"]["start_utc"]), utc(reg["data_window"]["end_utc"])


def credentials():
    env = {}
    for line in open(ENV_FILE):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env["CDSE_USERNAME"], env["CDSE_PASSWORD"]


class Token:
    def __init__(self):
        self.user, self.password = credentials()
        self.value, self.time = None, 0

    def header(self):
        if time.time() - self.time > TOKEN_LIFETIME_S:
            r = requests.post(TOKEN_URL, data={"grant_type": "password", "client_id": "cdse-public",
                                               "username": self.user, "password": self.password}, timeout=60)
            if r.status_code != 200:
                sys.exit(f"CDSE login refused (HTTP {r.status_code}): check the account and the .env credentials")
            self.value, self.time = r.json()["access_token"], time.time()
        return {"Authorization": f"Bearer {self.value}"}


def search(lat, lon):
    f = ("Collection/Name eq 'SENTINEL-3' and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
         "and att/OData.CSC.StringAttribute/Value eq 'SL_2_FRP___') "
         f"and OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon} {lat})') "
         f"and ContentDate/Start gt {start:%Y-%m-%dT%H:%M:%S.000Z} and ContentDate/Start lt {end:%Y-%m-%dT%H:%M:%S.000Z}")
    r = requests.get(CATALOGUE, params={"$filter": f, "$top": 1000, "$orderby": "ContentDate/Start"}, timeout=120)
    r.raise_for_status()
    return r.json()["value"]


gt = pd.read_csv(EVENTS_FILE).set_index("candidate_id")
rows = []
for ev in EVENTS:
    for p in search(gt.loc[ev, "lat"], gt.loc[ev, "lon"]):
        rows.append(dict(event=ev, product=p["Name"], product_id=p["Id"], platform=p["Name"][:3],
                         sensing_start_utc=p["ContentDate"]["Start"], sensing_end_utc=p["ContentDate"]["End"]))
products = pd.DataFrame(rows)
PROC.mkdir(parents=True, exist_ok=True)
products.to_csv(PROC / "slstr_products.csv", index=False)
unique = products.drop_duplicates("product")
print(f"{len(unique)} products ({products.groupby('event').size().to_dict()})")

token, n_new = Token(), 0
for i, p in enumerate(unique.itertuples(), 1):
    out_dir = RAW / p.product
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn in FILES:
        out = out_dir / fn
        if out.exists():
            continue
        r = requests.get(f"{DOWNLOAD}({p.product_id})/Nodes({p.product})/Nodes({fn})/$value",
                         headers=token.header(), timeout=300)
        r.raise_for_status()
        out.with_suffix(".part").write_bytes(r.content)
        out.with_suffix(".part").rename(out)
        n_new += 1
    if i % 20 == 0:
        print(f"  {i} / {len(unique)} products")
print(f"downloaded {n_new} new files into {RAW}")
