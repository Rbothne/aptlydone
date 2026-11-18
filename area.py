"""Collect the slow-changing data around the buildings: census figures, crime nearby, and ZIP rent trends.

    py area.py                 everything
    py area.py --only crime    one part: census, crime or rents

Reads data/buildings.json and writes data/area.json. The next build.py run puts it on the page.
"""

import argparse
import os
import sys

from aptrack import area, fetch, files

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILDINGS = os.path.join(ROOT, "data", "buildings.json")
AREA = os.path.join(ROOT, "data", "area.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=area.PARTS, help="collect one part")
    args = parser.parse_args()

    buildings = files.load(BUILDINGS, None)
    if buildings is None:
        sys.exit("data/buildings.json is missing: run discover.py first")
    buildings = [b for b in buildings if b.get("in_region")]
    settings = files.load(os.path.join(ROOT, "managers.json"), None)["settings"]
    get = fetch.polite(settings["delay_seconds"], settings.get("site_delays"))

    collected = area.collect(buildings, files.load(AREA, {}), get, files.today(), files.now(),
                             parts=(args.only,) if args.only else area.PARTS)
    files.save(AREA, collected)
    print(f"{len(collected.get('tracts', {}))} tracts, crime counts for {len(collected.get('crime', {}))} buildings in "
          f"{len(collected.get('crime_counties', []))} counties, rent trends for {len(collected.get('zips', {}))} ZIP codes")


if __name__ == "__main__":
    main()
