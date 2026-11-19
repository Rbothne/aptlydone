"""Equity Residential: one regional page lists every building; each building page carries its units as JSON."""
import os
import subprocess
import sys
import unittest

from aptrack import costs, discover, fetch
from aptrack.discover import equity as find
from aptrack.readers import READERS, NotAnswering, equity
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.equityapartments.com/washington-dc/northwest-dc/1210-mass-apartments"
PAGE, MARKET = fixture("equity_building.html"), fixture("equity_market.html")
B = {"id": "equity-residential-1210-mass-apartments", "url": URL, "platform": "equity", "feed": URL}


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


class ReaderTests(unittest.TestCase):
    def test_units(self):
        units = by_unit(equity.parse(PAGE, B))
        self.assertEqual(sorted(units), ["0407", "0411", "0703", "1305"])
        u = units["0407"]
        self.assertEqual((u["id"], u["plan"], u["beds"], u["baths"], u["sqft"], u["floor"], u["rent"], u["lease"], u["available"], u["url"]),
                         ("equity-residential-1210-mass-apartments:0407", "Providence", 0, 1, 523, 4, 2381, 12, "2026-12-16", URL))
        self.assertTrue(u["plan_image"].startswith("https://media.equityapartments.com/"))
        self.assertIsNone(u["restricted"])

    def test_required_monthly_charges_are_the_units_fees_and_estimated_utilities_are_not(self):
        self.assertEqual(by_unit(equity.parse(PAGE, B))["0407"]["fees"], 65 + 25)        # connectivity and tech package; not water, sewer, electric

    def test_a_units_special_counts_in_its_true_cost(self):
        result = equity.parse(PAGE, B)
        u = by_unit(result)["0407"]
        self.assertEqual(u["special"], "Save $500 Off Move-In!")
        self.assertEqual(costs.dollars_off(u["special"]), 500)
        self.assertEqual(costs.one_time(result["fees"]), 50 + 50 + 500)                  # application, amenity, move-in; never the deposit
        self.assertEqual(costs.true_monthly(u, result["fees"]), round(2381 + 90 + (600 - 500) / 12))

    def test_an_expired_or_switched_off_special_is_not_one(self):
        page = PAGE.replace('"Active": true', '"Active": false')
        self.assertNotEqual(page, PAGE)
        self.assertIsNone(by_unit(equity.parse(page, B))["0407"]["special"])

    def test_optional_charges_give_parking_and_pets(self):
        result = equity.parse(PAGE, B)
        self.assertEqual(costs.parking_from(result["fees"]), 250)
        self.assertTrue(costs.pets_allowed(result["fees"]))
        self.assertEqual((result["facts"]["rating"], result["facts"]["rating_count"], result["facts"]["pets"], result["facts"]["parking"]),
                         (4.5, 1315, True, True))
        self.assertIsNone(result["facts"]["special"])                                    # specials sit on the units they apply to

    def test_a_unit_marked_affordable_is_income_restricted(self):
        page = PAGE.replace('"AFFORDABLE": null', '"AFFORDABLE": "Y"', 1)
        self.assertNotEqual(page, PAGE)
        flags = [u["restricted"] for u in equity.parse(page, B)["units"]]
        self.assertEqual(flags.count(True), 1)

    def test_a_unit_marked_not_affordable_is_market_rate(self):
        # live pages carry "N", " " or nothing; "N" must never read as income-restricted
        page = PAGE.replace('"AFFORDABLE": null', '"AFFORDABLE": "N"', 1).replace('"AFFORDABLE": null', '"AFFORDABLE": " "', 1)
        self.assertEqual([u["restricted"] for u in equity.parse(page, B)["units"]], [False, None, None, None])

    def test_unit_numbers_repeated_across_a_propertys_buildings_stay_apart(self):
        page = PAGE.replace('"UnitId": "0411", "BuildingId": "01"', '"UnitId": "0407", "BuildingId": "02"')
        self.assertNotEqual(page, PAGE)
        self.assertEqual(sorted(by_unit(equity.parse(page, B))), ["01-0407", "01-0703", "01-1305", "02-0407"])

    def test_a_full_building_reads_as_no_units_not_as_a_failure(self):
        page = '<script>ea5.property = {"Name": "X"};\nea5.unitAvailability = {"BedroomTypes": [{"Id": 0, "AvailableUnits": []}]};</script>'
        result = equity.parse(page, B)
        self.assertEqual((result["units"], result["fees"]), ([], []))

    def test_a_page_without_its_data_is_not_answering(self):
        with self.assertRaises(NotAnswering):
            equity.parse("<html>Please verify you are human</html>", B)

    def test_the_readers_load_without_the_discoverers(self):
        # build.py imports the readers first; a reader that reaches into the discoverers breaks that order
        root = os.path.dirname(os.path.dirname(__file__))
        done = subprocess.run([sys.executable, "-c", "import aptrack.readers"], cwd=root, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_read_fetches_the_building_page(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return PAGE.encode()
        self.assertEqual(len(READERS["equity"](B, get)["units"]), 4)
        self.assertEqual(asked, [URL])


class DiscoverTests(QuietTestCase):
    def test_buildings_come_from_the_regional_page(self):
        found = find.parse(MARKET)
        self.assertEqual([b["id"] for b in found],
                         ["equity-residential-2400-m-apartments", "equity-residential-1210-mass-apartments",
                          "equity-residential-1800-oak-apartments", "equity-residential-edgemont-at-bethesda-metro-apartments"])
        b = found[0]
        self.assertEqual((b["manager"], b["name"], b["platform"], b["url"], b["feed"]),
                         ("Equity Residential", "2400 M Apartments", "equity",
                          "https://www.equityapartments.com/washington-dc/georgetown/2400-m-apartments",
                          "https://www.equityapartments.com/washington-dc/georgetown/2400-m-apartments"))
        self.assertEqual(b["address"], {"street": "2400 M Street NW", "city": "Washington", "state": "DC", "zip": "20037"})
        self.assertAlmostEqual(b["lat"], 38.9053, places=3)
        self.assertAlmostEqual(b["lon"], -77.0514, places=3)

    def test_other_companies_buildings_advertised_on_the_page_are_left_out(self):
        self.assertIn("avaloncommunities.com", MARKET)
        self.assertFalse([b for b in find.parse(MARKET) if "avalon" in b["url"]])

    def test_discover_asks_for_one_page_and_honours_the_limit(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return MARKET.encode()
        self.assertEqual(len(discover.DISCOVERERS["equity"](get)), 4)
        self.assertEqual(asked, [find.MARKET])
        self.assertEqual(len(find.discover(get, limit=2)), 2)

    def test_a_page_without_the_list_is_a_failure_not_an_empty_company(self):
        with self.assertRaises(fetch.RateLimited):
            find.discover(lambda url, **options: b"<html>Please verify you are human</html>")


if __name__ == "__main__":
    unittest.main()
