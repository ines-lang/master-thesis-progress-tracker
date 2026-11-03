"""Shared schema v2 (identical in all repos) and a checked CSV writer."""
import pandas as pd

SCHEMA_V2 = ["source", "sensor", "platform", "role", "obs_time_utc", "latitude", "longitude",
             "frp_mw", "confidence_raw", "confidence_class", "pixel_size_km", "pixel_area_km2",
             "day_night", "qc_flag", "static_proxy"]
EVENT_COLUMNS = ["event_id", "in_search_box", "event_member", "event_member_sensitivity"]

CONF_CLASSES = {"low", "nominal", "high"}
QC_FLAGS = {"ok", "static", "non_vegetation", "type_missing"}


def check_and_write(df, path, columns):
    """Check columns, allowed values and the time format, then write the CSV."""
    assert list(df.columns) == columns, f"columns differ from schema: {list(df.columns)}"
    assert df.confidence_class.isin(CONF_CLASSES).all()
    assert df.qc_flag.isin(QC_FLAGS).all()
    assert df.obs_time_utc.str.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$").all()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
