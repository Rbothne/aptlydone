"""Greystar's own page for a building (www.greystar.com/<building>/p_<number>).

The page hands its scripts the building's data in pieces (`self.__next_f.push([1,"..."])`). Put together, it
holds `"propertyUnits"`: every apartment that is free, with its number, square footage, floor, the day it is free,
its lowest rent and the lease length that rent is for; `"floorplans"`: each plan's bedrooms, bathrooms and
drawing; and `"monthlyFees"`: the required monthly fees.

This is the route for Greystar buildings whose own websites cannot be read apartment by apartment. Many of those
sites refuse the tracker; the company's page answers ordinary requests and carries the same apartments.
"""

import json
import re

from ..units import looks_restricted, make_unit, unique
from . import NotAnswering

PIECE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
DECODER = json.JSONDecoder()


def page_data(page_html):
    """The text of the data the page hands its scripts, its pieces joined."""
    parts = []
    for piece in PIECE.findall(page_html or ""):
        try:
            parts.append(json.loads(piece))
        except ValueError:
            continue
    return "".join(parts)


def value_of(data, key):
    """The JSON value after the first `"key":` in the page's data, or None when it is not there."""
    at = data.find(f'"{key}":')
    if at < 0:
        return None
    start = at + len(key) + 3
    while start < len(data) and data[start] in " \t\r\n":
        start += 1
    try:
        return DECODER.raw_decode(data, start)[0]
    except ValueError:
        return None


def has_units(page_html):
    return isinstance(value_of(page_data(page_html), "propertyUnits"), list)


def read(building, get):
    data = page_data(get(building["feed"]).decode("utf-8", "replace"))
    listed = value_of(data, "propertyUnits")
    if not isinstance(listed, list):
        raise NotAnswering(f"{building['id']}: {building['feed']} does not carry the building's apartments")
    plans = {str(p.get("id")): p for p in value_of(data, "floorplans") or [] if isinstance(p, dict)}
    fees = (value_of(data, "monthlyFees") or {}).get("requiredMonthlyFeesMin") if isinstance(value_of(data, "monthlyFees"), dict) else None
    units = []
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        plan = plans.get(str(entry.get("floorPlanId")), {})
        name = entry.get("floorPlanLabel") or plan.get("label")
        unit = make_unit(
            building["id"], entry.get("unitNumber") or entry.get("unitId"),
            rent=entry.get("minPrice"),
            fees=fees,
            lease=entry.get("minBaseRentLeaseTerm"),
            plan=name,
            beds=plan.get("bedroomCount"),
            baths=plan.get("bathroomCount"),
            sqft=entry.get("area"),
            floor=entry.get("floorShortLabel"),
            available=entry.get("availableOn"),
            url=building["feed"],
            plan_image=plan.get("imageUrl") or None,
            restricted=True if looks_restricted(name) else None,
        )
        if unit:
            units.append(unit)
    return {"units": unique(units), "fees": [], "amenities": []}
