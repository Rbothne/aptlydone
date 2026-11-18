import os
import unittest

from aptrack import discover, fetch, units
from aptrack.discover import rentpress as find
from aptrack.readers import READERS, NotAnswering, rentpress
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://wcsmith.com/apartments/clarence-house/"
PAGE = fixture("rentpress_building.html")
B = {"id": "wc-smith-clarence-house", "url": URL, "platform": "rentpress", "feed": URL}


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


class PlanLevelUnitTests(unittest.TestCase):
    def test_count_is_part_of_the_common_format_and_empty_for_ordinary_units(self):
        self.assertIsNone(units.make_unit("b", "1", rent=2000)["count"])
        self.assertEqual(units.make_unit("b", "Studio A", rent=1550, count="3")["count"], 3)

    def test_each_available_floor_plan_is_one_entry_at_its_lowest_rent(self):
        got = by_unit(rentpress.parse(PAGE, B))
        self.assertEqual(set(got), {"Studio A", "2 Bed 1.5 Bath A - Tiers 02 + 03", "Studio B"})
        u = got["Studio A"]
        self.assertEqual((u["id"], u["plan"], u["beds"], u["baths"], u["sqft"], u["rent"], u["count"], u["floor"], u["available"]),
                         ("wc-smith-clarence-house:Studio A", "Studio A", 0, 1, 500, 1550, 3, None, None))
        self.assertEqual(u["notes"], "3 available, $1,550 to $1,655")
        self.assertTrue(u["plan_image"].startswith("https://"))
        self.assertEqual(got["Studio B"]["notes"], "1 available")

    def test_plans_with_nothing_available_or_no_rent_are_left_out(self):
        self.assertNotIn("1 Bedroom B - Tier 00", by_unit(rentpress.parse(PAGE, B)))

    def test_facts(self):
        result = rentpress.parse(PAGE, B)
        facts = result["facts"]
        self.assertEqual((facts["neighborhood"], facts["pets"], facts["parking"], facts["special"], facts["rating"]),
                         ("Van Ness / Wakefield", True, True, None, None))
        self.assertIn("Concierge", facts["features"])
        self.assertIn("Concierge", result["amenities"])

    def test_a_building_described_as_income_restricted_marks_its_units(self):
        page = PAGE.replace("Looking for a studio", "An income-restricted community. Looking for a studio")
        self.assertNotEqual(page, PAGE)
        self.assertTrue(all(u["restricted"] is True for u in rentpress.parse(page, B)["units"]))
        self.assertTrue(all(u["restricted"] is None for u in rentpress.parse(PAGE, B)["units"]))

    def test_page_without_its_data_means_the_site_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            rentpress.parse("<html>nothing</html>", B)

    def test_read_and_registration(self):
        self.assertEqual(len(rentpress.read(B, lambda url: PAGE.encode())["units"]), 3)
        self.assertIs(READERS["rentpress"], rentpress.read)


class DiscoverTests(QuietTestCase):
    def test_urls(self):
        urls = find.building_urls(fixture("rentpress_sitemap.xml"), "wcsmith.com")
        self.assertEqual(len(urls), 5)
        self.assertIn(URL, urls)

    def test_parse(self):
        b = find.parse(URL, PAGE, "WC Smith")
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"]),
                         ("wc-smith-clarence-house", "WC Smith", "Clarence House", "rentpress", URL))
        self.assertEqual(b["address"], {"street": "4530 Connecticut Ave NW", "city": "Washington", "state": "DC", "zip": "20008"})
        self.assertAlmostEqual(b["lat"], 38.949025, places=5)
        self.assertAlmostEqual(b["lon"], -77.066925, places=5)

    def test_parse_page_without_data_is_none(self):
        self.assertIsNone(find.parse(URL, "<html></html>", "WC Smith"))

    def test_wc_smith_is_registered(self):
        asked = []

        def get(url):
            asked.append(url)
            pages = {"https://wcsmith.com/rentpress_property-sitemap.xml": fixture("rentpress_sitemap.xml"), URL: PAGE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        found = discover.DISCOVERERS["wcsmith"](get, limit=1)
        self.assertEqual([b["id"] for b in found], ["wc-smith-clarence-house"])


if __name__ == "__main__":
    unittest.main()
