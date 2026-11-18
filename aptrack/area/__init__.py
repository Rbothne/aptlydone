"""Area data around the buildings: census figures per tract, reported crime nearby, and the ZIP rent trend.

It changes slowly, so it is collected weekly into data/area.json, apart from the twice-daily unit reads.
Every part is optional: a source that fails leaves what was collected before in place.
"""

import re

from . import affordable, census, crime, rents

PARTS = ("census", "crime", "rents", "affordable")


def zip_code(building):
    """A building's 5-digit ZIP code: the one looked up from its coordinates, else the one in its address.

    Some managers put the street number where the ZIP belongs, so an address ZIP is believed only when it
    could be one here: every ZIP code in DC, Maryland and Virginia starts with 2.
    """
    if building.get("zip"):
        return building["zip"]
    address = building.get("address") or {}
    match = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", address.get("zip") or address.get("full") or "")
    return match.group(1) if match and match.group(1).startswith("2") else None


def collect(buildings, previous, get, today, now, parts=PARTS):
    """Area data for these (in-region) buildings, starting from what was collected before."""
    area = dict(previous or {})

    if "census" in parts:
        counties = sorted({b["county"] for b in buildings if b.get("county")})
        tracts = census.read(counties, get, wanted={b["tract"] for b in buildings if b.get("tract")})
        if tracts:
            area["tracts"] = tracts

    if "crime" in parts:
        counts, covered = dict(area.get("crime") or {}), set(area.get("crime_counties") or [])
        for county, reader in crime.SOURCES.items():
            mine = [b for b in buildings if b.get("county") == county]
            if not mine:
                continue
            start, end = crime.FROZEN.get(county, (crime.year_ago(today), today))
            try:
                incidents = reader(get, start, end)
            except Exception as error:
                print(f"  no crime data for county {county} this time: {error!r}")
                continue
            found = crime.near(mine, incidents)
            if county in crime.FROZEN:                  # say which year these counts are from
                for tally in found.values():
                    tally["period"] = [start, end]
            counts.update(found)
            covered.add(county)
            print(f"  county {county}: {len(incidents)} incidents in 12 months, {len(mine)} buildings")
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

    area["updated"] = now
    return area
