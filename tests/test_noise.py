"""Transport noise at a building, read from the US DOT's noise map: coloured map tiles, decoded here."""
import base64
import json
import struct
import unittest
import zlib

from aptrack import fetch
from aptrack.area import noise, png
from tests.quiet import QuietTestCase

CLEAR = (0, 0, 0, 0)
YELLOW, ORANGE, RED = (255, 255, 0, 255), (255, 170, 0, 255), (230, 0, 0, 255)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def encode(rows, kind=0, alpha=True):
    """A PNG of `rows` (lists of (r, g, b, a)), every line written with filter type `kind`."""
    size = 4 if alpha else 3
    raw, before = b"", bytes(len(rows[0]) * size)
    for row in rows:
        line = bytes(value for pixel in row for value in pixel[:size])
        out = bytearray()
        for i, value in enumerate(line):
            left = line[i - size] if i >= size else 0
            up, corner = before[i], before[i - size] if i >= size else 0
            guess = (0, left, up, (left + up) // 2, paeth(left, up, corner))[kind]
            out.append((value - guess) % 256)
        raw += bytes([kind]) + bytes(out)
        before = line

    def chunk(name, body):
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))
    head = struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 6 if alpha else 2, 0, 0, 0)
    packed = zlib.compress(raw)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"pHYs", bytes(9))
            + chunk(b"IDAT", packed[:7]) + chunk(b"IDAT", packed[7:]) + chunk(b"IEND", b""))


def encode_palette(rows, depth):
    """The same picture as a palette PNG: `depth` bits per pixel, transparency listed per palette entry."""
    colours = sorted({pixel for row in rows for pixel in row})
    raw = b""
    for row in rows:
        bits = "".join(format(colours.index(pixel), f"0{depth}b") for pixel in row)
        bits += "0" * (-len(bits) % 8)
        raw += b"\x00" + bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))

    def chunk(name, body):
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", len(rows[0]), len(rows), depth, 3, 0, 0, 0))
            + chunk(b"PLTE", bytes(v for c in colours for v in c[:3])) + chunk(b"tRNS", bytes(c[3] for c in colours))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def swatch(colour):
    return base64.b64encode(encode([[colour] * 4] * 4)).decode()


LEGEND = json.dumps({"layers": [
    {"layerName": "Boundary", "legend": [{"label": "", "imageData": swatch((9, 9, 9, 255))}]},
    {"layerName": "Image", "legend": [{"label": "45.0 - 49.9", "imageData": swatch(YELLOW)},
                                      {"label": "50.0 - 54.9", "imageData": swatch(ORANGE)},
                                      {"label": "> 90.0", "imageData": swatch(RED)}]}]})


class PngTests(unittest.TestCase):
    ROWS = [[YELLOW, CLEAR, RED], [ORANGE, (1, 2, 3, 4), CLEAR], [(250, 251, 252, 253), RED, YELLOW]]

    def test_every_line_filter_decodes_to_the_same_picture(self):
        for kind in range(5):
            self.assertEqual(png.pixels(encode(self.ROWS, kind)), self.ROWS, kind)

    def test_a_picture_without_transparency_is_opaque(self):
        self.assertEqual(png.pixels(encode(self.ROWS, 4, alpha=False)), [[p[:3] + (255,) for p in row] for row in self.ROWS])

    def test_something_else_is_an_error(self):
        with self.assertRaises(ValueError):
            png.pixels(b"<html>Please verify you are human</html>")
        with self.assertRaises(ValueError):                                   # a grey picture: not what this map sends
            png.pixels(encode(self.ROWS).replace(struct.pack(">IIBBBBB", 3, 3, 8, 6, 0, 0, 0), struct.pack(">IIBBBBB", 3, 3, 8, 0, 0, 0, 0)))

    def test_a_palette_picture_decodes_too(self):
        few = [[YELLOW, CLEAR, RED], [CLEAR, CLEAR, YELLOW]]
        for depth in (2, 4, 8):
            self.assertEqual(png.pixels(encode_palette(few, depth)), few, depth)
        self.assertEqual(png.pixels(encode_palette([[CLEAR] * 9, [CLEAR] * 9], 1)), [[CLEAR] * 9, [CLEAR] * 9])
        self.assertEqual(png.pixels(encode_palette(self.ROWS, 4)), self.ROWS)


class TileTests(unittest.TestCase):
    def test_where_a_place_falls_on_the_map_s_tiles(self):
        self.assertEqual(noise.tile_of(38.8650, -77.0403, 12), (1171, 1567, 115, 97))
        self.assertEqual(noise.tile_of(38.8650, -77.0403, 11), (585, 783, 185, 176))

    def test_the_legend_gives_each_colour_its_loudness(self):
        self.assertEqual(noise.bands(json.loads(LEGEND)), [(YELLOW[:3], 45), (ORANGE[:3], 50), (RED[:3], 90)])

    def test_a_pixel_s_loudness_is_its_colour_s_band(self):
        bands = noise.bands(json.loads(LEGEND))
        self.assertEqual(noise.level(ORANGE, bands), 50)
        self.assertEqual(noise.level((253, 172, 3, 255), bands), 50)           # a shade off, as tile edges are
        self.assertIsNone(noise.level(CLEAR, bands))                           # nothing mapped here: under 45
        self.assertIsNone(noise.level((0, 0, 255, 255), bands))                # a colour the legend does not have


class ReadTests(QuietTestCase):
    def web(self, tiles, asked):
        def get(url, **options):
            asked.append(url)
            if url.endswith("/legend?f=json"):
                return LEGEND.encode()
            layer, z, y, x = url.split("/Hosted/")[1].split("/MapServer/tile/")[0], *url.rsplit("/", 3)[1:]
            answer = tiles.get((layer, int(x), int(y)))
            if answer is None:
                raise fetch.Gone(url)
            return answer
        return get

    def tile(self, marks):
        rows = [[CLEAR] * 256 for _ in range(256)]
        for (px, py), colour in marks.items():
            rows[py][px] = colour
        return encode(rows)

    def test_each_building_gets_the_loudness_under_it_for_each_kind_of_noise(self):
        air = noise.LAYERS["air"]
        asked = []
        buildings = [{"id": "by-the-runway", "lat": 38.8650, "lon": -77.0403}, {"id": "same-tile", "lat": 38.8660, "lon": -77.0410},
                     {"id": "far", "lat": 39.2, "lon": -77.3}, {"id": "nowhere", "lat": None, "lon": None}]
        got = noise.read(self.web({(air, 1171, 1567): self.tile({(115, 97): RED})}, asked), buildings, zoom=12)
        self.assertEqual(got["by-the-runway"], {"air": 90, "road": None, "rail": None})
        self.assertEqual(got["same-tile"], {"air": None, "road": None, "rail": None})
        self.assertEqual(got["far"], {"air": None, "road": None, "rail": None})               # no tile there: nothing mapped
        self.assertNotIn("nowhere", got)
        tiles = [url for url in asked if "/tile/" in url]
        self.assertEqual(len(tiles), len(set(tiles)))                                          # a tile is fetched once
        self.assertEqual(len(tiles), 2 * len(noise.LAYERS))

    def test_a_layer_that_cannot_be_read_leaves_that_kind_out(self):
        def get(url, **options):
            if noise.LAYERS["rail"] in url:
                raise OSError("timed out")
            return self.web({}, [])(url, **options)
        got = noise.read(get, [{"id": "a", "lat": 38.9, "lon": -77.0}], zoom=12)
        self.assertEqual(got["a"], {"air": None, "road": None})


if __name__ == "__main__":
    unittest.main()
