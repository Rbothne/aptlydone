import json
import unittest

from aptrack import area
from aptrack.area import places
from tests import shapefiles
from tests.quiet import QuietTestCase

MILE = 1 / 69.0
BOX = (38.5, -77.7, 39.4, -76.4)
LAYERS = ("gis_osm_pois_free_1", "gis_osm_pois_a_free_1")


def state_zip(points=(), areas=()):
    """A state's file: `points` and `areas` are (kind, shape) for the two place layers."""
    members = {"README": b"x", "gis_osm_roads_free_1.shp": b"r" * 5000}
    for name, listed in zip(LAYERS, (points, areas)):
        members[name + ".shp"] = shapefiles.shp([shape for _, shape in listed])
        members[name + ".dbf"] = shapefiles.dbf([kind for kind, _ in listed])
    return shapefiles.archive(members)


def stations(*points):
    return json.dumps({"features": [{"attributes": {"NAME": "X"}, "geometry": {"x": lon, "y": lat}} for lat, lon in points]}).encode()


DC = state_zip(points=[("supermarket", ("point", -77.0, 38.9)), ("bench", ("point", -77.0, 38.9)), ("restaurant", ("point", -77.01, 38.9)),
                       ("cafe", ("point", -77.02, 38.9)), ("pharmacy", ("point", -77.0, 38.91)), ("supermarket", ("point", -80.0, 37.0))],
               areas=[("park", ("polygon", -77.06, 38.93, -77.04, 38.95)), ("dog_park", ("polygon", -77.03, 38.92, -77.029, 38.921)),
                      ("pitch", ("polygon", -77.0, 38.9, -76.99, 38.91)), ("library", ("polygon", -77.0, 38.9, -76.999, 38.901))])
MD = state_zip(points=[("community_centre", ("point", -77.1, 39.0)), ("fitness_centre", ("point", -77.1, 39.01)), ("pub", ("point", -77.1, 39.02))],
               areas=[("supermarket", ("polygon", -77.1, 39.0, -77.099, 39.001))])


class ShapesTests(unittest.TestCase):
    def test_distance_is_zero_inside_and_measured_to_the_edge_outside(self):
        box = (38.95, -77.01, 38.97, -76.99)
        self.assertEqual(places.miles_to(38.96, -77.0, box), 0)
        self.assertAlmostEqual(places.miles_to(38.95 - 0.5 * MILE, -77.0, box), 0.5, places=2)
        self.assertAlmostEqual(places.miles_to(38.9, -77.0, (38.9 + MILE, -77.0, 38.9 + MILE, -77.0)), 1.0, places=2)

    def test_the_kinds_of_place_counted(self):
        self.assertEqual(set(places.CATEGORIES), {"park", "dog_park", "community", "library", "grocery", "metro", "food", "gym", "pharmacy"})
        self.assertEqual(set(places.KINDS.values()) | {"metro"}, set(places.CATEGORIES))
        self.assertEqual((places.KINDS["supermarket"], places.KINDS["community_centre"], places.KINDS["cafe"], places.KINDS["fitness_centre"]),
                         ("grocery", "community", "food", "gym"))

    def test_bbox_covers_the_buildings_with_a_margin(self):
        box = places.bbox([{"lat": 38.9, "lon": -77.1}, {"lat": 39.0, "lon": -77.0}, {"lat": None, "lon": None}])
        self.assertLess(box[0], 38.9)
        self.assertGreater(box[2], 39.0)
        self.assertLess(box[1], -77.1)
        self.assertGreater(box[3], -77.0)

    def test_states_come_from_the_buildings_counties(self):
        self.assertEqual(places.states([{"county": "11001"}, {"county": "51013"}, {"county": "51059"}, {"county": None}, {}]), ["11", "51"])


class NearTests(unittest.TestCase):
    def test_count_within_half_a_mile_and_the_nearest(self):
        buildings = [{"id": "a", "lat": 38.9, "lon": -77.0}, {"id": "nowhere", "lat": None, "lon": None}]
        found = {"park": [(38.9 + 0.1 * MILE, -77.0) * 2, (38.9 + 0.4 * MILE, -77.0) * 2, (38.9 + 0.9 * MILE, -77.0) * 2],
                 "metro": [(38.9 + 1.5 * MILE, -77.0) * 2], "grocery": [(38.9 + 3 * MILE, -77.0) * 2], "library": []}
        self.assertEqual(places.near(buildings, found), {"a": {"park": [2, 0.1], "metro": [0, 1.5], "grocery": [0, None], "library": [0, None]}})


class FetchTests(QuietTestCase):
    def web(self, **replace):
        files = {places.STATE_FILES["11"]: DC, places.STATE_FILES["24"]: MD, places.METRO: stations((38.9, -77.03), (38.95, -77.08))}
        files.update(replace)
        self.asked = []
        return shapefiles.ranged(files, self.asked)

    def test_places_come_from_each_states_file_and_stations_from_the_metro_list(self):
        found = places.fetch_all(self.web(), BOX, ["11", "24"], sleep=lambda s: None)
        self.assertEqual(set(found), set(places.CATEGORIES))
        self.assertEqual(sorted(found["grocery"]), [(38.9, -77.0, 38.9, -77.0), (39.0, -77.1, 39.001, -77.099)])     # a point in DC, an outline in Maryland; not the one far away
        self.assertEqual(found["park"], [(38.93, -77.06, 38.95, -77.04)])
        self.assertEqual((len(found["food"]), len(found["dog_park"]), len(found["library"]), len(found["community"]), len(found["gym"]), len(found["pharmacy"])),
                         (3, 1, 1, 1, 1, 1))
        self.assertEqual(found["metro"], [(38.9, -77.03, 38.9, -77.03), (38.95, -77.08, 38.95, -77.08)])

    def test_the_big_layers_are_never_downloaded(self):
        places.fetch_all(self.web(), BOX, ["11"], sleep=lambda s: None)
        ranges = [r for url, r in self.asked if url == places.STATE_FILES["11"]]
        self.assertTrue(ranges and all(ranges))                                   # every request to the state file names a byte range
        self.assertNotIn(places.STATE_FILES["24"], [url for url, _ in self.asked])

    def test_a_state_that_cannot_be_read_keeps_last_weeks_places_but_stations_still_come(self):
        def broken(url, **options):
            raise OSError("down")
        found = places.fetch_all(self.web(**{places.STATE_FILES["24"]: broken}), BOX, ["11", "24"], sleep=lambda s: None)
        self.assertEqual(set(found), {"metro"})

    def test_a_missing_station_list_leaves_the_rest(self):
        def broken(url, **options):
            raise OSError("down")
        found = places.fetch_all(self.web(**{places.METRO: broken}), BOX, ["11"], sleep=lambda s: None)
        self.assertEqual(set(found), set(places.CATEGORIES) - {"metro"})

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
    def web(self, fail_state=False):
        calls = {"epa": 0}
        park = state_zip(areas=[("park", ("polygon", -77.001, 38.9 + 0.2 * MILE, -76.999, 38.9 + 0.3 * MILE))])
        files = shapefiles.ranged({places.STATE_FILES["11"]: park, places.METRO: stations((38.9 + 0.4 * MILE, -77.0))})

        def get(url, **options):
            if "WalkabilityIndex" in url:
                calls["epa"] += 1
                return json.dumps({"features": [{"attributes": {"NatWalkInd": 15.0}}]}).encode()
            if fail_state and url == places.STATE_FILES["11"]:
                raise OSError("down")
            if url in (places.STATE_FILES["11"], places.METRO):
                return files(url, **options)
            raise OSError("not part of this test")
        return get, calls

    def buildings(self):
        return [{"id": "a", "county": "11001", "lat": 38.9, "lon": -77.0, "tract": "1", "address": {"zip": "20001"}, "in_region": True}]

    def test_collect_adds_places_and_walkability(self):
        get, calls = self.web()
        got = area.collect(self.buildings(), {}, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual(got["places"]["a"]["park"], [1, 0.2])
        self.assertEqual(got["places"]["a"]["metro"], [1, 0.4])
        self.assertEqual(got["walk"], {"a": 15.0})
        self.assertEqual(calls["epa"], 1)

    def test_walkability_is_only_looked_up_once_per_building(self):
        get, calls = self.web()
        area.collect(self.buildings(), {"walk": {"a": 12.3}}, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual(calls["epa"], 0)

    def test_a_source_that_failed_keeps_last_weeks_numbers(self):
        get, _ = self.web(fail_state=True)
        previous = {"places": {"a": {"dog_park": [2, 0.3], "park": [9, 0.0], "metro": [0, 1.8]}}}
        got = area.collect(self.buildings(), previous, get, "2026-11-18", "now", parts=("places",), sleep=lambda s: None)
        self.assertEqual((got["places"]["a"]["dog_park"], got["places"]["a"]["park"]), ([2, 0.3], [9, 0.0]))
        self.assertEqual(got["places"]["a"]["metro"], [1, 0.4])                    # the station list did answer


if __name__ == "__main__":
    unittest.main()
