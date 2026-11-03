"""Step 2: Standardize the EFFIS records into processed/effis_events_es.csv.

One row per EFFIS record. No geometry exists in the delivery (Step 1), so the
centroid columns stay empty and has_geometry is False.
Assumption A1: initialdate has no time zone suffix and is taken as UTC.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from registry import REPO_DIR, load_registry, utc  # noqa: E402
import pandas as pd

# ---- parameters ----
BASE_DIR = REPO_DIR
RAW_CSV = BASE_DIR / "raw" / "608dedc69b3c4e95977728cfa96fa32a.csv"
OUT_FILE = BASE_DIR / "processed" / "effis_events_es.csv"
PERIOD_END_DAY = utc(load_registry()["data_window"]["end_utc"]).normalize()   # last day of the window
N_LARGEST = 10
LAND_COVER_COLS = [
    "broadleaved_forest_percent", "coniferous_forest_percent", "mixed_forest_percent",
    "sclerophillous_vegetation_percent", "transitional_vegetation_percent",
    "other_natural_percent", "agriculture_percent", "artificial_percent",
    "other_percent", "natura2k_percent",
]

# read as text so land cover values are copied unchanged
raw = pd.read_csv(RAW_CSV, dtype=str, keep_default_na=False)

out = pd.DataFrame({
    "effis_id": raw["id"],
    "country": raw["iso2"],
    "province": raw["admlvl3"],
    "commune": raw["admlvl5"],
    # A1: initialdate taken as UTC; finaldate carries "+00"
    "start_date": pd.to_datetime(raw["initialdate"], format="mixed").dt.tz_localize("UTC"),
    "last_update": pd.to_datetime(raw["finaldate"].str.replace(r"\+00$", "", regex=True),
                                  format="mixed").dt.tz_localize("UTC"),
    "area_ha": raw["area_ha"].astype(int),
})
out["duration_days"] = ((out["last_update"] - out["start_date"]).dt.total_seconds() / 86400).round(2)
out["has_geometry"] = False
out["centroid_lat"] = ""
out["centroid_lon"] = ""
# extra context columns (not in the spec, kept for traceability)
out["region"] = raw["admlvl2"]
out["map_source"] = raw["map_source"]
for c in LAND_COVER_COLS:
    out[c] = raw[c]

core = ["effis_id", "country", "province", "commune", "start_date", "last_update",
        "duration_days", "area_ha", "has_geometry", "centroid_lat", "centroid_lon"]
out = out[core + ["region", "map_source"] + LAND_COVER_COLS].sort_values("start_date")

assert (out["duration_days"] >= 0).all(), "last_update before start_date"
out.to_csv(OUT_FILE, index=False, date_format="%Y-%m-%d %H:%M:%S%z")
print(f"written {OUT_FILE.name}: {len(out)} records")

# ---- report ----
show = ["effis_id", "region", "province", "commune", "start_date", "last_update", "duration_days", "area_ha"]
fmt = {"start_date": lambda t: t.strftime("%m-%d %H:%M"), "last_update": lambda t: t.strftime("%m-%d %H:%M")}
print(f"total area: {out['area_ha'].sum():,} ha")
print(f"by region (ha): {out.groupby('region')['area_ha'].sum().sort_values(ascending=False).to_dict()}")
print(f"\n{N_LARGEST} largest records:")
print(out.nlargest(N_LARGEST, "area_ha")[show].to_string(index=False, formatters=fmt))

late = out[out["last_update"] >= PERIOD_END_DAY].sort_values("area_ha", ascending=False)
print(f"\nrecords with last_update on or after {PERIOD_END_DAY.date()}: {len(late)} "
      f"({late['area_ha'].sum():,} ha); after the window (>= 08-17): "
      f"{(late['last_update'] >= PERIOD_END_DAY + pd.Timedelta(days=1)).sum()}")
print(late[show].to_string(index=False, formatters=fmt))
