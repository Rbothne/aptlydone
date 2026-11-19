"""Equity Residential: its Washington-area page embeds the whole list of buildings there, with name, address
and coordinates, so discovery is a single request."""

from .. import fetch
from ..readers import ReadError
from ..readers.equity import assigned
from . import common

SITE = "https://www.equityapartments.com"
MARKET = SITE + "/washington-dc-apartments"
MANAGER = "Equity Residential"


def parse(market_html):
    listed = ((assigned(market_html, "srp").get("MetroArea") or {}).get("Properties")) or []
    found = []
    for record in listed:
        path = record.get("Url") or ""
        if not path.startswith("/") or record.get("State") not in common.REGION_STATES:     # other companies' buildings are advertised here too
            continue
        where = record.get("Coordinates") or {}
        described = {
            "name": record.get("Name"),
            "address": {"street": record.get("Address"), "city": record.get("City"), "state": record.get("State"), "zip": record.get("Zip")},
            "lat": common.number(where.get("Latitude")),
            "lon": common.number(where.get("Longitude")),
        }
        entry = common.building(MANAGER, path.rstrip("/").rsplit("/", 1)[1], SITE + path, described, None)
        entry.update(platform="equity", feed=SITE + path)
        found.append(entry)
    return found


def discover(get, limit=None):
    """Every Equity building in DC, Maryland and Virginia."""
    try:
        found = parse(get(MARKET).decode("utf-8", "replace"))
    except ReadError as error:
        raise fetch.RateLimited(f"{MARKET} came back without its list of buildings") from error
    if not found:
        raise fetch.RateLimited(f"{MARKET} listed no buildings")
    return found[:limit]
