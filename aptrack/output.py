"""The files the page loads: index.json (buildings and counts) and one units-<county>.json per county."""

import os

from . import costs, deals, files
from .area import zip_code
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
            if not entry["features"] and building.get("features"):               # found at discovery
                entry["features"] = building["features"]
            if entry["laundry"] is None:
                entry["laundry"] = laundry.detect(entry["features"] + amenities)
        if entry.get("rating") is None and building.get("rating") is not None:      # found at discovery
            entry.update(rating=building["rating"], rating_count=building.get("rating_count"))
        entries.append(entry)
        units_of[building["id"]] = units
    return entries, units_of


def price(entries, units_of):
    """Work out each unit's true monthly cost, how it compares, and its tag; and each building's cost facts."""
    everything = []
    for entry in entries:
        fees = entry["fees"] or []
        for unit in units_of[entry["id"]]:
            costs.apply(unit, fees, entry.get("special"))
            everything.append(unit)
        entry.update(one_time=costs.one_time(fees), parking_from=costs.parking_from(fees),
                     pets=costs.pets_allowed(fees), senior=deals.is_senior(entry))
    deals.score(everything, entries)
    deals.rank(everything, entries)


def write_site(buildings, results, state, out_dir, now, area=None):
    """`area` is what area.py collected (census, crime, rent trends), or None when it has not run yet."""
    area = area or {}
    entries, units_of = assemble(buildings, results, state, out_dir)
    price(entries, units_of)
    crime = area.get("crime") or {}
    for entry in entries:
        entry["crime"] = crime.get(entry["id"])
        entry["zip"] = zip_code(entry)
    tracts = {e["tract"]: area["tracts"][e["tract"]] for e in entries if e.get("tract") in (area.get("tracts") or {})}
    zips = {e["zip"]: area["zips"][e["zip"]] for e in entries if e.get("zip") in (area.get("zips") or {})}

    counties, by_county = {}, {}
    for entry in entries:
        county = counties.setdefault(entry["county"], {"buildings": 0, "units": 0})
        county["buildings"] += 1
        county["units"] += entry["units"]
        by_county.setdefault(entry["county"], []).extend(units_of[entry["id"]])
    for county, units in by_county.items():
        files.save(os.path.join(out_dir, f"units-{county}.json"), {"units": units})
    files.save(os.path.join(out_dir, "index.json"), {
        "updated": now, "counties": counties, "buildings": entries,
        "tracts": tracts, "zips": zips, "crime_counties": area.get("crime_counties") or [], "area_updated": area.get("updated"),
    })
