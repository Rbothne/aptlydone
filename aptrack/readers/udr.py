"""UDR: a building's pricing page assigns its whole record to `udr.jsonObjPropertyViewModel`: floor plans, and
under each the available units with their lowest rent and its lease term, size, floor and move-in date."""

import datetime
import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

SITE = "https://www.udr.com"
MODEL = re.compile(r"udr\.jsonObjPropertyViewModel\s*=\s*")
MS_DATE = re.compile(r"/Date\((-?\d+)")


def view_model(html):
    match = MODEL.search(html or "")
    try:
        return json.JSONDecoder().raw_decode(html[match.end():])[0]
    except (AttributeError, ValueError) as error:
        raise NotAnswering("no unit data in the page") from error


def iso_date(value):
    """'/Date(1795132800000)/' (milliseconds) -> '2026-11-20'."""
    match = MS_DATE.search(value or "")
    if not match:
        return None
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=int(match.group(1)))).date().isoformat()


def absolute(path):
    return SITE + path if path and path.startswith("/") else path or None


def one_time_fee(label, amount):
    return {"label": label, "type": None, "category": None, "required": True, "when": "additional", "refundable": False,
            "amount": float(amount), "text": f"${amount:g}"}


def parse(html, building):
    model = view_model(html)
    plans = [plan for plan in model.get("floorPlans") or [] if isinstance(plan, dict)]
    listed = [(plan, u) for plan in plans for u in plan.get("units") or [] if u.get("isAvailable", True)]
    several = len({u.get("building") for _, u in listed}) > 1                 # the same unit number in two of a property's buildings
    units = []
    for plan, u in listed:
        number = str(u.get("marketingName") or "").strip()
        if not number:
            continue
        quote = u.get("lowestRent") or {}
        base, total = num(quote.get("baseRent")), num(quote.get("rent"))
        rent = base or total
        charges = total - base if base and total and total > base else num(u.get("monthlyCharges"))
        name = u.get("floorplanName") or plan.get("Name")
        unit = make_unit(
            building["id"], f"{u.get('building')}-{number}" if several else number,
            rent=rent,
            plan=name,
            beds=u.get("bedrooms"),
            baths=u.get("bathrooms"),
            sqft=u.get("sqFt"),
            floor=u.get("floorNumber"),
            fees=charges or None,
            lease=quote.get("leaseTerm"),
            available=iso_date(u.get("availableDate")),
            notes=", ".join(a["value"] for a in u.get("amenities") or [] if isinstance(a, dict) and a.get("value")) or None,
            url=absolute(u.get("previewLink")) or building.get("url"),
            restricted=True if u.get("isAffordable") or looks_restricted(name) else False if u.get("isAffordable") is False else None,
            plan_image=absolute(u.get("ListingImageSrc")),
        )
        if unit:
            units.append(unit)

    fees = []
    for label, key in (("Application fee", "applicationFee"), ("Admin fee", "adminFee")):
        amounts = [num(plan.get(key)) for plan in plans if num(plan.get(key))]
        if amounts:
            fees.append(one_time_fee(label, min(amounts)))
    return {"units": unique(units), "fees": fees, "amenities": []}


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
