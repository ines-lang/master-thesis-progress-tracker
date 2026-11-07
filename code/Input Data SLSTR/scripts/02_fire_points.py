"""Step 2: fire list of every downloaded SL_2_FRP product, cropped around the events.

Reads the 1 km MWIR fire list (FRP_in.nc) and the 500 m SWIR fire lists (FRP_an.nc, FRP_bn.nc) of each product and
keeps every vegetation-fire pixel (classification bit 1) within BOX_DEG of an event point.
Time: per-pixel acquisition time, microseconds since 2000-01-01 UTC.

Output: processed/slstr_fire_points.csv  one row per fire pixel near an event
Usage: python scripts/02_fire_points.py
"""
from pathlib import Path

import h5py
import pandas as pd

# ---- parameters ----
SL_DIR = Path(__file__).resolve().parents[1]
RAW, PROC = SL_DIR / "raw", SL_DIR / "processed"
EVENTS_FILE = SL_DIR.parent / "Event Selection" / "notes" / "candidates_ground_truth.csv"
BOX_DEG = 0.6                   # same crop as the GOES step
EPOCH = pd.Timestamp("2000-01-01", tz="UTC")
GRIDS = {"FRP_in.nc": "1 km MWIR", "FRP_an.nc": "500 m SWIR (a stripe)", "FRP_bn.nc": "500 m SWIR (b stripe)"}

products = pd.read_csv(PROC / "slstr_products.csv")
gt = pd.read_csv(EVENTS_FILE).set_index("candidate_id")
rows = []
for p in products.itertuples():
    e = gt.loc[p.event]
    for fn, grid in GRIDS.items():
        path = RAW / p.product / fn
        if not path.exists():
            continue
        with h5py.File(path) as f:
            if f["fires"].shape[0] == 0:
                continue
            d = pd.DataFrame({"lat": f["latitude"][:], "lon": f["longitude"][:], "time_us": f["time"][:],
                              "classification": f["classification"][:],
                              "frp_mwir_mw": f["FRP_MWIR"][:] if "FRP_MWIR" in f else float("nan")})
        d = d[((d.classification & 1) == 1) & ((d.lat - e.lat).abs() <= BOX_DEG) & ((d.lon - e.lon).abs() <= BOX_DEG)]
        for r in d.itertuples():
            rows.append(dict(event=p.event, platform=p.platform, product=p.product, grid=grid,
                             time_utc=EPOCH + pd.Timedelta(microseconds=int(r.time_us)),
                             lat=round(float(r.lat), 4), lon=round(float(r.lon), 4), frp_mwir_mw=r.frp_mwir_mw))
out = pd.DataFrame(rows).sort_values(["event", "time_utc"])
out.to_csv(PROC / "slstr_fire_points.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
print(f"{products['product'].nunique()} products read; {len(out)} fire pixels near the events "
      f"({out.groupby('event').size().to_dict()})")
