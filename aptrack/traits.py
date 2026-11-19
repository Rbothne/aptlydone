"""What a listing says about one unit beyond its size and price: outdoor space of its own, and a front door of
its own. Read from the floor plan's name and the unit's own feature list, never from the building's amenities
("balconies in select homes" says nothing about this unit). A unit whose listing is silent is simply unmarked.
"""

import re

# wording that names the thing without the unit having it
NOT_OUTDOOR = re.compile(r"juliet(?:te)?\s+balcon\w*|\b(?:terrace|balcony|patio|courtyard|garden|yard|deck)\s+(?:views?|level|facing)"
                         r"|\bno\s+(?:balcony|patio|terrace)", re.I)
OUTDOOR = (                                 # first match names it
    ("Terrace", re.compile(r"\bterrace", re.I)),
    ("Patio or balcony", re.compile(r"\bpatio\b.*\bbalcon|\bbalcon\w*\b.*\bpatio\b", re.I)),
    ("Patio", re.compile(r"\bpatio\b", re.I)),
    ("Balcony", re.compile(r"\bbalcon", re.I)),
    ("Roof deck", re.compile(r"\broof\s?(?:top)?\s+deck", re.I)),
    ("Deck", re.compile(r"\b(?:private|sun)\s+deck\b", re.I)),
    ("Yard", re.compile(r"\b(?:back)?yard\b", re.I)),
)
OWN_DOOR = re.compile(
    r"\bprivate[\s-]+(?:entrance|entry|stoop|front\s+door)"
    r"|\b(?:separate|own|exterior|street[\s-]+level|direct)[\s-]+(?:(?:exterior|street|outside)[\s-]+)?(?:entrance|entry)\b"
    r"|\bdirect[\s-]+(?:street|exterior|outside|outdoor|sidewalk)[\s-]+access"
    r"|\bwalk[\s-]?out\b|\bstoop\b"
    r"|\btown\s?(?:home|house)s?\b(?![\s-]style)", re.I)


def said(unit):
    return " , ".join(part for part in (unit.get("plan"), unit.get("notes")) if part)


def outdoor(unit):
    """"Balcony", "Terrace", "Patio"... when the unit's own listing names one; None when it does not."""
    text = NOT_OUTDOOR.sub(" ", said(unit))
    return next((label for label, pattern in OUTDOOR if pattern.search(text)), None)


def own_door(unit):
    """Does the unit's own listing say it has its own door to the outside (a private entrance, a townhome)?"""
    return bool(OWN_DOOR.search(said(unit)))


def apply(unit):
    unit["outdoor"], unit["own_door"] = outdoor(unit), own_door(unit)
