"""Noise and construction in the weekly collection, and what the page files say about them and about each unit."""
import json
import os
import tempfile
import unittest

from aptrack import area, history, output
from aptrack.area import noise, works
from tests.quiet import QuietTestCase
from tests.test_area_collect import building
from tests.test_noise import LEGEND, RED, CLEAR, encode
from tests.test_works import SERVICE, permit

TODAY = "2026-11-19"


def web(asked, permits_fail=False):
    def get(url, **options):
        asked.append(url)
        if url.endswith("/legend?f=json"):
            return LEGEND.encode()
        if "/MapServer/tile/" in url:
            return encode([[RED if noise.LAYERS["air"] in url else CLEAR] * 256] * 256)
        if url == works.SERVICE + "?f=json":
            if permits_fail:
                raise OSError("down")
            return json.dumps(SERVICE).encode()
        if url.startswith(works.SERVICE + "/18/"):
            return json.dumps({"features": [permit("NEW BUILDING", "2026-06-01", 38.8685, -77.0107, address="9 SIDE ST SE", what="New 10-story building")]}).encode()
        if url.startswith(works.SERVICE):
            return b'{"features": []}'
        raise AssertionError("unexpected request: " + url)
    return get


class CollectTests(QuietTestCase):
    def collect(self, buildings, before=None, parts=("noise", "works"), **options):
        self.asked = []
        return area.collect(buildings, before or {}, web(self.asked, **options), TODAY, "now", parts=parts, sleep=lambda s: None)

    def test_noise_and_construction_are_collected(self):
        got = self.collect([building("dc"), building("md", county="24031", lat=39.0, lon=-77.1)])
        self.assertEqual(got["noise"]["dc"], {"air": 90, "road": None, "rail": None})
        self.assertEqual(got["noise"]["md"]["air"], 90)
        self.assertEqual([w["kind"] for w in got["works"]["dc"]["next"]], ["New building"])
        self.assertNotIn("md", got["works"])                                    # permits are DC's: Maryland is not checked
        self.assertEqual(got["works_counties"], ["11001"])
        self.assertIn("noise", area.PARTS)
        self.assertIn("works", area.PARTS)

    def test_noise_already_known_is_not_asked_for_again(self):
        known = {"noise": {"dc": {"air": 50, "road": None, "rail": None}}}
        got = self.collect([building("dc")], known, parts=("noise",))
        self.assertEqual(got["noise"]["dc"]["air"], 50)
        self.assertEqual(self.asked, [])

    def test_permits_that_cannot_be_read_keep_last_week_s(self):
        known = {"works": {"dc": {"next": [], "here": []}}, "works_counties": ["11001"]}
        got = self.collect([building("dc")], known, parts=("works",), permits_fail=True)
        self.assertEqual(got["works"], known["works"])


class OutputTests(QuietTestCase):
    def index(self, collected):
        with tempfile.TemporaryDirectory() as out:
            b = building("dc", manager="X", platform="link", url="https://x.test", neighborhood="Navy Yard", first_seen=TODAY, state="DC")
            output.write_site([b], {}, history.new_state(), out, TODAY + "T13:00Z", area=collected)
            with open(os.path.join(out, "index.json"), encoding="utf-8") as f:
                return json.load(f)

    def test_the_page_gets_each_building_s_noise_and_construction(self):
        index = self.index({"noise": {"dc": {"air": 55, "road": None, "rail": None}}, "works": {"dc": {"next": [{"kind": "New building"}], "here": []}},
                            "works_counties": ["11001"]})
        entry = index["buildings"][0]
        self.assertEqual((entry["noise"], entry["works"]["next"][0]["kind"]), ({"air": 55, "road": None, "rail": None}, "New building"))
        self.assertEqual(index["works_counties"], ["11001"])

    def test_without_them_the_page_says_not_known(self):
        index = self.index(None)
        self.assertEqual((index["buildings"][0]["noise"], index["buildings"][0]["works"], index["works_counties"]), (None, None, []))


class UnitTests(QuietTestCase):
    def test_units_carry_what_their_listing_says_and_a_recent_price_drop(self):
        b = {"id": "b", "name": "B", "in_region": True, "county": "11001"}
        units = [{"id": "b:1", "building": "b", "unit": "1", "plan": "TH Townhome", "notes": "Patio", "beds": 1, "baths": 1, "sqft": 700,
                  "rent": 2000, "fees": None, "lease": 12, "special": None, "available": None},
                 {"id": "b:2", "building": "b", "unit": "2", "plan": "A1", "notes": None, "beds": 1, "baths": 1, "sqft": 700,
                  "rent": 2000, "fees": None, "lease": 12, "special": None, "available": None}]
        state = history.new_state()
        history.record(state, "b", units, "2026-11-10")
        cheaper = [dict(units[0], rent=1900), units[1]]
        history.record(state, "b", cheaper, TODAY)
        with tempfile.TemporaryDirectory() as out:
            entries, units_of = output.assemble([b], {"b": {"units": cheaper, "fees": [], "amenities": [], "facts": None}}, state, out, today=TODAY)
        first, second = units_of["b"]
        self.assertEqual((first["outdoor"], first["own_door"], first["drop"]), ("Patio", True, {"was": 2000, "by": 100, "pct": -5.0, "day": TODAY}))
        self.assertEqual((second["outdoor"], second["own_door"], second["drop"]), (None, False, None))


if __name__ == "__main__":
    unittest.main()
