"""Managers whose sites run the RentPress WordPress plugin: a sitemap of building pages, each carrying the
building's name, address and coordinates in the same data the reader takes prices from."""

import re

from .. import fetch
from ..readers import ReadError
from ..readers.rentpress import PROPERTIES, attribute
from . import common


def building_urls(sitemap_xml, site):
    pattern = re.compile(r"<loc>\s*(https://" + re.escape(site) + r"/apartments/[^/<\s]+/)\s*</loc>")
    return list(dict.fromkeys(pattern.findall(sitemap_xml)))


def parse(url, page_html, manager):
    try:
        properties = attribute(PROPERTIES, page_html)
    except ReadError:
        return None
    prop = properties[0] if isinstance(properties, list) and properties else {}
    if not prop.get("property_name"):
        return None
    described = {
        "name": prop["property_name"],
        "address": {"street": prop.get("property_address"), "city": prop.get("property_city"),
                    "state": prop.get("property_state"), "zip": prop.get("property_zip")},
        "lat": common.number(prop.get("property_latitude")),
        "lon": common.number(prop.get("property_longitude")),
    }
    entry = common.building(manager, url.rstrip("/").rsplit("/", 1)[1], url, described, None)
    entry.update(platform="rentpress", feed=url)
    return entry


def discoverer(manager, site):
    """A discover(get, limit) function for one RentPress site."""
    def discover(get, limit=None):
        found, watch = [], common.Watch()
        sitemap = get(f"https://{site}/rentpress_property-sitemap.xml").decode("utf-8", "replace")
        for url in building_urls(sitemap, site)[:limit]:
            try:
                building = parse(url, get(url).decode("utf-8", "replace"), manager)
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  skipped {url}: {error!r}")
                continue
            if building and building["address"]["state"] in common.REGION_STATES:
                watch.ok()
                found.append(building)
            elif building:
                watch.ok()
            else:
                watch.miss(url)
        return found
    return discover
