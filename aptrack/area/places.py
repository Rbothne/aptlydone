"""What is near each building, and how walkable its block is.

Nearby places come from OpenStreetMap through the public Overpass service: one query per kind of place for the
whole region, then each building counts what is within half a mile and notes the nearest. Parks are measured to
their edge, not their middle, so living beside a big park counts. Walkability is the EPA's National
Walkability Index for the building's block group (1 to 20).
"""

import json
import math
import re
import time
from urllib.parse import quote

OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter")
EPA = "https://geodata.epa.gov/arcgis/rest/services/OA/WalkabilityIndex/MapServer/0/query"
NEAR_MILES = 0.5            # "nearby" for counting
FAR_MILES = 2.0             # beyond this the nearest one is not worth mentioning
PAUSE = 5                   # seconds between Overpass queries: it is a shared, free service

CATEGORIES = {
    "park": ('way["leisure"="park"]', 'relation["leisure"="park"]'),
    "dog_park": ('node["leisure"="dog_park"]', 'way["leisure"="dog_park"]', 'relation["leisure"="dog_park"]'),
    "community": ('node["amenity"="community_centre"]', 'way["amenity"="community_centre"]'),
    "library": ('node["amenity"="library"]', 'way["amenity"="library"]'),
    "grocery": ('node["shop"="supermarket"]', 'way["shop"="supermarket"]'),
    "metro": ('node["railway"="station"]["station"="subway"]',),
    "food": ('node["amenity"~"^(restaurant|cafe|bar|pub)$"]',),
    "gym": ('node["leisure"="fitness_centre"]', 'way["leisure"="fitness_centre"]'),
    "pharmacy": ('node["amenity"="pharmacy"]', 'way["amenity"="pharmacy"]'),
}
PET_AMENITY = re.compile(r"dog (run|park|wash|spa)|pet (spa|wash|park|grooming|salon)|bark park|paw wash", re.I)


def bbox(buildings, margin=0.04):
    """(south, west, north, east) around the buildings, with a margin of a couple of miles."""
    placed = [b for b in buildings if b.get("lat") is not None and b.get("lon") is not None]
    return (round(min(b["lat"] for b in placed) - margin, 3), round(min(b["lon"] for b in placed) - margin, 3),
            round(max(b["lat"] for b in placed) + margin, 3), round(max(b["lon"] for b in placed) + margin, 3))


def query(category, box):
    area = ",".join(str(n) for n in box)
    return "[out:json][timeout:120];(" + "".join(f"{selector}({area});" for selector in CATEGORIES[category]) + ");out tags bb;"


def shapes(payload):
    """Every place as a box (south, west, north, east); a point is a box of no size."""
    found = []
    for element in payload.get("elements") or []:
        if element.get("lat") is not None and element.get("lon") is not None:
            found.append((element["lat"], element["lon"], element["lat"], element["lon"]))
        elif element.get("bounds"):
            b = element["bounds"]
            found.append((b["minlat"], b["minlon"], b["maxlat"], b["maxlon"]))
        elif element.get("center"):
            c = element["center"]
            found.append((c["lat"], c["lon"], c["lat"], c["lon"]))
    return found


def miles_to(lat, lon, box):
    """Miles from a point to the nearest edge of a box; 0 when the point is inside it."""
    south, west, north, east = box
    dy = max(south - lat, 0, lat - north) * 69.0
    dx = max(west - lon, 0, lon - east) * 69.0 * math.cos(math.radians(lat))
    return math.hypot(dx, dy)


def near(buildings, found):
    """{building id: {category: [how many within half a mile, miles to the nearest or None]}}."""
    result = {}
    for building in buildings:
        if building.get("lat") is None or building.get("lon") is None:
            continue
        lat, lon = building["lat"], building["lon"]
        span = FAR_MILES / 69.0 + 0.001
        mine = {}
        for category, boxes in found.items():
            count, nearest = 0, None
            for box in boxes:
                if box[2] < lat - span or box[0] > lat + span:           # quick reject by latitude
                    continue
                distance = miles_to(lat, lon, box)
                if distance <= NEAR_MILES:
                    count += 1
                if distance <= FAR_MILES and (nearest is None or distance < nearest):
                    nearest = distance
            mine[category] = [count, None if nearest is None else round(nearest, 1)]
        result[building["id"]] = mine
    return result


def fetch_all(get, box, sleep=time.sleep):
    """{category: boxes} for every category that could be read. Each query tries the mirrors in turn."""
    found = {}
    for category in CATEGORIES:
        for endpoint in OVERPASS:
            try:
                payload = json.loads(get(f"{endpoint}?data={quote(query(category, box))}", timeout=180, tries=1))
            except Exception as error:
                print(f"  {category}: {endpoint.split('/')[2]} did not answer ({error!r})")
                continue
            found[category] = shapes(payload)
            print(f"  {category}: {len(found[category])} places")
            break
        sleep(PAUSE)
    return found


def walkability(get, lat, lon):
    """The EPA walkability index (1 least walkable to 20 most) for the block group a point is in, or None."""
    answer = json.loads(get(f"{EPA}?geometry={quote(f'{lon},{lat}')}&geometryType=esriGeometryPoint&inSR=4326"
                            f"&spatialRel=esriSpatialRelIntersects&outFields=NatWalkInd&returnGeometry=false&f=json"))
    features = answer.get("features") or []
    score = (features[0].get("attributes") or {}).get("NatWalkInd") if features else None
    return round(score, 1) if isinstance(score, (int, float)) else None


def walk_label(score):
    """The EPA's own four bands."""
    if score is None:
        return None
    if score > 15.25:
        return "Most walkable"
    if score > 10.5:
        return "Above average"
    if score > 5.75:
        return "Below average"
    return "Least walkable"


def dog_score(pets, features, nearby):
    """How good a building is for a dog, 1 to 5, with the reasons; None when it does not say pets are allowed.

    One point for allowing pets, two for a dog park within half a mile (one if within a mile), one for a park
    within a quarter mile, one for a dog run, pet spa or similar on site.
    """
    if pets is not True:
        return None
    nearby = nearby or {}
    score, reasons = 1, ["pets allowed"]
    dog_park = (nearby.get("dog_park") or [0, None])[1]
    if dog_park is not None and dog_park <= 1.0:
        score += 2 if dog_park <= 0.5 else 1
        reasons.append(f"dog park {dog_park} mi")
    park = (nearby.get("park") or [0, None])[1]
    if park is not None and park <= 0.25:
        score += 1
        reasons.append(f"park {park} mi")
    if any(PET_AMENITY.search(text or "") for text in features or []):
        score += 1
        reasons.append("pet amenities on site")
    return {"score": score, "reasons": reasons}
