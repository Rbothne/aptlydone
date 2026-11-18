"""RentPress: a WordPress plugin smaller managers use to show RentCafe listings. A building page carries its
floor plans (rent range, size, how many are available) and its own details as JSON in two attributes.

It publishes prices per floor plan, not per unit. So each available floor plan becomes one entry at its lowest
rent, with `count` saying how many units are available at that plan.
"""

import html as htmllib
import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

FLOORPLANS = re.compile(r"data-floorplans='([^']*)'")
PROPERTIES = re.compile(r"data-parentproperties='([^']*)'")
RESTRICTED = re.compile(r"income[- ]restricted|income limits?|affordable housing|tax credit|LIHTC|housing choice voucher", re.I)


def attribute(pattern, page_html):
    match = pattern.search(page_html or "")
    try:
        return json.loads(htmllib.unescape(match.group(1)))
    except (AttributeError, ValueError) as error:
        raise NotAnswering("no listing data in the page") from error


def listed(value):
    """A field that holds a JSON list as text ('["Concierge","Garage"]'), as a list of strings."""
    try:
        items = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return []
    return [str(item).strip() for item in items or [] if str(item).strip()] if isinstance(items, list) else []


def money(amount):
    return f"${amount:,.0f}"


def parse(page_html, building):
    plans = attribute(FLOORPLANS, page_html)
    properties = attribute(PROPERTIES, page_html)
    prop = properties[0] if isinstance(properties, list) and properties else {}
    restricted = True if RESTRICTED.search(f"{prop.get('property_name') or ''} {prop.get('property_description') or ''}") else None

    units = []
    for plan in plans if isinstance(plans, list) else []:
        count, low, high = num(plan.get("floorplan_units_available")), num(plan.get("floorplan_rent_min")), num(plan.get("floorplan_rent_max"))
        if not count or not low:
            continue
        name = (plan.get("floorplan_name") or plan.get("floorplan_code") or "").strip()
        note = f"{count} available" + (f", {money(low)} to {money(high)}" if high and high > low else "")
        unit = make_unit(
            building["id"], name,
            rent=low,
            plan=name,
            beds=plan.get("floorplan_bedrooms"),
            baths=plan.get("floorplan_bathrooms"),
            sqft=plan.get("floorplan_sqft_min"),
            lease=plan.get("floorplan_rent_term"),
            special=plan.get("floorplan_specials_message"),
            notes=note,
            url=plan.get("floorplan_post_link") or building.get("url"),
            restricted=True if restricted or looks_restricted(name) else None,
            plan_image=plan.get("floorplan_image"),
            count=count,
        )
        if unit:
            units.append(unit)

    amenities = listed(prop.get("property_community_amenities"))
    features = listed(prop.get("property_features")) + listed(prop.get("property_apartment_amenities"))
    everything = " ".join(amenities + features).lower()
    return {
        "units": unique(units),
        "fees": [],
        "amenities": amenities,
        "facts": {
            "special": " ".join((prop.get("property_specials_message") or "").split()) or None,
            "rating": num(prop.get("property_rating")),
            "rating_count": None,
            "neighborhood": (prop.get("property_neighborhood_post_name") or "").strip() or None,
            "features": amenities + features,
            "pets": True if listed(prop.get("property_pets")) else None,
            "parking": True if "parking" in everything or "garage" in everything else None,
        },
    }


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
