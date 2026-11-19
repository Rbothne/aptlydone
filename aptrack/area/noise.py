"""Transport noise at each building, from the US Department of Transportation's National Transportation Noise
Map (2020): modeled average sound over 24 hours from aircraft, from roads and from railways.

The map is published only as coloured tiles, so this reads the tile a building falls on and looks up the colour
of its pixel in the map's own legend. The result is the bottom of the building's band in decibels (45, 50, 55,
60, 70, 80, 90), or None where nothing is mapped (quieter than 45). The Department says the map is for trends
and not exact enough to judge a single address, so it is shown as a band, and a block either way may differ.
"""

import base64
import json
import math
import re

from .. import fetch
from . import png

SERVICE = "https://geo.dot.gov/server/rest/services/Hosted/{layer}/MapServer"
LAYERS = {"air": "NTAD_Noise_2020_CONUS_Aviation", "road": "NTAD_Noise_2020_CONUS_Road", "rail": "NTAD_Noise_2020_CONUS_Rail"}
ZOOM = 12                     # the map's finest tiles: a pixel is about 30 metres here
CLOSE = 40                    # how far a pixel's colour may sit from a legend colour and still be that band


def tile_of(lat, lon, zoom):
    """(tile column, tile row, pixel across, pixel down) of a place on the usual web-map tiling."""
    n = 2 ** zoom
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(x), int(y), int((x % 1) * 256), int((y % 1) * 256)


def bands(legend):
    """[((red, green, blue), decibels at the bottom of the band), ...] from the map's legend."""
    found = []
    for layer in legend.get("layers") or []:
        for entry in layer.get("legend") or []:
            number = re.search(r"\d+(?:\.\d+)?", entry.get("label") or "")
            if not number or not entry.get("imageData"):
                continue
            swatch = png.pixels(base64.b64decode(entry["imageData"]))
            middle = swatch[len(swatch) // 2][len(swatch[0]) // 2]
            found.append((middle[:3], int(float(number.group(0)))))
    return found


def level(pixel, legend_bands):
    """The band a pixel's colour stands for, or None for a clear pixel or a colour the legend does not have."""
    if pixel[3] < 128:
        return None
    distance, decibels = min((sum(abs(a - b) for a, b in zip(pixel[:3], colour)), decibels) for colour, decibels in legend_bands)
    return decibels if distance <= CLOSE else None


def read(get, buildings, zoom=ZOOM):
    """{building id: {"air": decibels or None, "road": ..., "rail": ...}}. A kind of noise whose map could not be
    read is left out of every building, so the caller keeps what it had."""
    placed = [b for b in buildings if b.get("lat") is not None and b.get("lon") is not None]
    found = {b["id"]: {} for b in placed}
    for kind, layer in LAYERS.items():
        base = SERVICE.format(layer=layer)
        try:
            legend_bands = bands(json.loads(get(f"{base}/legend?f=json")))
            if not legend_bands:
                raise ValueError("the legend lists no bands")
            tiles, levels = {}, {}
            for building in placed:
                x, y, px, py = tile_of(building["lat"], building["lon"], zoom)
                if (x, y) not in tiles:
                    try:
                        tiles[x, y] = png.pixels(get(f"{base}/tile/{zoom}/{y}/{x}"))
                    except fetch.Gone:
                        tiles[x, y] = None                        # no tile: nothing mapped anywhere on it
                rows = tiles[x, y]
                levels[building["id"]] = level(rows[py][px], legend_bands) if rows else None
        except Exception as error:
            print(f"  no {kind} noise this time: {error!r}")
            continue
        for building_id, decibels in levels.items():
            found[building_id][kind] = decibels
        print(f"  {kind} noise: {len(tiles)} tiles, {sum(1 for v in levels.values() if v)} of {len(levels)} buildings in a mapped band")
    return found
