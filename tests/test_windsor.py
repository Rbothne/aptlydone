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

    def test_a_unit_map_address_run_together_with_what_follows_it_is_cut_at_the_maps_own_name(self):
        # Two Kettler sites print the address straight into another word; a map's name is always eleven characters.
        self.assertEqual(common.sightmap_embed("x https://sightmap.com/embed/4d7p16movkxaspx_MenuLink y"),
                         "https://sightmap.com/embed/4d7p16movkx")

    def test_the_sightmap_script_is_not_a_unit_map(self):
        script = '<script src="https://sightmap.com/embed/api.js"></script>'
        self.assertEqual(common.sightmap_embed(script + '<iframe data-src="https://sightmap.com/embed/yjp2k7d9pxl"></iframe>'),
                         "https://sightmap.com/embed/yjp2k7d9pxl")
        self.assertIsNone(common.sightmap_embed(script))


class WindsorTests(QuietTestCase):
    def test_location_pages_for_the_region_only(self):
        self.assertEqual(sorted(u.split("/apartments/")[1] for u in windsor.location_urls(fixture("windsor_locations.xml"))),
                         ["maryland-bethesda/", "virginia-arlington/", "washington-dc/"])

    def test_building_links_on_a_location_page(self):
        self.assertEqual(windsor.building_urls(fixture("windsor_location.html")),
                         ["https://www.windsorcommunities.com/properties/io-piazza-by-windsor/", URL])

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

    def test_discover_reads_region_location_pages_then_their_buildings(self):
        self.assertNotEqual(ELSEWHERE, PAGE)
        arlington = "https://www.windsorcommunities.com/apartments/virginia-arlington/"
        other = "https://www.windsorcommunities.com/properties/io-piazza-by-windsor/"
        asked = []

        def get(url):
            asked.append(url)
            pages = {windsor.SITEMAP: fixture("windsor_locations.xml"), arlington: fixture("windsor_location.html"),
                     URL: PAGE, URL + "floorplans/": FLOORPLANS, other: ELSEWHERE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = windsor.discover(get)
        self.assertEqual([b["id"] for b in found], ["windsor-courthouse"])
        self.assertIn(URL + "floorplans/", asked)
        self.assertNotIn(other + "floorplans/", asked)                    # its page says it is in another state
        self.assertFalse([u for u in asked if "colorado" in u or "georgia" in u])
        self.assertEqual(len(asked), len(set(asked)))

    def test_registered(self):
        self.assertIs(discover.DISCOVERERS["windsor"], windsor.discover)


if __name__ == "__main__":
    unittest.main()
