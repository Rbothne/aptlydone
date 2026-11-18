import os
import unittest

from aptrack import discover, fetch
from aptrack.discover import common, greystar
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.greystar.com/the-wendy-arlington-va/p_21811"
PAGE, SITE = fixture("greystar_building.html"), fixture("greystar_site.html")


class PlaceTests(unittest.TestCase):
    def test_coordinates_directly_on_the_object(self):
        place = common.place(PAGE)
        self.assertEqual((place["name"], place["address"]["street"], place["address"]["state"]), ("The Wendy", "2025 Clarendon Blvd", "VA"))
        self.assertAlmostEqual(place["lat"], 38.8918915876, places=6)
        self.assertAlmostEqual(place["lon"], -77.083378016, places=6)

    def test_amenity_features_are_listed(self):
        features = common.place(PAGE)["features"]
        self.assertGreater(len(features), 3)
        self.assertTrue(all(isinstance(name, str) and name for name in features))

    def test_no_amenity_features_is_an_empty_list(self):
        self.assertEqual(common.place(fixture("bozzuto_building.html"))["features"], [])


class GreystarTests(QuietTestCase):
    def test_urls_are_region_states_only(self):
        urls = greystar.building_urls(fixture("greystar_sitemap.xml"))
        self.assertEqual(len(urls), 5)
        self.assertIn(URL, urls)
        self.assertFalse([u for u in urls if "-tx/" in u or "-ca/" in u])

    def test_website(self):
        self.assertEqual(greystar.website(PAGE), "https://livethewendy.com/")
        self.assertIsNone(greystar.website("<html></html>"))

    def test_parse(self):
        b = greystar.parse(URL, PAGE, SITE)
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"], b["url"]),
                         ("greystar-the-wendy-arlington-va", "Greystar", "The Wendy", "sightmap",
                          "https://sightmap.com/embed/n9w60lrew71", "https://livethewendy.com/"))
        self.assertGreater(len(b["features"]), 3)

    def test_parse_without_a_unit_map_is_a_link(self):
        b = greystar.parse(URL, PAGE, "<html></html>")
        self.assertEqual((b["platform"], b["feed"]), ("link", None))

    def test_discover(self):
        asked = []

        def get(url):
            asked.append(url)
            pages = {greystar.SITEMAP: fixture("greystar_sitemap.xml"), URL: PAGE, "https://livethewendy.com/floorplans": SITE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = greystar.discover(get, limit=1)
        self.assertEqual([(b["id"], b["platform"]) for b in found], [("greystar-the-wendy-arlington-va", "sightmap")])
        self.assertEqual(asked, [greystar.SITEMAP, URL, "https://livethewendy.com/floorplans"])

    def test_registered(self):
        self.assertIs(discover.DISCOVERERS["greystar"], greystar.discover)


if __name__ == "__main__":
    unittest.main()
