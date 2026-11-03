"""Official discovery times of the US candidate fires from NIFC WFIGS (Step 2a, ground truth).

Usage: python scripts/00_wfigs_query.py
Output: processed/wfigs_candidates.csv (one row per fire, discovery time in UTC)
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

# ---- parameters ----
URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
       "WFIGS_Incident_Locations/FeatureServer/0/query")
FIRE_IDS = ["2025-WYWBD-000254", "2025-IDBOD-000997", "2025-IDBOF-000991",   # Red Canyon, Box, Rock
            "2025-WYWAX-000252", "2025-WYPAX-000256", "2025-MTCRA-250811"]   # Spring Creek, Sleeper Ranch, Mission Butte
FIELDS = ["IncidentName", "UniqueFireIdentifier", "FireDiscoveryDateTime", "IncidentSize",
          "FireCause", "InitialLatitude", "InitialLongitude", "POOState", "IncidentTypeCategory"]
OUT_FILE = Path(__file__).resolve().parents[1] / "processed" / "wfigs_candidates.csv"

query = {"where": "UniqueFireIdentifier IN ({})".format(",".join(f"'{i}'" for i in FIRE_IDS)),
         "outFields": ",".join(FIELDS), "returnGeometry": "false", "f": "json"}
with urllib.request.urlopen(f"{URL}?{urllib.parse.urlencode(query)}", timeout=60) as resp:
    rows = [f["attributes"] for f in json.load(resp)["features"]]

df = pd.DataFrame(rows)
df["discovery_utc"] = pd.to_datetime(df.FireDiscoveryDateTime, unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
df["size_ha"] = (df.IncidentSize * 0.404686).round(0)
df = df.drop(columns="FireDiscoveryDateTime").sort_values("discovery_utc")
df["source"] = "NIFC WFIGS Incident Locations (FireDiscoveryDateTime, UTC)"
df["queried_utc"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")

OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_FILE, index=False)
print(df[["IncidentName", "UniqueFireIdentifier", "discovery_utc", "size_ha", "FireCause"]].to_string(index=False))
print(f"written: {OUT_FILE}")
