import os
import unittest

from aptrack import costs, discover, fetch
from aptrack.discover import avalon as find
from aptrack.readers import READERS, NotAnswering, avalon
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.avaloncommunities.com/district-of-columbia/washington-apartments/avalon-at-foxhall/"
PAGE = fixture("avalon_community.html")
B = {"id": "avalonbay-avalon-at-foxhall", "url": URL, "platform": "avalon", "feed": URL}


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


class ReaderTests(unittest.TestCase):
    def test_units(self):
        u = by_unit(avalon.parse(PAGE, B))["209"]
        self.assertEqual((u["id"], u["plan"], u["beds"], u["baths"], u["sqft"], u["floor"], u["rent"], u["fees"], u["lease"], u["available"]),
                         ("avalonbay-avalon-at-foxhall:209", "S1", 0, 1, 550, 2, 1790, 58, 14, "2027-01-01"))
        self.assertIn("/apartment/", u["url"])

    def test_a_units_own_promotion_is_its_special_and_counts_in_the_true_cost(self):
        units = by_unit(avalon.parse(PAGE, B))
        self.assertIsNone(units["209"]["special"])
        self.assertIn("1.5 months off", units["611"]["special"])
        self.assertEqual(costs.free_months(units["611"]["special"]), 1.5)
        self.assertEqual(costs.true_monthly(units["611"], []), round(1851 * (15 - 1.5) / 15 + 58))

    def test_characteristics_become_notes(self):
        self.assertEqual(by_unit(avalon.parse(PAGE, B))["LT08"]["notes"], "With Den")

    def test_facts_from_the_same_page(self):
        result = avalon.parse(PAGE, B)
        facts = result["facts"]
        self.assertEqual((facts["rating"], facts["rating_count"], facts["pets"], facts["parking"], facts["special"]), (4.4, 278, True, True, None))
        self.assertIn("In-Unit Washer/Dryer", facts["features"])
        self.assertIn("Concierge", result["amenities"])
        self.assertEqual(result["fees"], [])

    def test_page_without_its_data_means_the_site_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            avalon.parse("<html>Access denied</html>", B)

    def test_a_community_with_no_units_is_an_empty_list(self):
        page = PAGE.replace('"units": [', '"units_were": [', 1)
        self.assertNotEqual(page, PAGE)
        self.assertEqual(avalon.parse(page, B)["units"], [])

    def test_read_and_registration(self):
        asked = []

        def get(url):
            asked.append(url)
            return PAGE.encode()
        self.assertEqual(len(avalon.read(B, get)["units"]), 3)
        self.assertEqual(asked, [URL])
        self.assertIs(READERS["avalon"], avalon.read)


class DiscoverTests(QuietTestCase):
    def test_community_pages_in_the_region_only(self):
        urls = find.building_urls(fixture("avalon_sitemap.xml"))
        self.assertEqual(len(urls), 4)
        self.assertIn(URL, urls)
        self.assertFalse([u for u in urls if "california" in u or u.endswith("washington-apartments/")])

    def test_parse(self):
        b = find.parse(URL, PAGE)
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"], b["url"]),
                         ("avalonbay-avalon-at-foxhall", "AvalonBay", "Avalon at Foxhall", "avalon", URL, URL))
        self.assertEqual(b["address"], {"street": "4100 Massachusetts Avenue N.W.", "city": "Washington", "state": "DC", "zip": "20016"})
        self.assertAlmostEqual(b["lat"], 38.9334125, places=5)
        self.assertAlmostEqual(b["lon"], -77.0818578, places=5)

    def test_parse_page_without_data_is_none(self):
        self.assertIsNone(find.parse(URL, "<html></html>"))

    def test_discover(self):
        def get(url):
            pages = {find.SITEMAP: fixture("avalon_sitemap.xml"), URL: PAGE}
            if url not in pages:
                raise fetch.Gone(url)
            return pages[url].encode()
        self.assertEqual([b["id"] for b in find.discover(get)], ["avalonbay-avalon-at-foxhall"])
        self.assertIs(discover.DISCOVERERS["avalon"], find.discover)


if __name__ == "__main__":
    unittest.main()
