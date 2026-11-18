"""The files the page loads: index.json (buildings and counts) and one units-<county>.json per county."""

import os

from . import files
from .facts import laundry

BUILDING_FIELDS = ("id", "name", "manager", "url", "platform", "address", "lat", "lon", "state", "county", "tract",
                   "neighborhood", "first_seen")
FACT_FIELDS = ("special", "rating", "rating_count", "coming_soon", "features", "laundry")


def assemble(buildings, results, state, out_dir):
    """(building entries, units by building id) for every building in the region.

    `results` holds this run's successful reads by building id. A building whose read failed keeps the units,
    fees and amenities written last time, and is marked stale. A building whose facts could not be read keeps
    the facts written last time.
    """
    before = {b["id"]: b for b in files.load(os.path.join(out_dir, "index.json"), {}).get("buildings", [])}
    before_units = {}

    def previous_units(building):
        county = before.get(building["id"], {}).get("county")
        if county and county not in before_units:
            before_units[county] = files.load(os.path.join(out_dir, f"units-{county}.json"), {}).get("units", [])
        return [u for u in before_units.get(county, []) if u["building"] == building["id"]]

    entries, units_of = [], {}
    for building in buildings:
        if not building.get("in_region"):
            continue
        status = state["buildings"].get(building["id"], {})
        result = results.get(building["id"])
        old = before.get(building["id"], {})
        if result:
            units = []
            for unit in result["units"]:
                record = state["units"][unit["id"]]
                units.append(dict(unit, first=record["first"], history=record["points"]))
            fees, amenities = result["fees"], result["amenities"]
        else:
            units, fees, amenities = previous_units(building), old.get("fees", []), old.get("amenities", [])

        entry = {key: building.get(key) for key in BUILDING_FIELDS}
        entry.update(units=len(units), fees=fees, amenities=amenities,
                     stale=bool(status.get("failed")), read=status.get("ok"))
        facts = (result or {}).get("facts")
        if facts is not None:
            features = facts.get("features") or []
            entry.update(special=facts.get("special"), rating=facts.get("rating"), rating_count=facts.get("rating_count"),
                         coming_soon=bool(facts.get("coming_soon")), features=features,
                         laundry=laundry.detect(features + amenities))
            if facts.get("neighborhood"):                 # the manager's own name for the area beats the map lookup
                entry["neighborhood"] = facts["neighborhood"]
        else:
            for key in FACT_FIELDS:
                entry[key] = old.get(key, [] if key == "features" else None)
            entry["neighborhood"] = old.get("neighborhood") or entry["neighborhood"]
        entries.append(entry)
        units_of[building["id"]] = units
    return entries, units_of


def write_site(buildings, results, state, out_dir, now):
    entries, units_of = assemble(buildings, results, state, out_dir)

    counties, by_county = {}, {}
    for entry in entries:
        county = counties.setdefault(entry["county"], {"buildings": 0, "units": 0})
        county["buildings"] += 1
        county["units"] += entry["units"]
        by_county.setdefault(entry["county"], []).extend(units_of[entry["id"]])
    for county, units in by_county.items():
        files.save(os.path.join(out_dir, f"units-{county}.json"), {"units": units})
    files.save(os.path.join(out_dir, "index.json"), {"updated": now, "counties": counties, "buildings": entries})
