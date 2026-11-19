"""UDR: the sitemap lists every page; building pages sit two levels under the Washington metro page and
describe themselves (name, address, coordinates, rating) in schema.org data."""

import re

from .. import fetch
from . import common

SITEMAP = "https://www.udr.com/sitemap.xml"
BUILDING = re.compile(r"<loc>\s*(https://www\.udr\.com/washington-dc-apartments/[a-z0-9-]+/[a-z0-9-]+/)\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def parse(url, html):
    """UDR nests the place inside the listing: the address is under "mainEntity", the rating beside it."""
    for node in common.ld_nodes(html):
        place = node.get("mainEntity")
        address = place.get("address") if isinstance(place, dict) else None
        if not (isinstance(address, dict) and address.get("streetAddress") and place.get("name")):
            continue
        where = place.get("geo") if isinstance(place.get("geo"), dict) else {}
        rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
        stars = common.number(rating.get("ratingValue"))
        described = {
            "name": place["name"].strip(),
            "address": {"street": address.get("streetAddress"), "city": address.get("addressLocality"),
                        "state": address.get("addressRegion"), "zip": address.get("postalCode")},
            "lat": common.number(where.get("latitude")),
            "lon": common.number(where.get("longitude")),
            "rating": round(stars, 1) if stars is not None else None,
            "rating_count": common.number(rating.get("ratingCount") or rating.get("reviewCount"), int),
        }
        entry = common.building("UDR", url.rstrip("/").rsplit("/", 1)[1], url, described, None)
        entry.update(platform="udr", feed=url.rstrip("/") + "/apartments-pricing/")
        return entry
    return None


def discover(get, limit=None):
    """Every UDR building in the Washington area."""
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
            if building["address"]["state"] in common.REGION_STATES:
                found.append(building)
        else:
            watch.miss(url)
    return found
