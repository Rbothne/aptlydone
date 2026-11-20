"""A company whose site lists its buildings as cards on one page, each card naming the building, its address and a
link to the building's own website. One managers.json line describes the card with a regular expression whose
named groups pick out the parts:

    {"name": "AIR Communities", "site": "www.aircommunities.com", "discover": "cards",
     "list": "https://www.aircommunities.com/en/community.html",
     "card": "data-state=\\"(?P<state>[A-Z]{2})\\" data-city=\\"(?P<city>[^\\"]+)\\".*?href=\\"(?P<site>https?://[^\\"]+)\\" ..."}

`within` (optional) is a regular expression for the part of the page that holds the cards.
Groups: `site` (the building's website, required), `name`, `state`, `city`, `street`, `zip`, and `address` (a
whole one-line address, "8300 Wisconsin Avenue Bethesda, MD 20814", split here into its parts). A card with no
address is only a link: the building's own home page then says where it is, in its schema.org data. The building's
website is looked through for the listing system it uses (common.site_feed). There are no coordinates: discovery
places the building by its address with the Census Bureau, as for any building."""

import html as htmllib
import re

from .. import fetch
from . import common
from .generic import tidy as generic_tidy

ONE_LINE = re.compile(r"^(?P<rest>.*?),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?\s*$")


def clean(value):
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", value or "")).split()) or None


def split_address(address, city=None):
    """'8300 Wisconsin Avenue Bethesda, MD 20814' (with the city known to be Bethesda) -> its parts."""
    match = ONE_LINE.match(address or "")
    if not match:
        return {"street": address, "city": city, "state": None, "zip": None}
    rest = match.group("rest").rstrip(",")
    if "," in rest:
        street, found_city = rest.rsplit(",", 1)
    elif city and rest.lower().endswith(city.lower()):
        street, found_city = rest[: -len(city)], city
    else:
        street, found_city = rest, city
    return {"street": street.strip(" ,"), "city": (found_city or city or "").strip() or None,
            "state": match.group("state"), "zip": match.group("zip")}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def discoverer(config):
    pages = config["list"] if isinstance(config["list"], list) else [config["list"]]
    card = re.compile(config["card"], re.S)

    def discover(get, limit=None):
        cards = []
        for page in pages:
            text = get(page).decode("utf-8", "replace")
            if config.get("within"):                 # only the part of the page that lists the buildings
                block = re.search(config["within"], text, re.S)
                text = block.group(0) if block else ""
            cards += [m.groupdict() for m in card.finditer(text)]
        if not cards:
            raise fetch.RateLimited(f"no buildings found on {pages[0]}")       # the page changed or did not load
        found = []
        for parts in cards:
            parts = {k: clean(v) for k, v in parts.items()}
            address = split_address(parts.get("address"), parts.get("city")) if parts.get("address") else {}
            address = {"street": parts.get("street") or address.get("street"), "city": parts.get("city") or address.get("city"),
                       "state": parts.get("state") or address.get("state"), "zip": parts.get("zip") or address.get("zip")}
            own = htmllib.unescape(parts["site"])
            where = {"lat": None, "lon": None}
            if not address["street"]:                # the card is only a link: the building's own site says where it is
                try:
                    place = common.place(get(own).decode("utf-8", "replace"))
                except fetch.RateLimited:
                    raise
                except Exception as error:
                    print(f"  skipped {own}: {error!r}")
                    continue
                if not place:
                    print(f"  skipped {own}: its site does not say where it is")
                    continue
                address = generic_tidy(place["address"])
                where = {"lat": place["lat"], "lon": place["lon"]}
                parts["name"] = parts.get("name") or place["name"]
            if address["state"] not in common.REGION_STATES:
                continue
            if limit is not None and len(found) >= limit:
                break
            try:
                platform, feed = common.site_feed(get, own)
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  {parts.get('name')}: its website could not be read: {error!r}")
                platform, feed = "link", None
            described = {"name": parts.get("name") or own, "address": address, **where}
            found.append(common.building(config["name"], slug(parts.get("name") or own), own, described, feed, platform))
        return found
    return discover


discoverer.needs_config = True
