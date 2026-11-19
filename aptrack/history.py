"""Price history: what gets remembered each time a building is read.

state = {
  "version": 1,
  "units":     {unit id: {building, plan, beds, baths, sqft, available, first, last, gone,
                          points: [[day, rent, special, lease months, monthly fees]], past: [...]}},
  "plans":     {"<building id>|<plan>": {beds, points: [[day, lowest rent, median rent, units listed]]}},
  "buildings": {building id: {ok: day of last good read, failed: day of last failed read since then}},
}
"""

import datetime
import statistics

UNIT_KEEP_DAYS = 400      # a leased unit's record is kept this long, so next year's search can see this year's prices
SAVE_FLOOR = 0.8          # refuse to save a history with fewer than this share of the previous unit records
DROP_DAYS = 30            # a price drop is measured against the highest price that stood in this many days...
DROP_PCT = 2              # ...and has to be at least this many percent: pricing software moves prices a little every day


def new_state():
    return {"version": 1, "units": {}, "plans": {}, "buildings": {}}


def put(points, point):
    """Add `point` ([day, value...]) unless nothing changed; a second point on the same day replaces the first."""
    if points and points[-1][1:] == point[1:]:
        return
    if points and points[-1][0] == point[0]:
        points[-1] = point
        if len(points) > 1 and points[-2][1:] == point[1:]:
            points.pop()
    else:
        points.append(point)


def plan_key(building_id, unit):
    beds = "?" if unit["beds"] is None else unit["beds"]
    return f"{building_id}|{unit['plan'] or f'{beds} bed'}"


def whole(number):
    return int(number) if number == int(number) else number


def record(state, building_id, units, day):
    """A successful read of one building: `units` is everything it lists today."""
    known = state["units"]
    listed = set()
    for unit in units:
        listed.add(unit["id"])
        entry = known.get(unit["id"])
        if entry and entry["gone"]:
            entry["past"].append({key: entry[key] for key in ("first", "last", "gone", "points")})
            entry.update(first=day, gone=None, points=[])
        if not entry:
            entry = known[unit["id"]] = {"building": building_id, "first": day, "gone": None, "points": [], "past": []}
        entry.update(plan=unit["plan"], beds=unit["beds"], baths=unit["baths"], sqft=unit["sqft"],
                     available=unit.get("available"), last=day)
        put(entry["points"], [day, unit["rent"], unit["special"], unit.get("lease"), unit.get("fees")])

    for unit_id, entry in known.items():
        if entry["building"] == building_id and unit_id not in listed and not entry["gone"]:
            entry["gone"] = day

    by_plan = {}
    for unit in units:
        by_plan.setdefault(plan_key(building_id, unit), []).append(unit)
    for key, group in by_plan.items():
        rents = [unit["rent"] for unit in group]
        series = state["plans"].setdefault(key, {"beds": group[0]["beds"], "points": []})
        put(series["points"], [day, min(rents), whole(statistics.median(rents)), len(rents)])
    for key, series in state["plans"].items():
        if key.startswith(building_id + "|") and key not in by_plan:
            put(series["points"], [day, None, None, 0])

    status = state["buildings"].setdefault(building_id, {})
    status.update(ok=day, failed=None)
    status.pop("why", None)


def drop(points, today):
    """{"was", "by", "pct", "day"} when a unit's rent now is at least DROP_PCT below the highest it stood at in the
    last DROP_DAYS and its latest move was down; None otherwise. Only prices for the same lease length compare."""
    if not points:
        return None
    rent, lease = points[-1][1], points[-1][3]
    same = [p for p in points if p[3] == lease]
    since = len(same) - 1                                   # where the current rent began
    while since > 0 and same[since - 1][1] == rent:
        since -= 1
    if since == 0 or same[since - 1][1] <= rent:
        return None
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=DROP_DAYS)).isoformat()
    if same[since][0] < cutoff:
        return None
    stood = [p[1] for i, p in enumerate(same[:since]) if same[i + 1][0] >= cutoff]      # prices still up inside the window
    high = max(stood)
    pct = round((rent / high - 1) * 100, 1)
    return {"was": high, "by": high - rent, "pct": pct, "day": same[since][0]} if pct <= -DROP_PCT else None


def record_failure(state, building_id, day, why=None):
    """A failed read: remember that it failed (and why, in a few words), and leave every unit as it was."""
    building = state["buildings"].setdefault(building_id, {"ok": None, "failed": None})
    building["failed"] = day
    if why:
        building["why"] = why
    else:
        building.pop("why", None)


def record_special(state, building_id, text, day):
    """The building-wide concession text, kept as a dated series so past net rents can be worked out."""
    building = state["buildings"].setdefault(building_id, {"ok": None, "failed": None})
    series = building.setdefault("specials", [])
    if series or text:
        put(series, [day, text])


def retire(state, building_ids, day):
    """Units of buildings that are no longer tracked stop counting as listed."""
    for entry in state["units"].values():
        if entry["building"] not in building_ids and not entry["gone"]:
            entry["gone"] = day


def prune(state, day):
    cutoff = (datetime.date.fromisoformat(day) - datetime.timedelta(days=UNIT_KEEP_DAYS)).isoformat()
    for unit_id in [u for u, entry in state["units"].items() if entry["gone"] and entry["gone"] < cutoff]:
        del state["units"][unit_id]


def safe_to_save(before, after):
    """False when `after` has lost so many unit records that the run probably went wrong."""
    return len(after["units"]) >= SAVE_FLOOR * len(before["units"])
