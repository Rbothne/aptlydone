"""Which of the companies in managers.json are being followed right now.

A line carrying `"paused": "<why>"` is left alone entirely: not searched, not read, not on the page. Its code,
its buildings and its price history all stay, so deleting the word brings the company back at the next run.
"""


def paused(managers):
    """{company name: why it is paused}."""
    return {m["name"]: m["paused"] for m in managers if m.get("paused")}


def active(managers):
    return [m for m in managers if not m.get("paused")]


def tracked(buildings, managers):
    """The buildings of companies that are not paused: the same records, not copies."""
    left_out = paused(managers)
    return [b for b in buildings if b.get("manager") not in left_out]
