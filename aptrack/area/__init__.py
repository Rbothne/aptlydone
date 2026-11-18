"""Area data around the buildings: census figures per tract, reported crime nearby, and the ZIP rent trend.

It changes slowly, so it is collected weekly into data/area.json, apart from the twice-daily unit reads.
Every part is optional: a source that fails leaves what was collected before in place.
"""

import re

from . import census, crime, rents

PARTS = ("census", "crime", "rents")


def zip_code(building):
    """A building's 5-digit ZIP code, from its address parts or the end of a one-line address."""
    address = building.get("address") or {}
    match = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", address.get("zip") or address.get("full") or "")
    return match.group(1) if match else None


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
            try:
                incidents = reader(get, crime.year_ago(today), today)
            except Exception as error:
                print(f"  no crime data for county {county} this time: {error!r}")
                continue
            counts.update(crime.near(mine, incidents))
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

    area["updated"] = now
    return area
