"""One discoverer per management company. Each is `discover(get, limit=None) -> [building, ...]`."""

from . import bozzuto, camden

DISCOVERERS = {
    "bozzuto": bozzuto.discover,
    "camden": camden.discover,
}
