"""A few files out of a big zip on the web, and the shapefiles inside them.

OpenStreetMap's data for a whole state is published as one zip of shapefiles (hundreds of megabytes, mostly
roads and building outlines). The zip's directory sits at its end and says where each member starts, so the
two small layers wanted here are downloaded by byte range: the end of the file, then just those members.

A shapefile is a pair: .shp holds one shape per record (a point, or an outline with its bounding box written
ahead of it), and .dbf holds one row of attributes per record, in the same order.
"""

import struct
import zlib

TAIL = 65536                # bytes from the end of the zip that normally hold its whole directory
NEAR = 65536                # members closer together than this are fetched in one request
END, ENTRY, LOCAL = b"PK\x05\x06", b"PK\x01\x02", b"PK\x03\x04"


def ranged(get, url, spec):
    return get(url, headers={"Range": f"bytes={spec}", "Accept-Encoding": "identity"}, raw=True, timeout=300)


def directory(get, url, tail=TAIL):
    """({member name: (start of its record, compressed size, size, method)}, where the directory starts)."""
    end = ranged(get, url, f"-{tail}")
    at = end.rfind(END)
    if at < 0 or len(end) < at + 22:
        raise ValueError(f"{url} is not a zip file")
    count, size, start = struct.unpack("<HII", end[at + 10: at + 20])
    if start == 0xFFFFFFFF or count == 0xFFFF:
        raise ValueError(f"{url} is too big a zip for this reader")
    begins = start + size - at                                   # where `end` begins in the file
    listing = end[start - begins: start - begins + size] if start >= begins else ranged(get, url, f"{start}-{start + size - 1}")
    found, at = {}, 0
    for _ in range(count):
        if listing[at: at + 4] != ENTRY:
            raise ValueError(f"{url}: the zip's directory is damaged")
        method, = struct.unpack("<H", listing[at + 10: at + 12])
        packed, full, name_len, extra_len, comment_len = struct.unpack("<IIHHH", listing[at + 20: at + 34])
        offset, = struct.unpack("<I", listing[at + 42: at + 46])
        name = listing[at + 46: at + 46 + name_len].decode("utf-8", "replace")
        found[name] = (offset, packed, full, method)
        at += 46 + name_len + extra_len + comment_len
    return found, start


def unpack(record, packed, full, method, name):
    """A member's contents from its record in the zip (a short header, then the data)."""
    if record[:4] != LOCAL:
        raise ValueError(f"{name}: not where the zip's directory says it is")
    name_len, extra_len = struct.unpack("<HH", record[26:30])
    data = record[30 + name_len + extra_len: 30 + name_len + extra_len + packed]
    if method == 8:
        data = zlib.decompress(data, -15)
    elif method != 0:
        raise ValueError(f"{name}: compressed in a way this reader does not know ({method})")
    if len(data) != full:
        raise ValueError(f"{name}: {len(data)} bytes where {full} were expected")
    return data


def members(get, url, names, tail=TAIL):
    """{name: contents} for the named members of the zip at `url`, downloading little else."""
    listed, directory_start = directory(get, url, tail)
    missing = [name for name in names if name not in listed]
    if missing:
        raise ValueError(f"{url} has no {', '.join(missing)}")
    starts = sorted(offset for offset, *_ in listed.values()) + [directory_start]
    spans = sorted((listed[name][0], starts[starts.index(listed[name][0]) + 1], name) for name in names)
    groups = []
    for start, end, name in spans:                               # neighbours in the file share a request
        if groups and start - groups[-1][1] <= NEAR:
            groups[-1][1] = end
            groups[-1][2].append((start, end, name))
        else:
            groups.append([start, end, [(start, end, name)]])
    found = {}
    for first, last, held in groups:
        chunk = ranged(get, url, f"{first}-{last - 1}")
        for start, end, name in held:
            _, packed, full, method = listed[name]
            found[name] = unpack(chunk[start - first: end - first], packed, full, method, name)
    return {name: found[name] for name in names}


def boxes(shp):
    """One (south, west, north, east) per record, or None for a record without a shape. A point is a box of no size."""
    if len(shp) < 100 or struct.unpack(">i", shp[:4])[0] != 9994:
        raise ValueError("not a shapefile")
    found, at = [], 100
    while at + 12 <= len(shp):
        words, = struct.unpack(">i", shp[at + 4: at + 8])
        kind, = struct.unpack("<i", shp[at + 8: at + 12])
        if kind == 0:
            found.append(None)
        elif kind in (1, 11, 21):                                # a point (plain, with height, with a measure)
            x, y = struct.unpack("<2d", shp[at + 12: at + 28])
            found.append((y, x, y, x))
        else:                                                    # every other kind starts with its bounding box
            west, south, east, north = struct.unpack("<4d", shp[at + 12: at + 44])
            found.append((south, west, north, east))
        at += 8 + 2 * words
    return found


def kinds(dbf, column="fclass"):
    """The value of one text column for every row of the table."""
    count, header_len, record_len = struct.unpack("<IHH", dbf[4:12])
    at, offset, width = 32, 1, None
    while dbf[at] != 0x0D:
        name, length = dbf[at: at + 11].split(b"\0")[0].decode(), dbf[at + 16]
        if name == column:
            width = length
            break
        offset += length
        at += 32
    if width is None:
        raise ValueError(f"the table has no {column} column")
    return [dbf[header_len + n * record_len + offset: header_len + n * record_len + offset + width].decode("utf-8", "replace").strip()
            for n in range(count)]


def layer(shp, dbf):
    """[(kind, box)] for every record that has a shape."""
    shapes, names = boxes(shp), kinds(dbf)
    if len(shapes) != len(names):
        raise ValueError(f"{len(shapes)} shapes but {len(names)} rows: the layer's two files do not match")
    return [(name, shape) for name, shape in zip(names, shapes) if shape is not None]
