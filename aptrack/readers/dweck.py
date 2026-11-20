"""Dweck Properties' own site: a community's page lists every available apartment there as a row (its number,
its size, its square footage, the site's "Starting at" price and the day it is free), each linking to
`/availabilities/<unit>-<community number>`. One request reads a whole community.

The site's robots file asks for five minutes between requests (`site_delays`), so the communities are read a few
per run (`"spread"` in managers.json). Its terms discourage automated reading; read at the owner's instruction
(2026-11-20), under the tracker's own name.
"""

import html
import re

from ..units import looks_restricted, make_unit, unique
from . import NotAnswering

DETAILS = re.compile(r'id="property-details"')
ROW = re.compile(r'(?=<div class="listing\b)')
LINK = re.compile(r'href="(https://www\.dweckproperties\.com/availabilities/([^"/]+)/?)"')
LABEL = re.compile(r'class="list_title"[^>]*>\s*#?\s*([^<]+?)\s*<')
PLAN = re.compile(r"<h3[^>]*>\s*(.*?)\s*</h3>", re.S)
SQFT = re.compile(r'class="sqft"[^>]*>\s*([\d,]+)')
PRICE = re.compile(r"Starting at\s*\$\s?([\d,]+)")
FREE_ON = re.compile(r'class="list_avai"[^>]*>[^<]*?(\d{1,2})/(\d{1,2})/(\d{4})')
SOON = re.compile(r'<div[^>]*class="cssoo(?![^"]*hiddens)[^"]*"')
BEDS = re.compile(r"^\s*(studio|\d+)", re.I)
BATHS = re.compile(r"(\d+(?:\.\d)?)\s*baths?", re.I)
NUMBER = re.compile(r"-\d{5,}$")              # the community's number at the end of an apartment's address


def unit_label(slug):
    """'2203-1236434' -> '2203'; '56w-1713-1236434' -> '56w-1713'; '1812-431-' -> '1812-431'."""
    return NUMBER.sub("", slug.strip("-")).strip("-") or slug.strip("-")


def read(building, get):
    page = get(building["feed"]).decode("utf-8", "replace")
    if not DETAILS.search(page):
        raise NotAnswering(f"{building['id']}: {building['feed']} is not a community's page")
    units = []
    for row in ROW.split(page)[1:]:
        link = LINK.search(row)
        if not link:
            continue
        label = LABEL.search(row)
        plan = PLAN.search(row)
        name = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", plan.group(1))).split()) if plan else None
        price = PRICE.search(row)
        size = SQFT.search(row)
        beds = BEDS.search(name or "")
        baths = BATHS.search(name or "")
        free = FREE_ON.search(row)
        unit = make_unit(
            building["id"], html.unescape(label.group(1)) if label else unit_label(link.group(2)),
            rent=price.group(1) if price else None,
            plan=name,
            beds=beds.group(1) if beds else None,
            baths=baths.group(1) if baths else None,
            sqft=size.group(1) if size else None,
            available=f"{free.group(3)}-{int(free.group(1)):02d}-{int(free.group(2)):02d}" if free else None,
            notes="the site's starting price" + ("; listed as coming soon" if SOON.search(row) else ""),
            url=link.group(1),
            restricted=True if looks_restricted(name) else None,
        )
        if unit:
            units.append(unit)
    return {"units": unique(units), "fees": [], "amenities": []}
