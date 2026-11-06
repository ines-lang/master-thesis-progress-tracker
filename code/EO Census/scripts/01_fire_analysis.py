"""Step 1.2: which payloads in orbit during the window are useful for wildfire detection, and the EO-layer proposal.

Inputs:  processed/window_payloads.csv (00_fetch_window.py)
         notes/fire_capability.csv (hand-curated: instrument, fire bands, public fire product, status in Aug 2025,
         source and verification level per mission)
Criteria (Strategy v3.1, decisions of 6 Nov 2026):
  A. in orbit during the window (orbit record between 8 and 16 Aug 2025)
  B. fire-capable: thermal fire band (MWIR / LWIR) or high-resolution SWIR with an active-fire method
  C. operational in the window (not decommissioned, standby, backup or commissioning)
  D. layer (decisions of 6 Nov 2026; GEO and HEO stay census only, as S0 alert / T0 reference):
     S1 EO layer:              public LEO mission whose global active-fire product was openly available in near
                               real time during the window (the public record S0 is built from these; S1 vs S0)
     S3 extended public layer: every other public LEO mission
     S4 commercial layer:      private LEO mission
  thermal = has a MWIR fire band; LWIR-only sensors are not fire-capable (same rule as ECOSTRESS)
Outputs (processed/): eo_census.csv (one row per fire-capable mission, with its orbit), eo_layer_proposal.csv

Usage: python scripts/01_fire_analysis.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

# ---- parameters ----
CENSUS_DIR = Path(__file__).resolve().parents[1]
PROC = CENSUS_DIR / "processed"
FIRE_CAPABLE = {"thermal", "high-res SWIR"}
NOT_OPERATIONAL = ["decommission", "standby", "backup", "commissioning", "end of operations", "not operational",
                   "not imaging", "not confirmed", "not found"]
CURRENT_EO_LAYER = {37849, 43013, 54234, 25994, 27424, 41335, 43437}   # Month 2: VIIRS x3, MODIS x2, SLSTR x2
EARTH_RADIUS_KM = 6378.137
MU_KM3_S2 = 398600.4418

window = pd.read_csv(PROC / "window_payloads.csv")
cap = pd.read_csv(CENSUS_DIR / "notes" / "fire_capability.csv")

census = cap.merge(window, on="norad_id", how="left")
census["A_in_orbit"] = census["epoch_utc"].notna()
census["B_fire_capable"] = census["band_class"].isin(FIRE_CAPABLE)
census["C_operational"] = ~census["status_aug2025"].str.contains("|".join(NOT_OPERATIONAL), case=False)
census["is_geo"] = ~census["orbit_family"].fillna("").str.startswith("LEO")      # GEO and HEO imagers
census["D_public_product"] = ~census["public_fire_product"].fillna("none").str.lower().str.startswith("none")
# mean altitude from the mean motion (circular orbit), for the table
n_rad_s = census["mean_motion_rev_day"] * 2 * np.pi / 86400
census["altitude_km"] = ((MU_KM3_S2 / n_rad_s ** 2) ** (1 / 3) - EARTH_RADIUS_KM).round(0)
census["in_current_eo_layer"] = census["norad_id"].isin(CURRENT_EO_LAYER)

ok = census["A_in_orbit"] & census["B_fire_capable"] & census["C_operational"]
public, leo = census["sector"].eq("public"), ~census["is_geo"]
validated = census["D_public_product"] & census["product_coverage"].eq("global")
census["role"] = np.select(
    [ok & leo & public & validated, ok & leo & public, ok & leo & ~public, ok & ~leo],
    ["S1 EO layer", "S3 extended public layer", "S4 commercial layer", "GEO / HEO: census only (S0 alert / T0 reference)"],
    default="excluded")
census["validation"] = np.where(public & validated, "yes (global public product)",
                                np.where(census["D_public_product"] & public,
                                         "limited: " + census["product_coverage"].fillna(""), "no public product"))
census.loc[~census["A_in_orbit"], "reason"] = "not in orbit in the window"
census.loc[census["A_in_orbit"] & ~census["B_fire_capable"], "reason"] = "no MWIR fire band and no high-res SWIR with an active-fire method"
census.loc[census["A_in_orbit"] & census["B_fire_capable"] & ~census["C_operational"], "reason"] = \
    census["status_aug2025"]

cols = ["norad_id", "mission", "sector", "agency", "instrument", "band_class", "fire_bands", "pixel_fire_band", "orbit_family",
        "altitude_km", "inclination_deg", "public_fire_product", "product_coverage", "status_aug2025", "level",
        "source", "in_current_eo_layer", "role", "validation", "reason", "epoch_utc", "line1", "line2"]
census = census.sort_values(["role", "orbit_family", "mission"])
census[cols].to_csv(PROC / "eo_census.csv", index=False)
layer = census[census["role"].str.match("S[134] ")]
layer[cols].to_csv(PROC / "eo_layer_proposal.csv", index=False)

# ---- report ----
print(f"payloads in orbit in the window: {len(window)}; missions in fire_capability.csv: {len(cap)}")
print(f"not found in the window download: {', '.join(census.loc[~census.A_in_orbit, 'mission']) or 'none'}")
print("\nrole per mission:\n" + census.groupby("role").size().to_string())
pd.set_option("display.width", 220)
print("\nproposed layers:\n" + layer[["role", "mission", "instrument", "band_class", "altitude_km",
                                       "status_aug2025", "validation", "level"]]
      .to_string(index=False))
print("\nexcluded:\n" + census[census.role == "excluded"][["mission", "orbit_family", "reason"]].to_string(index=False))
