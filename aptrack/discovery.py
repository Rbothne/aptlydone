"""Turning what the discoverers found into the building list: merge with last time, then locate each building."""

import concurrent.futures
import time

from . import geo

MISS_LIMIT = 3                 # a building absent from this many discoveries in a row is dropped
SHRINK = 0.5                   # a company listing under this share of its known buildings is not believed...
SMALL = 4                      # ...unless it had fewer buildings than this to begin with
RETRY_WAIT = 60                # seconds before going back to companies whose sites stopped answering
KEPT = ("first_seen", "state", "county", "tract", "neighborhood", "zip", "in_region")


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


def locate_all(buildings, get, counties, *, locate=geo.locate, reverse=geo.reverse, osm_get=None):
    """Fill in tract, county, neighborhood and ZIP for buildings that lack them. Lookups that fail are left for next time."""
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
        if building["in_region"] and not (building.get("neighborhood") and building.get("zip")):
            try:
                found = reverse(osm_get or get, building["lat"], building["lon"])
            except Exception as error:
                print(f"  no neighborhood for {building['id']}: {error!r}")
                continue
            for key in ("neighborhood", "zip"):
                if not building.get(key) and found.get(key):
                    building[key] = found[key]
