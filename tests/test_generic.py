"""Companies added with one line in managers.json: a sitemap, a pattern for building pages, and where the unit map is."""
import os
import unittest

from aptrack import discover, discovery, fetch
from aptrack.discover import generic
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


PAGE, FLOORPLANS = fixture("windsor_building.html"), fixture("windsor_floorplans.html")
SITEMAP = ("<urlset><url><loc>https://www.example.test/apartments/va/arlington/the-one</loc></url>"
           "<url><loc>https://www.example.test/apartments/va/arlington/the-one/gallery</loc></url>"
           "<url><loc>https://www.example.test/apartments/tx/austin/the-other</loc></url>"
           "<url><loc>https://www.example.test/about</loc></url></urlset>")
CONFIG = {"name": "Example Living", "site": "www.example.test", "discover": "generic",
          "sitemap": "https://www.example.test/sitemap.xml",
          "pattern": r"https://www\.example\.test/apartments/(?:va|md|dc)/[^/<\s]+/[^/<\s]+",
          "map_paths": ["", "/floorplans"]}
ONE = "https://www.example.test/apartments/va/arlington/the-one"


class GenericTests(QuietTestCase):
    def web(self, pages):
        self.asked = []

        def get(url, **options):
            self.asked.append(url)
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        return get

    def test_building_pages_come_from_the_sitemap_by_pattern(self):
        self.assertEqual(generic.building_urls(SITEMAP, CONFIG["pattern"]), [ONE])

    def test_discover_finds_the_place_and_the_unit_map_on_a_listed_path(self):
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: PAGE, ONE + "/floorplans": FLOORPLANS})
        found = generic.discoverer(CONFIG)(get)
        self.assertEqual(len(found), 1)
        b = found[0]
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"], b["url"]),
                         ("example-living-the-one", "Example Living", "Windsor Courthouse", "sightmap",
                          "https://sightmap.com/embed/y8px84x5v19", ONE))
        self.assertEqual(self.asked, [CONFIG["sitemap"], ONE, ONE + "/floorplans"])

    def test_the_unit_map_on_the_building_page_itself_needs_no_second_request(self):
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: PAGE + FLOORPLANS})
        found = generic.discoverer(CONFIG)(get)
        self.assertEqual((found[0]["platform"], self.asked), ("sightmap", [CONFIG["sitemap"], ONE]))

    def test_no_unit_map_anywhere_is_a_link(self):
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: PAGE})
        self.assertEqual(generic.discoverer(CONFIG)(get)[0]["platform"], "link")

    def test_buildings_outside_the_region_are_dropped_by_their_address(self):
        elsewhere = PAGE.replace('"addressRegion":"VA"', '"addressRegion":"TX"')
        self.assertNotEqual(elsewhere, PAGE)
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: elsewhere})
        self.assertEqual(generic.discoverer(CONFIG)(get), [])
        self.assertEqual(self.asked, [CONFIG["sitemap"], ONE])               # no floor-plans request for it

    def test_pages_without_their_data_stop_the_crawl(self):
        sitemap = "<urlset>" + "".join(f"<url><loc>https://www.example.test/apartments/va/x/b{n}</loc></url>" for n in range(9)) + "</urlset>"
        pages = {CONFIG["sitemap"]: sitemap}
        pages.update({f"https://www.example.test/apartments/va/x/b{n}": "<html>Please verify you are human</html>" for n in range(9)})
        with self.assertRaises(fetch.RateLimited):
            generic.discoverer(CONFIG)(self.web(pages))

    def test_several_sitemaps_and_a_limit(self):
        config = dict(CONFIG, sitemap=["https://www.example.test/a.xml", "https://www.example.test/b.xml"])
        other = ONE.replace("the-one", "the-two")
        get = self.web({"https://www.example.test/a.xml": SITEMAP, "https://www.example.test/b.xml": SITEMAP.replace("the-one", "the-two"),
                        ONE: PAGE + FLOORPLANS, other: PAGE + FLOORPLANS})
        self.assertEqual([b["id"] for b in generic.discoverer(config)(get)], ["example-living-the-one", "example-living-the-two"])
        self.assertEqual(len(generic.discoverer(config)(get, limit=1)), 1)

    def test_building_pages_can_come_from_the_links_on_a_list_page(self):
        listing = ('<a href="/apartments/va/arlington/the-one">The One</a> <a href="/apartments/va/arlington/the-one">again</a> '
                   '<a href="/apartments/va/arlington/the-one/gallery">Gallery</a> <a href="/about">About</a> '
                   '<a href="https://elsewhere.test/apartments/va/arlington/other">Other</a>')
        config = {k: v for k, v in CONFIG.items() if k != "sitemap"}
        config["list"] = "https://www.example.test/metro/dc/"
        self.assertEqual(generic.link_urls(listing, config["list"], CONFIG["pattern"]), [ONE])
        get = self.web({config["list"]: listing, ONE: PAGE + FLOORPLANS})
        found = generic.discoverer(config)(get)
        self.assertEqual(([b["id"] for b in found], self.asked), (["example-living-the-one"], [config["list"], ONE]))

    def test_a_company_whose_pages_carry_titles_not_names_is_named_from_the_address_of_the_page(self):
        self.assertEqual(generic.slug_name("maa-national-landing", "MAA"), "MAA National Landing")
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: PAGE + FLOORPLANS})
        found = generic.discoverer(dict(CONFIG, name_from_slug=True))(get)
        self.assertEqual(found[0]["name"], "The One")

    def test_run_all_builds_a_generic_discoverer_from_the_managers_line(self):
        get = self.web({CONFIG["sitemap"]: SITEMAP, ONE: PAGE + FLOORPLANS})
        found = discovery.run_all([CONFIG], discover.DISCOVERERS, get, workers=1, sleep=lambda s: None)
        self.assertEqual([b["id"] for b in found["Example Living"]], ["example-living-the-one"])


if __name__ == "__main__":
    unittest.main()
