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
from urllib.parse import quote

RADIUS_MILES = 0.5
DC_VIOLENT = {"HOMICIDE", "SEX ABUSE", "ASSAULT W/DANGEROUS WEAPON", "ROBBERY"}
DC_PROPERTY = {"BURGLARY", "THEFT/OTHER", "THEFT F/AUTO", "MOTOR VEHICLE THEFT", "ARSON"}
NIBRS_VIOLENT = {"09A", "09B", "11A", "11B", "11C", "11D", "120", "13A"}
NIBRS_PROPERTY_PREFIXES = ("200", "220", "23", "240")

DC_SERVICE = "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/MPD/FeatureServer"
MONTGOMERY = "https://data.montgomerycountymd.gov/resource/icn6-v9z3.json"
PRINCE_GEORGES = "https://data.princegeorgescountymd.gov/resource/xjru-idbe.json"      # "Crime Incidents July 2023 to Present"
FAIRFAX = "https://services9.arcgis.com/kYvfX7YK8OobHItA/arcgis/rest/services"          # Fairfax County Police open data
FAIRFAX_LAYERS = ("CrimesAgainstPerson_CST_FCPOD_FC", "CrimesAgainstProperty_CST_FCPOD_FC")
ARLINGTON = "https://datahub-v2.arlingtonva.us/api/Police/IncidentLog"
PG_VIOLENT = {"HOMICIDE", "SEX OFFENSE", "ASSAULT, SHOOTING", "ASSAULT, WEAPON"}
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


# ---------- Prince George's County, MD ----------

def classify_pg(kind):
    """The county's own incident types. A plain "ASSAULT" is left out: it does not say whether a weapon was involved."""
    if not kind:
        return None
    if kind in PG_VIOLENT or kind.startswith("ROBBERY"):
        return "violent"
    if kind in ("THEFT", "THEFT FROM AUTO") or kind.startswith(("AUTO, STOLEN", "B & E")):
        return "property"
    return None


def pg_incidents(rows):
    incidents = []
    for row in rows:
        kind = classify_pg(row.get("clearance_code_inc_type"))
        try:
            lat, lon = float(row.get("latitude")), float(row.get("longitude"))
        except (TypeError, ValueError):
            continue
        if kind and lat and lon and row.get("date"):
            incidents.append((lat, lon, kind, row["date"][:10]))
    return incidents


def prince_georges(get, start, today):
    incidents, offset, page_size = [], 0, 50000
    for _ in range(MAX_PAGES):
        rows = json.loads(get(f"{PRINCE_GEORGES}?$select=clearance_code_inc_type,latitude,longitude,date"
                              f"&$where=date%20%3E=%20'{start}T00:00:00'&$order=incident_case_id&$limit={page_size}&$offset={offset}"))
        incidents += pg_incidents(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return since(incidents, start)


# ---------- Fairfax County, VA ----------

def fairfax_incidents(page):
    incidents = []
    for feature in page.get("features") or []:
        a, point = feature.get("attributes") or {}, feature.get("geometry") or {}
        kind = classify_nibrs((a.get("IBRCode") or "").strip())
        if not kind or point.get("x") is None or point.get("y") is None or a.get("DateReported") is None:
            continue
        day = datetime.datetime.fromtimestamp(a["DateReported"] / 1000, datetime.timezone.utc).date().isoformat()
        incidents.append((point["y"], point["x"], kind, day))
    return incidents


def fairfax(get, start, today, max_pages=MAX_PAGES):
    """Fairfax County Police publish crimes against persons and against property as two map layers, coded by NIBRS."""
    where = quote(f"DateReported >= TIMESTAMP '{start} 00:00:00'")
    incidents = []
    for service in FAIRFAX_LAYERS:
        layer = json.loads(get(f"{FAIRFAX}/{service}/FeatureServer?f=json"))["layers"][0]["id"]
        offset = 0
        for _ in range(max_pages):
            page = json.loads(get(f"{FAIRFAX}/{service}/FeatureServer/{layer}/query?where={where}&outFields=IBRCode,DateReported"
                                  f"&outSR=4326&resultOffset={offset}&resultRecordCount={PAGE}&f=json"))
            features = page.get("features") or []
            if not features:
                break
            incidents += fairfax_incidents(page)
            offset += len(features)
        else:
            raise RuntimeError(f"Fairfax crime layer {service} did not end after {max_pages} pages")
    return since(incidents, start)


# ---------- Arlington County, VA ----------
# Arlington stopped publishing incidents with locations in June 2022 (its newer "Crime Data Hub" shows totals only).
# The last year it did publish is used, and labelled as such: old, but it still tells one block from another.

ARLINGTON_VIOLENT = ("ROBBERY", "CARJACK", "WOUNDING", "STRANGULATION", "MURDER", "MANSLAUGHTER", "HOMICIDE", "RAPE", "SODOMY",
                     "SEXUAL BATTERY", "OBJECT SEXUAL PENETRATION", "SHOOT")
ARLINGTON_PROPERTY = ("LARCENY", "BURGLARY", "ARSON", "UNAUTHORIZED USE OF VEHICLE")


def classify_arlington(text):
    text = (text or "").upper()
    if any(word in text for word in ARLINGTON_VIOLENT):
        return "violent"
    if any(word in text for word in ARLINGTON_PROPERTY):
        return "property"
    return None


def arlington_incidents(rows):
    incidents = []
    for row in rows:
        kind = classify_arlington(row.get("offenseDsc"))
        try:
            lat, lon = float(row.get("latitudeCrd")), float(row.get("longitudeCrd"))
        except (TypeError, ValueError):
            continue
        if kind and lat and lon and row.get("firstReportDtm"):
            incidents.append((lat, lon, kind, row["firstReportDtm"][:10]))
    return incidents


def arlington(get, start, today):
    rows = json.loads(get(f"{ARLINGTON}?$filter=firstReportDtm%20ge%20{start}T00:00:00.000Z&$top=50000"
                          f"&$select=offenseDsc,latitudeCrd,longitudeCrd,firstReportDtm", timeout=120))
    return [incident for incident in since(arlington_incidents(rows), start) if incident[3] <= today]


# ---------- Alexandria, VA: a search form and block addresses, in alexandria.py ----------

def alexandria(get, start, today, post=None, cache=None):
    from .. import geo
    from . import alexandria as source
    place = lambda addresses, known: geo.batch(addresses, "Alexandria", "VA", post, known)
    return source.incidents(get, start, today, place=place, cache=cache if cache is not None else {})


# county FIPS -> reader(get, start day, end day); a reader in NEEDS_PLACING also takes post= and cache= to geocode addresses
SOURCES = {"11001": dc, "24031": montgomery, "24033": prince_georges, "51059": fairfax, "51013": arlington, "51510": alexandria}
NEEDS_PLACING = {"51510"}
# Counties whose data has stopped: the fixed (start, end) their reader is asked for, shown beside their counts.
FROZEN = {"51013": ("2021-06-28", "2022-06-28")}


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
