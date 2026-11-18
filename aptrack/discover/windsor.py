"""Windsor Communities: one sitemap of every building nationwide; each page states its address, and its
floor-plans page names the SightMap unit map."""

import re

from .. import fetch
from . import common

SITEMAP = "https://www.windsorcommunities.com/windsor_properties-sitemap.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.windsorcommunities\.com/properties/[^/<\s]+/)\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def parse(url, page_html, floorplans_html):
    described = common.place(page_html)
    if not described:
        return None
    return common.building("Windsor", url.rstrip("/").rsplit("/", 1)[1], url, described, common.sightmap_embed(floorplans_html))


def discover(get, limit=None):
    """Every Windsor building in DC, Maryland and Virginia. The sitemap does not say where a building is,
    so each page is read; only buildings in those states get a second request for their unit map."""
    found = []
    for url in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            page = get(url).decode("utf-8", "replace")
            described = common.place(page)
            if not described or described["address"]["state"] not in common.REGION_STATES:
                continue
            try:
                floorplans = get(url + "floorplans/").decode("utf-8", "replace")
            except fetch.Gone:
                floorplans = ""
            found.append(parse(url, page, floorplans))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
    return found
