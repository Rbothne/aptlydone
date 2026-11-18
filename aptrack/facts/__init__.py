"""Facts about a building beyond its units, read from the manager's own building page.

Each reader is `read(building, get) -> dict | None`, keyed here by the manager's name in managers.json.
A reader that finds nothing returns None, and the building keeps the facts it had.
"""

from . import bozzuto

FACTS = {
    "Bozzuto": bozzuto.read,
}
