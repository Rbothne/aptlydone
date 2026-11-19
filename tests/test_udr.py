"""UDR: the sitemap lists building pages; each building's pricing page carries its units as JSON."""
import os
import unittest

from aptrack import costs, discover, fetch
from aptrack.discover import udr as find
from aptrack.readers import READERS, NotAnswering, udr
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.udr.com/washington-dc-apartments/arlington/the-whitmore/"
PRICING, BUILDING = fixture("udr_pricing.html"), fixture("udr_building.html")
B = {"id": "udr-the-whitmore", "url": URL, "platform": "udr", "feed": URL + "apartments-pricing/"}
SITEMAP = ("<urlset><url><loc>https://www.udr.com/washington-dc-apartments/</loc></url>"
           "<url><loc>https://www.udr.com/washington-dc-apartments/arlington/</loc></url>"
           f"<url><loc>{URL}</loc></url><url><loc>{URL}apartments-pricing/</loc></url><url><loc>{URL}faq/pets/</loc></url>"
           "<url><loc>https://www.udr.com/baltimore-apartments/towson/20-lambourne/</loc></url>"
           "<url><loc>https://www.udr.com/washington-dc-apartments/u-street-corridor/view-14/</loc></url></urlset>")


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


class ReaderTests(unittest.TestCase):
    def test_units(self):
        units = by_unit(udr.parse(PRICING, B))
        self.assertEqual(sorted(units), ["126", "303", "308", "311", "326", "411"])
        u = units["126"]
        self.assertEqual((u["id"], u["plan"], u["beds"], u["baths"], u["sqft"], u["floor"], u["rent"], u["fees"], u["lease"], u["available"]),
                         ("udr-the-whitmore:126", "Plan E1A", 0, 1, 574, 1, 1643, None, 12, "2026-11-20"))
        self.assertEqual(u["url"], "https://www.udr.com/washington-dc-apartments/arlington/the-whitmore/apartments-pricing/apartment/?number=126")
        self.assertEqual(u["plan_image"], "https://www.udr.com/globalassets/communities/the-whitmore/floor-plans/plan-e1a---thewhitmore_1000x800_e1a_3d.gif")
        self.assertIs(u["restricted"], False)                                   # the page says so for each unit
        self.assertEqual((units["311"]["beds"], units["311"]["baths"], units["311"]["sqft"], units["326"]["lease"]), (2, 1.5, 1138, 13))

    def test_a_rent_above_the_base_rent_is_rent_plus_required_monthly_charges(self):
        page = PRICING.replace('"lowestRent": {"leaseTerm": 12, "baseRent": 1643.0, "rent": 1643.0}',
                               '"lowestRent": {"leaseTerm": 12, "baseRent": 1643.0, "rent": 1700.0}')
        self.assertNotEqual(page, PRICING)
        u = by_unit(udr.parse(page, B))["126"]
        self.assertEqual((u["rent"], u["fees"]), (1643, 57))

    def test_the_application_fee_is_a_required_one_time_fee(self):
        result = udr.parse(PRICING, B)
        self.assertEqual(costs.one_time(result["fees"]), 60)                    # the admin fee is $0 here; the deposit never counts
        self.assertEqual(costs.true_monthly(by_unit(result)["126"], result["fees"]), 1643 + 5)

    def test_an_affordable_unit_is_income_restricted_and_an_unavailable_one_is_left_out(self):
        page = PRICING.replace('"isAffordable": false', '"isAffordable": true', 1).replace('"isAvailable": true', '"isAvailable": false', 1)
        units = udr.parse(page, B)["units"]
        self.assertEqual(len(units), 5)
        self.assertEqual([u["restricted"] for u in units].count(True), 0)       # the affordable one was also the unavailable one
        page = PRICING.replace('"isAffordable": false', '"isAffordable": true', 1)
        self.assertIs(by_unit(udr.parse(page, B))["126"]["restricted"], True)

    def test_unit_numbers_repeated_across_buildings_stay_apart(self):
        page = PRICING.replace('"marketingName": "326", "building": "N/A"', '"marketingName": "126", "building": "B"')
        self.assertNotEqual(page, PRICING)
        self.assertEqual(sorted(by_unit(udr.parse(page, B))), ["B-126", "N/A-126", "N/A-303", "N/A-308", "N/A-311", "N/A-411"])

    def test_a_full_building_reads_as_no_units_and_a_page_without_data_is_not_answering(self):
        self.assertEqual(udr.parse('<script>udr.jsonObjPropertyViewModel = {"floorPlans": [], "propertyName": "X"};</script>', B)["units"], [])
        with self.assertRaises(NotAnswering):
            udr.parse("<html>Please verify you are human</html>", B)

    def test_read_fetches_the_pricing_page(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return PRICING.encode()
        self.assertEqual(len(READERS["udr"](B, get)["units"]), 6)
        self.assertEqual(asked, [URL + "apartments-pricing/"])


class DiscoverTests(QuietTestCase):
    def test_building_pages_in_the_washington_area_come_from_the_sitemap(self):
        self.assertEqual(find.building_urls(SITEMAP), [URL, "https://www.udr.com/washington-dc-apartments/u-street-corridor/view-14/"])

    def test_a_building_page_gives_name_address_coordinates_and_rating(self):
        b = find.parse(URL, BUILDING)
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["url"], b["feed"]),
                         ("udr-the-whitmore", "UDR", "The Whitmore", "udr", URL, URL + "apartments-pricing/"))
        self.assertEqual(b["address"], {"street": "4301 Columbia Pike", "city": "Arlington", "state": "VA", "zip": "22204"})
        self.assertEqual((b["lat"], b["lon"], b["rating"], b["rating_count"]), (38.8584561, -77.104797, 3.9, 157))
        self.assertIsNone(find.parse(URL, "<html></html>"))

    def test_discover_reads_each_building_and_honours_the_limit(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return (SITEMAP if url == find.SITEMAP else BUILDING).encode()
        self.assertEqual(len(discover.DISCOVERERS["udr"](get)), 2)
        self.assertEqual(asked[0], find.SITEMAP)
        self.assertEqual(len(find.discover(get, limit=1)), 1)

    def test_pages_without_their_data_stop_the_crawl(self):
        sitemap = "<urlset>" + "".join(f"<url><loc>https://www.udr.com/washington-dc-apartments/x/b{n}/</loc></url>" for n in range(9)) + "</urlset>"
        with self.assertRaises(fetch.RateLimited):
            find.discover(lambda url, **options: (sitemap if url == find.SITEMAP else "<html>Please verify you are human</html>").encode())


if __name__ == "__main__":
    unittest.main()
