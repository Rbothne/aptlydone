"""Which buildings are income-restricted housing, from DC's public list of affordable-housing projects.

Managers rarely label these, and they would otherwise look like the best deals on the page. A building that sits
on a completed project where at least half the units are affordable is treated as income-restricted.
The list covers projects since 2015, in DC only; elsewhere, and for older buildings, the "check price" rule
in deals.py is the fallback.
"""

import json
import math

DC = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/FeatureServer/62"
SAME_PLACE_METRES = 60
MOSTLY = 0.5
MAX_PAGES = 50


def projects(page):
    found = []
    for feature in page.get("features") or []:
        a = feature.get("attributes") or {}
        if a.get("LATITUDE") is None or a.get("LONGITUDE") is None or not a.get("TOTAL_AFFORDABLE_UNITS"):
            continue
        if (a.get("STATUS_PUBLIC") or "").lower().startswith(("pipeline", "under")):       # not built yet
            continue
        total = a.get("UNITS_TOTAL")
        found.append({"name": (a.get("PROJECT_NAME") or "").strip(), "lat": a["LATITUDE"], "lon": a["LONGITUDE"],
                      "affordable": round(a["TOTAL_AFFORDABLE_UNITS"]), "total": round(total) if total else None})
    return found


def dc(get, max_pages=MAX_PAGES):
    found, offset = [], 0
    for _ in range(max_pages):
        page = json.loads(get(f"{DC}/query?where=1%3D1&outFields=PROJECT_NAME,LATITUDE,LONGITUDE,TOTAL_AFFORDABLE_UNITS,UNITS_TOTAL,STATUS_PUBLIC"
                              f"&returnGeometry=false&orderByFields=OBJECTID&resultOffset={offset}&resultRecordCount=1000&f=json"))
        features = page.get("features") or []
        if not features:
            break
        found += projects(page)
        offset += len(features)
    else:
        raise RuntimeError(f"DC's affordable housing list did not end after {max_pages} pages")
    return found


def metres(a, b):
    dy = (a["lat"] - b["lat"]) * 111_320.0
    dx = (a["lon"] - b["lon"]) * 111_320.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


def match(buildings, found, within=SAME_PLACE_METRES):
    """{building id: {"name", "affordable", "total"}} for buildings standing on a project (the closest one wins)."""
    matched = {}
    for building in buildings:
        if building.get("lat") is None or building.get("lon") is None:
            continue
        near = [(metres(building, project), project) for project in found]
        near = [pair for pair in near if pair[0] <= within]
        if near:
            project = min(near, key=lambda pair: pair[0])[1]
            matched[building["id"]] = {"name": project["name"], "affordable": project["affordable"], "total": project["total"]}
    return matched


def mostly(project):
    """Is at least half of this building income-restricted, going by the project matched to it?"""
    if not project or not project.get("affordable"):
        return False
    return not project.get("total") or project["affordable"] >= MOSTLY * project["total"]
