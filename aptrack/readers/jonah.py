"""Jonah Digital building websites: the floor-plans page carries every available apartment as JSON in
`<script id="jd-fp-data-script-app">`, with its base rent, its total with required monthly fees, and its date."""

import json
import re
from collections import Counter

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

DATA = re.compile(r'<script[^>]*id="jd-fp-data-script-app"[^>]*>(.*?)</script>', re.S)


def page_data(page_html):
    match = DATA.search(page_html or "")
    try:
        data = json.loads(match.group(1))
    except (AttributeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse(page_html, building):
    data = page_data(page_html)
    if data is None:
        raise NotAnswering(f"{building['id']}: no listing data in the page")
    plans = {p.get("id"): p for p in data.get("floorplans") or [] if isinstance(p, dict)}
    base = building.get("feed") or building.get("url") or ""
    listed = [u for u in data.get("units") or [] if isinstance(u, dict) and u.get("type", "unit") == "unit"]
    numbers = Counter(u.get("apartment_number") for u in listed)
    units = []
    for u in listed:
        plan = plans.get(u.get("floorplan_id")) or {}
        price = u.get("price_entity") or {}
        adjusted = price.get("adjusted") or {}
        rent = num(adjusted.get("low_no_fees")) or num(u.get("rent_min"))
        total = num(adjusted.get("low"))
        name = u.get("floorplan_title") or plan.get("title")
        number = u.get("apartment_number") or u.get("title") or u.get("id")
        label = f"{u['building']}-{number}" if u.get("building") and numbers[u.get("apartment_number")] > 1 else number
        unit = make_unit(
            building["id"], label,
            rent=rent,
            plan=name,
            beds=u.get("bedrooms"),
            baths=u.get("bathrooms"),
            sqft=u.get("square_feet"),
            fees=round(total - rent, 2) if rent and total and price.get("pricingReflectFees") and total >= rent else None,
            available=price.get("date"),
            special=", ".join(s.get("title") or s.get("name") or "" for s in u.get("specials") or [] if isinstance(s, dict)) or None,
            url=(re.sub(r"(https?://[^/]+).*", r"\1", base) + u["permalink"]) if str(u.get("permalink") or "").startswith("/") else base or None,
            restricted=True if looks_restricted(name) else None,
            plan_image=((plan.get("thumbnail") or {}).get("src") if isinstance(plan.get("thumbnail"), dict) else None),
        )
        if unit:
            units.append(unit)
    return {"units": unique(units), "fees": [], "amenities": []}


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
