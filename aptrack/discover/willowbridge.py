"""Willow Bridge (formerly Lincoln Property): the company page gives a building's address and a link to the
building's own website, and that website's floor-plans page names the SightMap unit map."""

import json
import re

from .. import fetch
from . import common

SITEMAP = "https://www.willowbridgepc.com/sitemap.xml"
# Building pages end in the place; keep the ones that look to be in DC, Maryland or Virginia (their spellings vary).
BUILDING = re.compile(r"<loc>\s*(https://www\.willowbridgepc\.com/properties/"
                      r"[^/<\s]*-(?:va|md|dc|virginia|virgnia|maryland|district-of-columbia)/?)\s*</loc>")
PROPERTY = re.compile(r"var propData\s*=\s*(\{.*?\});", re.S)
WEBSITE = re.compile(r"""<a[^>]*href=['"]((?:https?:)?//[^'"]+)['"][^>]*title=['"]Visit Website['"]""")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def website(page_html):
    """The building's own website, as linked from the company page."""
    match = WEBSITE.search(page_html or "")
    if not match:
        return None
    return match.group(1) if match.group(1).startswith("http") else "https:" + match.group(1)


def described(page_html):
    match = PROPERTY.search(page_html or "")
    try:
        prop = json.loads(match.group(1))["property"]
    except (AttributeError, ValueError, KeyError, TypeError):
        return None
    return {"name": prop.get("name"), "lat": common.number(prop.get("lat")), "lon": common.number(prop.get("long")),
            "address": {"street": prop.get("address"), "city": prop.get("city"), "state": prop.get("state"), "zip": prop.get("zip")}}


def parse(url, page_html, site_html):
    place = described(page_html)
    if not place:
        return None
    own = website(page_html)
    slug = url.rstrip("/").rsplit("/", 1)[1]
    return common.building("Willow Bridge", slug, own or url, place, common.sightmap_embed(site_html) if own else None)


def discover(get, limit=None):
    """Every Willow Bridge building in DC, Maryland and Virginia."""
    found, watch = [], common.Watch()
    for url in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            page = get(url).decode("utf-8", "replace")
            place = described(page)
            if not place:
                watch.miss(url)
                continue
            watch.ok()
            if place["address"]["state"] not in common.REGION_STATES:
                continue
            own = website(page)
            found.append(parse(url, page, common.own_site_html(get, own) if own else ""))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
    return found
