"""One discoverer per management company. Each is `discover(get, limit=None) -> [building, ...]`."""

from . import avalon, bozzuto, camden, cards, equity, generic, greystar, jbgsmith, rentpress, udr, willowbridge, windsor, wpjson

DISCOVERERS = {
    "bozzuto": bozzuto.discover,
    "camden": camden.discover,
    "windsor": windsor.discover,
    "willowbridge": willowbridge.discover,
    "greystar": greystar.discover,
    "avalon": avalon.discover,
    "wcsmith": rentpress.discoverer("WC Smith", "wcsmith.com"),
    "equity": equity.discover,
    "udr": udr.discover,
    "jbgsmith": jbgsmith.discover,
    "generic": generic.discoverer,          # built per company from its managers.json line
    "rentpress_list": rentpress.listed_discoverer,      # likewise: a RentPress page listing a company's buildings
    "wpjson": wpjson.discoverer,
    "cards": cards.discoverer,              # likewise: one page of building cards, described by a regular expression            # likewise: a WordPress site that lists its buildings through its REST API
}
