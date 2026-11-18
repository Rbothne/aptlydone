"""Census figures per tract (American Community Survey, 5-year), through Census Reporter, which needs no key.

Per tract: population, median household income, median rent, median age, share of adults with a degree,
share of homes rented, and race and ethnicity as shares of the population.
"""

import json

API = "https://api.censusreporter.org/1.0/data/show/latest"
TABLES = ("B01003", "B19013", "B25064", "B01002", "B15003", "B03002", "B25003")


def url(county):
    """Every tract in one county (5-digit FIPS)."""
    return f"{API}?table_ids={','.join(TABLES)}&geo_ids=140%7C05000US{county}"


def share(part, whole):
    return round(part * 100 / whole) if part is not None and whole else None


def parse(payload):
    """{tract GEOID: figures} from one answer."""
    tracts = {}
    for geo_id, tables in (payload.get("data") or {}).items():
        def value(column):
            number = ((tables.get(column[:6]) or {}).get("estimate") or {}).get(column)
            return number if isinstance(number, (int, float)) and number >= 0 else None

        def whole(column):
            number = value(column)
            return None if number is None else round(number)

        people = value("B03002001")
        race = None
        if people:
            named = {"white": share(value("B03002003"), people), "black": share(value("B03002004"), people),
                     "asian": share(value("B03002006"), people), "hispanic": share(value("B03002012"), people)}
            if None not in named.values():
                race = dict(named, other=max(0, 100 - sum(named.values())))
        graduates = [value(f"B15003{n:03d}") for n in (22, 23, 24, 25)]
        tracts[geo_id.split("US")[-1]] = {
            "pop": whole("B01003001"),
            "income": whole("B19013001"),
            "rent": whole("B25064001"),
            "age": value("B01002001"),
            "degree": share(sum(graduates), value("B15003001")) if None not in graduates else None,
            "renters": share(value("B25003003"), value("B25003001")),
            "race": race,
        }
    return tracts


def read(counties, get, wanted=None):
    """Figures for the tracts in `wanted` (or all) across `counties`. A county that fails is skipped."""
    tracts = {}
    for county in counties:
        try:
            found = parse(json.loads(get(url(county))))
        except Exception as error:
            print(f"  no census figures for county {county}: {error!r}")
            continue
        tracts.update({tract: figures for tract, figures in found.items() if wanted is None or tract in wanted})
    return tracts
