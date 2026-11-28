"""Collect the slow-changing data around the buildings: census figures, crime nearby, and ZIP rent trends.

    py area.py                 everything
    py area.py --only crime    one part: census, crime, rents, affordable, places, noise, works or google

Google ratings need a Google Maps key with the Places API (New) enabled, in the GOOGLE_MAPS_KEY environment variable.

Reads data/buildings.json and writes data/area.json. The next build.py run puts it on the page.
"""

import argparse
import os
import sys

from aptrack import area, companies, fetch, files, vpn

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
    config = files.load(os.path.join(ROOT, "managers.json"), None)
    settings = config["settings"]
    buildings = [b for b in companies.tracked(buildings, config["managers"]) if b.get("in_region")]
    get = fetch.polite(settings["delay_seconds"], settings.get("site_delays"), routes=vpn.routes())

    collected = area.collect(buildings, files.load(AREA, {}), get, files.today(), files.now(),
                             parts=(args.only,) if args.only else area.PARTS, post=fetch.post,
                             google_key=os.environ.get("GOOGLE_MAPS_KEY", "").strip() or None, gone=fetch.Gone)
    files.save(AREA, collected)
    print(f"{len(collected.get('tracts', {}))} tracts, crime counts for {len(collected.get('crime', {}))} buildings in "
          f"{len(collected.get('crime_counties', []))} counties, rent trends for {len(collected.get('zips', {}))} ZIP codes, "
          f"{len(collected.get('affordable', {}))} buildings on affordable-housing projects, "
          f"nearby places for {len(collected.get('places', {}))} buildings, walkability for {sum(1 for v in collected.get('walk', {}).values() if v is not None)}, "
          f"Google ratings for {sum(1 for v in collected.get('google', {}).values() if v.get('rating') is not None)}")


if __name__ == "__main__":
    main()
