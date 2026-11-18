"""Camden: the sitemap lists each building's "available apartments" page, which also names the building."""

import re

from .. import fetch
from . import common
from ..readers import ReadError
from ..readers.camden import page_data

SITEMAP = "https://www.camdenliving.com/sitemap/available-apartment-pages.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.camdenliving\.com/apartments/[a-z0-9-]+-(?:dc|md|va)/[^/<\s]+"
                      r"/available-apartments)\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def parse(url, html):
    try:
        community = (page_data(html).get("data") or {}).get("community") or {}
    except ReadError:
        return None
    if not community.get("name"):
        return None
    home = url.rsplit("/available-apartments", 1)[0]
    slug = home.rsplit("/", 1)[1]
    return {
        "id": slug if slug.startswith("camden-") else "camden-" + slug,
        "manager": "Camden",
        "name": community["name"],
        "url": home,
        "platform": "camden",
        "feed": url,
        "address": {"full": community.get("address")},
        "lat": None,
        "lon": None,
    }


def discover(get, limit=None):
    """Every Camden building in DC, Maryland and Virginia. A building whose page fails is skipped."""
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
