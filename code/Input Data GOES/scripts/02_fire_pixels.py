"""Step 2: fire pixels of the GOES ABI fire product (FDC) around the North American events.

For every downloaded scan: decode the fire mask, compute pixel latitude and longitude from the fixed-grid scan angles
(GOES-R Product User Guide, Vol. 5, Sect. 4.2.8), and keep every fire pixel within BOX_DEG of an event point.

Fire mask codes (ABI FDC): 10 good-quality fire, 11 saturated, 12 cloud contaminated, 13 high, 14 medium, 15 low
probability; 30 to 35 the same classes after temporal filtering. Code 10 to 13 and 30 to 33 are counted as
"confident" (analogous to FIRMS nominal/high), 14, 15, 34, 35 as "low".
Scan time: the scan start in the file name (s<YYYYDDDHHMMSSs>); a CONUS scan lasts about 2.5 min.

Output: processed/goes_fire_pixels.csv  one row per fire pixel near an event
Usage: python scripts/02_fire_pixels.py
"""
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

# ---- parameters ----
GOES_DIR = Path(__file__).resolve().parents[1]
RAW, PROC = GOES_DIR / "raw", GOES_DIR / "processed"
EVENTS_FILE = GOES_DIR.parent / "Event Selection" / "notes" / "candidates_ground_truth.csv"
EVENTS = ["red_canyon", "mount_underwood"]
BOX_DEG = 0.6                   # crop around each event point; larger than both final perimeters
FIRE_CODES = {10: "good", 11: "saturated", 12: "cloud contaminated", 13: "high", 14: "medium", 15: "low"}
CONFIDENT = {10, 11, 12, 13}


def lat_lon(f):
    """Latitude and longitude of every pixel centre from the ABI fixed grid (NaN off the Earth)."""
    p = f["goes_imager_projection"].attrs
    req, rpol = float(p["semi_major_axis"][0]), float(p["semi_minor_axis"][0])
    h = float(p["perspective_point_height"][0]) + req
    lon0 = np.radians(float(p["longitude_of_projection_origin"][0]))
    x = f["x"][:] * f["x"].attrs["scale_factor"][0] + f["x"].attrs["add_offset"][0]
    y = f["y"][:] * f["y"].attrs["scale_factor"][0] + f["y"].attrs["add_offset"][0]
    x, y = np.meshgrid(x, y)
    a = np.sin(x) ** 2 + np.cos(x) ** 2 * (np.cos(y) ** 2 + (req / rpol) ** 2 * np.sin(y) ** 2)
    b = -2 * h * np.cos(x) * np.cos(y)
    c = h ** 2 - req ** 2
    with np.errstate(invalid="ignore"):
        rs = (-b - np.sqrt(b ** 2 - 4 * a * c)) / (2 * a)
        sx, sy, sz = rs * np.cos(x) * np.cos(y), -rs * np.sin(x), rs * np.cos(x) * np.sin(y)
        lat = np.degrees(np.arctan((req / rpol) ** 2 * sz / np.sqrt((h - sx) ** 2 + sy ** 2)))
        lon = np.degrees(lon0 - np.arctan(sy / (h - sx)))
    return lat, lon


gt = pd.read_csv(EVENTS_FILE).set_index("candidate_id").loc[EVENTS]
rows, n_files = [], 0
for sat_dir in sorted(RAW.iterdir()):
    grid = None
    for path in sorted(sat_dir.glob("*.nc")):
        n_files += 1
        with h5py.File(path) as f:
            if grid is None:                                  # the fixed grid is the same in every scan
                lat, lon = lat_lon(f)
                windows = {}
                for ev, e in gt.iterrows():
                    inside = (np.abs(lat - e.lat) <= BOX_DEG) & (np.abs(lon - e.lon) <= BOX_DEG)
                    if inside.any():
                        r, c = np.nonzero(inside)
                        windows[ev] = (slice(r.min(), r.max() + 1), slice(c.min(), c.max() + 1))
                grid = True
                print(f"{sat_dir.name}: events in view {list(windows)}")
            mask = f["Mask"]
            power, area, temp = f["Power"], f["Area"], f["Temp"]
            scan = pd.to_datetime(path.name.split("_s")[1][:13], format="%Y%j%H%M%S").tz_localize("UTC")
            for ev, (rs, cs) in windows.items():
                m = mask[rs, cs]
                code = np.where(m >= 30, m - 20, m)            # temporally filtered classes 30 to 35 -> 10 to 15
                for i, j in zip(*np.nonzero((code >= 10) & (code <= 15))):
                    rows.append(dict(event=ev, satellite=sat_dir.name.upper().replace("GOES", "GOES-"),
                                     scan_start_utc=scan, lat=round(float(lat[rs, cs][i, j]), 4),
                                     lon=round(float(lon[rs, cs][i, j]), 4), mask=int(m[i, j]),
                                     fire_class=FIRE_CODES[int(code[i, j])], confident=int(code[i, j]) in CONFIDENT,
                                     frp_mw=float(power[rs, cs][i, j]), file=path.name))
out = pd.DataFrame(rows).sort_values(["event", "scan_start_utc"])
PROC.mkdir(exist_ok=True)
out.to_csv(PROC / "goes_fire_pixels.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
print(f"{n_files} scans read; {len(out)} fire pixels near the events written to processed/goes_fire_pixels.csv")
