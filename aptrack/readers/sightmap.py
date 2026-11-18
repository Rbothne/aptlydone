"""SightMap (Engrain) unit maps: an embed page that points at a JSON feed of units, fees and amenities."""

import json
import re
from collections import Counter

from .. import fetch
from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering, ReadError

API = re.compile(r"https:\\?/\\?/sightmap\.com\\?/app\\?/api\\?/v1\\?/(\w+)\\?/sightmaps\\?/(\d+)")


def feed_url(embed_html):
    """The feed address named in an embed page, or None."""
    match = API.search(embed_html)
    return f"https://sightmap.com/app/api/v1/{match.group(1)}/sightmaps/{match.group(2)}" if match else None


def plan_name(name):
    """Some feeds wrap the name: '{"name": "1 Bed 1 Bath B", "provider_id": "..."}'."""
    if isinstance(name, str) and name.lstrip().startswith("{"):
        try:
            return json.loads(name).get("name") or name
        except ValueError:
            return name
    return name


def parse_fees(data):
    listed = data.get("units") or []
    amounts = {}
    if listed:
        amounts.update(listed[0].get("static_expense_amounts") or {})
        amounts.update(listed[0].get("expense_amounts") or {})
    fees = []
    for key, expense in (data.get("expenses") or {}).items():
        amount = amounts.get(key) or {}
        fees.append({
            "label": (expense.get("label") or "").strip(),
            "type": expense.get("type"),
            "category": expense.get("category"),
            "required": bool(expense.get("is_required")),
            "when": expense.get("classification"),
            "refundable": bool(expense.get("is_refundable")),
            "amount": float(amount["amount"]) if num(amount.get("amount")) is not None else None,
            "text": amount.get("display_amount"),
        })
    return fees


def parse(feed, building):
    data = feed.get("data", feed)
    plans = {p["id"]: p for p in data.get("floor_plans") or []}
    floors = {f["id"]: num(f.get("filter_short_label")) for f in data.get("floors") or []}
    flat_term = data.get("flat_pricing_lease_term_months")
    listed = data.get("units") or []
    repeated = {n for n, count in Counter(u.get("unit_number") for u in listed).items() if count > 1}

    units = []
    for u in listed:
        plan = plans.get(u.get("floor_plan_id")) or {}
        number = u.get("unit_number")
        label = f"{u.get('building')}-{number}" if number in repeated and u.get("building") else number
        rent, total = num(u.get("price")), u.get("total_price")
        total = num(total[0]) if isinstance(total, list) and total else num(total)
        name = plan_name(plan.get("name"))
        flagged = (u.get("affordable_housing_info") or {}).get("is_affordable_housing_unit")
        unit = make_unit(
            building["id"], label,
            rent=rent,
            plan=name,
            restricted=True if flagged or looks_restricted(name) else flagged,
            plan_image=plan.get("image_url"),
            beds=plan.get("bedroom_count"),
            baths=plan.get("bathroom_count"),
            sqft=u.get("area"),
            floor=floors.get(u.get("floor_id")),
            fees=total - rent if rent and total is not None and total >= rent else None,
            lease=u.get("display_lease_term") or flat_term,
            available=u.get("available_on"),
            special=u.get("specials_description"),
            url=building.get("url"),
        )
        if unit:
            units.append(unit)
    if listed and not units:
        raise ReadError(f"{building['id']}: {len(listed)} units listed, none with a price")

    return {
        "units": unique(units),
        "fees": parse_fees(data),
        "amenities": [a["title"].strip() for a in data.get("amenities") or [] if (a.get("title") or "").strip()],
    }


def read(building, get):
    api = building.get("feed_api")
    body = None
    if api:
        try:
            body = get(api)
        except fetch.Gone:
            api = None
    if body is None:
        api = feed_url(get(building["feed"]).decode("utf-8", "replace"))
        if not api:
            raise NotAnswering(f"{building['id']}: no feed address in {building['feed']}")
        body = get(api)
    try:
        feed = json.loads(body)
    except ValueError as error:
        raise NotAnswering(f"{building['id']}: feed is not JSON") from error
    result = parse(feed, building)
    result["feed_api"] = api
    return result
