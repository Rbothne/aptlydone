"""Reported crime near each building, from the open incident data each jurisdiction publishes.

One reader per county, each returning incidents as (lat, lon, "violent" | "property", day). Jurisdictions name and
count offences differently, so the two buckets are kept deliberately narrow and comparisons across a border
are approximate:
  violent:  homicide, sex offences, robbery, aggravated assault (with a weapon)
  property: burglary, theft, theft from a vehicle, vehicle theft, arson
"""

import datetime
import json
import math

RADIUS_MILES = 0.5
DC_VIOLENT = {"HOMICIDE", "SEX ABUSE", "ASSAULT W/DANGEROUS WEAPON", "ROBBERY"}
DC_PROPERTY = {"BURGLARY", "THEFT/OTHER", "THEFT F/AUTO", "MOTOR VEHICLE THEFT", "ARSON"}
NIBRS_VIOLENT = {"09A", "09B", "11A", "11B", "11C", "11D", "120", "13A"}
NIBRS_PROPERTY_PREFIXES = ("200", "220", "23", "240")

DC_SERVICE = "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/MPD/FeatureServer"
MONTGOMERY = "https://data.montgomerycountymd.gov/resource/icn6-v9z3.json"
PAGE = 2000
MAX_PAGES = 300          # far more than a year of incidents needs; beyond it something is wrong with the feed


def classify_dc(offence):
    if offence in DC_VIOLENT:
        return "violent"
    if offence in DC_PROPERTY:
        return "property"
    return None


def classify_nibrs(code):
    if not code:
        return None
    if code in NIBRS_VIOLENT:
        return "violent"
    if code.startswith(NIBRS_PROPERTY_PREFIXES):
        return "property"
    return None


def year_ago(day):
    date = datetime.date.fromisoformat(day)
    try:
        return date.replace(year=date.year - 1).isoformat()
    except ValueError:                                   # 29 February
        return date.replace(year=date.year - 1, day=28).isoformat()


def since(incidents, day):
    return [incident for incident in incidents if incident[3] >= day]


# ---------- Washington, DC ----------

def dc_incidents(payload):
    incidents = []
    for feature in payload.get("features") or []:
        a = feature.get("attributes") or {}
        kind = classify_dc(a.get("OFFENSE"))
        if not kind or a.get("LATITUDE") is None or a.get("LONGITUDE") is None or a.get("REPORT_DAT") is None:
            continue
        day = datetime.datetime.fromtimestamp(a["REPORT_DAT"] / 1000, datetime.timezone.utc).date().isoformat()
        incidents.append((a["LATITUDE"], a["LONGITUDE"], kind, day))
    return incidents


def dc(get, start, today, max_pages=MAX_PAGES):
    """DC publishes one layer per year: read the layers for the years the window touches."""
    layers = json.loads(get(DC_SERVICE + "?f=json")).get("layers") or []
    by_year = {layer["name"].rsplit(" ", 1)[-1]: layer["id"] for layer in layers if layer["name"].startswith("Crime Incidents - 2")}
    incidents = []
    for year in range(int(start[:4]), int(today[:4]) + 1):
        layer = by_year[str(year)]
        offset = 0
        for _ in range(max_pages):
            page = json.loads(get(f"{DC_SERVICE}/{layer}/query?where=1%3D1&outFields=OFFENSE,REPORT_DAT,LATITUDE,LONGITUDE"
                                  f"&returnGeometry=false&orderByFields=OBJECTID&resultOffset={offset}&resultRecordCount={PAGE}&f=json"))
            features = page.get("features") or []
            if not features:                    # the server caps a page at its own size, so only an empty page ends it
                break
            incidents += dc_incidents(page)
            offset += len(features)
        else:
            raise RuntimeError(f"DC crime layer {layer} did not end after {max_pages} pages")
    return since(incidents, start)


# ---------- Montgomery County, MD ----------

def montgomery_incidents(rows):
    incidents = []
    for row in rows:
        kind = classify_nibrs(row.get("nibrs_code"))
        try:
            lat, lon = float(row.get("latitude")), float(row.get("longitude"))
        except (TypeError, ValueError):
            continue
        if kind and lat and lon and row.get("start_date"):
            incidents.append((lat, lon, kind, row["start_date"][:10]))
    return incidents


def montgomery(get, start, today):
    incidents, offset, page_size = [], 0, 50000
    for _ in range(MAX_PAGES):
        rows = json.loads(get(f"{MONTGOMERY}?$select=nibrs_code,latitude,longitude,start_date"
                              f"&$where=start_date%20%3E=%20'{start}T00:00:00'&$order=incident_id&$limit={page_size}&$offset={offset}"))
        incidents += montgomery_incidents(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return since(incidents, start)


SOURCES = {"11001": dc, "24031": montgomery}          # county FIPS -> reader(get, start day, today)


# ---------- counting ----------

def near(buildings, incidents, miles=RADIUS_MILES):
    """{building id: {"violent": n, "property": n}} within `miles` of each building that has coordinates."""
    lat_span = miles / 69.0
    counts = {}
    for building in buildings:
        if building.get("lat") is None or building.get("lon") is None:
            continue
        lat, lon = building["lat"], building["lon"]
        lon_span = miles / (69.0 * math.cos(math.radians(lat)))
        tally = {"violent": 0, "property": 0}
        for i_lat, i_lon, kind, _ in incidents:
            if abs(i_lat - lat) > lat_span or abs(i_lon - lon) > lon_span:
                continue
            dy, dx = (i_lat - lat) * 69.0, (i_lon - lon) * 69.0 * math.cos(math.radians(lat))
            if dx * dx + dy * dy <= miles * miles:
                tally[kind] += 1
        counts[building["id"]] = tally
    return counts
