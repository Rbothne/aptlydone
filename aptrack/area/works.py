"""Construction noise to expect: building sites beside a building, and big renovation inside it, read from the
District of Columbia's building permits (one map layer per year). Other counties are not covered yet.

A permit is counted when it is for a new building or for razing one, or for alteration or demolition work
big enough to have paid BIG_FEE in permit fees (the fee follows the cost of the work, so it is the only
measure of size the record has). A building site counts for two years from its permit, renovation for one.
"""

import datetime
import json
import re
from urllib.parse import urlencode

from ..deals import miles

SERVICE = "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/MapServer"
KINDS = {"NEW BUILDING": "New building", "RAZE": "Demolition", "DEMOLITION": "Demolition",
         "ALTERATION AND REPAIR": "Major work", "ADDITION ALTERATION REPAIR": "Major work"}
ALWAYS = ("NEW BUILDING", "RAZE")
BIG_FEE = 5000
SITE_DAYS, RENOVATION_DAYS = 730, 365
NEXT_MILES = 0.1            # about a block
HERE_MILES = 0.03           # the same lot
FIELDS = "PERMIT_SUBTYPE_NAME,ISSUE_DATE,LATITUDE,LONGITUDE,FEES_PAID,FULL_ADDRESS,DESC_OF_WORK"
COUNTIES = ("11001",)


def days_before(today, days):
    return (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()


def street(full_address):
    """"2250 8TH ST NW, WASHINGTON, DC 20001" -> "2250 8th St NW"."""
    first = (full_address or "").split(",")[0].strip()
    return " ".join(word if word in ("NW", "NE", "SW", "SE") else word.capitalize() if not word[:1].isdigit() else word.lower()
                    for word in first.split())


def layers(get, years):
    """{year: layer number} for the yearly permit layers."""
    listed = json.loads(get(SERVICE + "?f=json")).get("layers") or []
    found = {}
    for layer in listed:
        match = re.fullmatch(r"Building Permits - (\d{4})", layer.get("name") or "")
        if match and int(match.group(1)) in years:
            found[int(match.group(1))] = layer["id"]
    return found


def permits(get, today, page=2000):
    """Every counted permit issued in the last two years: [{kind, day, lat, lon, address, what}]."""
    start = days_before(today, SITE_DAYS)
    others = ", ".join(f"'{name}'" for name in KINDS if name not in ALWAYS)
    where = (f"PERMIT_TYPE_NAME = 'CONSTRUCTION' AND ISSUE_DATE >= DATE '{start}' AND "
             f"(PERMIT_SUBTYPE_NAME IN ({', '.join(repr(name) for name in ALWAYS)}) "
             f"OR (PERMIT_SUBTYPE_NAME IN ({others}) AND FEES_PAID >= {BIG_FEE}))")
    years = range(int(start[:4]), int(today[:4]) + 1)
    found = []
    for year, layer in sorted(layers(get, years).items()):
        offset = 0
        while True:
            query = urlencode({"where": where, "outFields": FIELDS, "returnGeometry": "false", "orderByFields": "OBJECTID",
                               "resultOffset": offset, "resultRecordCount": page, "f": "json"})
            reply = json.loads(get(f"{SERVICE}/{layer}/query?{query}"))
            if reply.get("error"):
                raise ValueError(f"permits {year}: {reply['error'].get('message')}")
            rows = reply.get("features") or []
            for row in rows:
                a = row["attributes"]
                if a.get("LATITUDE") is None or a.get("LONGITUDE") is None or a.get("ISSUE_DATE") is None:
                    continue
                day = datetime.datetime.fromtimestamp(a["ISSUE_DATE"] / 1000, datetime.timezone.utc).date().isoformat()
                found.append({"kind": KINDS.get(a.get("PERMIT_SUBTYPE_NAME"), "Major work"), "day": day,
                              "lat": float(a["LATITUDE"]), "lon": float(a["LONGITUDE"]), "address": street(a.get("FULL_ADDRESS")),
                              "what": " ".join((a.get("DESC_OF_WORK") or "").split())[:160]})
            offset += len(rows)
            if not rows or not reply.get("exceededTransferLimit"):
                break
    return found


def near(buildings, found, today):
    """{building id: {"next": building sites within a block, "here": big work on the building's own lot}}, nearest first.
    Several permits for one site are one entry: its latest."""
    site_from, renovation_from = days_before(today, SITE_DAYS), days_before(today, RENOVATION_DAYS)
    out = {}
    for building in buildings:
        if building.get("lat") is None or building.get("lon") is None:
            continue
        nearby, here = {}, {}
        for work in found:
            if abs(work["lat"] - building["lat"]) > 0.005 or abs(work["lon"] - building["lon"]) > 0.005:
                continue
            distance = miles(building, work)
            site = work["kind"] in ("New building", "Demolition")
            if work["day"] < (site_from if site else renovation_from):
                continue
            entry = dict(kind=work["kind"], day=work["day"], miles=round(distance, 2), address=work["address"], what=work["what"])
            if distance <= HERE_MILES:
                if work["kind"] != "New building":                 # a new-building permit on its own lot is the building itself
                    keep(here, entry)
            elif distance <= NEXT_MILES and site:
                keep(nearby, entry)
        order = lambda entry: (entry["miles"], entry["day"])
        out[building["id"]] = {"next": one_per_site(nearby, order), "here": one_per_site(here, order)}
    return out


def keep(sites, entry):
    """Remember `entry` for its address unless a later permit there is already kept; a building site outranks the rest."""
    rank = lambda e: (e["kind"] == "New building", e["day"])
    if entry["address"] not in sites or rank(entry) > rank(sites[entry["address"]]):
        sites[entry["address"]] = entry


def one_per_site(sites, order):
    return sorted(sites.values(), key=order)
