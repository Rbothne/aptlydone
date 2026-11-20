"""A company whose WordPress site publishes its buildings through the WordPress REST API (`/wp-json/wp/v2/<type>`),
each record giving the name, address, coordinates and the building's own website. One managers.json line:

    {"name": "Mill Creek", "site": "millcreekplaces.com", "discover": "wpjson",
     "api": "https://millcreekplaces.com/wp-json/wp/v2/community",
     "fields": {"name": "title.rendered", "street": "acf.street_address", "city": "acf.city", "state": "acf.state",
                "zip": "acf.zip_code", "lat": "acf.latitude", "lon": "acf.longitude", "website": "acf.community_url"}}

Each field names where it sits in a record, dotted. The building's own website is looked through for the listing
system it uses (common.site_feed)."""

import html as htmllib
import json

from .. import fetch
from . import common

STATES = {"district of columbia": "DC", "washington dc": "DC", "washington, dc": "DC", "dc": "DC",
          "maryland": "MD", "md": "MD", "virginia": "VA", "va": "VA"}
PAGE_SIZE = 100


def state_code(value):
    value = " ".join(str(value or "").split())
    return STATES.get(value.lower(), value.upper() if len(value) == 2 else value)


def pick(record, path):
    value = record
    for part in (path or "").split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return htmllib.unescape(value).strip() if isinstance(value, str) else value


def records(get, api):
    out, page = [], 1
    while True:
        joiner = "&" if "?" in api else "?"
        try:
            batch = json.loads(get(f"{api}{joiner}per_page={PAGE_SIZE}&page={page}"))
        except fetch.Gone:                      # WordPress answers past the last page with 400/404
            break
        except ValueError as error:
            raise fetch.RateLimited(f"{api} did not answer with JSON") from error
        if not isinstance(batch, list) or not batch:
            break
        out += batch
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return out


def discoverer(config):
    fields = config["fields"]

    def discover(get, limit=None):
        found = []
        for record in records(get, config["api"]):
            state = state_code(pick(record, fields.get("state")))
            if state not in common.REGION_STATES:
                continue
            if limit is not None and len(found) >= limit:
                break
            described = {
                "name": pick(record, fields.get("name", "title.rendered")),
                "address": {"street": pick(record, fields.get("street")), "city": pick(record, fields.get("city")),
                            "state": state, "zip": pick(record, fields.get("zip"))},
                "lat": common.number(pick(record, fields.get("lat"))),
                "lon": common.number(pick(record, fields.get("lon"))),
            }
            own = pick(record, fields.get("website"))
            if own and not own.startswith("http"):
                own = "https://" + own.lstrip("/")
            own = own.split("?")[0] if own else own           # tracking parameters off: the site's own address
            try:
                platform, feed = common.site_feed(get, own) if own else ("link", None)
            except fetch.RateLimited:
                raise
            except Exception as error:
                print(f"  {described['name']}: its website could not be read: {error!r}")
                platform, feed = "link", None
            page = record.get("link") or own
            found.append(common.building(config["name"], record.get("slug") or str(record.get("id")), own or page,
                                         described, feed, platform))
        return found
    return discover


discoverer.needs_config = True
