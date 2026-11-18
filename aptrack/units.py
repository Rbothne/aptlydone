"""The common unit format every reader writes."""

import re


def num(value):
    """A number from 2700, "2,700.00" or "$2,700"; None when there is none."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
        if not match:
            return None
        number = float(match.group(0).replace(",", ""))
    return int(number) if number == int(number) else number


def beds_count(value):
    if isinstance(value, str) and value.strip().lower().startswith("studio"):
        return 0
    return num(value)


def make_unit(building_id, unit, *, rent, plan=None, beds=None, baths=None, sqft=None, floor=None, fees=None,
              lease=None, available=None, special=None, notes=None, url=None):
    """One available unit, or None when it has no usable rent."""
    rent = num(rent)
    if not rent or rent <= 0:
        return None
    unit = str(unit).strip()
    return {
        "id": f"{building_id}:{unit}",
        "building": building_id,
        "unit": unit,
        "floor": num(floor),
        "plan": (plan or "").strip() or None,
        "beds": beds_count(beds),
        "baths": num(baths),
        "sqft": num(sqft) or None,
        "rent": rent,
        "fees": num(fees),
        "lease": num(lease),
        "available": str(available)[:10] if available else None,
        "special": (special or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "url": url,
    }
