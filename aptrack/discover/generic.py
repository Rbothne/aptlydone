"""A company described by one line in managers.json, with no code of its own:

    {"name": "Example Living", "site": "www.example.com", "discover": "generic",
     "sitemap": "https://www.example.com/sitemap.xml",          (one address or a list)
     "pattern": "https://www\\\\.example\\\\.com/apartments/(?:va|md|dc)/[^/<\\\\s]+/[^/<\\\\s]+",
     "map_paths": ["", "/floorplans"]}

It works for any company whose building pages describe themselves in schema.org data (name, street address)
and embed a SightMap unit map on the page or on one of the listed sub-pages. A building with no map found
becomes a plain link.
"""

import re

from .. import fetch
from . import common

DEFAULT_PATHS = ("", "/floorplans", "/floor-plans")


def building_urls(sitemap_xml, pattern):
    found = re.findall(r"<loc>\s*(" + pattern + r")\s*</loc>", sitemap_xml)
    return list(dict.fromkeys(url if isinstance(url, str) else url[0] for url in found))


def discoverer(config):
    """A discover(get, limit=None) function for one managers.json line."""
    sitemaps = config["sitemap"] if isinstance(config["sitemap"], list) else [config["sitemap"]]
    paths = config.get("map_paths") or DEFAULT_PATHS

    def discover(get, limit=None):
        urls = []
        for sitemap in sitemaps:
            urls += building_urls(get(sitemap).decode("utf-8", "replace"), config["pattern"])
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
                found.append(common.building(config["name"], url.rstrip("/").rsplit("/", 1)[1], url, described, embed))
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  skipped {url}: {error!r}")
        return found
    return discover


discoverer.needs_config = True          # tells discovery.run_all to build it from the managers.json line
