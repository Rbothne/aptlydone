"""Area data around the buildings: census figures per tract, reported crime nearby, and the ZIP rent trend.

It changes slowly, so it is collected weekly into data/area.json, apart from the twice-daily unit reads.
Every part is optional: a source that fails leaves what was collected before in place.
"""

import concurrent.futures
import re
import time

from . import affordable, census, crime, noise, places, rents, works

PARTS = ("census", "crime", "rents", "affordable", "places", "noise", "works")


def zip_code(building):
    """A building's 5-digit ZIP code: the one in its own address; failing that the one the Census Bureau gives for
    the address; failing that the one looked up from its coordinates.

    An audit on 2026-11-19 found the published ZIP agreed with the Census Bureau every time both were usable
    (444 of 444), while the ZIP looked up from coordinates was wrong for 246 of 564 buildings. Some managers put
    the street number where the ZIP belongs, so a published ZIP is believed only when it could be one here:
    every ZIP code in DC, Maryland and Virginia starts with 2.
    """
    address = building.get("address") or {}
    match = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", address.get("zip") or address.get("full") or "")
    if match and match.group(1).startswith("2"):
        return match.group(1)
    return (building.get("placed") or {}).get("zip") or building.get("zip") or None


def collect(buildings, previous, get, today, now, parts=PARTS, post=None, sleep=time.sleep):
    """Area data for these (in-region) buildings, starting from what was collected before."""
    area = dict(previous or {})

    # what is looked up once per place (walkability, noise) is forgotten for a building that has moved
    at = dict(area.get("at") or {})
    for building in buildings:
        if building.get("lat") is None or building.get("lon") is None:
            continue
        here = [building["lat"], building["lon"]]
        if at[building["id"]] != here if building["id"] in at else "site_lat" in building:
            for cache in ("walk", "noise"):
                if building["id"] in (area.get(cache) or {}):
                    area[cache] = {key: value for key, value in area[cache].items() if key != building["id"]}
        at[building["id"]] = here
    area["at"] = at

    if "census" in parts:
        counties = sorted({b["county"] for b in buildings if b.get("county")})
        tracts = census.read(counties, get, wanted={b["tract"] for b in buildings if b.get("tract")})
        if tracts:
            area["tracts"] = tracts

    if "crime" in parts:
        counts, covered = dict(area.get("crime") or {}), set(area.get("crime_counties") or [])
        geocache = area.setdefault("geocache", {})

        def one(county):
            """{building id: counts} for one county, or None when its source could not be read."""
            reader = crime.SOURCES[county]
            mine = [b for b in buildings if b.get("county") == county]
            start, end = crime.FROZEN.get(county, (crime.year_ago(today), today))
            try:
                if county in crime.NEEDS_PLACING:
                    incidents = reader(get, start, end, post=post, cache=geocache)
                elif county in crime.NEEDS_POST:
                    incidents = reader(get, start, end, post=post)
                else:
                    incidents = reader(get, start, end)
                found = crime.near(mine, incidents)
            except Exception as error:
                print(f"  no crime data for county {county} this time: {error!r}")
                return None
            if county in crime.FROZEN:                  # say which year these counts are from
                for tally in found.values():
                    tally["period"] = [start, end]
            print(f"  county {county}: {len(incidents)} incidents in 12 months, {len(mine)} buildings")
            return found

        # every county has its own source, so they are all asked at once, each at its own pace
        wanted = [county for county in crime.SOURCES if any(b.get("county") == county for b in buildings)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(wanted))) as pool:
            for county, found in zip(wanted, pool.map(one, wanted)):
                if found is not None:
                    counts.update(found)
                    covered.add(county)
        area["crime"], area["crime_counties"] = counts, sorted(covered)

    if "rents" in parts:
        try:
            trends = rents.read(get, {zip_code(b) for b in buildings} - {None})
        except Exception as error:
            print(f"  no rent trend this time: {error!r}")
            trends = None
        if trends:
            area["zips"] = trends

    if "affordable" in parts:
        mine = [b for b in buildings if b.get("county") == "11001"]
        if mine:
            try:
                area["affordable"] = affordable.match(mine, affordable.dc(get))
                print(f"  {len(area['affordable'])} DC buildings stand on an affordable-housing project")
            except Exception as error:
                print(f"  no affordable-housing list this time: {error!r}")

    if "places" in parts:
        placed = [b for b in buildings if b.get("lat") is not None and b.get("lon") is not None]
        if placed:
            fresh = places.near(placed, places.fetch_all(get, places.bbox(placed), places.states(placed), sleep=sleep))
            before = area.get("places") or {}
            # a kind of place that could not be read this week keeps last week's numbers
            area["places"] = {building_id: {**(before.get(building_id) or {}), **mine} for building_id, mine in fresh.items()}
            walk = dict(area.get("walk") or {})
            for building in placed:
                if building["id"] in walk:
                    continue
                try:
                    walk[building["id"]] = places.walkability(get, building["lat"], building["lon"])
                except Exception as error:
                    print(f"  no walkability for {building['id']}: {error!r}")
            area["walk"] = walk

    if "noise" in parts:                      # the noise map is a 2020 model: a building is looked up once
        known = dict(area.get("noise") or {})
        fresh = [b for b in buildings if len(known.get(b["id"]) or {}) < len(noise.LAYERS)]
        if fresh:
            for building_id, levels in noise.read(get, fresh).items():
                known[building_id] = {**(known.get(building_id) or {}), **levels}
        area["noise"] = known

    if "works" in parts:
        mine = [b for b in buildings if b.get("county") in works.COUNTIES]
        if mine:
            try:
                area["works"] = works.near(mine, works.permits(get, today), today)
                area["works_counties"] = list(works.COUNTIES)
                print(f"  construction: {sum(1 for w in area['works'].values() if w['next'])} buildings with a site next door, "
                      f"{sum(1 for w in area['works'].values() if w['here'])} with big work on their own lot")
            except Exception as error:
                print(f"  no building permits this time: {error!r}")

    area["updated"] = now
    return area
