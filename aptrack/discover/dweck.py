"""Dweck Properties: the site's sitemap names each community's page, and the page carries the community's name,
one-line address and coordinates. The same page lists its available apartments (readers/dweck.py), so it is also
the feed.

The site's robots file asks for five minutes between requests (`site_delays` holds that), so this search takes over
an hour for some fifteen communities. It runs weekly.
"""

import html
import re

from .. import fetch
from . import common
from .cards import split_address

SITEMAP = "https://www.dweckproperties.com/properties-sitemap.xml"
COMMUNITY = re.compile(r"<loc>\s*(https://www\.dweckproperties\.com/communities/([a-z0-9-]+)/?)\s*</loc>")
ATTRIBUTE = r'{}="([^"]*)"'


def attribute(page, name):
    match = re.search(ATTRIBUTE.format(re.escape(name)), page)
    return html.unescape(match.group(1)).strip() if match else None


def described(page):
    name, address, where = (attribute(page, key) for key in ("data-property-name", "data-address", "data-property-lat-long"))
    if not name or not address:
        return None
    lat, _, lon = (where or "").partition(",")
    return {"name": name, "address": split_address(address), "lat": common.number(lat.strip()), "lon": common.number(lon.strip())}


def discover(get, limit=None):
    found, watch = [], common.Watch()
    for url, slug in list(dict.fromkeys(COMMUNITY.findall(get(SITEMAP).decode("utf-8", "replace"))))[:limit]:
        try:
            place = described(get(url).decode("utf-8", "replace"))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
            continue
        if not place:
            watch.miss(url)
            continue
        watch.ok()
        if place["address"]["state"] in common.REGION_STATES:
            found.append(common.building("Dweck", slug, url, place, url, "dweck"))
    return found
