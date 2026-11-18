"""Camden: each building's "available apartments" page embeds its floor plans and units as JSON."""

import json
import re

from ..units import make_unit, num
from . import ReadError

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def page_data(html):
    """The page's `props.pageProps` object."""
    match = NEXT_DATA.search(html)
    try:
        return json.loads(match.group(1))["props"]["pageProps"]
    except (AttributeError, ValueError, KeyError, TypeError) as error:
        raise ReadError("no page data") from error


def parse(html, building):
    props = page_data(html)
    plans = (props.get("data") or {}).get("availableApartments")
    if plans is None:
        raise ReadError(f"{building['id']}: page has no listing data")
    special = ". ".join(part.strip().rstrip(".") for part in
                        (props.get("specialCtaTitle"), props.get("specialCtaDescription")) if part and part.strip())
    special = special + "." if special else None

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
            )
            if unit:
                units.append(unit)
    listed = sum(len(plan.get("availableUnitRefs") or []) for plan in plans)
    if listed and not units:
        raise ReadError(f"{building['id']}: {listed} units listed, none with a price")
    return {"units": units, "fees": [], "amenities": []}


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
