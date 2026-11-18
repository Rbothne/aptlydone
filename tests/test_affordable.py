import json
import os
import tempfile
import unittest

from aptrack import area, deals, history, output
from aptrack.area import affordable
from tests.quiet import QuietTestCase
from tests.test_deals import b, block, u

METRE = 1 / 111_320.0          # degrees of latitude in a metre, near enough


def feature(name, lat, lon, units, total, status="Completed"):
    return {"attributes": {"PROJECT_NAME": name, "LATITUDE": lat, "LONGITUDE": lon, "TOTAL_AFFORDABLE_UNITS": units,
                           "UNITS_TOTAL": total, "STATUS_PUBLIC": status}}


class ProjectsTests(unittest.TestCase):
    def test_projects_from_a_page(self):
        page = {"features": [feature("Sheridan Station", 38.86, -76.99, 114.0, 327.0),
                             feature("No place", None, None, 10.0, 10.0),
                             feature("Planned", 38.9, -77.0, 50.0, 50.0, status="Pipeline"),
                             feature("No count", 38.9, -77.0, None, 80.0)]}
        self.assertEqual(affordable.projects(page), [{"name": "Sheridan Station", "lat": 38.86, "lon": -76.99, "affordable": 114, "total": 327}])

    def test_reader_pages_until_empty(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            offset = int(url.split("resultOffset=")[1].split("&")[0])
            return json.dumps({"features": [feature("A", 38.9, -77.0, 10.0, 20.0)] if offset == 0 else []}).encode()
        self.assertEqual(len(affordable.dc(get)), 1)
        self.assertEqual(len(asked), 2)

    def test_a_building_takes_the_project_at_its_address(self):
        buildings = [{"id": "here", "lat": 38.9, "lon": -77.0}, {"id": "near", "lat": 38.9 + 50 * METRE, "lon": -77.0},
                     {"id": "far", "lat": 38.9 + 120 * METRE, "lon": -77.0}, {"id": "nowhere", "lat": None, "lon": None}]
        found = affordable.match(buildings, [{"name": "P", "lat": 38.9, "lon": -77.0, "affordable": 40, "total": 50}])
        self.assertEqual(found, {"here": {"name": "P", "affordable": 40, "total": 50}, "near": {"name": "P", "affordable": 40, "total": 50}})

    def test_the_closest_project_wins(self):
        buildings = [{"id": "x", "lat": 38.9, "lon": -77.0}]
        projects = [{"name": "Next door", "lat": 38.9 + 40 * METRE, "lon": -77.0, "affordable": 9, "total": 90},
                    {"name": "This one", "lat": 38.9 + 5 * METRE, "lon": -77.0, "affordable": 80, "total": 80}]
        self.assertEqual(affordable.match(buildings, projects)["x"]["name"], "This one")

    def test_mostly_affordable(self):
        self.assertTrue(affordable.mostly({"affordable": 40, "total": 50}))
        self.assertTrue(affordable.mostly({"affordable": 25, "total": 50}))
        self.assertFalse(affordable.mostly({"affordable": 24, "total": 50}))
        self.assertTrue(affordable.mostly({"affordable": 30, "total": None}))        # no total given: the project is all we know
        self.assertFalse(affordable.mostly(None))


class CollectAndOutputTests(QuietTestCase):
    def test_collect_adds_affordable_projects_for_dc_buildings(self):
        def get(url, **options):
            if url.startswith(affordable.DC):
                offset = int(url.split("resultOffset=")[1].split("&")[0])
                return json.dumps({"features": [feature("P", 38.9, -77.0, 40.0, 50.0)] if offset == 0 else []}).encode()
            raise OSError("not part of this test")
        buildings = [{"id": "dc", "county": "11001", "lat": 38.9, "lon": -77.0, "tract": "1", "address": {"zip": "20001"}, "in_region": True},
                     {"id": "va", "county": "51013", "lat": 38.9, "lon": -77.0, "tract": "2", "address": {"zip": "22201"}, "in_region": True}]
        got = area.collect(buildings, {}, get, "2026-11-18", "now", parts=("affordable",))
        self.assertEqual(got["affordable"], {"dc": {"name": "P", "affordable": 40, "total": 50}})

    def test_units_of_a_mostly_affordable_building_are_marked_restricted_and_not_tagged(self):
        from tests.test_build import GOOD, Web, camden
        import build
        with tempfile.TemporaryDirectory() as out:
            state = history.new_state()
            buildings = [camden()]
            results = build.run(buildings, state, Web(GOOD), "2026-11-18", sleep=lambda s: None)
            output.write_site(buildings, results, state, out, "now",
                              area={"affordable": {"camden-noma": {"name": "P", "affordable": 300, "total": 320}}})
            with open(os.path.join(out, "index.json"), encoding="utf-8") as f:
                entry = json.load(f)["buildings"][0]
            with open(os.path.join(out, "units-11001.json"), encoding="utf-8") as f:
                units = json.load(f)["units"]
        self.assertEqual(entry["affordable"], {"name": "P", "affordable": 300, "total": 320})
        self.assertTrue(all(unit["restricted"] is True and unit["tag"] is None for unit in units))


class SuspectLocalTests(unittest.TestCase):
    def test_a_price_far_under_its_neighbours_is_marked_for_checking(self):
        suspect, real = u("A", 1, 1500), u("E", 1, 1502)
        units = block("B", 2500, count=2) + block("C", 2500, count=2) + block("D", 2500, count=1) + [suspect, real]
        deals.score(units, [b("A"), b("E", 0.1), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertEqual((suspect["local"]["pct"], suspect["tag"]), (-40.0, "check"))
        self.assertEqual((real["local"]["pct"], real["tag"]), (-39.9, "local"))


if __name__ == "__main__":
    unittest.main()
