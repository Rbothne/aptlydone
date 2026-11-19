"""Where a building is: census tract and county from the Census geocoder, a neighborhood name from OpenStreetMap."""

import json
from urllib.parse import quote

CENSUS = "https://geocoding.geo.census.gov/geocoder/geographies"
CENSUS_OPTIONS = "&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
CENSUS_BATCH = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 5000          # the service takes up to 10,000 addresses a request
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


def reverse(get, lat, lon):
    """What OpenStreetMap says about a point: {"neighborhood": name or None, "zip": 5 digits or None}."""
    address = json.loads(get(f"{NOMINATIM}?format=jsonv2&zoom=16&lat={lat}&lon={lon}")).get("address") or {}
    postcode = (address.get("postcode") or "")[:5]
    return {"neighborhood": pick_name(address), "zip": postcode if len(postcode) == 5 and postcode.isdigit() else None}


def neighborhood(get, lat, lon):
    """The neighborhood (or failing that the town) OpenStreetMap gives for a point."""
    return reverse(get, lat, lon)["neighborhood"]


def batch(addresses, city, state, post, cache):
    """Coordinates for many street addresses in one city: {address: (lat, lon)} for those that could be placed.

    `cache` maps "address, city, state" to [lat, lon] or None and is updated in place, so an address is only ever
    sent once (including the ones that cannot be placed). A failed request caches nothing.
    """
    import csv
    import io
    key = lambda address: f"{address}, {city}, {state}"
    new = sorted(address for address in set(addresses) if key(address) not in cache)
    for start in range(0, len(new), BATCH_SIZE):
        part = new[start:start + BATCH_SIZE]
        lines = io.StringIO()
        writer = csv.writer(lines, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for number, address in enumerate(part, 1):
            writer.writerow([number, address, city, state, ""])
        boundary = "----aptrack-geocode-batch"
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="benchmark"\r\n\r\nPublic_AR_Current\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="addressFile"; filename="addresses.csv"\r\n'
                f'Content-Type: text/csv\r\n\r\n{lines.getvalue()}\r\n--{boundary}--\r\n').encode("utf-8")
        try:
            answer = post(CENSUS_BATCH, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=300)
        except Exception as error:
            print(f"  could not place {len(part)} addresses this time: {error!r}")
            continue
        placed = {}
        for row in csv.reader(io.StringIO(answer.decode("utf-8", "replace"))):
            if len(row) >= 6 and row[2] == "Match" and "," in row[5]:
                lon, lat = row[5].split(",")
                placed[row[0]] = [float(lat), float(lon)]
        for number, address in enumerate(part, 1):
            cache[key(address)] = placed.get(str(number))
    return {address: tuple(cache[key(address)]) for address in set(addresses) if cache.get(key(address))}
