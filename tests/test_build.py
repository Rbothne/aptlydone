import json
import os
import tempfile
import unittest

import build
from aptrack import fetch, history, output

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


API = "https://sightmap.com/app/api/v1/rxwj9mldp1e/sightmaps/27596"
CAMDEN_FEED = "https://www.camdenliving.com/apartments/washington-dc/camden-noma/available-apartments"
DAY = "2026-11-18"


def bozzuto(**more):
    return dict({"id": "bozzuto-5333-connecticut", "manager": "Bozzuto", "name": "5333 Connecticut", "platform": "sightmap",
                 "url": "https://www.bozzuto.com/apartments-for-rent/dc/washington/5333-connecticut",
                 "feed": "https://sightmap.com/embed/8ywkoe19vlx", "feed_api": API, "lat": 38.96, "lon": -77.07,
                 "address": {"street": "5333 Connecticut Ave NW", "city": "Washington", "state": "DC", "zip": "20015"},
                 "state": "DC", "county": "11001", "tract": "11001001402", "neighborhood": "Chevy Chase",
                 "in_region": True, "first_seen": DAY, "missed": 0}, **more)


def camden(**more):
    return dict({"id": "camden-noma", "manager": "Camden", "name": "Camden NoMa", "platform": "camden",
                 "url": "https://www.camdenliving.com/apartments/washington-dc/camden-noma", "feed": CAMDEN_FEED,
                 "lat": 38.9, "lon": -77.0, "address": {"full": "61 Pierce St NE Washington, DC 20002"},
                 "state": "DC", "county": "11001", "tract": "11001010603", "neighborhood": "NoMa",
                 "in_region": True, "first_seen": DAY, "missed": 0}, **more)


class Web:
    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def __call__(self, url, **kwargs):
        self.asked.append(url)
        answer = self.pages.get(url)
        if isinstance(answer, list):                 # a script: one answer per call
            answer = answer.pop(0)
        if answer is None:
            raise fetch.Gone(url)
        if isinstance(answer, Exception):
            raise answer
        return answer.encode()


GOOD = {API: fixture("sightmap_feed.json"), CAMDEN_FEED: fixture("camden_available.html")}


class RunTests(unittest.TestCase):
    def run_it(self, buildings, pages, state=None):
        self.state = state or history.new_state()
        self.web = Web(pages)
        self.slept = []
        return build.run(buildings, self.state, self.web, DAY, sleep=self.slept.append)

    def test_run_records_success_and_failure(self):
        results = self.run_it([bozzuto(), camden()], {API: fixture("sightmap_feed.json"), CAMDEN_FEED: OSError("timed out")})
        self.assertEqual(set(results), {"bozzuto-5333-connecticut"})
        self.assertEqual(len(results["bozzuto-5333-connecticut"]["units"]), 5)
        self.assertEqual(self.state["buildings"], {"bozzuto-5333-connecticut": {"ok": DAY, "failed": None},
                                                   "camden-noma": {"ok": None, "failed": DAY}})
        self.assertEqual(len(self.state["units"]), 5)

    def test_unreadable_page_counts_as_failure(self):
        self.run_it([camden()], {CAMDEN_FEED: "<html>Access denied</html>"})
        self.assertEqual(self.state["buildings"]["camden-noma"], {"ok": None, "failed": DAY})

    def test_rate_limited_host_is_retried_after_others(self):
        results = self.run_it([camden(), bozzuto()],
                              {API: fixture("sightmap_feed.json"), CAMDEN_FEED: [fetch.RateLimited("slow down"), fixture("camden_available.html")]})
        self.assertEqual(set(results), {"bozzuto-5333-connecticut", "camden-noma"})
        self.assertEqual(self.web.asked, [CAMDEN_FEED, API, CAMDEN_FEED])
        self.assertEqual(self.slept, [60])

    def test_rest_of_a_rate_limited_host_waits_for_the_retry(self):
        second = camden(id="camden-roosevelt", feed=CAMDEN_FEED + "?2")
        self.run_it([camden(), second], {CAMDEN_FEED: [fetch.RateLimited("slow down"), fixture("camden_available.html")],
                                         CAMDEN_FEED + "?2": fixture("camden_available.html")})
        self.assertEqual(self.web.asked, [CAMDEN_FEED, CAMDEN_FEED, CAMDEN_FEED + "?2"])

    def test_still_rate_limited_counts_as_failure(self):
        results = self.run_it([camden()], {CAMDEN_FEED: [fetch.RateLimited("1"), fetch.RateLimited("2")]})
        self.assertEqual((results, self.state["buildings"]["camden-noma"]["failed"]), ({}, DAY))

    def test_no_wait_when_nothing_was_rate_limited(self):
        self.run_it([bozzuto()], GOOD)
        self.assertEqual(self.slept, [])

    def test_out_of_region_and_link_buildings_are_not_read(self):
        results = self.run_it([bozzuto(in_region=False), camden(platform="link", feed=None)], GOOD)
        self.assertEqual((results, self.web.asked, self.state["buildings"]), ({}, [], {}))

    def test_feed_api_is_cached_on_the_building(self):
        building = bozzuto()
        del building["feed_api"]
        self.run_it([building], dict(GOOD, **{building["feed"]: fixture("sightmap_embed.html")}))
        self.assertEqual(building["feed_api"], API)


class TotalsTests(unittest.TestCase):
    def test_totals_count_new_gone_and_changed(self):
        state = history.new_state()
        unit = lambda n, rent: {"id": f"b:{n}", "building": "b", "unit": n, "plan": "A", "beds": 1, "baths": 1, "sqft": 700,
                                "rent": rent, "special": None}
        history.record(state, "b", [unit("1", 2000), unit("2", 2000), unit("3", 2000)], "2026-11-17")
        history.record(state, "b", [unit("1", 1900), unit("2", 2000), unit("4", 2500)], DAY)
        self.assertEqual(build.totals(state, DAY), {"listed": 3, "new": 1, "gone": 1, "changed": 1})


class WriteSiteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = self.dir.name

    def load(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8") as f:
            return json.load(f)

    def build_and_write(self, buildings, pages, state, now="2026-11-18T12:00Z", day=DAY):
        results = build.run(buildings, state, Web(pages), day, sleep=lambda s: None)
        output.write_site(buildings, results, state, self.out, now)
        return results

    def test_write_site_splits_units_by_county(self):
        arlington = camden(county="51013", state="VA")
        self.build_and_write([bozzuto(), arlington], GOOD, history.new_state())
        self.assertEqual({u["building"] for u in self.load("units-11001.json")["units"]}, {"bozzuto-5333-connecticut"})
        self.assertEqual({u["building"] for u in self.load("units-51013.json")["units"]}, {"camden-noma"})
        index = self.load("index.json")
        self.assertEqual(index["updated"], "2026-11-18T12:00Z")
        self.assertEqual(index["counties"], {"11001": {"buildings": 1, "units": 5}, "51013": {"buildings": 1, "units": 5}})

    def test_units_carry_first_seen_and_history(self):
        self.build_and_write([camden()], GOOD, history.new_state())
        unit = next(u for u in self.load("units-11001.json")["units"] if u["unit"] == "1215")
        self.assertEqual((unit["first"], unit["history"], unit["rent"], unit["sqft"]), (DAY, [[DAY, 1829, None]], 1829, 495))

    def test_index_describes_each_building(self):
        self.build_and_write([bozzuto(), camden(platform="link", feed=None)], GOOD, history.new_state())
        by_id = {b["id"]: b for b in self.load("index.json")["buildings"]}
        b = by_id["bozzuto-5333-connecticut"]
        self.assertEqual((b["name"], b["manager"], b["county"], b["tract"], b["neighborhood"], b["units"], b["stale"], b["read"]),
                         ("5333 Connecticut", "Bozzuto", "11001", "11001001402", "Chevy Chase", 5, False, DAY))
        self.assertIn("Concierge", b["amenities"])
        self.assertTrue(any(f["label"] == "Parking - Reserved" for f in b["fees"]))
        self.assertNotIn("feed_api", b)
        link = by_id["camden-noma"]
        self.assertEqual((link["platform"], link["units"], link["stale"], link["read"]), ("link", 0, False, None))

    def test_out_of_region_buildings_are_left_out(self):
        self.build_and_write([bozzuto(in_region=False, county="24510")], GOOD, history.new_state())
        self.assertEqual((self.load("index.json")["buildings"], self.load("index.json")["counties"]), ([], {}))

    def test_failed_building_keeps_previous_units_in_output(self):
        state = history.new_state()
        self.build_and_write([bozzuto(), camden()], GOOD, state)
        self.build_and_write([bozzuto(), camden()], dict(GOOD, **{CAMDEN_FEED: OSError("down")}), state,
                             now="2026-11-19T12:00Z", day="2026-11-19")
        by_id = {b["id"]: b for b in self.load("index.json")["buildings"]}
        self.assertEqual((by_id["camden-noma"]["stale"], by_id["camden-noma"]["units"], by_id["camden-noma"]["read"]), (True, 5, DAY))
        self.assertFalse(by_id["bozzuto-5333-connecticut"]["stale"])
        units = self.load("units-11001.json")["units"]
        self.assertEqual(len([u for u in units if u["building"] == "camden-noma"]), 5)
        self.assertEqual(len(units), 10)

    def test_stale_building_keeps_its_fees_and_amenities(self):
        state = history.new_state()
        self.build_and_write([bozzuto()], GOOD, state)
        self.build_and_write([bozzuto()], {API: OSError("down")}, state, day="2026-11-19")
        b = self.load("index.json")["buildings"][0]
        self.assertTrue(b["stale"])
        self.assertIn("Concierge", b["amenities"])


if __name__ == "__main__":
    unittest.main()
