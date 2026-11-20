"""Kettler's own property search, asked for floor plans too: every building's plans, each with a starting price
and the number of apartments free. One request answers for every building, so it is asked once in a run.

This prices a floor plan, not an apartment. It is the route for Kettler buildings whose own websites cannot be
read apartment by apartment (their RentCafe sites refuse the tracker); a building with a unit map is read from
that instead. A building's feed is the search's address with the building's number after a `#`.
"""

import json
import re
import threading

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

PAGE = "https://www.kettler.com/find-your-home/our-communities"
API = "https://www.kettler.com/api/v1/properties?api_key={}&include_properties=1&include_floorplans=1&per_page=500"
NUMBER = re.compile(r"ng-init='init\((\d+)\)'")

_listed = {}                      # what the search answered, kept for the run: {building number: its record}
_lock = threading.Lock()


def forget():
    with _lock:
        _listed.clear()


def listed(get):
    """{building number: record} from the search, asked once. The site number is read from the page each time."""
    with _lock:
        if not _listed:
            number = NUMBER.search(get(PAGE).decode("utf-8", "replace"))
            if not number:
                raise NotAnswering(f"Kettler: {PAGE} no longer carries its search number")
            try:
                found = json.loads(get(API.format(number.group(1)))).get("properties") or []
            except ValueError as error:
                raise NotAnswering(f"Kettler: its search did not answer with a list ({error})")
            found = list(found.values()) if isinstance(found, dict) else found
            _listed.update({str(p.get("property_id")): p for p in found if isinstance(p, dict)})
        return dict(_listed)


def read(building, get):
    number = building["feed"].rsplit("#", 1)[-1]
    record = listed(get).get(number)
    if record is None:
        raise NotAnswering(f"{building['id']}: Kettler's search no longer lists building {number}")
    units = []
    for plan in record.get("floorplans") or []:
        count, rent = num(plan.get("units_available")), num(plan.get("pricing"))
        if not count or not rent:
            continue
        name = (plan.get("name") or "").strip() or str(plan.get("floorplan_id"))
        unit = make_unit(
            building["id"], name, rent=rent, plan=name, beds=plan.get("beds"), baths=plan.get("baths"),
            sqft=plan.get("sqft") or None, count=count,
            notes=f"{int(count)} available; the company's starting price for this floor plan",
            url=building.get("url"), plan_image=plan.get("image_url") or None,
            restricted=True if looks_restricted(name) else None,
        )
        if unit:
            units.append(unit)
    return {"units": unique(units), "fees": [], "amenities": []}
