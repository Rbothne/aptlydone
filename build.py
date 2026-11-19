"""Read every building's available units, update the price history, and write the files the page loads.

    py build.py                    every building in data/buildings.json that is in the region
    py build.py --only <id>        one building
    py build.py --limit 10         the first 10 buildings (for testing)
    py build.py --probe            read one building per listing system and report; writes nothing

Run discover.py first: it creates data/buildings.json.
"""

import argparse
import concurrent.futures
import copy
import os
import sys
import time
from urllib.parse import urlparse

from aptrack import fetch, files, history, output
from aptrack.facts import FACTS
from aptrack.readers import READERS, NotAnswering, ReadError

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILDINGS = os.path.join(ROOT, "data", "buildings.json")
STATE = os.path.join(ROOT, "data", "state.json")
AREA = os.path.join(ROOT, "data", "area.json")      # written by area.py; optional
SITE_DATA = os.path.join(ROOT, "site", "data")
FAIL_SHARE = 0.2          # a run where more than this share of buildings fail ends in failure
SILENT_AFTER = 3          # failures in a row before a site is left alone until the end of the run
RETRY_WAIT = 60          # seconds to wait before going back to sites that said "too many requests"


def readable(building):
    return bool(building.get("in_region")) and building.get("platform") in READERS


def read_one(building, get, facts_trouble=None):
    """(result, error): exactly one is None. RateLimited is raised, not returned.

    `facts_trouble` counts, per manager, facts reads that failed in a row during this run; once a facts site has
    failed SILENT_AFTER times running it is not asked again today, and its buildings keep the facts they had."""
    try:
        result = READERS[building["platform"]](building, get)
    except fetch.RateLimited:
        raise
    except Exception as error:
        return None, error
    # Facts about the building (concession, rating...) are a bonus: failing to get them never fails the read.
    result.setdefault("facts", None)
    manager = building.get("manager")
    facts_reader = FACTS.get(manager)
    trouble = facts_trouble if facts_trouble is not None else {}
    if facts_reader and trouble.get(manager, 0) < SILENT_AFTER:
        try:
            result["facts"] = facts_reader(building, get)
            trouble[manager] = 0
        except Exception as error:
            print(f"  no facts for {building['id']}: {error!r}")
            result["facts"] = None
            trouble[manager] = trouble.get(manager, 0) + 1
    return result, None


def host(building):
    """The site a building's units are read from."""
    return urlparse(building.get("feed_api") or building["feed"]).netloc


def reason(error):
    """A failed read in a few words, for the page: "HTTP 403", "timed out", or the error's own message."""
    if getattr(error, "code", None):
        return f"HTTP {error.code}"
    if isinstance(error, fetch.Gone):
        return "page not found"
    if isinstance(error, fetch.RateLimited):
        return "too many requests"
    if isinstance(error, TimeoutError) or "timed out" in str(error):
        return "timed out"
    return str(error)[:100] or type(error).__name__


def site_trouble(error):
    """Is this failure about the site (not answering, or answering with something that is not its data),
    as opposed to one building's listing being unusable?"""
    return error is not None and (isinstance(error, NotAnswering) or not isinstance(error, ReadError))


def read_host(group, get, facts_trouble=None):
    """Read one site's buildings in order. Returns (outcomes, buildings to come back to later).

    A site is left alone for the rest of the pass when it says "too many requests", or when it fails
    SILENT_AFTER times in a row; the run moves on to other sites and circles back once at the end.
    """
    outcomes, streak = [], 0
    for position, building in enumerate(group):
        try:
            result, error = read_one(building, get, facts_trouble)
        except fetch.RateLimited:
            return outcomes, group[position:]
        outcomes.append((building, result, error))
        streak = streak + 1 if site_trouble(error) else 0
        if streak >= SILENT_AFTER:
            del outcomes[-streak:]                      # those tries are not the last word: they get another go
            return outcomes, group[position + 1 - streak:]
    return outcomes, []


def run(buildings, state, get, day, *, workers=4, sleep=time.sleep):
    """Read every readable building and record what was found. Returns this run's successful reads by building id."""
    groups = {}
    for building in buildings:
        if readable(building):
            groups.setdefault(host(building), []).append(building)

    outcomes, deferred, facts_trouble = [], [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, left in pool.map(lambda group: read_host(group, get, facts_trouble), groups.values()):
            outcomes += done
            deferred += left
    if deferred:
        print(f"{len(deferred)} buildings at sites that stopped answering: waiting {RETRY_WAIT}s, then trying each once more")
        sleep(RETRY_WAIT)
        throttle = getattr(get, "throttle", None)
        if throttle:                                    # whatever speed those sites were on, come back at the default one
            for site in {host(building) for building in deferred}:
                throttle.slow_down(site)
        streaks = {}                                    # site -> failures in a row during this second pass
        for building in deferred:
            site = host(building)
            if streaks.get(site, 0) >= SILENT_AFTER:    # still silent: stop asking it today
                outcomes.append((building, None, NotAnswering("the site is still not answering")))
                continue
            try:
                result, error = read_one(building, get, facts_trouble)
            except fetch.RateLimited as limited:
                result, error = None, limited
            outcomes.append((building, result, error))
            streaks[site] = streaks.get(site, 0) + 1 if error is not None and (site_trouble(error) or isinstance(error, fetch.RateLimited)) else 0

    results = {}
    for building, result, error in outcomes:
        if error:
            print(f"  failed {building['id']}: {error!r}")
            history.record_failure(state, building["id"], day, why=reason(error))
            continue
        history.record(state, building["id"], result["units"], day)
        if result["facts"] is not None and "special" in result["facts"]:
            history.record_special(state, building["id"], result["facts"]["special"], day)
        if result.get("feed_api"):
            building["feed_api"] = result["feed_api"]
        results[building["id"]] = result
    return results


def too_many_failures(chosen, results):
    """True when so many buildings failed that the run should end in failure (and GitHub emails the owner)."""
    return len(chosen) - len(results) > FAIL_SHARE * len(chosen)


def totals(state, day):
    units = state["units"].values()
    return {
        "listed": sum(1 for u in units if not u["gone"]),
        "new": sum(1 for u in units if u["first"] == day and not u["gone"]),
        "gone": sum(1 for u in units if u["gone"] == day),
        "changed": sum(1 for u in units if not u["gone"] and len(u["points"]) > 1 and u["points"][-1][0] == day),
    }


def probe(buildings, get):
    """One building per listing system: can this machine read them?"""
    ok = True
    for platform in READERS:
        building = next((b for b in buildings if readable(b) and b["platform"] == platform), None)
        if not building:
            print(f"{platform}: no building to try")
            ok = False
            continue
        try:
            result, error = read_one(building, get)
        except fetch.RateLimited as limited:
            result, error = None, limited
        if error:
            print(f"{platform}: FAILED on {building['id']}: {error!r}")
            ok = False
        else:
            print(f"{platform}: ok, {len(result['units'])} units at {building['id']}")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="read one building (its id)")
    parser.add_argument("--limit", type=int, help="read the first N buildings")
    parser.add_argument("--probe", action="store_true", help="read one building per listing system; write nothing")
    args = parser.parse_args()

    settings = files.load(os.path.join(ROOT, "managers.json"), None)["settings"]
    buildings = files.load(BUILDINGS, None)
    if buildings is None:
        sys.exit("data/buildings.json is missing: run discover.py first")
    get = fetch.polite(settings["delay_seconds"], settings.get("site_delays"))
    if args.probe:
        sys.exit(0 if probe(buildings, get) else 1)

    chosen = [b for b in buildings if readable(b) and (not args.only or b["id"] == args.only)][:args.limit]
    if not chosen:
        sys.exit("no readable buildings match")
    state = files.load(STATE, None) or history.new_state()
    before = copy.deepcopy(state)
    day = files.today()

    results = run(chosen, state, get, day, workers=settings["workers"])
    history.retire(state, {b["id"] for b in buildings}, day)
    history.prune(state, day)
    if not history.safe_to_save(before, state):
        sys.exit(f"The new history has {len(state['units'])} unit records, under 80% of the {len(before['units'])} before. "
                 "Not saving it.")
    files.save(STATE, state)
    files.save(BUILDINGS, buildings, indent=1)
    output.write_site(buildings, results, state, SITE_DATA, files.now(), area=files.load(AREA, None))

    count = totals(state, day)
    print(f"{len(results)} buildings read, {len(chosen) - len(results)} failed; {count['listed']} units listed, "
          f"{count['new']} new today, {count['gone']} gone today, {count['changed']} price changes today")
    if too_many_failures(chosen, results):
        sys.exit(f"More than {FAIL_SHARE:.0%} of buildings could not be read. The data was saved, but something is wrong.")


if __name__ == "__main__":
    main()
