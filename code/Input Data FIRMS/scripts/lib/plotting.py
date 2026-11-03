"""Plot settings and helpers shared by the event figures (v1 style)."""
import textwrap

import contextily as cx
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from lib.helpers import PROCESSED, merc_x, merc_y

DPI = 300
# colors: validated categorical slots 1 to 3 (dataviz reference palette, light mode)
SENSOR_COLOR = {"VIIRS": "#2a78d6", "MODIS": "#eb6834", "OLI": "#1baf7a"}
OTHER_COLOR = "#c3c2b7"
INK, INK_2, MUTED, GRID, NO_DATA = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#f3f2ee"
PLATFORMS = ["Suomi-NPP", "NOAA-20", "NOAA-21", "Terra", "Aqua", "Landsat-8", "Landsat-9"]
PLATFORM_SENSOR = {"Suomi-NPP": "VIIRS", "NOAA-20": "VIIRS", "NOAA-21": "VIIRS", "Terra": "MODIS",
                   "Aqua": "MODIS", "Landsat-8": "OLI", "Landsat-9": "OLI"}
PLATFORM_MARKER = {"Suomi-NPP": "o", "NOAA-20": "s", "NOAA-21": "^", "Terra": "D", "Aqua": "v",
                   "Landsat-8": "P", "Landsat-9": "X"}
BASEMAP_SOURCE = cx.providers.Esri.WorldImagery
BASEMAP_CREDIT = ("Background: Esri World Imagery. " + BASEMAP_SOURCE.attribution
                  + " (imagery mosaic of various dates, not August 2025)")
TILE_CACHE_DIR = PROCESSED / "tile_cache"

plt.rcParams.update({
    "font.size": 8, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK_2, "xtick.color": INK_2,
    "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 9, "axes.titlecolor": INK,
    "legend.frameon": False, "figure.facecolor": "white", "axes.facecolor": "white",
})
TILE_CACHE_DIR.mkdir(exist_ok=True)
cx.set_cache_dir(TILE_CACHE_DIR)


def basemap_zoom(box):
    """Tile zoom so that the box is about 1,000 to 2,000 px wide."""
    width_deg = box["lon_max"] - box["lon_min"]
    return int(np.clip(np.round(np.log2(360 / width_deg * 1500 / 256)), 5, 12))


def add_basemap(ax, box):
    img, ext = cx.bounds2img(box["lon_min"], box["lat_min"], box["lon_max"], box["lat_max"],
                             zoom=basemap_zoom(box), source=BASEMAP_SOURCE, ll=True)
    ax.imshow(img, extent=ext, interpolation="bilinear", zorder=0)
    ax.set_xlim(merc_x(box["lon_min"]), merc_x(box["lon_max"]))
    ax.set_ylim(merc_y(box["lat_min"]), merc_y(box["lat_max"]))
    ax.set_aspect("equal")
    ax.grid(False)


def degree_ticks(ax, box):
    width = box["lon_max"] - box["lon_min"]
    step = 2 if width > 5 else 0.5 if width > 2 else 0.2
    lons = np.arange(np.ceil(box["lon_min"] / step) * step, box["lon_max"] + 1e-9, step)
    lats = np.arange(np.ceil(box["lat_min"] / step) * step, box["lat_max"] + 1e-9, step)
    ax.set_xticks(merc_x(lons), [f"{v:g}" for v in np.round(lons, 1)])
    ax.set_yticks(merc_y(lats), [f"{v:g}" for v in np.round(lats, 1)])


def box_patch_merc(box, **kw):
    x0, y0 = merc_x(box["lon_min"]), merc_y(box["lat_min"])
    return Rectangle((x0, y0), merc_x(box["lon_max"]) - x0, merc_y(box["lat_max"]) - y0, fill=False, **kw)


def halo_text(ax, x, y, text, **kw):
    t = ax.text(x, y, text, color="white", fontsize=7, zorder=5, **kw)
    t.set_path_effects([pe.withStroke(linewidth=2, foreground=INK)])


def credit(fig, x=0.99, y=0.015, width=75):
    fig.text(x, y, textwrap.fill(BASEMAP_CREDIT, width), ha="right", va="bottom", fontsize=5, color=INK_2)


def time_axis(ax, start, end, day_interval=1):
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=day_interval, tz="UTC"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b", tz="UTC"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[12], tz="UTC"))
