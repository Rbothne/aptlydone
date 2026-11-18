"""True monthly cost: what a unit really costs per month once free months and required fees are counted."""

import re

WORDS = {"half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
NUMBER = r"(\d+/\d+|\d+(?:\.\d+)?|" + "|".join(WORDS) + r")"
FREE = re.compile(
    NUMBER + r"(?:\s+an?)?[\s-]+(month|week)(?:'s|s)?\s+(?:(?:base\s+)?rent\s+)?free"      # "2 months free", "one month's rent free"
    + r"|" + NUMBER + r"[\s-]+(month|week)s?\s+of\s+free\s+(?:base\s+)?rent",               # "2 months of free rent"
    re.I)
WEEKS_PER_MONTH = 4.345
DEFAULT_LEASE = 12


def free_months(text):
    """Months of free rent a concession text promises, or None when it does not say so in a form we can read."""
    match = FREE.search(text or "")
    if not match:
        return None
    amount, period = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
    amount = amount.lower()
    if amount in WORDS:
        number = WORDS[amount]
    elif "/" in amount:
        top, bottom = amount.split("/")
        if not float(bottom):
            return None
        number = float(top) / float(bottom)
    else:
        number = float(amount)
    months = number / WEEKS_PER_MONTH if period.lower() == "week" else number
    return int(months) if months == int(months) else months


def is_deposit(fee):
    return "deposit" in f"{fee.get('type') or ''} {fee.get('label') or ''}".lower()


def one_time(fees):
    """Required, non-refundable fees charged once (an amenity or application fee), in dollars."""
    return sum(fee["amount"] for fee in fees
               if fee.get("required") and fee.get("when") == "additional" and not fee.get("refundable")
               and fee.get("amount") is not None and not is_deposit(fee))


def parking_from(fees):
    """The lowest monthly price of a car parking space, or None when none is listed with a price."""
    prices = [fee["amount"] for fee in fees
              if "parking" in f"{fee.get('type') or ''} {fee.get('label') or ''}".lower()
              and "motorcycle" not in f"{fee.get('type') or ''} {fee.get('label') or ''}".lower()
              and fee.get("amount") is not None]
    return min(prices) if prices else None


def pets_allowed(fees):
    """True when the fee list has a pet fee; None when it says nothing."""
    return True if any("pet" in f"{fee.get('type') or ''} {fee.get('category') or ''} {fee.get('label') or ''}".lower()
                       for fee in fees) else None


def true_monthly(unit, fees, special=None):
    """Rent spread over the lease after free months, plus monthly fees, plus one-time required fees spread out.

    `special` is the concession text to count; by default the unit's own. None when the figures do not add up
    (a concession but no lease term, or more free months than the lease has).
    """
    free = free_months(special if special is not None else unit.get("special")) or 0
    lease = unit.get("lease")
    if not lease:
        if free:
            return None
        lease = DEFAULT_LEASE
    if free >= lease:
        return None
    return round(unit["rent"] * (lease - free) / lease + (unit.get("fees") or 0) + one_time(fees) / lease)


def apply(unit, fees, building_special):
    """Set `true` (counting the unit's own concession) and `true_offer` (if the building-wide offer applied)."""
    unit["true"] = true_monthly(unit, fees)
    unit["true_offer"] = None
    if not unit.get("special") and free_months(building_special):
        unit["true_offer"] = true_monthly(unit, fees, special=building_special)
