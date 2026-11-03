"""Figure: FIRMS event members and other detections around one event (no EFFIS perimeter exists).

Run: python scripts/event/02_firms_context_figure.py --event <event_id> [--records ID ...]

Map frame = registry search_box (a crop, not the event). Background as in v1:
Esri World Imagery, zoom 11, Web Mercator, tiles from the FIRMS tile cache.
Writes events/<id>/figures/01_<id>_firms_context.png.
"""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from firms import TILE_CACHE_DIR, load_event_detections  # noqa: E402
from registry import REPO_DIR, event_args, event_dir, get_event, utc  # noqa: E402

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---- parameters (script level) ----
REFERENCE_FILE = "effis_reference.csv"
EARTH_RADIUS_M = 6378137.0    # Web Mercator sphere
BASEMAP_SOURCE = cx.providers.Esri.WorldImagery
BASEMAP_CREDIT = "Esri World Imagery. " + BASEMAP_SOURCE.attribution
BASEMAP_ZOOM = 11
TICK_STEP_DEG = 0.2
COL_OTHER = "#b4b3ad"     # muted grey: detections of other fires
COL_FIRE = "#2a78d6"      # categorical slot 1: event members
COL_TEXT = "#52514e"
COL_INK = "#0b0b0b"


def merc_x(lon):
    """Longitude (deg) to Web Mercator x (m), the projection of the map tiles."""
    return EARTH_RADIUS_M * np.radians(lon)


def merc_y(lat):
    return EARTH_RADIUS_M * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


args = event_args()
reg, ev = get_event(args.event)
box = ev["search_box"]
start = utc(reg["data_window"]["start_utc"])
firms_end = utc(reg["data_window"]["firms_data_end_utc"])
ref = pd.read_csv(event_dir(args.event, "processed") / REFERENCE_FILE, dtype={"effis_id": str},
                  parse_dates=["start_utc"])
total = ref[ref["effis_id"] == "TOTAL"].iloc[0]
ids = ref.loc[ref["effis_id"] != "TOTAL", "effis_id"].tolist()

det, firms_source = load_event_detections(args.event)
det = det[det["obs_time_utc"].between(start, firms_end)]
in_box = (det["latitude"].between(box["lat_min"], box["lat_max"])
          & det["longitude"].between(box["lon_min"], box["lon_max"]))
fire = det[det["event_member"]]
oth = det[~det["event_member"] & in_box]
print(f"members {len(fire)} (outside search box: {(~in_box[det['event_member']]).sum()}), "
      f"other detections in search box {len(oth)}; source: {firms_source}")

cx.set_cache_dir(TILE_CACHE_DIR)
fig, ax = plt.subplots(figsize=(7, 6.4))
img, ext = cx.bounds2img(box["lon_min"], box["lat_min"], box["lon_max"], box["lat_max"],
                         zoom=BASEMAP_ZOOM, source=BASEMAP_SOURCE, ll=True)
ax.imshow(img, extent=ext, interpolation="bilinear", zorder=0)
ax.set_xlim(merc_x(box["lon_min"]), merc_x(box["lon_max"]))
ax.set_ylim(merc_y(box["lat_min"]), merc_y(box["lat_max"]))
ax.set_aspect("equal")
ax.scatter(merc_x(oth["longitude"]), merc_y(oth["latitude"]), s=5, c=COL_OTHER, edgecolors=COL_INK,
           linewidths=0.15, zorder=2, label=f"other FIRMS detections in search box ({len(oth):,})")
ax.scatter(merc_x(fire["longitude"]), merc_y(fire["latitude"]), s=8, c=COL_FIRE, edgecolors="white",
           linewidths=0.3, zorder=3, label=f"FIRMS event members ({len(fire):,})")
ax.plot([], [], lw=0, label="map frame = registry search_box (a crop, not the event)")
lons = np.arange(np.ceil(box["lon_min"] / TICK_STEP_DEG) * TICK_STEP_DEG, box["lon_max"] + 1e-9, TICK_STEP_DEG)
lats = np.arange(np.ceil(box["lat_min"] / TICK_STEP_DEG) * TICK_STEP_DEG, box["lat_max"] + 1e-9, TICK_STEP_DEG)
ax.set_xticks(merc_x(lons), [f"{v:g}" for v in np.round(lons, 1)])
ax.set_yticks(merc_y(lats), [f"{v:g}" for v in np.round(lats, 1)])
ax.set_xlabel("Longitude (°E)", color=COL_TEXT)
ax.set_ylabel("Latitude (°N)", color=COL_TEXT)
ax.tick_params(colors=COL_TEXT, labelsize=8)
for s in ax.spines.values():
    s.set_edgecolor("#c3c2b7")
ax.set_title(f"{ev['name']}\nFIRMS detections {start:%d %b} to {firms_end:%d %b %Y}\n"
             f"EFFIS {', '.join(ids)} (no geometry): {int(total['area_ha']):,} ha, "
             f"start {total['start_utc']:%d %b %H:%M} UTC",
             fontsize=9, loc="left", color=COL_INK)
leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, fontsize=7, frameon=False)
leg.legend_handles[2].set_visible(False)
fig.text(0.99, 0.01, textwrap.fill("Detections: NASA FIRMS (MODIS, VIIRS). Record: EFFIS / European Commission JRC. "
                                   f"Background: {BASEMAP_CREDIT} (imagery mosaic of various dates, "
                                   "not August 2025)", 110), ha="right", va="bottom", fontsize=5, color=COL_TEXT)
fig.tight_layout(rect=(0, 0.04, 1, 1))
out_file = event_dir(args.event, "figures") / f"01_{args.event}_firms_context.png"
fig.savefig(out_file, dpi=300)
print(f"written {out_file.relative_to(REPO_DIR)}")
