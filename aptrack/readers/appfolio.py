"""AppFolio listing pages (`<company>.appfolio.com/listings`): one public page lists every apartment a company
has for rent, each with its address and unit number, rent, size, bedrooms and move-in date.

A building's feed is that page with the building's street address after a "#": the reader keeps the listings at
that address. The page is fetched once per run and shared by the company's buildings (AppFolio asks crawlers for
ten seconds between requests, and its whole list is one request)."""

import html as htmllib
import re
import threading
import time

from ..units import looks_restricted, make_unit, unique
from . import NotAnswering

ITEM = re.compile(r'<div class="listing-item result js-listing-item" id="listing_(\d+)">(.*?)(?=<div class="listing-item result js-listing-item"|<footer|\Z)', re.S)
FACT = re.compile(r'<dt class="detail-box__label">\s*([^<]+?)\s*</dt>\s*<dd class="detail-box__value[^"]*">\s*(.*?)\s*</dd>', re.S)
ADDRESS = re.compile(r'<span class="u-pad-rm js-listing-address">\s*(.*?)\s*</span>', re.S)
TITLE = re.compile(r'<h2 class="listing-item__title js-listing-title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)
CACHE_SECONDS = 1800

_cache, _lock = {}, threading.Lock()


def text(value):
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def street_key(street):
    """'1355 17th Street, NW' and '1355 17th St NW #204' -> '1355 17th'."""
    words = re.findall(r"[a-z0-9]+", (street or "").lower())
    return " ".join(words[:2])


def listings(page_html):
    """Every listing on the page: {"id", "address", "facts", "title", "link"}."""
    out = []
    for listing_id, body in ITEM.findall(page_html or ""):
        address = ADDRESS.search(body)
        title = TITLE.search(body)
        out.append({"id": listing_id, "address": text(address.group(1)) if address else "",
                    "facts": {text(k).lower(): text(v) for k, v in FACT.findall(body)},
                    "title": text(title.group(2)) if title else "", "link": title.group(1) if title else None})
    return out


def page(get, url):
    with _lock:
        hit = _cache.get(url)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    body = get(url).decode("utf-8", "replace")
    with _lock:
        _cache[url] = (time.monotonic(), body)
    return body


def available(value):
    """'NOW' -> None (the page means today; the history records the day it was seen); '12/15/26' -> '2026-12-15'."""
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})$", value or "")
    if not match:
        return None
    month, day, year = (int(x) for x in match.groups())
    return f"{year + 2000 if year < 100 else year:04d}-{month:02d}-{day:02d}"


def beds_baths(value):
    """'Studio / 1 ba' -> (0, 1); '2 bd / 1.5 ba' -> (2, 1.5)."""
    beds = 0 if re.search(r"studio", value or "", re.I) else (re.search(r"([\d.]+)\s*bd", value or "") or [None, None])[1]
    baths = (re.search(r"([\d.]+)\s*ba", value or "") or [None, None])[1]
    return beds, baths


def parse(page_html, building, base):
    if "js-listing-item" not in (page_html or "") and "listings" not in (page_html or ""):
        raise NotAnswering(f"{building['id']}: not an AppFolio listings page")
    street = building["feed"].split("#", 1)[1] if "#" in building["feed"] else (building.get("address") or {}).get("street")
    key = street_key(street)
    units = []
    for item in listings(page_html):
        if not key or street_key(item["address"]) != key:
            continue
        number = re.search(r"(?:#|unit\s+|apt\.?\s+)([A-Za-z0-9-]+)", item["address"], re.I)
        beds, baths = beds_baths(item["facts"].get("bed / bath"))
        unit = make_unit(
            building["id"], number.group(1) if number else item["id"],
            rent=item["facts"].get("rent"),
            beds=beds, baths=baths,
            sqft=item["facts"].get("square feet"),
            available=available(item["facts"].get("available")),
            special=item["title"] if re.search(r"special|off\b|free|deal|discount", item["title"], re.I) else None,
            url=base + item["link"] if item["link"] and item["link"].startswith("/") else item["link"] or building.get("url"),
            restricted=True if looks_restricted(item["title"]) else None,
        )
        if unit:
            units.append(unit)
    return {"units": unique(units), "fees": [], "amenities": []}


def read(building, get):
    url = building["feed"].split("#", 1)[0]
    base = re.match(r"https?://[^/]+", url).group(0)
    return parse(page(get, url), building, base)
