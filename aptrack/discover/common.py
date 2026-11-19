"""What most managers' building pages have in common: a structured description of the place, and a unit map."""

import json
import re
from urllib.parse import urlsplit

from .. import fetch

LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
SIGHTMAP_EMBED = re.compile(r"https:\\?/\\?/sightmap\.com\\?/embed\\?/(\w+)")
REGION_STATES = ("DC", "MD", "VA")


class Watch:
    """Notices a site that has stopped answering properly: page after page loads but lacks what it should hold
    (a block page, say). After LIMIT such pages in a row it raises, so the caller stops asking and the company
    is come back to later, instead of quietly concluding that the company has few buildings."""

    LIMIT = 4

    def __init__(self, limit=None):
        self.limit = limit or self.LIMIT
        self.misses = 0

    def ok(self):
        self.misses = 0

    def miss(self, url):
        self.misses += 1
        if self.misses >= self.limit:
            raise fetch.RateLimited(f"{self.misses} pages in a row without their data, last {url}")


def ld_nodes(page_html):
    """Every schema.org object embedded in a page."""
    for block in LD_JSON.findall(page_html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict):
                yield node


def number(value, kind=float):
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def place(page_html, kinds=None):
    """Name, address, coordinates and rating of the place a page describes; None when it describes none.

    `kinds` limits the search to those schema.org types; otherwise the first object with a street address wins.
    """
    for node in ld_nodes(page_html):
        address = node.get("address")
        if kinds and node.get("@type") not in kinds:
            continue
        if not kinds and not (isinstance(address, dict) and address.get("streetAddress")):
            continue
        address = address if isinstance(address, dict) else {}
        where = node.get("geo") if isinstance(node.get("geo"), dict) else {}
        rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
        return {
            "name": node.get("name"),
            "address": {"street": address.get("streetAddress"), "city": address.get("addressLocality"),
                        "state": address.get("addressRegion"), "zip": address.get("postalCode")},
            "lat": number(where.get("latitude", node.get("latitude"))),
            "lon": number(where.get("longitude", node.get("longitude"))),
            "features": [f["name"].strip() for f in node.get("amenityFeature") or []
                         if isinstance(f, dict) and isinstance(f.get("name"), str) and f["name"].strip()],
            "rating": number(rating.get("ratingValue")),
            "rating_count": number(rating.get("ratingCount") or rating.get("reviewCount"), int),
        }
    return None


def sightmap_embed(page_html):
    """The address of a SightMap unit map named in a page, or None."""
    for name in SIGHTMAP_EMBED.findall(page_html or ""):
        if name != "api":                      # sightmap.com/embed/api.js is the script, not a map
            return f"https://sightmap.com/embed/{name}"
    return None


def building(manager, slug, url, described, feed):
    """A building entry in the shape discovery produces. The id carries the manager's name once."""
    prefix = manager.lower().replace(" ", "-") + "-"
    entry = {
        "id": slug if slug.startswith(prefix) else prefix + slug,
        "manager": manager,
        "name": described["name"],
        "url": url,
        "platform": "sightmap" if feed else "link",
        "feed": feed,
        "address": described["address"],
        "lat": described["lat"],
        "lon": described["lon"],
    }
    if described.get("rating") is not None:
        entry.update(rating=described["rating"], rating_count=described.get("rating_count"))
    if described.get("features"):
        entry["features"] = described["features"]
    return entry


def own_site_html(get, own):
    """The page on a building's own website that names its unit map: usually the floor-plans page.
    Returns the first page that names one, else the last page fetched (or "" when none could be)."""
    parts = urlsplit(own)
    base = f"{parts.scheme}://{parts.netloc}"
    html = ""
    for address in (base + "/floorplans", base + "/floor-plans", own):
        try:
            html = get(address).decode("utf-8", "replace")
        except fetch.RateLimited:
            raise
        except Exception:
            continue
        if sightmap_embed(html):
            break
    return html
