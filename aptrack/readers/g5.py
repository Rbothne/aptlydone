"""G5 building websites (often run with RealPage): the floor-plans page names its "Floor Plans Plus" widget's
location, and the widget asks G5's inventory service (GraphQL) for the floor plans, then for each plan's units.

Each available unit has its base rent ("rate") and its total with required monthly fees ("total_rent")."""

import datetime
import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering, ReadError

CONFIG = re.compile(r'<script[^>]*id="floor-plans-plus-config"[^>]*>(.*?)</script>', re.S)
INVENTORY = "https://inventory.g5marketingcloud.com"

PLANS = """query ApartmentComplex($locationUrn: String!, $moveInDate: String!) {
  apartmentComplex(locationUrn: $locationUrn) {
    showUnits
    floorplans(moveInDate: $moveInDate) {
      id name totalAvailableUnits beds baths sqft startingRate imageUrl
    }
  }
}"""

UNITS = """query Units($locationUrn: String, $floorplanId: ID, $limit: Int) {
  units(locationUrn: $locationUrn, floorplanId: $floorplanId, limit: $limit) {
    name displayName building sqftDisplay availabilityDate
    specials { name }
    prices { priceType value leaseTermBasisMin }
  }
}"""


def config(page_html):
    """The widget's settings ({"locationUrn", "inventoryHost", "sightmapID", ...}), or None."""
    match = CONFIG.search(page_html or "")
    try:
        data = json.loads(match.group(1))
    except (AttributeError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("locationUrn") else None


def ask(get, host, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    try:
        answer = json.loads(get(host.rstrip("/") + "/graphql", data=body, headers={"Content-Type": "application/json"}))
    except ValueError as error:
        raise NotAnswering("the inventory service did not answer with JSON") from error
    if answer.get("errors") or not isinstance(answer.get("data"), dict):
        raise NotAnswering(f"the inventory service refused the question: {str(answer.get('errors'))[:120]}")
    return answer["data"]


def price(prices, kind):
    for p in prices or []:
        if p.get("priceType") == kind and num(p.get("value")):
            return num(p["value"]), num(p.get("leaseTermBasisMin"))
    return None, None


def units_of(building, plan, found, url):
    out = []
    for u in found:
        rent, lease = price(u.get("prices"), "rate")
        total, _ = price(u.get("prices"), "total_rent")
        out.append(make_unit(
            building["id"], u.get("displayName") or u.get("name"),
            rent=rent, plan=plan.get("name"), beds=plan.get("beds"), baths=plan.get("baths"),
            sqft=num(u.get("sqftDisplay")) or plan.get("sqft"),
            fees=round(total - rent, 2) if rent and total and total >= rent else None,
            lease=lease, available=u.get("availabilityDate"),
            special=", ".join(s["name"] for s in u.get("specials") or [] if s.get("name")) or None,
            url=url, restricted=True if looks_restricted(plan.get("name")) else None, plan_image=plan.get("imageUrl")))
    return out


def read(building, get, today=None):
    page = get(building["feed"]).decode("utf-8", "replace")
    settings = config(page)
    if not settings:
        raise NotAnswering(f"{building['id']}: no floor-plans widget in {building['feed']}")
    host, urn = settings.get("inventoryHost") or INVENTORY, settings["locationUrn"]
    day = (today or datetime.date.today()).isoformat()
    complex_ = ask(get, host, PLANS, {"locationUrn": urn, "moveInDate": day}).get("apartmentComplex")
    if not complex_:
        raise ReadError(f"{building['id']}: the inventory service knows no location {urn}")
    units = []
    for plan in complex_.get("floorplans") or []:
        count = num(plan.get("totalAvailableUnits"))
        if not count:
            continue
        found = ask(get, host, UNITS, {"locationUrn": urn, "floorplanId": plan["id"], "limit": 500}).get("units") or [] \
            if complex_.get("showUnits") else []
        listed = [u for u in units_of(building, plan, found, building["feed"]) if u]
        if not listed:                          # units are not shown: the plan is one entry at its lowest rent
            listed = [make_unit(building["id"], plan.get("name"), rent=plan.get("startingRate"), plan=plan.get("name"),
                                beds=plan.get("beds"), baths=plan.get("baths"), sqft=plan.get("sqft"),
                                notes=f"{count} available", count=count, url=building["feed"],
                                plan_image=plan.get("imageUrl"),
                                restricted=True if looks_restricted(plan.get("name")) else None)]
        units += [u for u in listed if u]
    return {"units": unique(units), "fees": [], "amenities": []}
