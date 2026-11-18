import os
import unittest

from aptrack import discover, fetch
from aptrack.discover import common, windsor
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.windsorcommunities.com/properties/windsor-courthouse/"
PAGE, FLOORPLANS = fixture("windsor_building.html"), fixture("windsor_floorplans.html")
ELSEWHERE = PAGE.replace('"addressRegion":"VA"', '"addressRegion":"CO"').replace('"addressRegion": "VA"', '"addressRegion": "CO"')


class CommonTests(unittest.TestCase):
    def test_place_reads_any_node_with_an_address(self):
        place = common.place(PAGE)
        self.assertEqual(place["name"], "Windsor Courthouse")
        self.assertEqual(place["address"], {"street": "2055 15th Street North", "city": "Arlington", "state": "VA", "zip": "22201"})
        self.assertAlmostEqual(place["lat"], 38.891192, places=5)
        self.assertAlmostEqual(place["lon"], -77.0846003, places=5)
        self.assertEqual((place["rating"], place["rating_count"]), (4.3, 161))

    def test_place_can_require_a_type(self):
        self.assertIsNone(common.place(PAGE, kinds=("ApartmentComplex",)))
        self.assertEqual(common.place(fixture("bozzuto_building.html"), kinds=("ApartmentComplex",))["name"], "5333 Connecticut")

    def test_place_without_structured_data(self):
        self.assertIsNone(common.place("<html></html>"))

    def test_sightmap_embed(self):
        self.assertEqual(common.sightmap_embed(FLOORPLANS), "https://sightmap.com/embed/y8px84x5v19")
        self.assertIsNone(common.sightmap_embed("<html></html>"))


class WindsorTests(QuietTestCase):
    def test_urls(self):
        urls = windsor.building_urls(fixture("windsor_sitemap.xml"))
        self.assertEqual(len(urls), 6)
        self.assertIn(URL, urls)

    def test_parse(self):
        b = windsor.parse(URL, PAGE, FLOORPLANS)
        self.assertEqual((b["id"], b["manager"], b["name"], b["url"], b["platform"], b["feed"]),
                         ("windsor-courthouse", "Windsor", "Windsor Courthouse", URL, "sightmap",
                          "https://sightmap.com/embed/y8px84x5v19"))
        self.assertEqual(b["address"]["state"], "VA")
        self.assertEqual((b["rating"], b["rating_count"]), (4.3, 161))

    def test_id_gets_the_company_prefix_when_the_name_lacks_it(self):
        b = windsor.parse("https://www.windsorcommunities.com/properties/the-woodley/", PAGE, FLOORPLANS)
        self.assertEqual(b["id"], "windsor-the-woodley")

    def test_parse_without_embed_is_link(self):
        self.assertEqual(windsor.parse(URL, PAGE, "")["platform"], "link")

    def test_discover_only_fetches_floor_plans_for_region_states(self):
        self.assertNotEqual(ELSEWHERE, PAGE)
        other = "https://www.windsorcommunities.com/properties/the-casey/"
        asked = []

        def get(url):
            asked.append(url)
            pages = {windsor.SITEMAP: fixture("windsor_sitemap.xml"), URL: PAGE, URL + "floorplans/": FLOORPLANS, other: ELSEWHERE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = windsor.discover(get)
        self.assertEqual([b["id"] for b in found], ["windsor-courthouse"])
        self.assertIn(URL + "floorplans/", asked)
        self.assertNotIn(other + "floorplans/", asked)

    def test_registered(self):
        self.assertIs(discover.DISCOVERERS["windsor"], windsor.discover)


if __name__ == "__main__":
    unittest.main()
