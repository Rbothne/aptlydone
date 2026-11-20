"""Greystar: the company sitemap names every building with its state; each company page gives the address and a
link to the building's own website, whose floor-plans page may name a SightMap unit map.

The company page also carries the building's free apartments in the data it hands its scripts. A building whose
own website prices each apartment and answers the tracker is read from that; any other is read from the company
page (readers/greystar.py)."""

import re

from .. import fetch
from ..readers import greystar as company_page
from . import common

BETTER = ("sightmap", "jonah", "g5", "offers")       # websites that price each apartment and answer the tracker

SITEMAP = "https://www.greystar.com/sitemap-pdp.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.greystar\.com/[^/<\s]+-(?:va|md|dc)/p_\d+)\s*</loc>")
WEBSITE = re.compile(r'communityWebsiteUrl\\?"\s*:\s*\\?"(https?:[^"\\]+)')


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def website(page_html):
    match = WEBSITE.search(page_html or "")
    return match.group(1) if match else None


def parse(url, page_html, site):
    """`site` is what the building's own website was found to hold: site_feed's (platform, feed), or a page's html."""
    described = common.place(page_html)
    if not described:
        return None
    own = website(page_html)
    slug = url.rstrip("/").rsplit("/", 2)[1]
    platform, feed = common.found_on(own, site) if own else ("link", None)
    if platform not in BETTER and company_page.has_units(page_html):
        platform, feed = "greystar", url          # the company page itself lists the building's apartments
    return common.building("Greystar", slug, own or url, described, feed, platform)


def discover(get, limit=None):
    """Every Greystar building in DC, Maryland and Virginia."""
    found, watch = [], common.Watch()
    for url in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            page = get(url).decode("utf-8", "replace")
            if not common.place(page):
                watch.miss(url)
                continue
            watch.ok()
            own = website(page)
            found.append(parse(url, page, common.site_feed(get, own) if own else ""))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
    return found
