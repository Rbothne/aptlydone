"""One reader per listing system. Each is `read(building, get) -> {"units", "fees", "amenities"}`."""


class ReadError(Exception):
    """The source answered, but not with listings we can trust."""


class NotAnswering(ReadError):
    """The source answered with something that is not its data at all (a block page, an error page).
    Several of these in a row mean the site has stopped answering properly, not that one building changed."""


from . import avalon, camden, equity, rentpress, sightmap  # noqa: E402  (ReadError must exist before the readers import it)

READERS = {
    "sightmap": sightmap.read,
    "camden": camden.read,
    "avalon": avalon.read,
    "rentpress": rentpress.read,
    "equity": equity.read,
}
