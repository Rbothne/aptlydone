"""AvalonBay: the sitemap lists every community page by state and city; the page itself gives name, address
and coordinates (the same record the reader takes units from)."""

import re

from .. import fetch
from ..readers import ReadError
from ..readers.avalon import content
from . import common

SITEMAP = "https://www.avaloncommunities.com/arc/outboundfeeds/avb-sitemap/?outputType=xml&_website=avalon-communities"
BUILDING = re.compile(r"<loc>\s*(https://www\.avaloncommunities\.com/(?:district-of-columbia|virginia|maryland)/"
                      r"[a-z0-9-]+-apartments/[a-z0-9-]+/?)\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def parse(url, html):
    try:
        record = content(html)
    except ReadError:
        return None
    if not record.get("name"):
        return None
    address, where = record.get("address") or {}, record.get("coordinates") or {}
    described = {
        "name": record["name"],
        "address": {"street": address.get("addressLine1"), "city": address.get("city"), "state": address.get("state"), "zip": address.get("zip")},
        "lat": common.number(where.get("latitude")),
        "lon": common.number(where.get("longitude")),
    }
    entry = common.building("AvalonBay", url.rstrip("/").rsplit("/", 1)[1], url, described, None)
    entry.update(platform="avalon", feed=url)
    return entry


def discover(get, limit=None):
    """Every AvalonBay community in DC, Maryland and Virginia."""
    found, watch = [], common.Watch()
    for url in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            building = parse(url, get(url).decode("utf-8", "replace"))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
            continue
        if building:
            watch.ok()
            found.append(building)
        else:
            watch.miss(url)
    return found
