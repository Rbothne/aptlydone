"""The files the page loads: index.json (buildings and counts) and one units-<county>.json per county."""

import os

from . import files

BUILDING_FIELDS = ("id", "name", "manager", "url", "platform", "address", "lat", "lon", "state", "county", "tract",
                   "neighborhood", "first_seen")


def write_site(buildings, results, state, out_dir, now):
    """`results` holds this run's successful reads by building id. A building whose read failed keeps the units,
    fees and amenities written last time, and is marked stale."""
    before = {b["id"]: b for b in files.load(os.path.join(out_dir, "index.json"), {}).get("buildings", [])}
    before_units = {}

    def previous_units(building):
        county = before.get(building["id"], {}).get("county")
        if county and county not in before_units:
            before_units[county] = files.load(os.path.join(out_dir, f"units-{county}.json"), {}).get("units", [])
        return [u for u in before_units.get(county, []) if u["building"] == building["id"]]

    index, by_county = [], {}
    for building in buildings:
        if not building.get("in_region"):
            continue
        status = state["buildings"].get(building["id"], {})
        result = results.get(building["id"])
        if result:
            units = []
            for unit in result["units"]:
                record = state["units"][unit["id"]]
                units.append(dict(unit, first=record["first"], history=record["points"]))
            fees, amenities = result["fees"], result["amenities"]
        else:
            old = before.get(building["id"], {})
            units, fees, amenities = previous_units(building), old.get("fees", []), old.get("amenities", [])
        entry = {key: building.get(key) for key in BUILDING_FIELDS}
        entry.update(units=len(units), fees=fees, amenities=amenities,
                     stale=bool(status.get("failed")), read=status.get("ok"))
        index.append(entry)
        by_county.setdefault(building["county"], []).extend(units)

    counties = {}
    for entry in index:
        county = counties.setdefault(entry["county"], {"buildings": 0, "units": 0})
        county["buildings"] += 1
        county["units"] += entry["units"]
    for county, units in by_county.items():
        files.save(os.path.join(out_dir, f"units-{county}.json"), {"units": units})
    files.save(os.path.join(out_dir, "index.json"), {"updated": now, "counties": counties, "buildings": index})
