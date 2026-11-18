import os
import unittest

from aptrack import discover, fetch
from aptrack.discover import willowbridge
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.willowbridgepc.com/properties/the-earl-arlington-virgnia/"
PAGE, SITE = fixture("willowbridge_building.html"), fixture("willowbridge_site.html")
OWN_SITE = "https://www.theearlapartments.com/the-earl-arlington-va"


class WillowBridgeTests(QuietTestCase):
    def test_urls_are_building_pages_that_look_to_be_in_the_region(self):
        urls = willowbridge.building_urls(fixture("willowbridge_sitemap.xml"))
        self.assertEqual(sorted(u.split("/properties/")[1] for u in urls),
                         ["4909-auburn-bethesda-maryland/", "aventura-at-contee-crossing-laurel-md/",
                          "balsa-washington-district-of-columbia/", "lincoln-at-old-town-alexandria-va/",
                          "the-earl-arlington-virgnia/"])

    def test_website(self):
        self.assertEqual(willowbridge.website(PAGE), OWN_SITE)
        self.assertEqual(willowbridge.website(PAGE.replace("https://www.theearl", "//www.theearl")), OWN_SITE)
        self.assertIsNone(willowbridge.website("<html></html>"))

    def test_parse(self):
        b = willowbridge.parse(URL, PAGE, SITE)
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"], b["url"]),
                         ("willow-bridge-the-earl-arlington-virgnia", "Willow Bridge", "The Earl", "sightmap",
                          "https://sightmap.com/embed/dgow3071w2m", OWN_SITE))
        self.assertEqual(b["address"], {"street": "1122 N Hudson St.", "city": "Arlington", "state": "VA", "zip": "22201"})
        self.assertAlmostEqual(b["lat"], 38.886923, places=5)
        self.assertAlmostEqual(b["lon"], -77.0966477, places=5)

    def test_parse_without_own_site_is_a_link_to_the_company_page(self):
        b = willowbridge.parse(URL, PAGE.replace("Visit Website", "Nothing"), "")
        self.assertEqual((b["platform"], b["feed"], b["url"]), ("link", None, URL))

    def test_parse_page_without_property_data_is_none(self):
        self.assertIsNone(willowbridge.parse(URL, "<html></html>", SITE))

    def test_discover_reads_the_buildings_own_floor_plans_page(self):
        asked = []
        elsewhere = "https://www.willowbridgepc.com/properties/lincoln-at-old-town-alexandria-va/"

        def get(url):
            asked.append(url)
            pages = {willowbridge.SITEMAP: fixture("willowbridge_sitemap.xml"), URL: PAGE,
                     "https://www.theearlapartments.com/floorplans": SITE,
                     elsewhere: PAGE.replace('"state":"VA"', '"state":"TX"')}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = willowbridge.discover(get)
        self.assertEqual([b["id"] for b in found], ["willow-bridge-the-earl-arlington-virgnia"])
        self.assertEqual(found[0]["feed"], "https://sightmap.com/embed/dgow3071w2m")
        self.assertIn("https://www.theearlapartments.com/floorplans", asked)

    def test_discover_falls_back_to_the_site_home_page(self):
        def get(url):
            pages = {willowbridge.SITEMAP: fixture("willowbridge_sitemap.xml"), URL: PAGE, OWN_SITE: SITE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = willowbridge.discover(get)
        self.assertEqual(found[0]["platform"], "sightmap")

    def test_registered(self):
        self.assertIs(discover.DISCOVERERS["willowbridge"], willowbridge.discover)


if __name__ == "__main__":
    unittest.main()
