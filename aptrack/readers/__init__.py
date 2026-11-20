"""One reader per listing system. Each is `read(building, get) -> {"units", "fees", "amenities"}`.

Not every listing system a building website uses is read. RentCafe (Yardi) building sites are not: their terms
of use forbid any robot, spider, scraper or other automated means of accessing them. Entrata and RealPage's online
leasing refuse automated visitors outright. A building on one of those stays a link."""


class ReadError(Exception):
    """The source answered, but not with listings we can trust."""


class NotAnswering(ReadError):
    """The source answered with something that is not its data at all (a block page, an error page).
    Several of these in a row mean the site has stopped answering properly, not that one building changed."""


from . import appfolio, avalon, camden, equity, g5, jonah, offers, rentpress, sightmap, udr  # noqa: E402  (ReadError must exist before the readers import it)

READERS = {
    "sightmap": sightmap.read,
    "camden": camden.read,
    "avalon": avalon.read,
    "rentpress": rentpress.read,
    "equity": equity.read,
    "udr": udr.read,
    "jonah": jonah.read,
    "g5": g5.read,
    "offers": offers.read,
    "appfolio": appfolio.read,
}
