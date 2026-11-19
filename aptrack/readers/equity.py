"""Equity Residential: each building page carries its record as JSON assigned to `ea5.property` and
`ea5.unitAvailability`: every available unit with its best lease term and price, size, floor, floor-plan
drawing, its own special, and itemised charges."""

import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

REQUIRED_MONTHLY = "required charges"       # the sub-heading Equity files compulsory monthly fees under


def assigned(page, name):
    """The JSON value a page assigns to ea5.<name>."""
    match = re.search(r"ea5\." + re.escape(name) + r"\s*=\s*", page or "")
    try:
        return json.JSONDecoder().raw_decode(page[match.end():])[0]
    except (AttributeError, ValueError) as error:
        raise NotAnswering(f"no ea5.{name} in the page") from error


def iso_date(text):
    """'12/16/2026' -> '2026-12-16'."""
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", text or "")
    return f"{match.group(3)}-{int(match.group(1)):02d}-{int(match.group(2)):02d}" if match else None


def monthly_fees(unit):
    """Compulsory monthly charges on top of rent. Estimated utilities are left out: other companies' totals do
    not include metered utilities, and counting them here would make Equity look dearer than it is."""
    amounts = [num(fee.get("AMOUNT")) for fee in unit.get("MonthlyRecurringFees") or []
               if (fee.get("SUBCATEGORY") or "").strip().lower() == REQUIRED_MONTHLY]
    amounts = [amount for amount in amounts if amount is not None]
    return sum(amounts) if amounts else None


def fee(charge, required):
    return {
        "label": (charge.get("CHGDESC") or "").strip(),
        "type": None,
        "category": (charge.get("CATEGORY") or "").strip() or None,
        "required": required,
        "when": "additional" if required else "optional",
        "refundable": False,
        "amount": float(num(charge.get("AMOUNT"))) if num(charge.get("AMOUNT")) is not None else None,     # the low end of a range
        "text": charge.get("AMOUNT"),
    }


RATING = re.compile(r'"aggregateRating"\s*:\s*(\{[^{}]*\})')


def rating(html):
    """(stars, how many reviews) from the page's schema.org summary; (None, None) when it has none."""
    match = RATING.search(html or "")
    try:
        found = json.loads(match.group(1))
    except (AttributeError, ValueError):
        return None, None
    return num(found.get("ratingValue")), num(found.get("ratingCount") or found.get("reviewCount"))


def restricted(unit, plan):
    """Equity marks each unit "N" (market rate), blank, or not at all. "Y" has not been seen on a live page yet;
    it is taken to mean an income-restricted unit."""
    mark = (unit.get("AFFORDABLE") or "").strip().upper() if isinstance(unit.get("AFFORDABLE"), str) else ""
    if mark == "Y" or looks_restricted(plan):
        return True
    return False if mark == "N" else None


def special_text(unit):
    special = unit.get("Special") if isinstance(unit.get("Special"), dict) else {}
    return special.get("Title") if special.get("Active") else None


def parse(html, building):
    listed = [u for kind in assigned(html, "unitAvailability").get("BedroomTypes") or [] for u in kind.get("AvailableUnits") or []]
    try:
        record = assigned(html, "property")
    except NotAnswering:
        record = {}
    several = len({(u.get("BuildingId") or "").strip() for u in listed}) > 1          # a property of several buildings
    units = []
    for u in listed:
        best = u.get("BestTerm") or {}
        number = (u.get("UnitId") or "").strip()
        if not number:
            continue
        plan = u.get("FloorplanName")
        unit = make_unit(
            building["id"], f"{(u.get('BuildingId') or '').strip()}-{number}" if several else number,
            rent=best.get("Price"),
            plan=plan,
            beds=u.get("Bed"),
            baths=u.get("Bath"),
            sqft=u.get("SqFt"),
            floor=u.get("Floor"),
            fees=monthly_fees(u),
            lease=best.get("Length"),
            available=iso_date(u.get("AvailableDate")),
            special=special_text(u),
            notes=", ".join(a["Name"] for a in u.get("Amenities") or [] if isinstance(a, dict) and a.get("Name")) or None,
            url=building.get("url"),
            restricted=restricted(u, plan),
            plan_image=u.get("Floorplan"),
        )
        if unit:
            units.append(unit)

    fees = ([fee(charge, True) for charge in record.get("OneTimeMoveInFees") or []]
            + [fee(charge, False) for charge in record.get("AdditionalOptionsFees") or []])
    labels = [f["label"].lower() for f in fees if not f["required"]]
    stars, reviews = rating(html)
    return {
        "units": unique(units),
        "fees": fees,
        "amenities": [],
        "facts": {
            "special": None,               # specials are attached to the units they apply to
            "rating": stars,
            "rating_count": reviews,
            "pets": True if any(label.startswith("pet") for label in labels) else None,
            "parking": True if any("parking" in label for label in labels) else None,
        },
    }


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
