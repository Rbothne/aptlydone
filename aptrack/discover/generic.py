"""A company described by one line in managers.json, with no code of its own:

    {"name": "Example Living", "site": "www.example.com", "discover": "generic",
     "sitemap": "https://www.example.com/sitemap.xml",          (one address or a list)
     "pattern": "https://www\\\\.example\\\\.com/apartments/(?:va|md|dc)/[^/<\\\\s]+/[^/<\\\\s]+",
     "map_paths": ["", "/floorplans"]}

In place of "sitemap" a line may give "list": one page (or several) whose links to building pages are followed,
for a company whose sitemap covers the whole country but which has a page for this region.
"name_from_slug": true names each building from the last part of its page address, for a company whose pages
give a marketing title where the name should be.

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
                described = common.place(page)
                if not described:
                    watch.miss(url)
                    continue
                watch.ok()
                if described["address"]["state"] not in common.REGION_STATES:
                    continue
                embed = None
                for path in paths:
                    try:
                        html = page if path == "" else get(url.rstrip("/") + path).decode("utf-8", "replace")
                    except fetch.RateLimited:
                        raise
                    except Exception:
                        continue
                    embed = common.sightmap_embed(html)
                    if embed:
                        break
                slug = url.rstrip("/").rsplit("/", 1)[1]
                if config.get("name_from_slug"):
                    described["name"] = slug_name(slug, config["name"])
                found.append(common.building(config["name"], slug, url, described, embed))
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  skipped {url}: {error!r}")
        return found
    return discover


discoverer.needs_config = True          # tells discovery.run_all to build it from the managers.json line
