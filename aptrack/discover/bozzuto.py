"""Bozzuto: the sitemap lists every building; each building page carries its address, and its floor-plans page
names the SightMap unit map."""

import json
import re

from .. import fetch

SITEMAP = "https://www.bozzuto.com/sitemap/properties_sitemap.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.bozzuto\.com/apartments-for-rent/(?:dc|md|va)/[^/<\s]+/[^/<\s]+)\s*</loc>")
LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
EMBED = re.compile(r"https:\\?/\\?/sightmap\.com\\?/embed\\?/(\w+)")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def complex_node(page_html):
    """The schema.org ApartmentComplex description embedded in a building page."""
    for block in LD_JSON.findall(page_html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "ApartmentComplex":
                return node
    return None


def parse(url, page_html, floorplans_html):
    node = complex_node(page_html)
    if not node:
        return None
    address, where = node.get("address") or {}, node.get("geo") or {}
    embed = EMBED.search(floorplans_html or "")
    try:
        lat, lon = float(where["latitude"]), float(where["longitude"])
    except (KeyError, TypeError, ValueError):
        lat = lon = None
    return {
        "id": "bozzuto-" + url.rstrip("/").rsplit("/", 1)[1],
        "manager": "Bozzuto",
        "name": node.get("name"),
        "url": url,
        "platform": "sightmap" if embed else "link",
        "feed": f"https://sightmap.com/embed/{embed.group(1)}" if embed else None,
        "address": {"street": address.get("streetAddress"), "city": address.get("addressLocality"),
                    "state": address.get("addressRegion"), "zip": address.get("postalCode")},
        "lat": lat,
        "lon": lon,
    }


def discover(get, limit=None):
    """Every Bozzuto building in DC, Maryland and Virginia. A building whose pages fail is skipped."""
    found = []
    for url in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            page = get(url).decode("utf-8", "replace")
            try:
                floorplans = get(url + "/floor-plans").decode("utf-8", "replace")
            except fetch.Gone:
                floorplans = ""
            building = parse(url, page, floorplans)
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
            continue
        if building:
            found.append(building)
    return found
