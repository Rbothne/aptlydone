"""A company described by one line in managers.json, with no code of its own:

    {"name": "Example Living", "site": "www.example.com", "discover": "generic",
     "sitemap": "https://www.example.com/sitemap.xml",          (one address or a list)
     "pattern": "https://www\\\\.example\\\\.com/apartments/(?:va|md|dc)/[^/<\\\\s]+/[^/<\\\\s]+",
     "map_paths": ["", "/floorplans"]}

In place of "sitemap" a line may give "list": one page (or several) whose links to building pages are followed,
for a company whose sitemap covers the whole country but which has a page for this region.
"name_from_slug": true names each building from the last part of its page address, for a company whose pages
give a marketing title where the name should be.
"place_type": "ApartmentComplex" takes the place from that kind of schema.org object only (a page that also
describes the company's own office first).
"appfolio": "https://<company>.appfolio.com/listings" reads every building's apartments from the company's
AppFolio listing page, matched by street address.
"own_site": true (or a regular expression whose first group is the address) follows the company page's link
to the building's own website and looks there for its listings, when the company page has none.

Any listing system a reader exists for is recognised on the pages looked at (common.recognise), not only SightMap.

It works for any company whose building pages describe themselves in schema.org data (name, street address)
and embed a SightMap unit map on the page or on one of the listed sub-pages. A building with no map found
becomes a plain link.
"""

import re
from urllib.parse import urljoin

from .. import fetch
from . import common

DEFAULT_PATHS = ("", "/floorplans", "/floor-plans")


def building_urls(sitemap_xml, pattern):
    found = re.findall(r"<loc>\s*(" + pattern + r")\s*</loc>", sitemap_xml)
    return list(dict.fromkeys(url if isinstance(url, str) else url[0] for url in found))


def link_urls(page_html, base, pattern):
    """The building pages a list page links to: every link that, made absolute, matches the pattern exactly."""
    links = (urljoin(base, href) for href in re.findall(r'href="([^"#]+)"', page_html))
    return list(dict.fromkeys(url for url in links if re.fullmatch(pattern, url)))


def slug_name(slug, manager):
    """'maa-national-landing' -> 'MAA National Landing': the company's name keeps its own spelling."""
    return " ".join(manager if word == manager.lower() else word.capitalize() for word in slug.split("-") if word)


def tidy(address):
    """Some sites put the whole address in the street line and nine digits in the ZIP: keep the street and five."""
    street, city = address.get("street") or "", address.get("city") or ""
    if city and f", {city}" in street:
        street = street.split(f", {city}")[0].strip()
    code = str(address.get("zip") or "")
    return dict(address, street=street or address.get("street"), zip=code[:5] if code[:5].isdigit() else address.get("zip"))


def several(value):
    return value if isinstance(value, list) else [value] if value else []


def discoverer(config):
    """A discover(get, limit=None) function for one managers.json line."""
    sitemaps, lists = several(config.get("sitemap")), several(config.get("list"))
    paths = config.get("map_paths") or DEFAULT_PATHS

    def discover(get, limit=None):
        urls = []
        for sitemap in sitemaps:
            urls += building_urls(get(sitemap).decode("utf-8", "replace"), config["pattern"])
        for page in lists:
            urls += link_urls(get(page).decode("utf-8", "replace"), page, config["pattern"])
        found, watch = [], common.Watch()
        for url in list(dict.fromkeys(urls))[:limit]:
            try:
                page = get(url).decode("utf-8", "replace")
                described = common.place(page, kinds=several(config.get("place_type")) or None)
                if not described:
                    watch.miss(url)
                    continue
                watch.ok()
                if described["address"]["state"] not in common.REGION_STATES:
                    continue
                described["address"] = tidy(described["address"])
                listing = None
                if config.get("appfolio"):              # the company lists every apartment on one AppFolio page
                    listing = ("appfolio", f"{config['appfolio']}#{described['address']['street']}")
                for path in [] if listing else paths:
                    address = url if path == "" else url.rstrip("/") + path
                    try:
                        html = page if path == "" else get(address).decode("utf-8", "replace")
                    except fetch.RateLimited:
                        raise
                    except Exception:
                        continue
                    listing = common.recognise(address, html)
                    if listing:
                        break
                platform, feed = listing or ("link", None)
                slug = url.rstrip("/").rsplit("/", 1)[1]
                if config.get("name_from_slug"):
                    described["name"] = slug_name(slug, config["name"])
                if platform == "link" and config.get("own_site"):           # the company page links the building's own site
                    own = common.own_link(page, config["own_site"])
                    if own:
                        platform, feed = common.site_feed(get, own)
                found.append(common.building(config["name"], slug, url, described, feed, platform))
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  skipped {url}: {error!r}")
        return found
    return discover


discoverer.needs_config = True          # tells discovery.run_all to build it from the managers.json line
