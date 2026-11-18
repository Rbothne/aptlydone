"""In-unit laundry, worked out from whatever a building says about itself."""

import re

IN_UNIT = re.compile(r"(?<!dish)washer|in[- ](unit|home|suite) laundry|\bw/d\b", re.I)
SHARED = re.compile(r"laundry (room|facilit|cent|lounge)|(on[- ]site|community|shared|common) laundry", re.I)


def detect(texts):
    """"in_unit", "shared", or None when nothing mentions laundry."""
    texts = [text for text in texts if text]
    if any(IN_UNIT.search(text) for text in texts):
        return "in_unit"
    if any(SHARED.search(text) for text in texts):
        return "shared"
    return None
