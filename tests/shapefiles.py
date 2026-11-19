"""Test helpers: tiny shapefiles, a zip of them, and a web that serves byte ranges of it."""
import io
import re
import struct
import zipfile


def shp(shapes):
    """shapes: ("point", lon, lat), ("polygon", west, south, east, north), ("rings", [[(lon, lat), ...], ...]) for an
    outline given corner by corner (several rings: the later ones are holes or separate pieces), or None for a record without a shape."""
    records = b""
    for number, shape in enumerate(shapes, 1):
        if shape is None:
            content = struct.pack("<i", 0)
        elif shape[0] == "point":
            content = struct.pack("<i2d", 1, shape[1], shape[2])
        elif shape[0] == "rings":
            points = [point for ring in shape[1] for point in ring]
            starts, at = [], 0
            for ring in shape[1]:
                starts.append(at)
                at += len(ring)
            content = struct.pack("<i4d2i", 5, min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points),
                                  max(y for _, y in points), len(starts), len(points))
            content += b"".join(struct.pack("<i", start) for start in starts) + b"".join(struct.pack("<2d", x, y) for x, y in points)
        else:
            west, south, east, north = shape[1:]
            ring = [(west, south), (west, north), (east, north), (east, south), (west, south)]
            content = struct.pack("<i4d2i", 5, west, south, east, north, 1, len(ring)) + struct.pack("<i", 0)
            content += b"".join(struct.pack("<2d", x, y) for x, y in ring)
        records += struct.pack(">2i", number, len(content) // 2) + content
    header = struct.pack(">i", 9994) + b"\0" * 20 + struct.pack(">i", (100 + len(records)) // 2) + struct.pack("<2i", 1000, 5) + b"\0" * 64
    return header + records


def dbf(kinds, names=None):
    """A table with the four columns Geofabrik writes: osm_id, code, fclass, name."""
    fields = [("osm_id", 12), ("code", 4), ("fclass", 28), ("name", 100)]
    header_len, record_len = 32 + 32 * len(fields) + 1, 1 + sum(length for _, length in fields)
    out = bytes([3, 126, 11, 18]) + struct.pack("<IHH", len(kinds), header_len, record_len) + b"\0" * 20
    for name, length in fields:
        out += name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([length, 0]) + b"\0" * 14
    out += b"\r"
    for n, kind in enumerate(kinds):
        label = (names or {}).get(n, "")
        out += b" " + str(n).encode().ljust(12) + b"2000" + kind.encode().ljust(28) + label.encode("utf-8").ljust(100)[:100]
    return out + b"\x1a"


def archive(members, stored=()):
    """A zip file's bytes. `stored` names members kept uncompressed, as Geofabrik keeps its tiny ones."""
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as z:
        for name, data in members.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED)
    return held.getvalue()


def ranged(files, asked=None):
    """get(url, headers={"Range": ...}) over {url: bytes}; anything else in `other` style is the caller's to add."""
    def get(url, **options):
        if asked is not None:
            asked.append((url, (options.get("headers") or {}).get("Range")))
        data = files[url]
        if callable(data):
            return data(url, **options)
        spec = (options.get("headers") or {}).get("Range")
        if not spec:
            return data
        suffix, between = re.fullmatch(r"bytes=-(\d+)", spec), re.fullmatch(r"bytes=(\d+)-(\d+)", spec)
        if suffix:
            return data[-int(suffix.group(1)):]
        return data[int(between.group(1)): int(between.group(2)) + 1]
    return get
