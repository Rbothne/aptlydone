"""What most managers' building pages have in common: a structured description of the place, and a unit map."""

import json
import re
from urllib.parse import urljoin, urlsplit

from .. import fetch
from ..readers import g5, jonah, offers, rentcafe, rentpress

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


VISIT = re.compile(r"""<a\b[^>]*href=["'](https?://[^"']+)["'][^>]*>(?:(?!</a>).){0,300}?"""
                   r"""(?:visit|property|community|building)\s+(?:our\s+)?(?:web)?site""", re.I | re.S)


def own_link(page_html, pattern=True):
    """The building's own website as linked from a company's page about it: the first match of `pattern` (a
    regular expression whose first group is the address), or with `True`, a link reading "Visit website"."""
    if isinstance(pattern, str):
        match = re.search(pattern, page_html or "")
    else:
        match = VISIT.search(page_html or "")
    return match.group(1).replace("&amp;", "&") if match else None


def found_on(own, site):
    """(platform, feed) from what a building's website was found to hold: either site_feed's answer already,
    or the html of one of its pages."""
    if isinstance(site, tuple):
        return site
    return recognise(own, site) or ("link", None)


def building(manager, slug, url, described, feed, platform=None):
    """A building entry in the shape discovery produces. The id carries the manager's name once."""
    prefix = re.sub(r"[^a-z0-9]+", "-", manager.lower()).strip("-") + "-"       # "B.F. Saul" -> "b-f-saul-"
    entry = {
        "id": slug if slug.startswith(prefix) else prefix + slug,
        "manager": manager,
        "name": described["name"],
        "url": url,
        "platform": platform or ("sightmap" if feed else "link"),
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


UNIT_LEVEL = ("sightmap", "jonah", "g5", "offers", "rentcafe")                  # sources that price each apartment
LISTING_PATH = re.compile(r"floor|avail|apartments/?$|units|pricing", re.I)
SITE_PAGES = 7                                                     # pages looked at on one building's website, at most


def recognise(url, page_html):
    """(platform, feed) for the first listing system a building website's page uses, or None.

    The feed is what that system's reader is given: the SightMap embed for a unit map, else the page itself."""
    embed = sightmap_embed(page_html)
    if embed:
        return "sightmap", embed
    if url is None:
        return None
    if rentcafe.is_floor_plans(page_html):
        return "rentcafe", url
    if jonah.page_data(page_html) is not None:
        return "jonah", url
    widget = g5.config(page_html)
    if widget:
        if (widget.get("sightmapID") or "").strip():
            return "sightmap", f"https://sightmap.com/embed/{widget['sightmapID'].strip()}"
        return "g5", url
    if offers.plan_links(page_html, url) or offers.has_offers(page_html):
        return "offers", url
    if rentpress.FLOORPLANS.search(page_html or ""):
        return "rentpress", url
    return None


def listing_links(page_html, page_url):
    """Links on a building website's page to its own floor-plans or availability pages."""
    host = urlsplit(page_url).netloc.lower()
    out = []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', page_html or ""):
        link = urljoin(page_url, href.strip())
        parts = urlsplit(link)
        if parts.scheme in ("http", "https") and parts.netloc.lower() == host and LISTING_PATH.search(parts.path) \
                and not re.search(r"[${}]|%7B|%24", link) \
                and not re.search(r"\.(?:pdf|jpe?g|png|svg|css|js)$", parts.path, re.I) \
                and not PLAN_DETAIL.search(parts.path):
            out.append(link.split("?")[0])
    return list(dict.fromkeys(out))


PLAN_DETAIL = re.compile(r"/availability/[^/]+/[^/]+/[^/]+")       # one floor plan's page, not a list of them


def site_feed(get, own):
    """Where a building's own website lists its apartments: (platform, feed), or ("link", None) when no page
    looked at names a listing system this tracker reads.

    Looks at the floor-plans page first, then the home page, then the floor-plans and availability pages the
    site links to, and stops at the first that prices each apartment."""
    parts = urlsplit(own)
    base = f"{parts.scheme}://{parts.netloc}"
    queue, seen, best = [base + "/floorplans", base + "/floor-plans", own], set(), None
    while queue and len(seen) < SITE_PAGES:
        address = queue.pop(0)
        if address in seen:               # "/floorplans" and "/floorplans/" can be different pages (one a soft 404)
            continue
        seen.add(address)
        try:
            html = get(address).decode("utf-8", "replace")
        except fetch.RateLimited:
            raise
        except Exception:
            continue
        found = recognise(address, html)
        if found and found[0] in UNIT_LEVEL:
            return found
        best = best or found
        queue += [link for link in listing_links(html, address) if link not in seen and link not in queue]
        if address == own and base + "/availability" not in queue:
            queue.append(base + "/availability")
    return best or ("link", None)


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
