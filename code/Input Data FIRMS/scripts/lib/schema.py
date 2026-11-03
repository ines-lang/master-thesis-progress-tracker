"""Shared schema v2 (identical in all repos): column order, allowed values, writer with checks."""
import pandas as pd

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

SCHEMA_V2 = ["source", "sensor", "platform", "role", "obs_time_utc", "latitude", "longitude", "frp_mw",
             "confidence_raw", "confidence_class", "pixel_size_km", "pixel_area_km2", "day_night", "qc_flag",
             "static_proxy"]
EVENT_COLUMNS = ["event_id", "in_search_box", "event_member", "event_member_sensitivity"]

ALLOWED = {
    "source": {"FIRMS", "LSASAF"},
    "sensor": {"VIIRS", "MODIS", "OLI", "SEVIRI"},
    "platform": {"Suomi-NPP", "NOAA-20", "NOAA-21", "Terra", "Aqua", "Landsat-8", "Landsat-9", "MSG"},
    "role": {"baseline", "context", "supplementary"},
    "confidence_class": {"low", "nominal", "high"},
    "day_night": {"D", "N", ""},
    "qc_flag": {"ok", "static", "non_vegetation", "type_missing"},
    "static_proxy": {"True", "False", ""},
}
MANDATORY = ["source", "sensor", "platform", "role", "obs_time_utc", "latitude", "longitude",
             "confidence_raw", "confidence_class", "pixel_size_km", "pixel_area_km2", "qc_flag"]


def to_bool_or_empty(series):
    """True/False as text, missing as empty string (schema: empty where not applicable)."""
    return series.map(lambda v: "" if pd.isna(v) else str(bool(v)))


def check_and_write(df, path, event=False):
    """Check df against schema v2 (plus event columns if event=True) and write it."""
    columns = SCHEMA_V2 + (EVENT_COLUMNS if event else [])
    assert list(df.columns) == columns, f"column order differs from schema v2: {list(df.columns)}"
    for col, allowed in ALLOWED.items():
        bad = set(df[col].unique()) - allowed
        assert not bad, f"{col}: values outside schema {bad}"
    for col in MANDATORY + (EVENT_COLUMNS if event else []):
        assert df[col].notna().all(), f"{col} has missing values"
    assert df["obs_time_utc"].str.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$").all(), "obs_time_utc not ISO with Z"
    assert df["latitude"].between(-90, 90).all() and df["longitude"].between(-180, 180).all()
    df.to_csv(path, index=False)


FIRMS_SOURCE = "FIRMS"
FIRMS_ROLE = {"VIIRS": "baseline", "MODIS": "baseline", "OLI": "supplementary"}


def firms_to_schema(df):
    """FIRMS clean table -> schema v2 columns (shared by the event scripts)."""
    return pd.DataFrame({
        "source": FIRMS_SOURCE,
        "sensor": df["sensor"],
        "platform": df["platform"],
        "role": df["sensor"].map(FIRMS_ROLE),
        "obs_time_utc": df["obs_time_utc"].dt.strftime(ISO_FMT),
        "latitude": df["latitude"],
        "longitude": df["longitude"],
        "frp_mw": df["frp"],
        "confidence_raw": df["confidence_raw"],
        "confidence_class": df["confidence_class"],
        "pixel_size_km": df["pixel_size_km"],
        "pixel_area_km2": df["pixel_area_km2"],
        "day_night": df["daynight"].fillna(""),
        "qc_flag": df["qc_flag"],
        "static_proxy": to_bool_or_empty(df["static_proxy"]),
    })


