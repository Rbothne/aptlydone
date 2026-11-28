"""Google ratings: each building's star rating and review count on Google, refreshed weekly.

Uses Google's Places API (New) with the key in the GOOGLE_MAPS_KEY environment variable (a GitHub secret in the
scheduled runs). Without a key this part does nothing and the ratings collected before stay.

Two requests, billed differently:
- finding a building's place: a Text Search for its name and address, biased to its coordinates, asking only for the
  place's id, name and location (the "Pro" tier). Done once per building, again only if Google forgets the id or the
  building moves, and retried every RETRY_DAYS for a building no place was matched to.
- its rating: a Place Details request for that id asking for rating, review count and the place's Google Maps link
  (the "Enterprise" tier). Done every run, so weekly.

A search result is accepted only when it is close: within NEAR_METERS when its name shares a word with the building's,
within SAME_SPOT_METERS when it does not (an address search often returns the building under a different name).
"""

import datetime
import json
import re
import urllib.parse

from .. import deals

SEARCH = "https://places.googleapis.com/v1/places:searchText"
DETAILS = "https://places.googleapis.com/v1/places/"
SEARCH_FIELDS = "places.id,places.displayName,places.location"
DETAILS_FIELDS = "id,displayName,rating,userRatingCount,googleMapsUri"
NEAR_METERS = 300
SAME_SPOT_METERS = 100
RETRY_DAYS = 28
GIVE_UP_AFTER = 5           # requests failing in a row: the key is wrong or the API is not enabled; stop for this run
METERS_PER_MILE = 1609.344
FILLER = {"the", "at", "of", "on", "and", "apartments", "apartment", "apts", "residences", "residence", "homes",
          "living", "lofts", "flats", "tower", "towers", "place", "park", "street", "st", "avenue", "ave", "road", "rd"}


def words(name):
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in FILLER and len(w) > 1}


def query(building):
    address = building.get("address") or {}
    where = address.get("full") or ", ".join(p for p in (address.get("street"), address.get("city"),
                                                         " ".join(p for p in (address.get("state"), address.get("zip")) if p)) if p)
    return ", ".join(p for p in (building.get("name"), where) if p)


def pick(building, places):
    """The search result that is this building, or None."""
    best = None
    mine = words(building.get("name"))
    for place in places or []:
        spot = place.get("location") or {}
        if spot.get("latitude") is None or spot.get("longitude") is None:
            continue
        meters = deals.miles(building, {"lat": spot["latitude"], "lon": spot["longitude"]}) * METERS_PER_MILE
        named = bool(mine & words((place.get("displayName") or {}).get("text")))
        if meters <= (NEAR_METERS if named else SAME_SPOT_METERS):
            score = (not named, meters)
            if best is None or score < best[0]:
                best = (score, place)
    return best[1] if best else None


def find(get, key, building):
    """(place id, Google's name for it) for this building, or (None, None) when no result is close enough."""
    body = {"textQuery": query(building), "pageSize": 5}
    if building.get("lat") is not None and building.get("lon") is not None:
        body["locationBias"] = {"circle": {"center": {"latitude": building["lat"], "longitude": building["lon"]},
                                           "radius": 500.0}}
    answer = json.loads(get(SEARCH, data=json.dumps(body).encode(), tries=2, headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": SEARCH_FIELDS}))
    place = pick(building, answer.get("places"))
    return (place["id"], (place.get("displayName") or {}).get("text")) if place else (None, None)


def details(get, key, place_id):
    answer = json.loads(get(DETAILS + urllib.parse.quote(place_id, safe=""), tries=2, headers={
        "X-Goog-Api-Key": key, "X-Goog-FieldMask": DETAILS_FIELDS}))
    rating = answer.get("rating")
    return {"rating": round(rating, 1) if isinstance(rating, (int, float)) and rating > 0 else None,
            "count": answer.get("userRatingCount") if isinstance(answer.get("userRatingCount"), int) else None,
            "url": answer.get("googleMapsUri"), "name": (answer.get("displayName") or {}).get("text")}


class NeverRaised(Exception):
    """Stands in for `gone` when the caller has none."""


def refused(error):
    code = getattr(error, "code", None) or getattr(getattr(error, "__cause__", None), "code", None)
    return code in (400, 401, 403)


def collect(buildings, previous, get, key, today, gone=None):
    """{building id: {"place", "name", "rating", "count", "url", "at"}} starting from `previous`.

    `gone` is the exception a request raises when the address no longer exists (fetch.Gone): Google answers 404 for
    a place id it no longer knows, and the building is searched for again next run.
    """
    gone = gone or NeverRaised
    known = {k: dict(v) for k, v in (previous or {}).items()}
    failures, found, rated = 0, 0, 0
    for building in buildings:
        if failures >= GIVE_UP_AFTER:
            print(f"  Google refused {failures} requests in a row (is the key right, with the Places API (New) enabled?): "
                  "stopping, the rest keep what they had")
            break
        mine = known.get(building["id"]) or {}
        here = [building.get("lat"), building.get("lon")]
        if mine.get("near") and mine["near"] != here:             # moved: match it again
            mine = {}
        try:
            if not mine.get("place"):
                if mine.get("tried") and days_between(mine["tried"], today) < RETRY_DAYS:
                    continue
                place_id, name = find(get, key, building)
                mine = {"place": place_id, "name": name, "tried": today, "near": here}
                known[building["id"]] = mine
                failures = 0
                if not place_id:
                    continue
                found += 1
            fresh = details(get, key, mine["place"])
            failures = 0
            mine.update(rating=fresh["rating"], count=fresh["count"], url=fresh["url"], at=today)
            if fresh["name"]:
                mine["name"] = fresh["name"]
            known[building["id"]] = mine
            rated += fresh["rating"] is not None
        except gone:
            known[building["id"]] = {"tried": None, "near": here}  # Google forgot the place: search again next run
        except Exception as error:
            failures = failures + 1 if refused(error) else 0
            print(f"  no Google rating for {building['id']}: {error!r}")
    print(f"  Google: {found} buildings newly matched, {rated} ratings refreshed, "
          f"{sum(1 for v in known.values() if v.get('place'))} matched in all")
    return known


def days_between(day, today):
    return (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(day)).days
