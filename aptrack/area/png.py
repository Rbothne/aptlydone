"""Reading the pixels of a PNG with nothing but the standard library: enough for map tiles (full colour with or
without transparency at 8 bits a channel, or a palette of up to 256 colours; not interlaced)."""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def unfilter(raw, height, stride, size):
    """The picture's lines with PNG's per-line prediction undone. `size` is bytes per whole pixel (at least 1)."""
    lines, before = [], bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - size] if i >= size else 0
            up, corner = before[i], before[i - size] if i >= size else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        before = bytes(line)
        lines.append(before)
    return lines


def pixels(data):
    """Rows of (red, green, blue, alpha), top row first. ValueError for anything that is not such a picture."""
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG picture")
    at, head, packed, palette, clear = 8, None, b"", b"", b""
    while at + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + length]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            packed += body
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            clear = body
        at += 12 + length
    if not head:
        raise ValueError("a PNG without a header")
    width, height, depth, colour, _, _, interlaced = head
    full, listed = colour in (2, 6) and depth == 8, colour == 3 and depth in (1, 2, 4, 8)
    if interlaced or not (full or listed):
        raise ValueError(f"a kind of PNG this reader does not handle (depth {depth}, colour type {colour}, interlaced {interlaced})")
    size = (4 if colour == 6 else 3) if full else 1
    stride = width * size if full else (width * depth + 7) // 8
    raw = zlib.decompress(packed)
    if len(raw) < height * (stride + 1):
        raise ValueError("the PNG's picture data is cut short")
    lines = unfilter(raw, height, stride, size)

    if full:
        return [[tuple(line[x:x + size]) + ((255,) if size == 3 else ()) for x in range(0, stride, size)] for line in lines]
    colours = [tuple(palette[i:i + 3]) + (clear[i // 3] if i // 3 < len(clear) else 255,) for i in range(0, len(palette), 3)]
    rows = []
    for line in lines:
        numbers = [(line[(x * depth) // 8] >> (8 - depth - (x * depth) % 8)) & ((1 << depth) - 1) for x in range(width)]
        if any(number >= len(colours) for number in numbers):
            raise ValueError("the PNG names a colour its palette does not have")
        rows.append([colours[number] for number in numbers])
    return rows
