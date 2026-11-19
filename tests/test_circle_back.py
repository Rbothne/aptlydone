"""Discovery when a company's site stops answering: stop asking, keep what was known, come back once."""
import os
import unittest

from aptrack import discovery, fetch
from aptrack.discover import common, windsor
from tests.quiet import QuietTestCase
from tests.test_windsor import fixture


def b(building_id, manager="Bozzuto", **more):
    return dict({"id": building_id, "manager": manager, "name": building_id, "platform": "sightmap",
                 "feed": "https://sightmap.com/embed/" + building_id, "lat": 38.9, "lon": -77.0}, **more)


class WatchTests(unittest.TestCase):
    def test_misses_in_a_row_raise(self):
        watch = common.Watch(limit=3)
        watch.miss("a")
        watch.miss("b")
        with self.assertRaises(fetch.RateLimited):
            watch.miss("c")

    def test_a_good_page_resets_the_count(self):
        watch = common.Watch(limit=3)
        for _ in range(5):
            watch.miss("a")
            watch.miss("b")
            watch.ok()


class SilentSiteTests(QuietTestCase):
    def test_windsor_stops_when_pages_come_back_without_their_data(self):
        arlington = "https://www.windsorcommunities.com/apartments/virginia-arlington/"
        links = "".join(f'<a href="https://www.windsorcommunities.com/properties/b{n}/">x</a>' for n in range(8))
        asked = []

        def get(url):
            asked.append(url)
            if url == windsor.SITEMAP:
                return fixture("windsor_locations.xml").encode()
            if url == arlington:
                return links.encode()
            if "/properties/" in url:
                return b"<html>Please verify you are human</html>"
            raise fetch.Gone(url)
        with self.assertRaises(fetch.RateLimited):
            windsor.discover(get)
        self.assertEqual(len([u for u in asked if "/properties/" in u]), common.Watch.LIMIT)


class RunAllTests(QuietTestCase):
    def test_a_company_that_fails_is_tried_once_more_after_the_others(self):
        calls, slept = [], []

        def flaky(get, limit=None):
            calls.append("flaky")
            if calls.count("flaky") == 1:
                raise fetch.RateLimited("slow down")
            return [b("f1", manager="Flaky")]

        def steady(get, limit=None):
            calls.append("steady")
            return [b("s1", manager="Steady")]
        managers = [{"name": "Flaky", "discover": "flaky"}, {"name": "Steady", "discover": "steady"}]
        found = discovery.run_all(managers, {"flaky": flaky, "steady": steady}, None, workers=1, sleep=slept.append)
        self.assertEqual((calls, slept), (["flaky", "steady", "flaky"], [60]))
        self.assertEqual({name: [x["id"] for x in buildings] for name, buildings in found.items()}, {"Flaky": ["f1"], "Steady": ["s1"]})

    def test_a_company_that_fails_twice_is_none(self):
        def dead(get, limit=None):
            raise OSError("down")
        found = discovery.run_all([{"name": "Dead", "discover": "dead"}], {"dead": dead}, None, workers=1, sleep=lambda s: None)
        self.assertEqual(found, {"Dead": None})

    def test_no_wait_when_nothing_failed(self):
        slept = []
        discovery.run_all([{"name": "A", "discover": "a"}], {"a": lambda get, limit=None: []}, None, workers=1, sleep=slept.append)
        self.assertEqual(slept, [])

    def test_limit_is_passed_through(self):
        seen = []
        discovery.run_all([{"name": "A", "discover": "a"}], {"a": lambda get, limit=None: seen.append(limit) or []}, None,
                          limit=3, workers=1, sleep=lambda s: None)
        self.assertEqual(seen, [3])


class ShrinkGuardTests(QuietTestCase):
    def previous(self, count):
        return [b(f"x{n}", first_seen="2026-11-01", missed=0) for n in range(count)]

    def test_a_company_that_suddenly_lists_far_fewer_buildings_is_treated_as_failed(self):
        merged = discovery.merge(self.previous(10), {"Bozzuto": [b("x0"), b("x1"), b("x2"), b("x3")]}, "2026-11-18")
        self.assertEqual((len(merged), {m["missed"] for m in merged}), (10, {0}))

    def test_half_or_more_is_believed(self):
        merged = discovery.merge(self.previous(10), {"Bozzuto": [b(f"x{n}") for n in range(5)]}, "2026-11-18")
        self.assertEqual(sorted(m["missed"] for m in merged), [0] * 5 + [1] * 5)

    def test_small_portfolios_are_not_second_guessed(self):
        merged = discovery.merge(self.previous(3), {"Bozzuto": [b("x0")]}, "2026-11-18")
        self.assertEqual(sorted(m["missed"] for m in merged), [0, 1, 1])

    def test_a_limited_test_run_is_not_second_guessed(self):
        merged = discovery.merge(self.previous(10), {"Bozzuto": [b("x0", name="Renamed")]}, "2026-11-18", partial=True)
        self.assertEqual(next(m for m in merged if m["id"] == "x0")["name"], "Renamed")


if __name__ == "__main__":
    unittest.main()


class EverySiteAtOnceTests(QuietTestCase):
    """One lane per site: a slow site (one that asks for five seconds between requests, say) never leaves the
    others waiting for a free lane. Each fake below only answers once every site is asking at the same moment."""

    SITES = 9

    def test_units_are_read_from_every_site_side_by_side(self):
        import threading

        import build
        from aptrack import history
        together = threading.Barrier(self.SITES, timeout=5)
        page = open(os.path.join(os.path.dirname(__file__), "fixtures", "camden_available.html"), encoding="utf-8").read()
        waited = set()
        lock = threading.Lock()

        def get(url, **options):
            site = url.split("/")[2]
            with lock:
                first = site not in waited
                waited.add(site)
            if first:
                together.wait()
            return page.encode()
        buildings = [{"id": f"b{n}", "manager": "M", "name": f"B{n}", "platform": "camden", "url": f"https://site{n}.test/b",
                      "feed": f"https://site{n}.test/b/available-apartments", "in_region": True, "county": "11001"} for n in range(self.SITES)]
        results = build.run(buildings, history.new_state(), get, "2026-11-19", sleep=lambda s: None)
        self.assertEqual(len(results), self.SITES)

    def test_companies_are_discovered_side_by_side(self):
        import threading
        together = threading.Barrier(self.SITES, timeout=5)

        def discoverer(get, limit=None):
            together.wait()
            return []
        managers = [{"name": f"M{n}", "discover": "x"} for n in range(self.SITES)]
        found = discovery.run_all(managers, {"x": discoverer}, None, sleep=lambda s: None)
        self.assertEqual(found, {f"M{n}": [] for n in range(self.SITES)})

    def test_a_limit_on_lanes_is_still_honoured_when_given(self):
        import threading
        running, most, lock = [0], [0], threading.Lock()

        def discoverer(get, limit=None):
            with lock:
                running[0] += 1
                most[0] = max(most[0], running[0])
            threading.Event().wait(0.02)
            with lock:
                running[0] -= 1
            return []
        discovery.run_all([{"name": f"M{n}", "discover": "x"} for n in range(6)], {"x": discoverer}, None, workers=2, sleep=lambda s: None)
        self.assertLessEqual(most[0], 2)

    def test_counties_crime_is_collected_side_by_side(self):
        import threading
        from unittest import mock

        from aptrack import area
        from aptrack.area import crime
        together = threading.Barrier(3, timeout=5)

        def reader(get, start, today):
            together.wait()
            return [(38.9, -77.0, "violent", "2026-06-01")]
        buildings = [{"id": f"b{n}", "county": county, "lat": 38.9, "lon": -77.0, "tract": "1", "in_region": True}
                     for n, county in enumerate(("11001", "24031", "24033"))]
        with mock.patch.dict(crime.SOURCES, {"11001": reader, "24031": reader, "24033": reader}):
            got = area.collect(buildings, {}, None, "2026-11-19", "now", parts=("crime",), sleep=lambda s: None)
        self.assertEqual(got["crime_counties"], ["11001", "24031", "24033"])
        self.assertEqual([got["crime"][f"b{n}"]["violent"] for n in range(3)], [1, 1, 1])
