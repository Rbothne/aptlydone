"""Building websites that describe each available apartment in schema.org data: an availability page links to
one page per floor plan (`/availability/<building>/<type>/<plan>`), and each plan page carries a `FloorPlan`
and one `OfferForLease` per available unit, with its monthly price. Greystar's own building sites work this way.

Where one availability page covers several buildings of a development (Aerie and Zephyr at Wardman Park), the
plan addresses name the building, and only the plans of the building being read are followed."""

import json
import re
from urllib.parse import urljoin, urlsplit

from .. import fetch
from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
PLAN_LINK = re.compile(r'href="((?:https?://[^"/]+)?/(?:[^"/]+/)?availability/[^"/#?]+/[^"/#?]+/[^"/#?]+)/?"'
                       r'|href="((?:https?://[^"/]+)?/floor-plan/[^"/#?]+/[^"/#?]+\.html)"')       # AIR Communities' sites
STARTING = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")


def ld_nodes(page_html):
    for block in LD_JSON.findall(page_html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict):
                yield node


def kind(node):
    types = node.get("@type")
    return set(types) if isinstance(types, list) else {types}


def has_offers(page_html):
    return any("OfferForLease" in kind(n) for n in ld_nodes(page_html))


def plan_links(page_html, page_url, building_url=None):
    """The plan pages an availability page links to; when they belong to several buildings, those of this one."""
    found = (a or b for a, b in PLAN_LINK.findall(page_html or ""))
    links = list(dict.fromkeys(urljoin(page_url, href) for href in found))
    owners = {urlsplit(link).path.rstrip("/").split("/")[-3] for link in links}
    if len(owners) > 1 and building_url:
        words = set(re.findall(r"[a-z0-9]+", urlsplit(building_url).path.lower()))
        mine = [link for link in links if urlsplit(link).path.rstrip("/").split("/")[-3].lower() in words]
        links = mine or links
    return links


def parse_plan(page_html, building, url):
    nodes = list(ld_nodes(page_html))
    plan = next((n for n in nodes if "FloorPlan" in kind(n)), {})
    size = plan.get("floorSize") if isinstance(plan.get("floorSize"), dict) else {}
    name = plan.get("name")
    units = []
    for offer in (n for n in nodes if "OfferForLease" in kind(n)):
        if "InStock" not in str(offer.get("availability") or "InStock"):
            continue
        spec = offer.get("priceSpecification") if isinstance(offer.get("priceSpecification"), dict) else {}
        label = re.sub(r"^(unit|apt\.?|apartment)\s+", "", str(offer.get("name") or ""), flags=re.I).strip() \
            or str(offer.get("@id") or "").rsplit("#", 1)[-1]
        unit = make_unit(
            building["id"], label,
            rent=spec.get("price", offer.get("price")),
            plan=name,
            beds=plan.get("numberOfBedrooms") or plan.get("numberOfRooms"),
            baths=plan.get("numberOfBathroomsTotal"),
            sqft=num(size.get("minValue") or size.get("value")),
            url=url,
            restricted=True if looks_restricted(name) else None,
            plan_image=plan.get("layoutImage") if isinstance(plan.get("layoutImage"), str) else None,
        )
        if unit:
            units.append(unit)
    # Another way of saying the same: an ItemList of the plan's available Apartments, each priced in words
    # ("Unit #247, Starting at $2473.0"). AIR Communities' sites say so, the price including required monthly fees.
    for listing in (n for n in nodes if "ItemList" in kind(n)):
        for entry in listing.get("itemListElement") or []:
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict) or not {"Apartment", "Accommodation", "SingleFamilyResidence"} & kind(item):
                continue
            item_size = item.get("floorSize") if isinstance(item.get("floorSize"), dict) else {}
            price = STARTING.search(str(item_size.get("description") or item.get("description") or ""))
            unit = make_unit(
                building["id"], item.get("name"),
                rent=price.group(1) if price else None,
                plan=name,
                beds=plan.get("numberOfBedrooms") or plan.get("numberOfRooms"),
                baths=plan.get("numberOfBathroomsTotal"),
                sqft=num(item_size.get("value")) or num(size.get("minValue") or size.get("value")),
                notes="the site's starting price, which it says includes required monthly fees",
                url=url,
                restricted=True if looks_restricted(name) else None,
            )
            if unit:
                units.append(unit)
    return units


def read(building, get):
    page = get(building["feed"]).decode("utf-8", "replace")
    links = plan_links(page, building["feed"], building.get("url"))
    if not links and not has_offers(page):
        raise NotAnswering(f"{building['id']}: no floor plans linked from {building['feed']}")
    units = parse_plan(page, building, building["feed"])
    for link in links:
        try:
            units += parse_plan(get(link).decode("utf-8", "replace"), building, link)
        except fetch.Gone:
            continue                               # a plan let go between the two requests
    return {"units": unique(units), "fees": [], "amenities": []}
