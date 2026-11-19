"""Construction beside a building, and big renovation inside it, from DC's building permits."""
import datetime
import json
import unittest
from urllib.parse import parse_qs, urlparse

from aptrack.area import works
from tests.quiet import QuietTestCase

TODAY = "2026-11-19"


def ms(day):
    return int(datetime.datetime.fromisoformat(day + "T12:00:00+00:00").timestamp() * 1000)


def permit(subtype, day, lat, lon, fee=9000, address="1 MAIN ST NW", what="WORK"):
    return {"attributes": {"PERMIT_SUBTYPE_NAME": subtype, "ISSUE_DATE": ms(day), "LATITUDE": lat, "LONGITUDE": lon,
                           "FEES_PAID": fee, "FULL_ADDRESS": address + ", WASHINGTON, DC 20001", "DESC_OF_WORK": what}}


SERVICE = {"layers": [{"id": 4, "name": "Building Permits - Last 30 Days"}, {"id": 18, "name": "Building Permits - 2026"},
                      {"id": 17, "name": "Building Permits - 2025"}, {"id": 16, "name": "Building Permits - 2024"},
                      {"id": 13, "name": "Basic Business License Points"}]}


class Web:
    def __init__(self, by_layer):
        self.by_layer, self.asked = by_layer, []

    def __call__(self, url, **options):
        parts = urlparse(url)
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        if parts.path.endswith("/MapServer"):
            return json.dumps(SERVICE).encode()
        layer = int(parts.path.split("/")[-2])
        self.asked.append((layer, query))
        rows = self.by_layer.get(layer, [])
        start, size = int(query.get("resultOffset", 0)), int(query["resultRecordCount"])
        return json.dumps({"features": rows[start:start + size], "exceededTransferLimit": start + size < len(rows)}).encode()


class PermitsTests(QuietTestCase):
    def test_the_last_two_years_of_permit_layers_are_read_page_by_page(self):
        web = Web({18: [permit("NEW BUILDING", "2026-06-01", 38.9, -77.0)] * 5, 17: [permit("RAZE", "2025-03-01", 38.91, -77.01)],
                   16: [permit("RAZE", "2024-12-01", 38.92, -77.02)]})
        got = works.permits(web, TODAY, page=2)
        self.assertEqual(sorted({layer for layer, _ in web.asked}), [16, 17, 18])          # 2024 still reaches into the two years
        self.assertEqual(len(got), 7)
        self.assertEqual([q["resultOffset"] for layer, q in web.asked if layer == 18], ["0", "2", "4"])
        where = web.asked[0][1]["where"]
        self.assertIn("NEW BUILDING", where)
        self.assertIn("FEES_PAID >= 5000", where)
        self.assertIn("2024-11-19", where)

    def test_a_permit_becomes_a_kind_a_day_and_a_place(self):
        web = Web({18: [permit("NEW BUILDING", "2026-06-01", 38.9, -77.0, address="2250 8TH ST NW", what="New mixed-use,   10-story\nbuilding " + "x" * 300),
                        permit("ALTERATION AND REPAIR", "2026-07-04", 38.9, -77.0), permit("RAZE", "2026-01-02", None, None)]})
        got = works.permits(web, TODAY)
        self.assertEqual(len(got), 2)                                                       # one has no place
        first = got[0]
        self.assertEqual((first["kind"], first["day"], first["lat"], first["lon"], first["address"]), ("New building", "2026-06-01", 38.9, -77.0, "2250 8th St NW"))
        self.assertTrue(first["what"].startswith("New mixed-use, 10-story building x"))
        self.assertLessEqual(len(first["what"]), 160)
        self.assertEqual(got[1]["kind"], "Major work")


class NearTests(unittest.TestCase):
    HOME = {"id": "home", "lat": 38.9000, "lon": -77.0000}

    def work(self, kind, day, north_miles, address="9 SIDE ST"):
        return {"kind": kind, "day": day, "lat": 38.9 + north_miles / 69.0, "lon": -77.0, "address": address, "what": "w"}

    def test_new_buildings_and_demolition_within_a_block_are_next_door(self):
        got = works.near([self.HOME], [self.work("New building", "2026-06-01", 0.06), self.work("Demolition", "2025-02-01", 0.09, "7 OTHER ST"),
                                       self.work("New building", "2026-06-01", 0.3), self.work("Major work", "2026-06-01", 0.06, "5 THIRD ST")], TODAY)
        self.assertEqual([(w["kind"], w["miles"]) for w in got["home"]["next"]], [("New building", 0.06), ("Demolition", 0.09)])
        self.assertEqual(got["home"]["here"], [])

    def test_big_renovation_at_the_building_s_own_address_is_work_in_the_building(self):
        got = works.near([self.HOME], [self.work("Major work", "2026-03-01", 0.01), self.work("New building", "2025-01-01", 0.0)], TODAY)
        self.assertEqual([w["kind"] for w in got["home"]["here"]], ["Major work"])
        self.assertEqual(got["home"]["next"], [])                                           # the new-building permit on its own lot is the building itself

    def test_old_permits_no_longer_count(self):
        got = works.near([self.HOME], [self.work("Major work", "2025-10-01", 0.01), self.work("New building", "2024-10-01", 0.05)], TODAY)
        self.assertEqual(got["home"], {"next": [], "here": []})                             # renovation: a year; a building site: two

    def test_several_permits_for_one_site_are_one_site_and_a_building_without_a_place_is_left_out(self):
        many = [self.work("New building", "2026-01-01", 0.05), self.work("New building", "2026-06-01", 0.05), self.work("Demolition", "2025-12-01", 0.05)]
        got = works.near([self.HOME, {"id": "lost", "lat": None, "lon": None}], many, TODAY)
        self.assertEqual([(w["kind"], w["day"]) for w in got["home"]["next"]], [("New building", "2026-06-01")])
        self.assertNotIn("lost", got)


if __name__ == "__main__":
    unittest.main()
