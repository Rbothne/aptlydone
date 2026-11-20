"""JBG SMITH: the sitemap names each residential property's page (`/property/residential/<NAME>/<id>`); the page's
data comes from the company's own API, which gives the address, coordinates and the building's website. The
website is looked through for the listing system it uses."""

import json
import re

from .. import fetch
from . import common

SITEMAP = "https://www.jbgsmith.com/sitemap.xml"
API = "https://api-jbgsmith.reol.com/api/page/property/residential?id={}"
BUILDING = re.compile(r"<loc>\s*(https://www\.jbgsmith\.com/property/residential/([^/<\s]+)/(\d+))\s*</loc>")


def building_urls(sitemap_xml):
    return list(dict.fromkeys(BUILDING.findall(sitemap_xml)))


def described(record):
    data = record.get("data")
    data = data[0] if isinstance(data, list) and data else data
    if not isinstance(data, dict) or not isinstance(data.get("property"), dict):
        return None, None
    prop = data["property"]
    street = " ".join(filter(None, [prop.get("street_number"), re.sub(r"_[A-Z]$", "", prop.get("street_address") or "")]))
    return {
        "name": (prop.get("name") or "").title(),
        "address": {"street": street or prop.get("full_address"), "city": prop.get("city"),
                    "state": prop.get("state_code"), "zip": prop.get("zip")},
        "lat": common.number(prop.get("latitude")),
        "lon": common.number(prop.get("longitude")),
    }, data.get("property_website") or prop.get("property_website")


def discover(get, limit=None):
    found, watch = [], common.Watch()
    for url, slug, number in building_urls(get(SITEMAP).decode("utf-8", "replace"))[:limit]:
        try:
            place, own = described(json.loads(get(API.format(number))))
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  skipped {url}: {error!r}")
            continue
        if not place or not place["name"]:
            watch.miss(url)
            continue
        watch.ok()
        if place["address"]["state"] not in common.REGION_STATES:
            continue
        try:
            platform, feed = common.site_feed(get, own) if own else ("link", None)
        except fetch.RateLimited:
            raise
        except Exception as error:
            print(f"  {place['name']}: its website could not be read: {error!r}")
            platform, feed = "link", None
        found.append(common.building("JBG SMITH", slug.lower(), own or url, place, feed, platform))
    return found
