"""Kettler: its communities page hands every visitor a site number, and its own property search, asked with that
number, lists every building with its address, coordinates and website. Used at the owner's instruction (2026-11-20)."""
import json
import unittest

from aptrack import fetch
from aptrack.discover import DISCOVERERS, kettler

PAGE = "<div class='property-search' ng-controller='searchQueries' ng-init='init(2405)'></div>"


def prop(name, state, site, **more):
    return {"name": name, "address": "800 John Carlyle St", "city": "Alexandria", "state": state, "zip": "22314 ",
            "lat": 38.798714, "long": -77.0617855, "slug": name.lower().replace(" ", "-"), "vanity_url": site, **more}


LISTED = {"total_pages": 1, "properties": [
    prop("800 Carlyle", "VA ", "https://www.800carlyle.com/?utm_source=Kettler.com&utm_medium=Property+List"),
    prop("Far Away", "UT", "https://www.faraway.com/"),
    prop("No Site", "DC", None),
]}
RENTCAFE = ('<script src="https://cdngeneralmvc.rentcafe.com/js/site.js"></script>'
            '<a href="/floorplans/a1" data-floorplan-name="A1" data-selenium-id="floorplan-0-apply-btn">Availability</a>')


def web(pages, asked=None):
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


class KettlerTest(unittest.TestCase):
    def test_buildings_in_the_region_come_from_the_search_the_page_itself_uses(self):
        asked = []
        get = web({kettler.PAGE: PAGE, kettler.API.format("2405"): json.dumps(LISTED),
                   "https://www.800carlyle.com/floorplans": RENTCAFE}, asked)
        found = DISCOVERERS["kettler"](get)
        self.assertEqual([b["name"] for b in found], ["800 Carlyle", "No Site"])
        first = found[0]
        self.assertEqual(first["id"], "kettler-800-carlyle")
        self.assertEqual(first["manager"], "Kettler")
        self.assertEqual(first["url"], "https://www.800carlyle.com/")                 # without the campaign tags
        self.assertEqual(first["address"], {"street": "800 John Carlyle St", "city": "Alexandria", "state": "VA", "zip": "22314"})
        self.assertEqual((first["lat"], first["lon"]), (38.798714, -77.0617855))
        self.assertEqual((first["platform"], first["feed"]), ("rentcafe", "https://www.800carlyle.com/floorplans"))
        self.assertEqual((found[1]["platform"], found[1]["url"]), ("link", kettler.PAGE))
        self.assertEqual(asked[:2], [kettler.PAGE, kettler.API.format("2405")])       # the number is read from the page each time
        self.assertFalse(any("faraway" in url for url in asked))

    def test_a_page_without_the_number_fails_loudly(self):
        with self.assertRaises(Exception):
            kettler.discover(web({kettler.PAGE: "<html>redesigned</html>"}))

    def test_limit_and_a_website_that_cannot_be_read(self):
        many = {"properties": [prop(f"Place {n}", "DC", f"https://place{n}.test/") for n in range(5)]}
        found = kettler.discover(web({kettler.PAGE: PAGE, kettler.API.format("2405"): json.dumps(many)}), limit=2)
        self.assertEqual([(b["name"], b["platform"]) for b in found], [("Place 0", "link"), ("Place 1", "link")])


if __name__ == "__main__":
    unittest.main()
