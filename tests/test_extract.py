"""Reading a few members out of a big remote zip by byte range, and the shapefiles inside."""
import os
import unittest

from aptrack import fetch
from aptrack.area import extract
from tests import shapefiles

URL = "https://download.example.test/dc-latest-free.shp.zip"
SHAPES = [("point", -77.03, 38.90), None, ("polygon", -77.06, 38.93, -77.04, 38.95)]
MEMBERS = {
    "README": b"hello",
    "gis_osm_buildings_a_free_1.shp": os.urandom(300_000),          # the bulk nobody asks for
    "gis_osm_pois_free_1.cpg": b"UTF-8",
    "gis_osm_pois_free_1.dbf": shapefiles.dbf(["supermarket", "bench", "park"], {2: "Rock Creek Park"}),
    "gis_osm_pois_free_1.shp": shapefiles.shp(SHAPES),
    "gis_osm_roads_free_1.dbf": os.urandom(200_000),
}
ZIP = shapefiles.archive(MEMBERS, stored=("gis_osm_pois_free_1.cpg",))


class MembersTests(unittest.TestCase):
    def test_only_the_wanted_members_are_downloaded(self):
        asked = []
        got = extract.members(shapefiles.ranged({URL: ZIP}, asked), URL, ["gis_osm_pois_free_1.dbf", "gis_osm_pois_free_1.shp", "gis_osm_pois_free_1.cpg"])
        self.assertEqual(got, {name: MEMBERS[name] for name in ("gis_osm_pois_free_1.dbf", "gis_osm_pois_free_1.shp", "gis_osm_pois_free_1.cpg")})
        self.assertEqual(asked[0], (URL, f"bytes=-{extract.TAIL}"))
        fetched = sum(int(r.split("-")[1]) - int(r.split("=")[1].split("-")[0]) + 1 for _, r in asked[1:])
        self.assertLess(fetched, 5_000)                               # not the 500 KB around them
        self.assertEqual(len(asked), 2)                               # neighbours in the file come in one request

    def test_members_far_apart_are_separate_requests(self):
        asked = []
        got = extract.members(shapefiles.ranged({URL: ZIP}, asked), URL, ["README", "gis_osm_pois_free_1.shp"])
        self.assertEqual((got["README"], len(asked)), (b"hello", 3))

    def test_a_missing_member_is_an_error_naming_it(self):
        with self.assertRaisesRegex(ValueError, "gis_osm_nothing"):
            extract.members(shapefiles.ranged({URL: ZIP}), URL, ["gis_osm_nothing.shp"])

    def test_something_that_is_not_a_zip_is_an_error(self):
        with self.assertRaises(ValueError):
            extract.members(shapefiles.ranged({URL: b"<html>Please verify you are human</html>" * 50}), URL, ["README"])

    def test_a_directory_longer_than_the_tail_is_fetched_whole(self):
        many = {f"member-{n:04d}.txt": b"x" for n in range(40)}
        data = shapefiles.archive(dict(many, wanted=b"here"))
        asked = []
        got = extract.members(shapefiles.ranged({URL: data}, asked), URL, ["wanted"], tail=200)
        self.assertEqual(got, {"wanted": b"here"})
        self.assertEqual(asked[0][1], "bytes=-200")
        self.assertEqual(len(asked), 3)                               # the tail, the directory, the member

    def test_ranges_are_asked_for_uncompressed_and_unaltered(self):
        seen = []

        def get(url, **options):
            seen.append(options)
            return shapefiles.ranged({URL: ZIP})(url, **options)
        extract.members(get, URL, ["README"])
        self.assertTrue(all(o.get("raw") is True and o["headers"]["Accept-Encoding"] == "identity" for o in seen))


class RawFetchTests(unittest.TestCase):
    def test_raw_keeps_bytes_that_only_look_compressed(self):
        body = b"\x1f\x8b not really gzip"

        class Response:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): return body
        self.assertEqual(fetch.get("https://x.test/a", opener=lambda request, timeout: Response(), raw=True), body)


class ShapefileTests(unittest.TestCase):
    def test_boxes_are_south_west_north_east_and_a_missing_shape_is_none(self):
        self.assertEqual(extract.boxes(shapefiles.shp(SHAPES)),
                         [(38.90, -77.03, 38.90, -77.03), None, (38.93, -77.06, 38.95, -77.04)])
        with self.assertRaises(ValueError):
            extract.boxes(b"not a shapefile at all" * 10)

    def test_kinds_are_the_fclass_column(self):
        self.assertEqual(extract.kinds(shapefiles.dbf(["supermarket", "bench", "park"])), ["supermarket", "bench", "park"])

    def test_a_layer_pairs_each_kind_with_its_box(self):
        self.assertEqual(extract.layer(shapefiles.shp(SHAPES), shapefiles.dbf(["supermarket", "bench", "park"])),
                         [("supermarket", (38.90, -77.03, 38.90, -77.03)), ("park", (38.93, -77.06, 38.95, -77.04))])
        with self.assertRaises(ValueError):
            extract.layer(shapefiles.shp(SHAPES), shapefiles.dbf(["supermarket"]))        # the two files disagree


if __name__ == "__main__":
    unittest.main()
