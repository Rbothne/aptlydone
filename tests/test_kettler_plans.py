"""Kettler's own property search, asked for floor plans too, lists each building's plans with a starting price and
the number of apartments free (one request for every building). It is the route used where a Kettler building's
own website cannot be read apartment by apartment: its RentCafe sites refuse the tracker."""
import json
import unittest

from aptrack import fetch
from aptrack.discover import kettler as finder
from aptrack.readers import READERS, NotAnswering, kettler as reader

PAGE = "<div class='property-search' ng-controller='searchQueries' ng-init='init(2405)'></div>"
RENTCAFE = ('<script src="https://cdngeneralmvc.rentcafe.com/js/site.js"></script>'
            '<a href="/floorplans/a1" data-floorplan-name="A1" data-selenium-id="floorplan-0-apply-btn">Availability</a>')
MAP = '<iframe src="https://sightmap.com/embed/abc123"></iframe>'


def plan(name, beds, baths, sqft, pricing, free, plan_id=1):
    return {"floorplan_id": plan_id, "name": name, "beds": beds, "baths": baths, "sqft": sqft, "pricing": pricing,
            "units_available": free, "image_url": "https://img.test/p.png" if sqft else "", "is_for_rent": False}


def prop(pid, name, site, plans):
    return {"property_id": pid, "name": name, "address": "800 John Carlyle St", "city": "Alexandria", "state": "VA", "zip": "22314",
            "lat": 38.79, "long": -77.06, "slug": name.lower().replace(" ", "-"), "vanity_url": site, "floorplans": plans,
            "floorplans_available": sum(1 for p in plans if p["units_available"])}


CARLYLE = prop(15886, "800 Carlyle", "https://www.800carlyle.com/", [
    plan("S1a", 0.0, 1.0, 0, 0, 0, 1), plan("S2a", 0.0, 1.0, 480, 2017, 2, 2), plan("B4 Den", 2.0, 2.5, 1210, 3397, 1, 3),
    plan("Priced, none free", 1.0, 1.0, 700, 2500, 0, 4)])
LISTED = {"properties": [CARLYLE, prop(2, "Has A Map", "https://www.hasamap.com/", [plan("A1", 1.0, 1.0, 700, 2100, 3)]),
                         prop(3, "No Plans", "https://www.noplans.com/", [])]}


def web(pages, asked=None):
    def get(url, **options):
        if asked is not None:
            asked.append(url)
        if url not in pages:
            raise fetch.Gone(url)
        return pages[url].encode()
    return get


SITE = {finder.PAGE: PAGE, finder.API.format("2405"): json.dumps(LISTED),
        "https://www.800carlyle.com/floorplans": RENTCAFE, "https://www.hasamap.com/floorplans": MAP}


class KettlerPlansDiscoveryTest(unittest.TestCase):
    def test_a_building_whose_site_cannot_be_read_by_apartment_is_read_from_kettlers_plans(self):
        found = {b["name"]: b for b in finder.discover(web(SITE))}
        carlyle = found["800 Carlyle"]
        self.assertEqual((carlyle["platform"], carlyle["feed"]), ("kettler", "https://www.kettler.com/api/v1/properties#15886"))
        self.assertEqual(carlyle["url"], "https://www.800carlyle.com/")
        self.assertEqual(found["Has A Map"]["platform"], "sightmap")              # a unit map prices each apartment: better
        self.assertEqual(found["No Plans"]["platform"], "link")                   # nothing in Kettler's list either
        self.assertIn("include_floorplans=1", finder.API)


class KettlerPlansReaderTest(unittest.TestCase):
    def setUp(self):
        reader.forget()

    def building(self, pid=15886):
        return {"id": "kettler-800-carlyle", "url": "https://www.800carlyle.com/", "feed": f"https://www.kettler.com/api/v1/properties#{pid}"}

    def test_each_plan_with_apartments_free_is_one_entry_at_its_starting_price(self):
        result = READERS["kettler"](self.building(), web(SITE))
        units = {u["unit"]: u for u in result["units"]}
        self.assertEqual(sorted(units), ["B4 Den", "S2a"])                         # no price or none free: not listed
        studio = units["S2a"]
        self.assertEqual((studio["rent"], studio["beds"], studio["baths"], studio["sqft"], studio["count"], studio["plan"]),
                         (2017, 0, 1, 480, 2, "S2a"))
        self.assertEqual(studio["notes"], "2 available; the company's starting price for this floor plan")
        self.assertEqual(studio["url"], "https://www.800carlyle.com/")
        self.assertEqual((units["B4 Den"]["beds"], units["B4 Den"]["baths"], units["B4 Den"]["count"]), (2, 2.5, 1))

    def test_every_building_is_read_from_one_request_in_a_run(self):
        asked = []
        get = web(SITE, asked)
        reader.read(self.building(), get)
        reader.read(self.building(2), get)
        self.assertEqual(asked, [finder.PAGE, finder.API.format("2405")])

    def test_a_building_no_longer_in_the_list_or_a_list_that_is_not_one_fails_plainly(self):
        with self.assertRaises(NotAnswering):
            reader.read(self.building(999), web(SITE))
        reader.forget()
        with self.assertRaises(NotAnswering):
            reader.read(self.building(), web({finder.PAGE: "<html>redesigned</html>"}))

    def test_a_building_with_plans_but_nothing_free_reads_as_no_units(self):
        self.assertEqual(reader.read(self.building(3), web(SITE))["units"], [])


if __name__ == "__main__":
    unittest.main()
