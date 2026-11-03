"""Step 1: Inspect the raw EFFIS delivery (read-only).

For every file in raw/: size and type. For every CSV: delimiter, encoding,
row count, columns, dtypes, example rows, geometry check, date formats.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from registry import REPO_DIR  # noqa: E402

import csv

import pandas as pd

# ---- parameters ----
BASE_DIR = REPO_DIR
RAW_DIR = BASE_DIR / "raw"
N_EXAMPLES = 5
DATE_COLS = ["initialdate", "finaldate"]
GEOMETRY_HINTS = ["x", "y", "lat", "lon", "latitude", "longitude", "geom", "geometry", "wkt", "centroid"]

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", 30)


def inspect_csv(path):
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8")   # raises if not UTF-8
    print(f"  encoding: UTF-8 (BOM: {raw_bytes.startswith(b'\xef\xbb\xbf')})")
    print(f"  delimiter: {csv.Sniffer().sniff(text[:5000]).delimiter!r}")

    # read everything as text first so nothing is silently converted
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    print(f"  rows (excluding header): {len(df)}, columns: {len(df.columns)}")

    print("\n  columns, inferred dtype, empty count, example value:")
    typed = pd.read_csv(path)
    for col in df.columns:
        n_empty = (df[col].str.strip() == "").sum()
        example = next((v for v in df[col] if v.strip()), "")
        print(f"    {col:38s} {str(typed[col].dtype):8s} empty={n_empty:4d}  e.g. {example!r}")

    print(f"\n  {N_EXAMPLES} example rows:")
    print(df.head(N_EXAMPLES).to_string())

    print("\n  geometry check:")
    hits = [c for c in df.columns if c.lower() in GEOMETRY_HINTS]
    for c in hits:
        n_filled = (df[c].str.strip() != "").sum()
        print(f"    column {c!r}: {n_filled} of {len(df)} rows filled")
    if not hits:
        print("    no column name suggests geometry")
    has_wkt = df.apply(lambda s: s.str.contains(r"POLYGON|POINT", case=False)).any().any()
    print(f"    any WKT text (POLYGON/POINT) anywhere: {has_wkt}")

    print("\n  date formats:")
    for c in DATE_COLS:
        if c in df.columns:
            patterns = df[c].str.replace(r"\d", "9", regex=True).value_counts()
            print(f"    {c}: patterns {patterns.to_dict()}")
            print(f"      min {df[c].min()}  max {df[c].max()}")

    print("\n  value counts of categorical columns:")
    for c in ["iso2", "country", "admlvl1", "admlvl2", "map_source"]:
        if c in df.columns:
            print(f"    {c}: {df[c].value_counts().to_dict()}")
    print(f"    id unique: {df['id'].is_unique}")


for path in sorted(RAW_DIR.iterdir()):
    print(f"\n=== {path.name}  ({path.stat().st_size} bytes)")
    if path.suffix.lower() == ".csv":
        inspect_csv(path)
    else:
        print("  not a CSV (text documentation, read separately)")
