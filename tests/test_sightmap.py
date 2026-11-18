import copy
import json
import os
import unittest

from aptrack import fetch, units
from aptrack.readers import READERS, ReadError, sightmap

HERE = os.path.join(os.path.dirname(__file__), "fixtures")
def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


EMBED = fixture("sightmap_embed.html")
FEED_TEXT = fixture("sightmap_feed.json")
FEED = json.loads(FEED_TEXT)
API = "https://sightmap.com/app/api/v1/rxwj9mldp1e/sightmaps/27596"
B = {"id": "bozzuto-5333-connecticut", "url": "https://www.bozzuto.com/apartments-for-rent/dc/washington/5333-connecticut",
     "platform": "sightmap", "feed": "https://sightmap.com/embed/8ywkoe19vlx"}


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


class MakeUnitTests(unittest.TestCase):
    def test_keys_are_the_common_format(self):
        u = units.make_unit("b", "1", rent=2000)
        self.assertEqual(list(u), ["id", "building", "unit", "floor", "plan", "beds", "baths", "sqft", "rent", "fees",
                                   "lease", "available", "special", "notes", "url", "restricted", "plan_image"])
        self.assertEqual((u["id"], u["building"], u["unit"]), ("b:1", "b", "1"))

    def test_no_rent_means_no_unit(self):
        for rent in (None, 0, "", "call"):
            self.assertIsNone(units.make_unit("b", "1", rent=rent))

    def test_studio_and_missing_sqft_are_kept(self):
        u = units.make_unit("b", "1", rent=1800, beds="Studio", sqft=0)
        self.assertEqual((u["beds"], u["sqft"]), (0, None))

    def test_numeric_strings_become_numbers(self):
        u = units.make_unit("b", "1", rent="2,150.00", beds="2", baths="1.5", sqft="900")
        self.assertEqual((u["rent"], u["beds"], u["baths"], u["sqft"]), (2150, 2, 1.5, 900))

    def test_available_is_trimmed_to_the_date(self):
        u = units.make_unit("b", "1", rent=1800, available="2026-12-18T00:00:00.000Z")
        self.assertEqual(u["available"], "2026-12-18")


class FeedUrlTests(unittest.TestCase):
    def test_feed_url_found_in_embed_page(self):
        self.assertEqual(sightmap.feed_url(EMBED), API)

    def test_feed_url_with_escaped_slashes(self):
        self.assertEqual(sightmap.feed_url(EMBED.replace("/", "\\/")), API)

    def test_feed_url_absent(self):
        self.assertIsNone(sightmap.feed_url("<html>nothing here</html>"))


class ParseTests(unittest.TestCase):
    def test_units_use_common_format(self):
        u = by_unit(sightmap.parse(FEED, B))["204"]
        self.assertEqual((u["id"], u["sqft"], u["rent"], u["beds"], u["baths"], u["available"], u["floor"]),
                         ("bozzuto-5333-connecticut:204", 530, 2196, 1, 1, "2026-11-30", 2))
        self.assertEqual(u["url"], B["url"])

    def test_plan_name_wrapped_in_json_is_unwrapped(self):
        self.assertEqual(by_unit(sightmap.parse(FEED, B))["204"]["plan"], "1 Bed 1 Bath JR B")

    def test_lease_falls_back_to_the_feeds_flat_term(self):
        self.assertEqual(by_unit(sightmap.parse(FEED, B))["204"]["lease"], 12)

    def test_fees_are_total_minus_rent(self):
        feed = copy.deepcopy(FEED)
        next(u for u in feed["data"]["units"] if u["unit_number"] == "204")["total_price"] = [2250, 2250]
        self.assertEqual(by_unit(sightmap.parse(feed, B))["204"]["fees"], 54)

    def test_unpriced_unit_is_skipped(self):
        self.assertNotIn("999", by_unit(sightmap.parse(FEED, B)))

    def test_duplicate_unit_numbers_get_distinct_ids(self):
        result = sightmap.parse(FEED, B)
        ids = [u["id"] for u in result["units"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({u["unit"] for u in result["units"] if u["sqft"] == 827}, {"1-215", "2-215"})

    def test_same_unit_listed_twice_appears_once(self):
        feed = copy.deepcopy(FEED)
        feed["data"]["units"].append(copy.deepcopy(next(u for u in feed["data"]["units"] if u["unit_number"] == "204")))
        ids = [u["id"] for u in sightmap.parse(feed, B)["units"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_units_unpriced_raises_read_error(self):
        feed = copy.deepcopy(FEED)
        for u in feed["data"]["units"]:
            u["price"] = None
        with self.assertRaises(ReadError):
            sightmap.parse(feed, B)

    def test_no_units_is_an_empty_list_not_an_error(self):
        feed = copy.deepcopy(FEED)
        feed["data"]["units"] = []
        self.assertEqual(sightmap.parse(feed, B)["units"], [])

    def test_fees_list_marks_required_and_amount(self):
        fees = {f["label"]: f for f in sightmap.parse(FEED, B)["fees"]}
        parking = fees["Parking - Reserved"]
        self.assertEqual((parking["required"], parking["amount"], parking["type"], parking["category"]),
                         (False, 225.0, "assigned_parking", "rentable_items"))
        self.assertTrue(fees["Utility - Water Service"]["required"])
        self.assertIsNone(fees["Utility - Water Service"]["amount"])

    def test_amenities_are_stripped_titles(self):
        amenities = sightmap.parse(FEED, B)["amenities"]
        self.assertIn("Business Center", amenities)
        self.assertIn("Concierge", amenities)


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.fetched = []

    def get(self, url):
        self.fetched.append(url)
        if url == B["feed"]:
            return EMBED.encode()
        if url == API:
            return FEED_TEXT.encode()
        raise fetch.Gone(url)

    def test_read_resolves_and_returns_feed_api(self):
        result = sightmap.read(dict(B), self.get)
        self.assertEqual(result["feed_api"], API)
        self.assertEqual(self.fetched, [B["feed"], API])
        self.assertEqual(len(result["units"]), 5)

    def test_cached_feed_api_skips_the_embed_page(self):
        sightmap.read(dict(B, feed_api=API), self.get)
        self.assertEqual(self.fetched, [API])

    def test_stale_feed_api_is_resolved_again(self):
        result = sightmap.read(dict(B, feed_api=API + "0"), self.get)
        self.assertEqual(result["feed_api"], API)

    def test_embed_without_feed_raises_read_error(self):
        with self.assertRaises(ReadError):
            sightmap.read(dict(B), lambda url: b"<html></html>")

    def test_registered(self):
        self.assertIs(READERS["sightmap"], sightmap.read)


if __name__ == "__main__":
    unittest.main()
