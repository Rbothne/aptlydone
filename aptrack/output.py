"""The files the page loads: index.json (buildings and counts) and one units-<county>.json per county."""

import datetime
import os

from . import costs, deals, files, history, traits
from .area import zip_code
from .area.affordable import mostly
from .area.places import dog_score, walk_label
from .facts import laundry

BUILDING_FIELDS = ("id", "name", "manager", "url", "platform", "address", "lat", "lon", "state", "county", "tract",
                   "neighborhood", "zip", "first_seen")
KEEP_UNREAD_DAYS = 3        # a building not read for longer than this has its prices withdrawn
FACT_FIELDS = ("special", "rating", "rating_count", "coming_soon", "features", "laundry", "pets", "parking", "manager_area")


def days_since(day, today):
    return (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(day)).days


def assemble(buildings, results, state, out_dir, today=None):
    """(building entries, units by building id) for every building in the region.

    `results` holds this run's successful reads by building id. A building whose read failed keeps the units,
    fees and amenities written last time, and is marked stale. After more than KEEP_UNREAD_DAYS without a
    successful read its prices are withdrawn (it is listed with no units, marked expired) until it reads again:
    a price nobody has confirmed for days is not one to compare others against. A building whose facts could
    not be read keeps the facts written last time.
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
        expired = bool(not result and today and status.get("failed") and status.get("ok")
                       and days_since(status["ok"], today) > KEEP_UNREAD_DAYS)
        if expired:
            units = []
        for unit in units:
            traits.apply(unit)
            unit["drop"] = history.drop(unit.get("history"), today) if today else None

        entry = {key: building.get(key) for key in BUILDING_FIELDS}
        entry.update(units=len(units), fees=fees, amenities=amenities,
                     stale=bool(status.get("failed")), expired=expired, read=status.get("ok"), why=status.get("why") if status.get("failed") else None)
        facts = (result or {}).get("facts")
        if facts is not None:
            features = facts.get("features") or []
            entry.update(special=facts.get("special"), rating=facts.get("rating"), rating_count=facts.get("rating_count"),
                         coming_soon=bool(facts.get("coming_soon")), features=features,
                         laundry=laundry.detect(features + amenities), pets=facts.get("pets"), parking=facts.get("parking"),
                         manager_area=facts.get("neighborhood"))
        else:
            for key in FACT_FIELDS:
                entry[key] = old.get(key, [] if key == "features" else None)
            if not entry["features"] and building.get("features"):               # found at discovery
                entry["features"] = building["features"]
            if entry["laundry"] is None:
                entry["laundry"] = laundry.detect(entry["features"] + amenities)
        if entry.get("manager_area"):                     # the manager's own name for the area beats the map lookup
            entry["neighborhood"] = entry["manager_area"]
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
                     pets=costs.pets_allowed(fees) or entry.get("pets"), senior=deals.is_senior(entry),
                     parking=True if costs.parking_from(fees) is not None else entry.get("parking"))
    deals.score(everything, entries)
    deals.rank(everything, entries)


def write_site(buildings, results, state, out_dir, now, area=None):
    """`area` is what area.py collected (census, crime, rent trends), or None when it has not run yet."""
    area = area or {}
    entries, units_of = assemble(buildings, results, state, out_dir, today=now[:10])
    projects = area.get("affordable") or {}
    for entry in entries:                      # before pricing, so restricted units are neither tagged nor used as comparisons
        entry["affordable"] = projects.get(entry["id"])
        if mostly(entry["affordable"]):
            for unit in units_of[entry["id"]]:
                unit["restricted"] = True
    price(entries, units_of)
    crime = area.get("crime") or {}
    nearby, walk = area.get("places") or {}, area.get("walk") or {}
    loud, building_sites = area.get("noise") or {}, area.get("works") or {}
    for entry in entries:
        entry["crime"] = crime.get(entry["id"])
        entry["zip"] = zip_code(entry)
        entry["near"] = nearby.get(entry["id"])
        entry["noise"] = loud.get(entry["id"])
        entry["works"] = building_sites.get(entry["id"])
        score = walk.get(entry["id"])
        entry["walk"] = {"score": score, "label": walk_label(score)} if score is not None else None
        entry["dog"] = dog_score(entry.get("pets"), (entry.get("features") or []) + (entry.get("amenities") or []), entry["near"])
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
        "tracts": tracts, "zips": zips, "crime_counties": area.get("crime_counties") or [], "works_counties": area.get("works_counties") or [],
        "area_updated": area.get("updated"),
    })
