"""Which units are priced unusually low: against their own building, against their neighbors, or both.

Everything compares true monthly cost per square foot between units with the same number of bedrooms and a
similar size. Income-restricted units, senior housing and single rooms are neither scored nor used as comparisons.
"""

import math
import statistics

BUILDING_STEAL = 15          # percent below similar units in the same building
LOCAL_VALUE = 20             # percent below similar units in nearby buildings
ABSOLUTE_OWN = 10            # ABSOLUTE STEAL needs both of these
ABSOLUTE_LOCAL = 15
SUSPECT_OWN = 30             # this far under its own building is "check the price", not a steal: usually an
                             # income-restricted unit the source did not label, or a data error
OWN_SIZE_BAND = 0.20         # "similar size" inside a building
LOCAL_SIZE_BAND = 0.15       # ...and across buildings, where layouts differ more
OWN_MIN = 3                  # similar units needed for a building comparison
LOCAL_MIN_UNITS = 5          # similar units needed for a neighbor comparison...
LOCAL_MIN_BUILDINGS = 3      # ...spread over at least this many other buildings
LOCAL_MILES = (1, 2)         # look within a mile first, then two
ROOM_SQFT = 300              # below this a "unit" is a room in a shared flat
RANK_MILES = 2               # a building is ranked against buildings this close
RANK_MIN_BUILDINGS = 3


def miles(a, b):
    """Great-circle distance between two things with "lat" and "lon"."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def is_senior(building):
    return "senior" in (building.get("name") or "").lower()


def comparable(unit, building):
    """Can this unit be scored, and be used to score others?"""
    return bool(unit.get("true") and unit.get("sqft") and unit["sqft"] >= ROOM_SQFT and unit.get("beds") is not None
                and not unit.get("restricted") and not is_senior(building))


def located(building):
    return building.get("lat") is not None and building.get("lon") is not None


def nearby(buildings, limit):
    """{building id: [(miles, other building id), ...]} for every pair within `limit` miles, nearest first."""
    placed = [b for b in buildings if located(b)]
    near = {b["id"]: [] for b in buildings}
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            distance = miles(a, b)
            if distance <= limit:
                near[a["id"]].append((distance, b["id"]))
                near[b["id"]].append((distance, a["id"]))
    for pairs in near.values():
        pairs.sort()
    return near


def percent(unit, others):
    """How far this unit's cost per sqft sits from the median of `others`, in percent to one decimal."""
    typical = statistics.median(other["true"] / other["sqft"] for other in others)
    return round((unit["true"] / unit["sqft"] / typical - 1) * 100, 1)


def tag_for(own, local):
    if own and own["pct"] <= -SUSPECT_OWN:
        return "check"
    if own and local and own["pct"] <= -ABSOLUTE_OWN and local["pct"] <= -ABSOLUTE_LOCAL:
        return "absolute"
    if own and own["pct"] <= -BUILDING_STEAL:
        return "building"
    if local and local["pct"] <= -LOCAL_VALUE:
        return "local"
    return None


def score(units, buildings):
    """Give every unit `own`, `local` and `tag` (each None when there is nothing fair to compare with)."""
    by_id = {b["id"]: b for b in buildings}
    usable = {}                                                       # building id -> its comparable units
    for unit in units:
        unit["own"] = unit["local"] = unit["tag"] = None
        building = by_id.get(unit["building"])
        if building and comparable(unit, building):
            usable.setdefault(unit["building"], []).append(unit)
    near = nearby(buildings, max(LOCAL_MILES))

    for building_id, mine in usable.items():
        for unit in mine:
            same = [o for o in mine if o is not unit and o["beds"] == unit["beds"]
                    and abs(o["sqft"] - unit["sqft"]) <= OWN_SIZE_BAND * unit["sqft"]]
            if len(same) >= OWN_MIN:
                unit["own"] = {"pct": percent(unit, same), "n": len(same)}

            for radius in LOCAL_MILES:
                around = [o for distance, other in near.get(building_id, []) if distance <= radius
                          for o in usable.get(other, [])
                          if o["beds"] == unit["beds"] and abs(o["sqft"] - unit["sqft"]) <= LOCAL_SIZE_BAND * unit["sqft"]]
                spread = len({o["building"] for o in around})
                if len(around) >= LOCAL_MIN_UNITS and spread >= LOCAL_MIN_BUILDINGS:
                    unit["local"] = {"pct": percent(unit, around), "n": len(around), "buildings": spread, "miles": radius}
                    break
            unit["tag"] = tag_for(unit["own"], unit["local"])


def rank(units, buildings):
    """Give every building `rank`: where its one-bedroom cost per sqft falls among buildings within two miles."""
    by_id = {b["id"]: b for b in buildings}
    costs = {}
    for unit in units:
        building = by_id.get(unit["building"])
        if building and unit.get("beds") == 1 and comparable(unit, building):
            costs.setdefault(unit["building"], []).append(unit["true"] / unit["sqft"])
    typical = {building_id: statistics.median(values) for building_id, values in costs.items()}
    near = nearby(buildings, RANK_MILES)
    for building in buildings:
        building["rank"] = None
        if building["id"] not in typical:
            continue
        peers = [typical[other] for _, other in near[building["id"]] if other in typical] + [typical[building["id"]]]
        if len(peers) >= RANK_MIN_BUILDINGS:
            at_or_below = sum(1 for value in peers if value <= typical[building["id"]])
            building["rank"] = {"pct": round(at_or_below * 100 / len(peers)), "n": len(peers)}
