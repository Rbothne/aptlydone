"""Windsor Communities: a sitemap of location pages (one per city), each linking its buildings; each building
page states its address, and its floor-plans page names the SightMap unit map.

Only the region's location pages are read. Reading every building nationwide to find the local ones made the
site stop answering properly partway through.
"""

import re

from .. import fetch
from . import common

SITEMAP = "https://www.windsorcommunities.com/locations-sitemap.xml"
LOCATION = re.compile(r"<loc>\s*(https://www\.windsorcommunities\.com/apartments/(?:virginia-[^/<\s]+|maryland-[^/<\s]+|washington-dc)/)\s*</loc>")
BUILDING = re.compile(r'href="(https://www\.windsorcommunities\.com/properties/[^/"\s]+/)"')


def location_urls(sitemap_xml):
    return list(dict.fromkeys(LOCATION.findall(sitemap_xml)))


def building_urls(location_html):
    return sorted(set(BUILDING.findall(location_html)))


def parse(url, page_html, floorplans_html):
    described = common.place(page_html)
    if not described:
        return None
    return common.building("Windsor", url.rstrip("/").rsplit("/", 1)[1], url, described, common.sightmap_embed(floorplans_html))


def discover(get, limit=None):
    """Every Windsor building in DC, Maryland and Virginia."""
    urls = []
    for location in location_urls(get(SITEMAP).decode("utf-8", "replace")):
        try:
            urls += building_urls(get(location).decode("utf-8", "replace"))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {location}: {error!r}")
    found = []
    for url in list(dict.fromkeys(urls))[:limit]:
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
