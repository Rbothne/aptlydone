import json
import os
import tempfile
import unittest
import urllib.error

from aptrack import area, output
from aptrack.area import google
from aptrack.fetch import Gone
from tests.quiet import QuietTestCase

TODAY = "2026-11-24"


def building(building_id="b1", name="The Sterling", lat=38.9000, lon=-77.0300, **more):
    return dict({"id": building_id, "name": name, "lat": lat, "lon": lon, "in_region": True, "county": "11001",
                 "address": {"street": "1 Main St", "city": "Washington", "state": "DC", "zip": "20001"}}, **more)


def place(place_id, name, lat, lon):
    return {"id": place_id, "displayName": {"text": name}, "location": {"latitude": lat, "longitude": lon}}


class Google:
    """A stand-in for the Places API: answers searches from `places`, details from `ratings`."""

    def __init__(self, places, ratings, refuse=False):
        self.places, self.ratings, self.refuse, self.calls = places, ratings, refuse, []

    def __call__(self, url, data=None, headers=None, **options):
        self.calls.append((url, json.loads(data) if data else None, headers))
        if self.refuse:
            raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)
        if url == google.SEARCH:
            return json.dumps({"places": self.places}).encode()
        place_id = url[len(google.DETAILS):]
        if place_id not in self.ratings:
            raise Gone(url)
        return json.dumps(self.ratings[place_id]).encode()


class PickTests(unittest.TestCase):
    def test_a_close_result_sharing_a_name_word_is_taken(self):
        got = google.pick(building(), [place("far", "The Sterling", 38.95, -77.03), place("p1", "Sterling Apartments", 38.9010, -77.0300)])
        self.assertEqual(got["id"], "p1")

    def test_a_differently_named_result_must_be_on_the_spot(self):
        self.assertIsNone(google.pick(building(), [place("x", "Joe's Pizza", 38.9015, -77.0300)]))      # about 170 m
        self.assertEqual(google.pick(building(), [place("y", "1 Main St", 38.9003, -77.0300)])["id"], "y")

    def test_a_named_match_beats_a_nearer_unnamed_one(self):
        got = google.pick(building(), [place("y", "Leasing office", 38.9001, -77.0300), place("p1", "Sterling", 38.9015, -77.0300)])
        self.assertEqual(got["id"], "p1")

    def test_filler_words_do_not_count_as_a_shared_name(self):
        self.assertIsNone(google.pick(building(name="The Park Apartments"), [place("x", "Park Apartments West", 38.9020, -77.03)]))

    def test_query_is_name_and_address(self):
        self.assertEqual(google.query(building()), "The Sterling, 1 Main St, Washington, DC 20001")


class CollectTests(QuietTestCase):
    def test_finds_once_then_only_refreshes_the_rating(self):
        api = Google([place("p1", "Sterling", 38.9001, -77.03)],
                     {"p1": {"rating": 4.26, "userRatingCount": 311, "googleMapsUri": "https://maps.google.com/?cid=1", "displayName": {"text": "The Sterling"}}})
        got = google.collect([building()], {}, api, "KEY", TODAY)
        self.assertEqual(got["b1"]["place"], "p1")
        self.assertEqual((got["b1"]["rating"], got["b1"]["count"], got["b1"]["at"]), (4.3, 311, TODAY))
        self.assertEqual(api.calls[0][2]["X-Goog-FieldMask"], google.SEARCH_FIELDS)
        self.assertEqual(api.calls[0][1]["locationBias"]["circle"]["center"], {"latitude": 38.9, "longitude": -77.03})
        self.assertEqual(api.calls[1][2]["X-Goog-FieldMask"], google.DETAILS_FIELDS)

        api.calls.clear()
        api.ratings["p1"]["rating"] = 4.1
        again = google.collect([building()], got, api, "KEY", "2026-12-01")
        self.assertEqual([c[0] for c in api.calls], [google.DETAILS + "p1"])        # no search the second time
        self.assertEqual((again["b1"]["rating"], again["b1"]["at"]), (4.1, "2026-12-01"))

    def test_no_match_is_retried_only_after_four_weeks(self):
        api = Google([], {})
        got = google.collect([building()], {}, api, "KEY", TODAY)
        self.assertEqual(got["b1"]["place"], None)
        api.calls.clear()
        google.collect([building()], got, api, "KEY", "2026-12-08")
        self.assertEqual(api.calls, [])
        google.collect([building()], got, api, "KEY", "2026-12-23")
        self.assertEqual(len(api.calls), 1)

    def test_a_forgotten_place_is_searched_for_again(self):
        api = Google([place("p2", "Sterling", 38.9001, -77.03)], {"p2": {"rating": 3.9, "userRatingCount": 12}})
        before = {"b1": {"place": "old", "rating": 4.0, "near": [38.9, -77.03], "tried": "2026-10-01"}}
        got = google.collect([building()], before, api, "KEY", TODAY, gone=Gone)
        self.assertNotIn("place", got["b1"])
        got = google.collect([building()], got, api, "KEY", TODAY, gone=Gone)
        self.assertEqual((got["b1"]["place"], got["b1"]["rating"]), ("p2", 3.9))

    def test_a_moved_building_is_matched_again(self):
        api = Google([place("p2", "Sterling", 38.9101, -77.03)], {"p2": {"rating": 4.5}})
        before = {"b1": {"place": "p1", "rating": 4.0, "near": [38.9, -77.03]}}
        got = google.collect([building(lat=38.91)], before, api, "KEY", TODAY)
        self.assertEqual(got["b1"]["place"], "p2")

    def test_a_refused_key_stops_early_and_keeps_what_was_there(self):
        api = Google([], {}, refuse=True)
        many = [building(f"b{i}") for i in range(20)]
        before = {"b3": {"place": "p3", "rating": 4.4, "near": [38.9, -77.03]}}
        got = google.collect(many, before, api, "KEY", TODAY)
        self.assertEqual(len(api.calls), google.GIVE_UP_AFTER)
        self.assertEqual(got["b3"]["rating"], 4.4)

    def test_area_collect_skips_google_without_a_key(self):
        def get(url, **options):
            raise AssertionError("nothing should be asked")
        got = area.collect([building()], {"google": {"b1": {"rating": 4.0}}}, get, TODAY, "now", parts=("google",))
        self.assertEqual(got["google"], {"b1": {"rating": 4.0}})


class OutputTests(unittest.TestCase):
    def test_google_rating_takes_the_place_of_the_managers(self):
        entry = {"rating": 4.8, "rating_count": 40}
        output.rate(entry, {"rating": 3.9, "count": 211, "url": "https://maps.google.com/?cid=1", "at": TODAY})
        self.assertEqual((entry["rating"], entry["rating_count"], entry["rating_source"]), (3.9, 211, "google"))
        self.assertEqual((entry["manager_rating"], entry["manager_rating_count"]), (4.8, 40))

    def test_manager_rating_stays_when_google_has_none(self):
        entry = {"rating": 4.8, "rating_count": 40}
        output.rate(entry, {"place": "p1", "rating": None})
        self.assertEqual((entry["rating"], entry["rating_source"]), (4.8, "manager"))
        bare = {"rating": None}
        output.rate(bare, None)
        self.assertIsNone(bare["rating_source"])

    def test_an_unread_building_keeps_the_managers_rating_not_last_times_google_one(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "index.json"), "w") as f:
                json.dump({"buildings": [{"id": "b1", "county": "11001", "rating": 3.9, "rating_count": 211, "rating_source": "google",
                                          "manager_rating": 4.8, "manager_rating_count": 40}]}, f)
            state = {"buildings": {"b1": {"failed": True, "ok": TODAY}}, "units": {}}
            entries, _ = output.assemble([building()], {}, state, out, today=TODAY)
        self.assertEqual((entries[0]["rating"], entries[0]["rating_count"]), (4.8, 40))


if __name__ == "__main__":
    unittest.main()
