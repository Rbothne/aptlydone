import os
import unittest

from aptrack import facts, history
from aptrack.facts import bozzuto, laundry

HERE = os.path.join(os.path.dirname(__file__), "fixtures")
with open(os.path.join(HERE, "bozzuto_page.html"), encoding="utf-8") as f:
    PAGE = f.read()
D1, D2, D3 = "2026-11-18", "2026-11-19", "2026-11-20"


class BozzutoFactsTests(unittest.TestCase):
    def test_parse_reads_offer_rating_neighborhood(self):
        got = bozzuto.parse(PAGE)
        self.assertEqual(got["special"], "Move in by November 30th to enjoy two months free of base rent on select units "
                                         "*Restrictions May Apply")
        self.assertEqual((got["rating"], got["rating_count"], got["neighborhood"], got["coming_soon"]),
                         (4.6, 483, "Chevy Chase", False))

    def test_parse_without_offer_has_no_special(self):
        page = PAGE.replace('hasSpecialOffer\\":true', 'hasSpecialOffer\\":false')
        self.assertNotEqual(page, PAGE)
        self.assertIsNone(bozzuto.parse(page)["special"])

    def test_coming_soon(self):
        page = PAGE.replace('isComingSoon\\":false', 'isComingSoon\\":true')
        self.assertNotEqual(page, PAGE)
        self.assertTrue(bozzuto.parse(page)["coming_soon"])

    def test_missing_rating_is_none(self):
        page = PAGE.replace('totalAvgRating\\":4.6', 'totalAvgRating\\":null').replace('totalRatingCount\\":483', 'totalRatingCount\\":null')
        got = bozzuto.parse(page)
        self.assertEqual((got["rating"], got["rating_count"]), (None, None))

    def test_parse_missing_block_is_none(self):
        self.assertIsNone(bozzuto.parse("<html><body>A redesigned page</body></html>"))

    def test_features_listed(self):
        features = bozzuto.parse(PAGE)["features"]
        self.assertIn("Bosch stainless steel appliances", features)
        self.assertIn("Hickory wood floors", features)
        self.assertEqual(len(features), len(set(features)))

    def test_read_fetches_the_building_page(self):
        asked = []

        def get(url):
            asked.append(url)
            return PAGE.encode()
        got = bozzuto.read({"id": "b", "url": "https://www.bozzuto.com/x"}, get)
        self.assertEqual((asked, got["rating"]), (["https://www.bozzuto.com/x"], 4.6))

    def test_registered_by_manager_name(self):
        self.assertIs(facts.FACTS["Bozzuto"], bozzuto.read)


class LaundryTests(unittest.TestCase):
    def test_in_unit(self):
        for text in ("Full-size washer and dryer", "In-home washer/dryer", "In-unit laundry", "Bosch washer & dryer in every home",
                     "Homes feature gourmet kitchens, full-size washer and dryer, and USB outlets."):
            self.assertEqual(laundry.detect([text]), "in_unit", text)

    def test_shared(self):
        for text in ("On-site laundry facilities", "Laundry room on every floor", "Community laundry"):
            self.assertEqual(laundry.detect([text]), "shared", text)

    def test_in_unit_wins_over_shared(self):
        self.assertEqual(laundry.detect(["Laundry room", "Washer and dryer in select homes"]), "in_unit")

    def test_unknown(self):
        self.assertIsNone(laundry.detect(["Hickory wood floors", "Quartz countertops"]))
        self.assertIsNone(laundry.detect([]))
        self.assertIsNone(laundry.detect(["Dry cleaning pickup", "Car wash station"]))


class SpecialSeriesTests(unittest.TestCase):
    def test_special_series_changes_only(self):
        state = history.new_state()
        history.record(state, "b", [], D1)
        history.record_special(state, "b", "1 month free", D1)
        history.record_special(state, "b", "1 month free", D2)
        history.record_special(state, "b", None, D3)
        self.assertEqual(state["buildings"]["b"]["specials"], [[D1, "1 month free"], [D3, None]])

    def test_special_series_survives_later_reads(self):
        state = history.new_state()
        history.record(state, "b", [], D1)
        history.record_special(state, "b", "1 month free", D1)
        history.record(state, "b", [], D2)
        history.record_failure(state, "b", D3)
        self.assertEqual(state["buildings"]["b"]["specials"], [[D1, "1 month free"]])
        self.assertEqual((state["buildings"]["b"]["ok"], state["buildings"]["b"]["failed"]), (D2, D3))

    def test_same_day_change_overwrites(self):
        state = history.new_state()
        history.record_special(state, "b", "1 month free", D1)
        history.record_special(state, "b", "2 months free", D1)
        self.assertEqual(state["buildings"]["b"]["specials"], [[D1, "2 months free"]])

    def test_no_special_ever_leaves_an_empty_series(self):
        state = history.new_state()
        history.record_special(state, "b", None, D1)
        self.assertEqual(state["buildings"]["b"]["specials"], [])


if __name__ == "__main__":
    unittest.main()
