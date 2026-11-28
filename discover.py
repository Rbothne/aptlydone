"""Find every building the listed management companies run in the region, and work out where each one is.

    py discover.py                 every company in managers.json
    py discover.py --only Bozzuto  one company
    py discover.py --limit 5       the first 5 buildings per company (for testing)

Writes data/buildings.json. Buildings found before keep their details; one that stops being listed is dropped
after three discoveries in a row without it. A company marked "paused" in managers.json is not searched, and
its buildings are kept as they are.
"""

import argparse
import os

from aptrack import companies, discovery, fetch, files, vpn
from aptrack.discover import DISCOVERERS

ROOT = os.path.dirname(os.path.abspath(__file__))
MANAGERS = os.path.join(ROOT, "managers.json")
BUILDINGS = os.path.join(ROOT, "data", "buildings.json")
OSM_AGENT = {"User-Agent": "aptrack/0.1 (personal apartment price tracker)"}    # OpenStreetMap asks apps to name themselves


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="run one company (its name in managers.json)")
    parser.add_argument("--limit", type=int, help="first N buildings per company")
    args = parser.parse_args()

    config = files.load(MANAGERS, None)
    settings = config["settings"]
    managers = [m for m in config["managers"] if not args.only or m["name"].lower() == args.only.lower()]
    if not managers:
        parser.error(f"no company named {args.only!r} in managers.json")
    for name, why in companies.paused(managers).items():
        if args.only:
            parser.error(f"{name} is paused in managers.json ({why}); delete its \"paused\" entry to bring it back")
        print(f"{name}: paused ({why}); keeping what is known about it")
    managers = companies.active(managers)
    get = fetch.polite(settings["delay_seconds"], settings.get("site_delays"), routes=vpn.routes())

    found = discovery.run_all(managers, DISCOVERERS, get, limit=args.limit, workers=settings.get("workers"))

    buildings = discovery.merge(files.load(BUILDINGS, []), found, files.today(), partial=bool(args.limit))
    discovery.check_addresses(buildings, fetch.post)
    moved = [b["id"] for b in buildings if discovery.correct(b)]
    if moved:
        print(f"  placed by their address, more than {discovery.MOVE_MILES} mile from their published coordinates: {', '.join(moved)}")
    discovery.adopt_cities(buildings, config["managers"])
    discovery.locate_all(buildings, get, settings["counties"], osm_get=lambda url: get(url, headers=OSM_AGENT))
    files.save(BUILDINGS, buildings, indent=1)

    for manager in managers:
        mine = [b for b in buildings if b["manager"] == manager["name"]]
        inside = [b for b in mine if b.get("in_region")]
        print(f"{manager['name']}: {len(found[manager['name']] or [])} found this run, {len(mine)} known, "
              f"{len(inside)} in the region, {sum(1 for b in inside if b['platform'] == 'link')} of those without a readable feed, "
              f"{sum(1 for b in mine if not b.get('tract'))} not located")


if __name__ == "__main__":
    main()
