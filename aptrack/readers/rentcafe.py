"""RentCafe (Yardi) building websites.

The floor-plans page (`/floorplans`) has an "Availability" button per plan that has apartments free, linking to
that plan's page; the plan's page lists each apartment: its number, the day it is free, its base rent, the
required monthly fees the site adds to it, the lease length that rent is for, and a line of what the listing
says about it ("7th Floor, Small Balcony/Patio, West").

RentCafe's terms of use forbid automated reading. These sites are read at the owner's instruction (2026-11-20),
under the tracker's own name and at its usual pace; a site that refuses is left alone like any other.
"""

import html
import re
from urllib.parse import urljoin

from .. import fetch
from ..units import looks_restricted, make_unit, unique
from . import NotAnswering

SITE = re.compile(r"cdngeneralmvc\.rentcafe\.com|ysi\.SiteId\s*=")
PLAN_DATA = re.compile(r'data-floorplan-name="')
TAG = re.compile(r"<a\b[^>]*>")
AVAILABLE = re.compile(r'data-selenium-id="floorplan-\d+-apply-btn"')
APARTMENT = re.compile(r"Apartment:\s*<span[^>]*>\s*#?\s*([^<]+?)\s*</span>")
ATTRIBUTE = r'{}="([^"]*)"'
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
FREE_ON = re.compile(r"Date Available:\s*(?:<[^>]+>\s*)*(\d{1,2})/(\d{1,2})/(\d{4})")
TERM = re.compile(r"(\d+)\s*-\s*month term")
ABOUT = re.compile(r'<div[^>]*id="amenities\d+"[^>]*>(.*?)</div>', re.S)
FLOOR = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+Floor\b", re.I)
BATHS = re.compile(r"(\d+(?:\.\d)?)\s*Bath", re.I)


def is_floor_plans(page_html):
    """A RentCafe site's floor-plans page: hosted by RentCafe, and carrying its floor plans' data."""
    return bool(SITE.search(page_html or "") and PLAN_DATA.search(page_html or ""))


def attribute(text, name):
    match = re.search(ATTRIBUTE.format(re.escape(name)), text)
    return html.unescape(match.group(1)).strip() if match else None


def plan_links(page_html, page_url):
    """The pages of the plans that have apartments free, in the page's order."""
    links = []
    for tag in TAG.findall(page_html or ""):
        href = attribute(tag, "href")
        if AVAILABLE.search(tag) and href and "/floorplans/" in href:
            links.append(urljoin(page_url, href))
    return list(dict.fromkeys(links))


def first_amount(text):
    match = MONEY.search(html.unescape(text or ""))
    return match.group(1) if match else None


def parse_plan(page_html, building, url):
    """The apartments a plan's page lists."""
    start = (page_html or "").find('id="availApts"')
    if start < 0:
        return None
    marks = list(APARTMENT.finditer(page_html, start))
    units = []
    for i, mark in enumerate(marks):
        block = page_html[mark.start():marks[i + 1].start() if i + 1 < len(marks) else len(page_html)]
        name = attribute(block, "data-floorplan-name")
        free = FREE_ON.search(block)
        term = TERM.search(block)
        about = ABOUT.search(block)
        notes = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", about.group(1)))).strip() if about else ""
        floor = FLOOR.search(notes)
        baths = BATHS.search(name or "")
        unit = make_unit(
            building["id"], html.unescape(mark.group(1)),
            rent=first_amount(attribute(block, "data-fp_base_charge")),
            fees=first_amount(attribute(block, "data-fp_inclusive_charge")),
            plan=name,
            beds=attribute(block, "data-floorplan-size"),
            baths=baths.group(1) if baths else None,
            sqft=attribute(block, "data-floorplan-sqft"),
            floor=floor.group(1) if floor else None,
            lease=term.group(1) if term else None,
            available=f"{free.group(3)}-{int(free.group(1)):02d}-{int(free.group(2)):02d}" if free else None,
            notes=notes or None,
            url=url,
            restricted=True if looks_restricted(name) else None,
        )
        if unit:
            units.append(unit)
    return units


def read(building, get):
    page = get(building["feed"]).decode("utf-8", "replace")
    if not is_floor_plans(page):
        raise NotAnswering(f"{building['id']}: {building['feed']} is not a RentCafe floor-plans page")
    units = []
    for link in plan_links(page, building["feed"]):
        try:
            found = parse_plan(get(link).decode("utf-8", "replace"), building, link)
        except fetch.Gone:
            continue                               # a plan let go between the two requests
        if found is None:
            raise NotAnswering(f"{building['id']}: {link} did not list its apartments")
        units += found
    return {"units": unique(units), "fees": [], "amenities": []}
