"""Camden: each building's "available apartments" page embeds its floor plans and units as JSON."""

import html as htmllib
import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering, ReadError

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# The page's banner is sometimes a price offer and sometimes an advert for tours. Only an offer is a "special".
OFFER = re.compile(r"\bfree\b|\boff\b|\bsav(e|ings?)\b|waiv|\bcredit|discount|concession|reduced|\$\s?\d", re.I)


def plain(text):
    """Text without HTML tags or entities."""
    text = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())
    return re.sub(r"\s+([.,!?;:])", r"\1", text)


def banner(title, description):
    """The banner as one sentence-ended string, or None when it is empty or not a price offer."""
    parts = [part for part in (plain(title), plain(description)) if part]
    text = " ".join(part if part[-1] in ".!?" else part + "." for part in parts)
    return text if text and OFFER.search(text) else None


def page_data(html):
    """The page's `props.pageProps` object."""
    match = NEXT_DATA.search(html)
    try:
        return json.loads(match.group(1))["props"]["pageProps"]
    except (AttributeError, ValueError, KeyError, TypeError) as error:
        raise NotAnswering("no page data") from error


def parse(html, building):
    props = page_data(html)
    plans = (props.get("data") or {}).get("availableApartments")
    if plans is None:
        raise ReadError(f"{building['id']}: page has no listing data")
    special = banner(props.get("specialCtaTitle"), props.get("specialCtaDescription"))

    units = []
    for plan in plans:
        base, total = num(plan.get("monthlyRent")), num(plan.get("totalMonthlyRent"))
        fees = total - base if base is not None and total is not None and total >= base else None
        for ref in plan.get("availableUnitRefs") or []:
            number = ref.get("unitNumber")
            label = f"{ref['buildingNumber']}-{number}" if ref.get("buildingNumber") else number
            unit = make_unit(
                building["id"], label,
                rent=ref.get("monthlyRent"),
                plan=plan.get("name"),
                beds=plan.get("bedrooms"),
                baths=plan.get("bathrooms"),
                sqft=ref.get("squareFeet") or plan.get("squareFeet"),
                floor=ref.get("floorNumber"),
                fees=fees,
                lease=ref.get("leaseTerm") or plan.get("leaseTerm"),
                available=ref.get("moveInDate"),
                special=special,
                url=building.get("url"),
                restricted=True if looks_restricted(plan.get("name")) else None,
                plan_image=(plan.get("media") or {}).get("floorPlanImage"),
            )
            if unit:
                units.append(unit)
    listed = sum(len(plan.get("availableUnitRefs") or []) for plan in plans)
    if listed and not units:
        raise ReadError(f"{building['id']}: {listed} units listed, none with a price")
    about = plain((props.get("data") or {}).get("metaDescription"))
    return {"units": unique(units), "fees": [], "amenities": [], "facts": {"features": [about] if about else []}}


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
