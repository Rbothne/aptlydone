import json
import unittest

from aptrack import area
from aptrack.area import places
from tests.quiet import QuietTestCase

MILE = 1 / 69.0


def node(lat, lon=-77.0):
    return {"type": "node", "id": 1, "lat": lat, "lon": lon, "tags": {}}


def way(minlat, maxlat, minlon=-77.01, maxlon=-76.99):
    return {"type": "way", "id": 2, "bounds": {"minlat": minlat, "minlon": minlon, "maxlat": maxlat, "maxlon": maxlon}, "tags": {}}


class ShapesTests(unittest.TestCase):
    def test_nodes_and_bounded_ways_become_boxes(self):
        shapes = places.shapes({"elements": [node(38.9), way(38.95, 38.97), {"type": "way", "id": 3, "center": {"lat": 39.0, "lon": -77.0}},
                                             {"type": "way", "id": 4}]})
        self.assertEqual(shapes, [(38.9, -77.0, 38.9, -77.0), (38.95, -77.01, 38.97, -76.99), (39.0, -77.0, 39.0, -77.0)])

    def test_distance_is_zero_inside_and_measured_to_the_edge_outside(self):
        box = (38.95, -77.01, 38.97, -76.99)
        self.assertEqual(places.miles_to(38.96, -77.0, box), 0)
        self.assertAlmostEqual(places.miles_to(38.95 - 0.5 * MILE, -77.0, box), 0.5, places=2)
        self.assertAlmostEqual(places.miles_to(38.9, -77.0, (38.9 + MILE, -77.0, 38.9 + MILE, -77.0)), 1.0, places=2)

    def test_query_asks_for_extents_inside_the_box(self):
        q = places.query("park", (38.5, -77.7, 39.4, -76.4))
        self.assertIn('way["leisure"="park"](38.5,-77.7,39.4,-76.4);', q)
        self.assertTrue(q.startswith("[out:json]"))
        self.assertTrue(q.rstrip().endswith("out tags bb;"))
        self.assertEqual(set(places.CATEGORIES), {"park", "dog_park", "community", "library", "grocery", "metro", "food", "gym", "pharmacy"})

    def test_bbox_covers_the_buildings_with_a_margin(self):
        box = places.bbox([{"lat": 38.9, "lon": -77.1}, {"lat": 39.0, "lon": -77.0}, {"lat": None, "lon": None}])
        self.assertLess(box[0], 38.9)
        self.assertGreater(box[2], 39.0)
        self.assertLess(box[1], -77.1)
        self.assertGreater(box[3], -77.0)


class NearTests(unittest.TestCase):
    def test_count_within_half_a_mile_and_the_nearest(self):
        buildings = [{"id": "a", "lat": 38.9, "lon": -77.0}, {"id": "nowhere", "lat": None, "lon": None}]
        found = {"park": [(38.9 + 0.1 * MILE, -77.0) * 2, (38.9 + 0.4 * MILE, -77.0) * 2, (38.9 + 0.9 * MILE, -77.0) * 2],
                 "metro": [(38.9 + 1.5 * MILE, -77.0) * 2], "grocery": [(38.9 + 3 * MILE, -77.0) * 2], "library": []}
        self.assertEqual(places.near(buildings, found), {"a": {"park": [2, 0.1], "metro": [0, 1.5], "grocery": [0, None], "library": [0, None]}})


class FetchTests(QuietTestCase):
    def test_each_category_is_asked_for_and_a_failed_one_is_left_out(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            if "dog_park" in url:
                raise OSError("busy")
            return json.dumps({"elements": [node(38.9)]}).encode()
        found = places.fetch_all(get, (38.5, -77.7, 39.4, -76.4), sleep=lambda s: None)
        self.assertEqual(set(found), set(places.CATEGORIES) - {"dog_park"})
        self.assertEqual(found["park"], [(38.9, -77.0, 38.9, -77.0)])
        self.assertEqual(len([u for u in asked if "dog_park" in u]), len(places.OVERPASS))       # each mirror was tried once

    def test_walkability_from_the_epa_index(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return json.dumps({"features": [{"attributes": {"NatWalkInd": 16.833333}}]}).encode()
        self.assertEqual(places.walkability(get, 38.96, -77.07), 16.8)
        self.assertIn("geometry=-77.07%2C38.96", asked[0])
        self.assertIsNone(places.walkability(lambda url, **o: b'{"features": []}', 38.96, -77.07))

    def test_walk_label(self):
        self.assertEqual([places.walk_label(s) for s in (3, 8, 12, 17.5, None)],
                         ["Least walkable", "Below average", "Above average", "Most walkable", None])


class DogTests(unittest.TestCase):
    def test_unknown_or_no_pets_means_no_score(self):
        self.assertIsNone(places.dog_score(None, [], {"dog_park": [1, 0.1]}))

    def test_points_for_pets_dog_parks_parks_and_on_site_amenities(self):
        near = {"dog_park": [1, 0.3], "park": [3, 0.1]}
        got = places.dog_score(True, ["Rooftop pool", "Dog run and pet spa"], near)
        self.assertEqual(got["score"], 5)
        self.assertEqual(got["reasons"], ["pets allowed", "dog park 0.3 mi", "park 0.1 mi", "pet amenities on site"])

    def test_a_farther_dog_park_counts_for_less(self):
        self.assertEqual(places.dog_score(True, [], {"dog_park": [0, 0.8], "park": [0, 0.6]}), {"score": 2, "reasons": ["pets allowed", "dog park 0.8 mi"]})
        self.assertEqual(places.dog_score(True, [], {}), {"score": 1, "reasons": ["pets allowed"]})
        self.assertEqual(places.dog_score(True, [], None), {"score": 1, "reasons": ["pets allowed"]})


class CollectTests(QuietTestCase):
    def web(self, fail_category=None):
        calls = {"epa": 0}

        def get(url, **options):
            if "WalkabilityIndex" in url:
                calls["epa"] += 1
                return json.dumps({"features": [{"attributes": {"NatWalkInd": 15.0}}]}).encode()
            if "interpreter" in url:
                if fail_category and fail_category in url:
                    raise OSError("busy")
                return json.dumps({"elements": [node(38.9 + 0.2 * MILE)]}).encode()
            raise OSError("not part of this test")
        return get, calls

    def buildings(self):
        return [{"id": "a", "county": "11001", "lat": 38.9, "lon": -77.0, "tract": "1", "address": {"zip": "20001"}, "in_region": True}]

    def test_collect_adds_places_and_walkability(self):
        get, calls = self.web()
        got = area.collect(self.buildings(), {}, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual(got["places"]["a"]["park"], [1, 0.2])
        self.assertEqual(got["walk"], {"a": 15.0})
        self.assertEqual(calls["epa"], 1)

    def test_walkability_is_only_looked_up_once_per_building(self):
        get, calls = self.web()
        area.collect(self.buildings(), {"walk": {"a": 12.3}}, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual(calls["epa"], 0)

    def test_a_category_that_failed_keeps_last_weeks_numbers(self):
        get, _ = self.web(fail_category="dog_park")
        previous = {"places": {"a": {"dog_park": [2, 0.3], "park": [9, 0.0]}}}
        got = area.collect(self.buildings(), previous, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual(got["places"]["a"]["dog_park"], [2, 0.3])
        self.assertEqual(got["places"]["a"]["park"], [1, 0.2])


if __name__ == "__main__":
    unittest.main()
