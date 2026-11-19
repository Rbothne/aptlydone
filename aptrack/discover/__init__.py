"""One discoverer per management company. Each is `discover(get, limit=None) -> [building, ...]`."""

from . import avalon, bozzuto, camden, generic, greystar, rentpress, willowbridge, windsor

DISCOVERERS = {
    "bozzuto": bozzuto.discover,
    "camden": camden.discover,
    "windsor": windsor.discover,
    "willowbridge": willowbridge.discover,
    "greystar": greystar.discover,
    "avalon": avalon.discover,
    "wcsmith": rentpress.discoverer("WC Smith", "wcsmith.com"),
    "generic": generic.discoverer,          # built per company from its managers.json line
}
