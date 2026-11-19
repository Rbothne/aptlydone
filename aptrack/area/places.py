"""What is near each building, and how walkable its block is.

Nearby places are OpenStreetMap's, read from the state files Geofabrik publishes each day (see extract.py):
the two layers of places, as points and as outlines. Metro stations are the transit authority's own list.
Each building counts what is within half a mile and notes the nearest. Parks and other outlined places are
measured to their edge, not their middle, so living beside a big park counts. Walkability is the EPA's
National Walkability Index for the building's block group (1 to 20).

The public OpenStreetMap query servers (Overpass) are not used: they are often at capacity and ask automated
users to stay away.
"""

import json
import math
import re
import time
from urllib.parse import quote

from . import extract

GEOFABRIK = "https://download.geofabrik.de/north-america/us"
STATE_FILES = {                 # by state FIPS code, the first two digits of a county's
    "11": f"{GEOFABRIK}/district-of-columbia-latest-free.shp.zip",
    "24": f"{GEOFABRIK}/maryland-latest-free.shp.zip",
    "51": f"{GEOFABRIK}/virginia-latest-free.shp.zip",
}
LAYERS = ("gis_osm_pois_free_1", "gis_osm_pois_a_free_1")          # places as points, places as outlines
METRO = ("https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Transportation_Rail_Bus_WebMercator/MapServer/51/query"
         "?where=1%3D1&outFields=NAME&outSR=4326&f=json")           # "Metro Stations (Regional)"
EPA = "https://geodata.epa.gov/arcgis/rest/services/OA/WalkabilityIndex/MapServer/0/query"
NEAR_MILES = 0.5            # "nearby" for counting
FAR_MILES = 2.0             # beyond this the nearest one is not worth mentioning
PAUSE = 1                   # seconds between requests to the download server

CATEGORIES = ("park", "dog_park", "community", "library", "grocery", "metro", "food", "gym", "pharmacy")
KINDS = {                   # OpenStreetMap's kind of place -> the category it counts toward
    "park": "park", "dog_park": "dog_park", "community_centre": "community", "library": "library", "supermarket": "grocery",
    "restaurant": "food", "cafe": "food", "bar": "food", "pub": "food", "fitness_centre": "gym", "pharmacy": "pharmacy",
}
PET_AMENITY = re.compile(r"dog (run|park|wash|spa)|pet (spa|wash|park|grooming|salon)|bark park|paw wash", re.I)


def states(buildings):
    """The state codes the buildings are in, from their counties."""
    return sorted({building["county"][:2] for building in buildings if building.get("county")})


def bbox(buildings, margin=0.04):
    """(south, west, north, east) around the buildings, with a margin of a couple of miles."""
    placed = [b for b in buildings if b.get("lat") is not None and b.get("lon") is not None]
    return (round(min(b["lat"] for b in placed) - margin, 3), round(min(b["lon"] for b in placed) - margin, 3),
            round(max(b["lat"] for b in placed) + margin, 3), round(max(b["lon"] for b in placed) + margin, 3))


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


def overlaps(shape, box):
    return shape[2] >= box[0] and shape[0] <= box[2] and shape[3] >= box[1] and shape[1] <= box[3]


def metro(get):
    """Every Metro station as a point."""
    listed = json.loads(get(METRO)).get("features") or []
    found = [(f["geometry"]["y"], f["geometry"]["x"]) * 2 for f in listed if (f.get("geometry") or {}).get("x") is not None]
    if not found:
        raise ValueError("the station list came back empty")
    return found


def state_places(get, url, box, sleep=time.sleep):
    """{category: boxes} for the places of one state's file that lie inside `box`."""
    found = {category: [] for category in set(KINDS.values())}
    for layer in LAYERS:
        sleep(PAUSE)
        files = extract.members(get, url, [layer + ".shp", layer + ".dbf"])
        for kind, shape in extract.layer(files[layer + ".shp"], files[layer + ".dbf"]):
            if kind in KINDS and overlaps(shape, box):
                found[KINDS[kind]].append(shape)
    return found


def fetch_all(get, box, wanted_states, sleep=time.sleep):
    """{category: boxes} for what could be read. The OpenStreetMap categories come together or not at all: a
    state missing would make every building near its border look short of places."""
    found = {}
    try:
        found["metro"] = metro(get)
        print(f"  metro: {len(found['metro'])} stations")
    except Exception as error:
        print(f"  no Metro station list this time: {error!r}")
    try:
        places = {category: [] for category in set(KINDS.values())}
        for state in wanted_states:
            for category, shapes in state_places(get, STATE_FILES[state], box, sleep).items():
                places[category] += shapes
        found.update(places)
        print("  " + ", ".join(f"{category}: {len(places[category])}" for category in CATEGORIES if category in places))
    except Exception as error:
        print(f"  no OpenStreetMap places this time: {error!r}")
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
