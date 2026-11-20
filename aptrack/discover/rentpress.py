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


PROPERTY_LIST = re.compile(r"data-properties='([^']*)'")


def listed_discoverer(config):
    """A company whose RentPress site lists its buildings on one page (`list` in its managers.json line) but whose
    floor plans live on each building's own website: the list gives name, address and coordinates, and the
    building's website is looked through for the listing system it uses."""
    pages = config["list"] if isinstance(config["list"], list) else [config["list"]]

    def discover(get, limit=None):
        props = []
        for page in pages:
            try:
                props += attribute(PROPERTY_LIST, get(page).decode("utf-8", "replace"))
            except ReadError as error:
                raise fetch.RateLimited(f"no building list in {page}") from error       # come back later, keep what is known
        found = []
        for prop in props[:limit]:
            if not isinstance(prop, dict) or not prop.get("property_name"):
                continue
            if prop.get("property_state") not in common.REGION_STATES:
                continue
            described = {
                "name": prop["property_name"],
                "address": {"street": prop.get("property_address"), "city": prop.get("property_city"),
                            "state": prop.get("property_state"), "zip": prop.get("property_zip")},
                "lat": common.number(prop.get("property_latitude")),
                "lon": common.number(prop.get("property_longitude")),
            }
            page_url = prop.get("property_post_link") or pages[0]
            own = prop.get("property_website") or prop.get("property_availability_url")
            if own and not own.startswith("http"):
                own = "https://" + own.lstrip("/")
            try:
                platform, feed = common.site_feed(get, own) if own else ("link", None)
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  {prop['property_name']}: its website could not be read: {error!r}")
                platform, feed = "link", None
            slug = page_url.rstrip("/").rsplit("/", 1)[1]
            found.append(common.building(config["name"], slug, own or page_url, described, feed, platform))
        return found
    return discover


listed_discoverer.needs_config = True


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
