"""Step 2.8: measured product latency of the geostationary fire products (detection to product).

The files record both times, so the latency is measured, not assumed:
    GOES ABI FDC   file name: s<scan start> ... c<file creation>   (YYYYDDDHHMMSSs)
    LSA SAF FRP    HDF5 attributes IMAGE_ACQUISITION_TIME (slot start) and NOMINAL_PRODUCT_TIME
The polar products cannot be measured this way: FIRMS publishes no production time, and only the reprocessed
(NTC) Sentinel-3 products remain archived. Their latency is the downlink wait (EO Census ground_contacts.csv)
plus a processing time stated by the providers (under 3 h), not measured here.

Output: processed/product_latency.csv   one row per product and file
Usage: python scripts/08_product_latency.py
"""
from pathlib import Path

import h5py
import pandas as pd

CODE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "processed" / "product_latency.csv"

rows = []
for sat in ["goes18", "goes19"]:
    for p in sorted((CODE / "Input Data GOES" / "raw" / sat).glob("*.nc")):
        parts = p.stem.split("_")                       # OR, ABI-L2-FDCC-M6, G19, s..., e..., c...
        start = pd.to_datetime(parts[3][1:14], format="%Y%j%H%M%S")
        created = pd.to_datetime(parts[5][1:14], format="%Y%j%H%M%S")
        rows.append(dict(product=f"GOES ABI FDC ({sat.upper().replace('GOES', 'GOES-')})", file=p.name,
                         observation_utc=start, product_utc=created))
for p in sorted((CODE / "Input Data LSA SAF" / "lsasaf_frp_raw").glob("HDF5_LSASAF_*")):
    with h5py.File(p) as f:
        rows.append(dict(product="LSA SAF FRP-PIXEL (SEVIRI)", file=p.name,
                         observation_utc=pd.to_datetime(f.attrs["IMAGE_ACQUISITION_TIME"].decode()),
                         product_utc=pd.to_datetime(f.attrs["NOMINAL_PRODUCT_TIME"].decode())))
d = pd.DataFrame(rows)
d["latency_min"] = ((d.product_utc - d.observation_utc).dt.total_seconds() / 60).round(1)
d.to_csv(OUT, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
print(d.groupby("product").latency_min.describe(percentiles=[0.5, 0.95])[["count", "50%", "95%", "max"]].round(1))
