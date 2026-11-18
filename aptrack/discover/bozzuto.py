"""Bozzuto: the sitemap lists every building; each building page carries its address, and its floor-plans page
names the SightMap unit map."""

import re

from .. import fetch
from . import common

SITEMAP = "https://www.bozzuto.com/sitemap/properties_sitemap.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.bozzuto\.com/apartments-for-rent/(?:dc|md|va)/[^/<\s]+/[^/<\s]+)\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def parse(url, page_html, floorplans_html):
    described = common.place(page_html, kinds=("ApartmentComplex",))
    if not described:
        return None
    described = dict(described, rating=None)        # Bozzuto's rating is read daily with its other facts
    return common.building("Bozzuto", url.rstrip("/").rsplit("/", 1)[1], url, described, common.sightmap_embed(floorplans_html))


def discover(get, limit=None):
    """Every Bozzuto building in DC, Maryland and Virginia. A building whose pages fail is skipped."""
    found, watch = [], common.Watch()
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
            watch.ok()
            found.append(building)
        else:
            watch.miss(url)
    return found
