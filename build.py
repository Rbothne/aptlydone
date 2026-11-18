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
from aptrack.readers import READERS

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILDINGS = os.path.join(ROOT, "data", "buildings.json")
STATE = os.path.join(ROOT, "data", "state.json")
SITE_DATA = os.path.join(ROOT, "site", "data")
RETRY_WAIT = 60           # seconds to wait before going back to sites that said "too many requests"


def readable(building):
    return bool(building.get("in_region")) and building.get("platform") in READERS


def read_one(building, get):
    """(result, error): exactly one is None. RateLimited is raised, not returned."""
    try:
        result = READERS[building["platform"]](building, get)
    except fetch.RateLimited:
        raise
    except Exception as error:
        return None, error
    # Facts about the building (concession, rating...) are a bonus: failing to get them never fails the read.
    result.setdefault("facts", None)
    facts_reader = FACTS.get(building.get("manager"))
    if facts_reader:
        try:
            result["facts"] = facts_reader(building, get)
        except Exception as error:
            print(f"  no facts for {building['id']}: {error!r}")
            result["facts"] = None
    return result, None


def read_host(group, get):
    """Read one site's buildings in order. Returns (outcomes, buildings left unread after a "too many requests")."""
    outcomes = []
    for position, building in enumerate(group):
        try:
            outcomes.append((building, *read_one(building, get)))
        except fetch.RateLimited:
            return outcomes, group[position:]
    return outcomes, []


def run(buildings, state, get, day, *, workers=4, sleep=time.sleep):
    """Read every readable building and record what was found. Returns this run's successful reads by building id."""
    groups = {}
    for building in buildings:
        if readable(building):
            groups.setdefault(urlparse(building.get("feed_api") or building["feed"]).netloc, []).append(building)

    outcomes, deferred = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, left in pool.map(lambda group: read_host(group, get), groups.values()):
            outcomes += done
            deferred += left
    if deferred:
        print(f"{len(deferred)} buildings at rate-limited sites: waiting {RETRY_WAIT}s, then trying each once more")
        sleep(RETRY_WAIT)
        for building in deferred:
            try:
                outcomes.append((building, *read_one(building, get)))
            except fetch.RateLimited as error:
                outcomes.append((building, None, error))

    results = {}
    for building, result, error in outcomes:
        if error:
            print(f"  failed {building['id']}: {error!r}")
            history.record_failure(state, building["id"], day)
            continue
        history.record(state, building["id"], result["units"], day)
        if result["facts"] is not None and "special" in result["facts"]:
            history.record_special(state, building["id"], result["facts"]["special"], day)
        if result.get("feed_api"):
            building["feed_api"] = result["feed_api"]
        results[building["id"]] = result
    return results


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
    get = fetch.polite(settings["delay_seconds"])
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
    output.write_site(buildings, results, state, SITE_DATA, files.now())

    count = totals(state, day)
    print(f"{len(results)} buildings read, {len(chosen) - len(results)} failed; {count['listed']} units listed, "
          f"{count['new']} new today, {count['gone']} gone today, {count['changed']} price changes today")


if __name__ == "__main__":
    main()
