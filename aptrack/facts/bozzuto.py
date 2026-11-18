"""Bozzuto building pages: concession, rating, neighborhood and feature lists, embedded in the page as data."""

import json
import re

CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
VALUE = r'"%s":("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)'
LIST_ITEM = re.compile(r'"list":("(?:[^"\\]|\\.)*")')
MISSING = object()


def embedded(page_html):
    """The page's embedded data as one text. Each chunk is a JavaScript string literal."""
    parts = []
    for chunk in CHUNK.findall(page_html):
        try:
            parts.append(json.loads('"' + chunk + '"', strict=False))
        except ValueError:
            parts.append(chunk.replace('\\"', '"'))
    return "".join(parts)


def value(text, key):
    match = re.search(VALUE % re.escape(key), text)
    if not match:
        return MISSING
    try:
        return json.loads(match.group(1))
    except ValueError:
        return MISSING


def parse(page_html):
    """Facts from a building page, or None when the page no longer carries them (a redesign, say)."""
    text = embedded(page_html)
    has_offer = value(text, "hasSpecialOffer")
    if has_offer is MISSING:
        return None

    def get(key, kind):
        found = value(text, key)
        return found if isinstance(found, kind) and not isinstance(found, bool) else None

    offer = get("specialOfferText", str)
    features = []
    for item in LIST_ITEM.findall(text):
        try:
            label = " ".join(json.loads(item).split())
        except ValueError:
            continue
        if label and label not in features:
            features.append(label)
    return {
        "special": " ".join(offer.split()) if has_offer is True and offer and offer.strip() else None,
        "rating": get("totalAvgRating", (int, float)),
        "rating_count": get("totalRatingCount", int),
        "neighborhood": get("neighborhood", str) or None,
        "coming_soon": value(text, "isComingSoon") is True or value(text, "isUnderConstruction") is True,
        "features": features,
    }


def read(building, get):
    return parse(get(building["url"]).decode("utf-8", "replace"))
