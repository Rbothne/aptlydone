"""AvalonBay (Avalon, AVA, eaves): each community page embeds its whole record as JSON, with every available
unit's rent, total price, lease term, size and floor, plus the community's rating, features and promotions."""

import json
import re

from ..units import looks_restricted, make_unit, num, unique
from . import NotAnswering

CONTENT = re.compile(r"Fusion\.globalContent\s*=\s*(\{.*?\});\s*Fusion\.", re.S)


def content(html):
    """The community record embedded in a page."""
    match = CONTENT.search(html or "")
    try:
        return json.loads(match.group(1))
    except (AttributeError, ValueError) as error:
        raise NotAnswering("no community data in the page") from error


def promotion_text(unit):
    parts = []
    for promotion in unit.get("promotions") or []:
        text = " ".join(filter(None, [promotion.get("promotionTitle"), promotion.get("promotionDescription")]))
        if text:
            parts.append(" ".join(text.split()))
    return " ".join(parts) or None


def parse(html, building):
    record = content(html)
    units = []
    for u in record.get("units") or []:
        quote = u.get("startingAtPricesUnfurnished") or {}
        prices = quote.get("prices") or {}
        rent, total = num(prices.get("price")), num(prices.get("totalPrice"))
        plan = (u.get("floorPlan") or {}).get("name")
        unit = make_unit(
            building["id"], u.get("unitName"),
            rent=rent,
            plan=plan,
            beds=u.get("bedroomNumber"),
            baths=u.get("bathroomNumber"),
            sqft=u.get("squareFeet"),
            floor=u.get("floorNumber"),
            fees=total - rent if rent and total is not None and total >= rent else None,
            lease=quote.get("leaseTerm"),
            available=u.get("availableDateUnfurnished") or quote.get("moveInDate"),
            special=promotion_text(u),
            notes=", ".join(u.get("characteristics") or []) or None,
            url=u.get("url") or building.get("url"),
            restricted=True if looks_restricted(plan) else None,
        ) if u.get("unitName") else None
        if unit:
            units.append(unit)

    features = record.get("features") if isinstance(record.get("features"), list) else []
    names = [f["name"].strip() for f in features if isinstance(f, dict) and (f.get("name") or "").strip()]
    rating = record.get("rating") if isinstance(record.get("rating"), dict) else {}
    return {
        "units": unique(units),
        "fees": [],
        "amenities": names,
        "facts": {
            # Promotions are attached to the units they apply to, so there is no building-wide "may apply" offer.
            "special": None,
            "rating": num(rating.get("averageRating")),
            "rating_count": num(rating.get("totalReviews")),
            "features": names,
            "pets": True if record.get("allowedPets") else None,
            "parking": True if any("parking" in name.lower() or "garage" in name.lower() for name in names) else None,
        },
    }


def read(building, get):
    return parse(get(building["feed"]).decode("utf-8", "replace"), building)
