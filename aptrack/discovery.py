"""Turning what the discoverers found into the building list: merge with last time, then locate each building."""

from . import geo

MISS_LIMIT = 3                 # a building absent from this many discoveries in a row is dropped
KEPT = ("first_seen", "state", "county", "tract", "neighborhood", "in_region")


def merge(previous, found, day, partial=False):
    """`found` maps manager name -> buildings found, or None when that manager's discovery failed.

    Managers that failed or were not run keep their buildings as they were. `partial` (a limited test run)
    means a building that was not found is not counted as missing.
    """
    before = {b["id"]: b for b in previous}
    merged = {}
    for manager, buildings in found.items():
        if buildings is None:
            continue
        for building in buildings:
            old = before.get(building["id"], {})
            new = dict(building, missed=0, first_seen=day)
            for key in KEPT:
                if key in old:
                    new[key] = old[key]
            if new.get("lat") is None and old.get("lat") is not None:
                new["lat"], new["lon"] = old["lat"], old["lon"]
            if old.get("feed_api") and old.get("feed") == building.get("feed"):
                new["feed_api"] = old["feed_api"]
            merged[new["id"]] = new
    succeeded = {manager for manager, buildings in found.items() if buildings is not None}
    for old in previous:
        if old["id"] in merged:
            continue
        if old["manager"] not in succeeded or partial:
            merged[old["id"]] = old
        elif old.get("missed", 0) + 1 < MISS_LIMIT:
            merged[old["id"]] = dict(old, missed=old.get("missed", 0) + 1)
    return sorted(merged.values(), key=lambda b: b["id"])


def in_region(building, counties):
    return building.get("county") in counties


def one_line(address):
    address = address or {}
    if address.get("full"):
        return address["full"]
    parts = [address.get("street"), address.get("city"), " ".join(filter(None, [address.get("state"), address.get("zip")]))]
    return ", ".join(part for part in parts if part)


def locate_all(buildings, get, counties, *, locate=geo.locate, neighborhood=geo.neighborhood, osm_get=None):
    """Fill in tract, county and neighborhood for buildings that lack them. Lookups that fail are left for next time."""
    for building in buildings:
        if not building.get("tract"):
            try:
                if building.get("lat") is not None and building.get("lon") is not None:
                    where = locate(get, lat=building["lat"], lon=building["lon"])
                else:
                    where = locate(get, address=one_line(building.get("address")))
            except Exception as error:
                print(f"  could not locate {building['id']}: {error!r}")
                where = None
            if where:
                building.update(where)
        building["in_region"] = in_region(building, counties)
        if building["in_region"] and not building.get("neighborhood"):
            try:
                building["neighborhood"] = neighborhood(osm_get or get, building["lat"], building["lon"])
            except Exception as error:
                print(f"  no neighborhood for {building['id']}: {error!r}")
