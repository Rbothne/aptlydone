import json
import os
import tempfile
import unittest

from tests.quiet import QuietTestCase
import build
from aptrack import costs, fetch, history, output

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


BOZZUTO_URL = "https://www.bozzuto.com/apartments-for-rent/dc/washington/5333-connecticut"
GOOD = {API: fixture("sightmap_feed.json"), CAMDEN_FEED: fixture("camden_available.html"),
        BOZZUTO_URL: fixture("bozzuto_page.html")}
OFFER = "Move in by November 30th to enjoy two months free of base rent on select units *Restrictions May Apply"


class RunTests(QuietTestCase):
    def run_it(self, buildings, pages, state=None):
        self.state = state or history.new_state()
        self.web = Web(pages)
        self.slept = []
        return build.run(buildings, self.state, self.web, DAY, workers=1, sleep=self.slept.append)

    def test_run_records_success_and_failure(self):
        results = self.run_it([bozzuto(), camden()], {API: fixture("sightmap_feed.json"), CAMDEN_FEED: OSError("timed out")})
        self.assertEqual(set(results), {"bozzuto-5333-connecticut"})
        self.assertEqual(len(results["bozzuto-5333-connecticut"]["units"]), 5)
        self.assertEqual(self.state["buildings"]["camden-noma"], {"ok": None, "failed": DAY, "why": "timed out"})
        self.assertEqual((self.state["buildings"]["bozzuto-5333-connecticut"]["ok"],
                          self.state["buildings"]["bozzuto-5333-connecticut"]["failed"]), (DAY, None))
        self.assertEqual(len(self.state["units"]), 5)

    def test_unreadable_page_counts_as_failure(self):
        self.run_it([camden()], {CAMDEN_FEED: "<html>Access denied</html>"})
        self.assertEqual(self.state["buildings"]["camden-noma"], {"ok": None, "failed": DAY, "why": "no page data"})

    def test_rate_limited_host_is_retried_after_others(self):
        results = self.run_it([camden(), bozzuto()],
                              {API: fixture("sightmap_feed.json"), CAMDEN_FEED: [fetch.RateLimited("slow down"), fixture("camden_available.html")]})
        self.assertEqual(set(results), {"bozzuto-5333-connecticut", "camden-noma"})
        self.assertEqual(self.web.asked, [CAMDEN_FEED, API, BOZZUTO_URL, CAMDEN_FEED])
        self.assertEqual(self.slept, [60])

    def test_rest_of_a_rate_limited_host_waits_for_the_retry(self):
        second = camden(id="camden-roosevelt", feed=CAMDEN_FEED + "?2")
        self.run_it([camden(), second], {CAMDEN_FEED: [fetch.RateLimited("slow down"), fixture("camden_available.html")],
                                         CAMDEN_FEED + "?2": fixture("camden_available.html")})
        self.assertEqual(self.web.asked, [CAMDEN_FEED, CAMDEN_FEED, CAMDEN_FEED + "?2"])

    def test_still_rate_limited_counts_as_failure(self):
        results = self.run_it([camden()], {CAMDEN_FEED: [fetch.RateLimited("1"), fetch.RateLimited("2")]})
        self.assertEqual((results, self.state["buildings"]["camden-noma"]["failed"]), ({}, DAY))

    def camden_site(self, count):
        feeds = [CAMDEN_FEED + f"?{n}" for n in range(count)]
        return feeds, [camden(id=f"c{n}", feed=feed) for n, feed in enumerate(feeds)]

    def test_a_site_that_stops_answering_is_left_alone_until_the_end(self):
        feeds, buildings = self.camden_site(5)
        pages = dict(GOOD)
        for feed in feeds[:3]:
            pages[feed] = [OSError("timed out"), fixture("camden_available.html")]
        for feed in feeds[3:]:
            pages[feed] = fixture("camden_available.html")
        results = self.run_it(buildings + [bozzuto()], pages)
        # three failures in a row: the rest of that site waits; the other site is read; then the whole site is tried once more
        self.assertEqual(self.web.asked, feeds[:3] + [API, BOZZUTO_URL] + feeds)
        self.assertEqual((len(results), self.slept), (6, [60]))
        self.assertFalse([b for b in self.state["buildings"].values() if b["failed"]])

    def test_a_site_that_pushed_back_is_read_slowly_when_we_come_back(self):
        slowed = []

        class Throttle:
            def slow_down(self, site):
                slowed.append(site)
        web = Web({CAMDEN_FEED: [fetch.RateLimited("slow down"), fixture("camden_available.html")], **{k: v for k, v in GOOD.items() if k != CAMDEN_FEED}})
        web.throttle = Throttle()
        build.run([camden(), bozzuto()], history.new_state(), web, DAY, workers=1, sleep=lambda s: None)
        self.assertEqual(slowed, ["www.camdenliving.com"])

    def test_scattered_failures_do_not_stop_a_site(self):
        feeds, buildings = self.camden_site(5)
        pages = {feed: fixture("camden_available.html") for feed in feeds}
        pages[feeds[0]] = OSError("timed out")
        pages[feeds[2]] = OSError("timed out")
        results = self.run_it(buildings, pages)
        self.assertEqual((self.web.asked, len(results), self.slept), (feeds, 3, []))

    def test_a_site_still_silent_on_the_second_pass_counts_as_failed(self):
        feeds, buildings = self.camden_site(4)
        results = self.run_it(buildings, {feed: OSError("timed out") for feed in feeds})
        # the second pass gives up on the site after three more failures in a row, without asking for the fourth
        self.assertEqual((self.web.asked, results), (feeds[:3] + feeds[:3], {}))
        self.assertEqual([b["failed"] for b in self.state["buildings"].values()], [DAY] * 4)

    def test_pages_without_data_count_as_the_site_not_answering(self):
        feeds, buildings = self.camden_site(4)
        self.run_it(buildings, {feed: "<html>Please verify you are human</html>" for feed in feeds})
        self.assertEqual((self.web.asked, self.slept), (feeds[:3] + feeds[:3], [60]))

    def test_buildings_that_publish_no_prices_do_not_count_as_the_site_not_answering(self):
        unpriced = json.loads(fixture("sightmap_feed.json"))
        for u in unpriced["data"]["units"]:
            u["price"] = None
        apis = [API + str(n) for n in range(4)]
        buildings = [bozzuto(id=f"b{n}", feed_api=api, manager="Other") for n, api in enumerate(apis)]
        self.run_it(buildings, {api: json.dumps(unpriced) for api in apis})
        self.assertEqual((self.web.asked, self.slept), (apis, []))

    def test_no_wait_when_nothing_was_rate_limited(self):
        self.run_it([bozzuto()], GOOD)
        self.assertEqual(self.slept, [])

    def test_out_of_region_and_link_buildings_are_not_read(self):
        results = self.run_it([bozzuto(in_region=False), camden(platform="link", feed=None)], GOOD)
        self.assertEqual((results, self.web.asked, self.state["buildings"]), ({}, [], {}))

    def test_facts_are_read_after_the_units(self):
        results = self.run_it([bozzuto()], GOOD)
        self.assertEqual(self.web.asked, [API, BOZZUTO_URL])
        self.assertEqual(results["bozzuto-5333-connecticut"]["facts"]["rating"], 4.6)

    def test_facts_failure_keeps_units(self):
        results = self.run_it([bozzuto()], {API: fixture("sightmap_feed.json"), BOZZUTO_URL: fetch.RateLimited("slow down")})
        self.assertEqual(len(results["bozzuto-5333-connecticut"]["units"]), 5)
        self.assertIsNone(results["bozzuto-5333-connecticut"]["facts"])
        self.assertEqual(self.state["buildings"]["bozzuto-5333-connecticut"]["failed"], None)
        self.assertEqual(self.slept, [])

    def test_a_facts_site_that_keeps_failing_is_left_alone_for_the_rest_of_the_run(self):
        apis = [API + str(n) for n in range(5)]
        pages = [f"https://www.bozzuto.com/b{n}" for n in range(5)]
        buildings = [bozzuto(id=f"b{n}", feed_api=apis[n], url=pages[n]) for n in range(5)]
        answers = {api: fixture("sightmap_feed.json") for api in apis}
        answers.update({page: fetch.RateLimited("slow down") for page in pages})
        results = self.run_it(buildings, answers)
        self.assertEqual(len(results), 5)                                        # every building's units were still read
        self.assertEqual([u for u in self.web.asked if u in pages], pages[:3])   # the facts site was asked three times, then left alone
        self.assertEqual(self.slept, [])

    def test_special_recorded_in_history(self):
        self.run_it([bozzuto()], GOOD)
        self.assertEqual(self.state["buildings"]["bozzuto-5333-connecticut"]["specials"], [[DAY, OFFER]])

    def test_unknown_facts_record_no_special(self):
        self.run_it([bozzuto()], {API: fixture("sightmap_feed.json"), BOZZUTO_URL: OSError("down")})
        self.assertNotIn("specials", self.state["buildings"]["bozzuto-5333-connecticut"])

    def test_reader_supplied_facts_are_kept(self):
        results = self.run_it([camden()], GOOD)
        self.assertEqual(results["camden-noma"]["facts"], {"features": []})

    def test_feed_api_is_cached_on_the_building(self):
        building = bozzuto()
        del building["feed_api"]
        self.run_it([building], dict(GOOD, **{building["feed"]: fixture("sightmap_embed.html")}))
        self.assertEqual(building["feed_api"], API)


class ReasonTests(unittest.TestCase):
    def test_a_short_reason_for_each_kind_of_failure(self):
        import urllib.error
        refused = urllib.error.HTTPError("https://x.test/a", 403, "Forbidden", {}, None)
        self.assertEqual(build.reason(refused), "HTTP 403")
        refused.close()
        self.assertEqual(build.reason(TimeoutError("The read operation timed out")), "timed out")
        self.assertEqual(build.reason(fetch.Gone("https://x.test/a")), "page not found")
        self.assertEqual(build.reason(fetch.RateLimited("https://x.test/a")), "too many requests")
        self.assertEqual(build.reason(OSError("down")), "down")
        self.assertEqual(build.reason(ValueError("x" * 300)), "x" * 100)
        self.assertEqual(build.reason(KeyError()), "KeyError")


class FailureShareTests(unittest.TestCase):
    def test_too_many_failures(self):
        chosen = [{"id": str(n)} for n in range(10)]
        self.assertTrue(build.too_many_failures(chosen, {str(n): {} for n in range(7)}))        # 30% failed
        self.assertFalse(build.too_many_failures(chosen, {str(n): {} for n in range(8)}))       # 20% is tolerated
        self.assertFalse(build.too_many_failures([], {}))


class TotalsTests(unittest.TestCase):
    def test_totals_count_new_gone_and_changed(self):
        state = history.new_state()
        unit = lambda n, rent: {"id": f"b:{n}", "building": "b", "unit": n, "plan": "A", "beds": 1, "baths": 1, "sqft": 700,
                                "rent": rent, "special": None, "lease": 12, "fees": None, "available": None}
        history.record(state, "b", [unit("1", 2000), unit("2", 2000), unit("3", 2000)], "2026-11-17")
        history.record(state, "b", [unit("1", 1900), unit("2", 2000), unit("4", 2500)], DAY)
        self.assertEqual(build.totals(state, DAY), {"listed": 3, "new": 1, "gone": 1, "changed": 1})


class WriteSiteTests(QuietTestCase):
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
        self.assertEqual((unit["first"], unit["history"], unit["rent"], unit["sqft"]), (DAY, [[DAY, 1829, None, 15, 124]], 1829, 495))

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
        self.assertEqual(by_id["camden-noma"]["why"], "down")                       # what went wrong, for the page to say
        self.assertFalse(by_id["bozzuto-5333-connecticut"]["stale"])
        self.assertIsNone(by_id["bozzuto-5333-connecticut"]["why"])
        units = self.load("units-11001.json")["units"]
        self.assertEqual(len([u for u in units if u["building"] == "camden-noma"]), 5)
        self.assertEqual(len(units), 10)

    def test_facts_are_written_to_the_index(self):
        self.build_and_write([bozzuto(neighborhood="Northwest"), camden()], GOOD, history.new_state())
        by_id = {b["id"]: b for b in self.load("index.json")["buildings"]}
        b = by_id["bozzuto-5333-connecticut"]
        self.assertEqual((b["special"], b["rating"], b["rating_count"], b["coming_soon"], b["neighborhood"]),
                         (OFFER, 4.6, 483, False, "Chevy Chase"))
        self.assertIn("Hickory wood floors", b["features"])
        self.assertIsNone(b["laundry"])
        c = by_id["camden-noma"]
        self.assertEqual((c["special"], c["rating"], c["features"], c["neighborhood"]), (None, None, [], "NoMa"))

    def test_laundry_from_feature_text(self):
        page = fixture("camden_available.html").replace('"lastUpdate"', '"metaDescription": "Full-size washer and dryer.", "lastUpdate"')
        self.build_and_write([camden()], dict(GOOD, **{CAMDEN_FEED: page}), history.new_state())
        self.assertEqual(self.load("index.json")["buildings"][0]["laundry"], "in_unit")

    def test_previous_facts_kept_when_read_fails(self):
        state = history.new_state()
        self.build_and_write([bozzuto(neighborhood="Northwest")], GOOD, state)
        self.build_and_write([bozzuto(neighborhood="Northwest")], dict(GOOD, **{BOZZUTO_URL: OSError("down")}), state, day="2026-11-19")
        b = self.load("index.json")["buildings"][0]
        self.assertEqual((b["stale"], b["special"], b["rating"], b["neighborhood"]), (False, OFFER, 4.6, "Chevy Chase"))
        self.assertIn("Hickory wood floors", b["features"])

    def test_units_carry_true_cost_and_comparisons(self):
        self.build_and_write([bozzuto(), camden()], GOOD, history.new_state())
        by_id = {b["id"]: b for b in self.load("index.json")["buildings"]}
        units = {u["id"]: u for u in self.load("units-11001.json")["units"]}
        studio = units["camden-noma:1215"]
        self.assertEqual((studio["true"], studio["true_offer"]), (1829 + 124, None))
        fees = by_id["bozzuto-5333-connecticut"]["fees"]
        one_bed = units["bozzuto-5333-connecticut:204"]
        self.assertEqual(one_bed["true"], costs.true_monthly(one_bed, fees))
        self.assertEqual(one_bed["true_offer"], costs.true_monthly(one_bed, fees, special=OFFER))
        self.assertLess(one_bed["true_offer"], one_bed["true"])
        for key in ("own", "local", "tag"):
            self.assertIn(key, one_bed)

    def test_building_entry_has_cost_facts(self):
        self.build_and_write([bozzuto()], GOOD, history.new_state())
        b = self.load("index.json")["buildings"][0]
        self.assertEqual((b["parking_from"], b["pets"], b["senior"], b["rank"], b["parking"]), (225.0, True, False, None, True))
        self.assertEqual(b["one_time"], costs.one_time(b["fees"]))
        self.assertGreater(b["one_time"], 0)

    def test_stale_units_are_scored_again(self):
        state = history.new_state()
        self.build_and_write([camden()], GOOD, state)
        self.build_and_write([camden()], {CAMDEN_FEED: OSError("down")}, state, day="2026-11-19")
        unit = next(u for u in self.load("units-11001.json")["units"] if u["unit"] == "1215")
        self.assertEqual((unit["true"], unit["tag"]), (1953, None))

    def test_rating_found_at_discovery_is_used_when_no_daily_facts_give_one(self):
        self.build_and_write([camden(rating=4.3, rating_count=161), bozzuto(rating=1.0, rating_count=2)], GOOD, history.new_state())
        by_id = {b["id"]: b for b in self.load("index.json")["buildings"]}
        self.assertEqual((by_id["camden-noma"]["rating"], by_id["camden-noma"]["rating_count"]), (4.3, 161))
        self.assertEqual(by_id["bozzuto-5333-connecticut"]["rating"], 4.6)          # the daily facts win

    def test_features_found_at_discovery_give_laundry_when_there_are_no_daily_facts(self):
        windsor = bozzuto(id="windsor-courthouse", manager="Windsor", features=["In-home washer and dryer", "Quartz countertops"])
        self.build_and_write([windsor], GOOD, history.new_state())
        b = self.load("index.json")["buildings"][0]
        self.assertEqual((b["laundry"], b["features"]), ("in_unit", ["In-home washer and dryer", "Quartz countertops"]))

    def test_a_corrected_neighborhood_from_discovery_shows_up(self):
        state = history.new_state()
        self.build_and_write([camden(neighborhood="Washington")], GOOD, state)
        self.build_and_write([camden(neighborhood="NoMa")], GOOD, state, day="2026-11-19")
        self.assertEqual(self.load("index.json")["buildings"][0]["neighborhood"], "NoMa")

    def test_stale_building_keeps_its_fees_and_amenities(self):
        state = history.new_state()
        self.build_and_write([bozzuto()], GOOD, state)
        self.build_and_write([bozzuto()], {API: OSError("down")}, state, day="2026-11-19")
        b = self.load("index.json")["buildings"][0]
        self.assertTrue(b["stale"])
        self.assertIn("Concierge", b["amenities"])


if __name__ == "__main__":
    unittest.main()
