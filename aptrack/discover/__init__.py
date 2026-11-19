"""One discoverer per management company. Each is `discover(get, limit=None) -> [building, ...]`."""

from . import avalon, bozzuto, camden, equity, generic, greystar, rentpress, willowbridge, windsor

DISCOVERERS = {
    "bozzuto": bozzuto.discover,
    "camden": camden.discover,
    "windsor": windsor.discover,
    "willowbridge": willowbridge.discover,
    "greystar": greystar.discover,
    "avalon": avalon.discover,
    "wcsmith": rentpress.discoverer("WC Smith", "wcsmith.com"),
    "equity": equity.discover,
    "generic": generic.discoverer,          # built per company from its managers.json line
}
