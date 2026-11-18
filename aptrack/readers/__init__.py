"""One reader per listing system. Each is `read(building, get) -> {"units", "fees", "amenities"}`."""


class ReadError(Exception):
    """The source answered, but not with listings we can trust."""


from . import camden, sightmap  # noqa: E402  (ReadError must exist before the readers import it)

READERS = {
    "sightmap": sightmap.read,
    "camden": camden.read,
}
