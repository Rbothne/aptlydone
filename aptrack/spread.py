"""Listing systems read a few buildings at a time through the day, instead of all at once.

`"spread": {"rentcafe": 6}` in managers.json settings: RentCafe buildings are left out of the ordinary runs and read
in six shares, one per run of `build.py --spread`, each run taking up where the last stopped. Many buildings'
RentCafe sites sit behind one service, and asking for all of them in one run arrives there as a burst.
"""

import math


def shares(settings):
    """{listing system: how many shares its buildings are read in}, from the settings; nonsense is left out."""
    found = (settings or {}).get("spread") or {}
    return {platform: parts for platform, parts in found.items() if isinstance(parts, int) and parts >= 1}


def rest(buildings, parts):
    """The buildings an ordinary run reads: those whose listing system is not spread."""
    return [b for b in buildings if b.get("platform") not in parts]


def turn(buildings, state, parts):
    """The buildings this spread run reads: for each spread system, the next share after the building the last
    turn stopped at (kept in `state["spread"]`). Buildings are taken in the order of their ids, round and round."""
    chosen = []
    place = state.setdefault("spread", {}) if parts else {}
    for platform, count in parts.items():
        mine = sorted((b for b in buildings if b.get("platform") == platform and b.get("in_region")), key=lambda b: b["id"])
        if not mine:
            continue
        size = min(len(mine), math.ceil(len(mine) / count))
        last = place.get(platform)
        start = next((i for i, b in enumerate(mine) if last is None or b["id"] > last), 0)
        share = [mine[(start + i) % len(mine)] for i in range(size)]
        place[platform] = share[-1]["id"]
        chosen += share
    return chosen
