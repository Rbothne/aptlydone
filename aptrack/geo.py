"""Where a building is: census tract and county from the Census geocoder, a neighborhood name from OpenStreetMap."""

import json
from urllib.parse import quote

CENSUS = "https://geocoding.geo.census.gov/geocoder/geographies"
CENSUS_OPTIONS = "&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
NAME_KEYS = ("neighbourhood", "suburb", "quarter", "city_district", "town", "city")


def locate(get, *, lat=None, lon=None, address=None):
    """{"lat", "lon", "state", "county", "tract"} for coordinates or a one-line address; None when nothing matches."""
    if lat is not None and lon is not None:
        result = json.loads(get(f"{CENSUS}/coordinates?x={lon}&y={lat}{CENSUS_OPTIONS}"))["result"]
        geographies = result.get("geographies") or {}
    else:
        result = json.loads(get(f"{CENSUS}/onelineaddress?address={quote(address)}{CENSUS_OPTIONS}"))["result"]
        matches = result.get("addressMatches") or []
        if not matches:
            return None
        geographies = matches[0].get("geographies") or {}
        lat, lon = matches[0]["coordinates"]["y"], matches[0]["coordinates"]["x"]
    tracts = geographies.get("Census Tracts") or []
    if not tracts:
        return None
    states = geographies.get("States") or [{}]
    return {"lat": lat, "lon": lon, "state": states[0].get("STUSAB"),
            "county": tracts[0]["STATE"] + tracts[0]["COUNTY"], "tract": tracts[0]["GEOID"]}


def pick_name(address):
    return next((address[key] for key in NAME_KEYS if address.get(key)), None)


def neighborhood(get, lat, lon):
    """The neighborhood (or failing that the town) OpenStreetMap gives for a point."""
    answer = json.loads(get(f"{NOMINATIM}?format=jsonv2&zoom=14&lat={lat}&lon={lon}"))
    return pick_name(answer.get("address") or {})
