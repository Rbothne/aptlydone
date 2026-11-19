"""Turning what the discoverers found into the building list: merge with last time, then locate each building."""

import concurrent.futures
import time

from . import geo
from .deals import miles

MISS_LIMIT = 3                 # a building absent from this many discoveries in a row is dropped
SHRINK = 0.5                   # a company listing under this share of its known buildings is not believed...
SMALL = 4                      # ...unless it had fewer buildings than this to begin with
RETRY_WAIT = 60                # seconds before going back to companies whose sites stopped answering
MOVE_MILES = 0.25              # published coordinates this far from an exactly matched address give way to the address
KEPT = ("first_seen", "state", "county", "tract", "neighborhood", "zip", "in_region", "placed", "placed_for", "located_at")


def merge(previous, found, day, partial=False):
    """`found` maps manager name -> buildings found, or None when that manager's discovery failed.

    Managers that failed or were not run keep their buildings as they were. `partial` (a limited test run)
    means a building that was not found is not counted as missing.
    """
    before = {b["id"]: b for b in previous}
    found = dict(found)
    if not partial:
        for manager, buildings in found.items():
            known = sum(1 for b in previous if b["manager"] == manager)
            if buildings is not None and known >= SMALL and len(buildings) < SHRINK * known:
                print(f"{manager}: found {len(buildings)} of {known} known buildings; not believing it, keeping what was known")
                found[manager] = None
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


def run_all(managers, discoverers, get, limit=None, workers=None, sleep=time.sleep):
    """{manager name: buildings found, or None when its discovery failed}. Every company is read at once, each
    at its own site's spacing (`workers` caps how many, for tests); one whose site fails or stops answering is
    left alone, and come back to once after the others are done."""
    def attempt(manager):
        try:
            find = discoverers[manager["discover"]]
            if getattr(find, "needs_config", False):          # a company described entirely by its managers.json line
                find = find(manager)
            return find(get, limit=limit)
        except Exception as error:
            print(f"{manager['name']}: discovery failed: {error!r}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers or len(managers), len(managers)))) as pool:
        found = dict(zip((m["name"] for m in managers), pool.map(attempt, managers)))
    failed = [m for m in managers if found[m["name"]] is None]
    if failed:
        print(f"Coming back to {', '.join(m['name'] for m in failed)} in {RETRY_WAIT}s")
        sleep(RETRY_WAIT)
        for manager in failed:
            found[manager["name"]] = attempt(manager)
            if found[manager["name"]] is None:
                print(f"{manager['name']}: still failing; keeping its buildings as they were")
    return found


def in_region(building, counties):
    return building.get("county") in counties


def one_line(address):
    address = address or {}
    if address.get("full"):
        return address["full"]
    parts = [address.get("street"), address.get("city"), " ".join(filter(None, [address.get("state"), address.get("zip")]))]
    return ", ".join(part for part in parts if part)


def address_key(address):
    return "|".join(str(address.get(part) or "") for part in ("street", "city", "state", "zip"))


def check_addresses(buildings, post):
    """Ask the Census Bureau where each building's street address is, and remember the answer on the building as
    `placed` ({"lat", "lon", "zip", "city", "exact"}, or None when the address was not found). An address is asked
    about once; a building is asked about again only when its address changes. A failed request changes nothing."""
    ask = [b for b in buildings if (b.get("address") or {}).get("street") and b.get("placed_for") != address_key(b["address"])]
    if not ask:
        return
    try:
        found = geo.place_addresses([(b["id"], b["address"]["street"], b["address"].get("city"), b["address"].get("state"),
                                      str(b["address"].get("zip") or "")[:5]) for b in ask], post)
    except Exception as error:
        print(f"  could not check {len(ask)} addresses this time: {error!r}")
        return
    for building in ask:
        building["placed"], building["placed_for"] = found.get(building["id"]), address_key(building["address"])
    print(f"  {len(ask)} addresses checked: {sum(1 for b in ask if b['placed'])} found, "
          f"{sum(1 for b in ask if b['placed'] and b['placed']['exact'])} of them exactly")


def correct(building):
    """Move a building to where its address is when its published coordinates are more than MOVE_MILES away and the
    address was matched exactly (a loose match is a guess, and guesses do not outrank the building's own site).
    The published coordinates are kept as site_lat and site_lon. True when the building moved."""
    placed = building.get("placed")
    if not placed or not placed.get("exact"):
        return False
    if building.get("lat") is None or building.get("lon") is None:
        building["lat"], building["lon"] = placed["lat"], placed["lon"]
        return True
    if miles(building, placed) <= MOVE_MILES:
        return False
    building["site_lat"], building["site_lon"] = building["lat"], building["lon"]
    building["lat"], building["lon"] = placed["lat"], placed["lon"]
    return True


def adopt_cities(buildings, managers):
    """A company marked `city_from_address` publishes a region where the city belongs ("DC Metro"): its buildings
    take the city the Census Bureau gives for their street address."""
    wanted = {m["name"] for m in managers if m.get("city_from_address")}
    for building in buildings:
        placed = building.get("placed")
        if building.get("manager") in wanted and placed and placed.get("city"):
            building["address"] = dict(building["address"], city=placed["city"].title())


def locate_all(buildings, get, counties, *, locate=geo.locate, reverse=geo.reverse, osm_get=None):
    """Fill in tract, county, neighborhood and ZIP for buildings that lack them, and again for a building whose
    coordinates have changed since it was located. Lookups that fail are left for next time."""
    for building in buildings:
        here = [building["lat"], building["lon"]] if building.get("lat") is not None and building.get("lon") is not None else None
        known = building.get("located_at")
        if building.get("tract") and here and (known != here if known is not None else "site_lat" in building):
            for key in ("tract", "neighborhood", "zip"):          # it has moved: what was looked up there no longer holds
                building.pop(key, None)
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
        if building.get("tract") and building.get("lat") is not None and building.get("lon") is not None:
            building["located_at"] = [building["lat"], building["lon"]]
        building["in_region"] = in_region(building, counties)
        if building["in_region"] and not (building.get("neighborhood") and building.get("zip")):
            try:
                found = reverse(osm_get or get, building["lat"], building["lon"])
            except Exception as error:
                print(f"  no neighborhood for {building['id']}: {error!r}")
                continue
            for key in ("neighborhood", "zip"):
                if not building.get(key) and found.get(key):
                    building[key] = found[key]
