"""Kettler: the communities page fills itself from the company's own property search
(`/api/v1/properties`), asked with a site number the page hands every visitor (`ng-init='init(2405)'`). The
answer lists every building with its address, coordinates and its own website, which is then looked through for
the listing system it uses.

The number is read from the page each time, never kept here. Used at the owner's instruction (2026-11-20).

Asked for floor plans too, the same search lists each building's plans with a starting price and the number free.
A building whose own website prices each apartment (a unit map) is read from that. One whose website is a
RentCafe site (which refuse the tracker) or names no listing system is read from Kettler's plans instead
(readers/kettler.py): a floor plan's starting price is less than an apartment's price, and far more than nothing.
"""

import json
import re

from .. import fetch
from ..readers.kettler import API, NUMBER, PAGE
from . import common

PLANS = "https://www.kettler.com/api/v1/properties#{}"       # a building's feed when it is read from Kettler's plans
BETTER = ("sightmap", "jonah", "g5", "offers")                # websites that price each apartment and answer the tracker


def text(value):
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else None


def discover(get, limit=None):
    number = NUMBER.search(get(PAGE).decode("utf-8", "replace"))
    if not number:
        raise ValueError(f"Kettler: {PAGE} no longer carries its search number")
    listed = json.loads(get(API.format(number.group(1)))).get("properties") or []
    listed = list(listed.values()) if isinstance(listed, dict) else listed
    found = []
    for prop in listed:
        state = (text(prop.get("state")) or "").upper()
        name = text(prop.get("name"))
        if state not in common.REGION_STATES or not name:
            continue
        if limit is not None and len(found) >= limit:
            break
        place = {
            "name": name,
            "address": {"street": text(prop.get("address")), "city": text(prop.get("city")), "state": state, "zip": text(prop.get("zip"))},
            "lat": common.number(prop.get("lat")),
            "lon": common.number(prop.get("long")),
        }
        own = (text(prop.get("vanity_url")) or "").split("?")[0] or None
        platform, feed = "link", None
        if own:
            try:
                platform, feed = common.site_feed(get, own)
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  {name}: its website could not be read: {error!r}")
        if platform not in BETTER and prop.get("floorplans") and prop.get("property_id") is not None:
            platform, feed = "kettler", PLANS.format(prop["property_id"])
        slug =re.sub(r"[^a-z0-9]+", "-", (text(prop.get("slug")) or name).lower()).strip("-")
        found.append(common.building("Kettler", slug, own or PAGE, place, feed, platform))
    return found
