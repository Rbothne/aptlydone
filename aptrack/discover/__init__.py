"""One discoverer per management company. Each is `discover(get, limit=None) -> [building, ...]`."""

from . import bozzuto, camden, greystar, willowbridge, windsor

DISCOVERERS = {
    "bozzuto": bozzuto.discover,
    "camden": camden.discover,
    "windsor": windsor.discover,
    "willowbridge": willowbridge.discover,
    "greystar": greystar.discover,
}
