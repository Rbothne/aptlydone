"""Checking each building's published location against where the Census Bureau places its street address.

What an audit of all 585 buildings found (2026-11-19): the ZIP a building publishes is right (444 of 444 agreed
with the Census where both were usable) while the ZIP looked up from its coordinates was wrong for 246; and
published coordinates are nearly always right, but 8 buildings sat more than a quarter mile from their address.
"""
import csv
import io
import unittest

from aptrack import area, discovery, geo
from tests.quiet import QuietTestCase

GALLERY = {"id": "gallery-64", "manager": "Greystar", "lat": 38.8999, "lon": -77.0114,
           "address": {"street": "64 H Street SW", "city": "Washington", "state": "DC", "zip": "20024"}}
NEAR = {"id": "near", "manager": "Bozzuto", "lat": 38.9600, "lon": -77.0700,
        "address": {"street": "5333 Connecticut Ave NW", "city": "Washington", "state": "DC", "zip": "20015"}}
REPLY = {"64 H Street SW": ("Match", "Exact", "64 H ST SW, WASHINGTON, DC, 20024", "-77.0118,38.8802"),
         "5333 Connecticut Ave NW": ("Match", "Exact", "5333 CONNECTICUT AVE NW, WASHINGTON, DC, 20015", "-77.0702,38.9601"),
         "301 West Broad St.": ("Match", "Non_Exact", "301 E BROAD ST, FALLS CHURCH, VA, 22046", "-77.1680,38.8830"),
         "1526 Lincoln Circle": ("Match", "Exact", "1526 LINCOLN CIR, MC LEAN, VA, 22102", "-77.2300,38.9300")}


class Post:
    """Stands in for the Census batch geocoder: answers from REPLY, and remembers what it was sent."""

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, url, body, headers=None, **options):
        if self.fail:
            raise OSError("down")
        text = body.decode("utf-8")
        table = text.split("Content-Type: text/csv\r\n\r\n")[1].split("\r\n--")[0]
        rows = list(csv.reader(io.StringIO(table)))
        self.sent.append(rows)
        out = io.StringIO()
        writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for number, street, city, state, zip_code in rows:
            answer = REPLY.get(street)
            given = f"{street}, {city}, {state}, {zip_code}"
            writer.writerow([number, given, *answer, "76225813", "L"] if answer else [number, given, "No_Match"])
        return out.getvalue().encode()


class PlaceAddressesTests(unittest.TestCase):
    def test_addresses_are_sent_in_one_request_and_come_back_placed(self):
        post = Post()
        got = geo.place_addresses([("a", "64 H Street SW", "Washington", "DC", "20024"), ("b", "1 Nowhere Rd", "Reston", "VA", "11410"),
                                   ("c", "301 West Broad St.", "Falls Church", "VA", "22046")], post)
        self.assertEqual(got["a"], {"lat": 38.8802, "lon": -77.0118, "zip": "20024", "city": "WASHINGTON", "exact": True})
        self.assertIsNone(got["b"])
        self.assertEqual((got["c"]["exact"], got["c"]["zip"]), (False, "22046"))
        self.assertEqual(len(post.sent), 1)
        self.assertEqual(post.sent[0][1][4], "")                                 # a ZIP that cannot be one here is not sent


class CheckTests(QuietTestCase):
    def test_each_building_with_a_street_address_is_placed_once(self):
        buildings = [dict(GALLERY), dict(NEAR), {"id": "camden", "lat": 38.9, "lon": -77.0, "address": {"full": "61 Pierce St NE Washington, DC 20002"}}]
        post = Post()
        discovery.check_addresses(buildings, post)
        self.assertEqual(buildings[0]["placed"]["zip"], "20024")
        self.assertNotIn("placed", buildings[2])                                 # no street to send
        self.assertEqual([row[1] for row in post.sent[0]], ["64 H Street SW", "5333 Connecticut Ave NW"])
        discovery.check_addresses(buildings, post)
        self.assertEqual(len(post.sent), 1)                                      # nothing new to ask
        buildings[1]["address"] = dict(buildings[1]["address"], street="301 West Broad St.")
        discovery.check_addresses(buildings, post)
        self.assertEqual([row[1] for row in post.sent[1]], ["301 West Broad St."])       # a changed address is asked about again

    def test_an_address_that_cannot_be_placed_is_remembered_as_such(self):
        building = dict(NEAR, address={"street": "20 Ridge Square NW", "city": "Washington", "state": "DC", "zip": "20016"})
        post = Post()
        discovery.check_addresses([building], post)
        discovery.check_addresses([building], post)
        self.assertEqual((building["placed"], len(post.sent)), (None, 1))

    def test_a_failed_request_changes_nothing(self):
        building = dict(GALLERY)
        discovery.check_addresses([building], Post(fail=True))
        self.assertNotIn("placed", building)


class CorrectTests(QuietTestCase):
    def placed(self, building, post=None):
        building = dict(building)
        with self.subTest():
            discovery.check_addresses([building], post or Post())
        return building

    def test_coordinates_far_from_an_exactly_matched_address_give_way_to_the_address(self):
        building = self.placed(GALLERY)
        self.assertTrue(discovery.correct(building))
        self.assertEqual((building["lat"], building["lon"], building["site_lat"], building["site_lon"]), (38.8802, -77.0118, 38.8999, -77.0114))
        self.assertFalse(discovery.correct(building))                            # already there: nothing more to do
        self.assertEqual(building["site_lat"], 38.8999)

    def test_coordinates_near_the_address_stay(self):
        building = self.placed(NEAR)
        self.assertFalse(discovery.correct(building))
        self.assertEqual((building["lat"], "site_lat" in building), (38.9600, False))

    def test_a_loose_match_never_moves_a_building(self):
        building = self.placed(dict(GALLERY, address={"street": "301 West Broad St.", "city": "Falls Church", "state": "VA", "zip": "22046"}))
        self.assertFalse(discovery.correct(building))
        self.assertEqual(building["lat"], 38.8999)

    def test_a_building_without_coordinates_takes_the_address_s(self):
        building = self.placed(dict(GALLERY, lat=None, lon=None))
        self.assertTrue(discovery.correct(building))
        self.assertEqual((building["lat"], "site_lat" in building), (38.8802, False))


class MergeTests(unittest.TestCase):
    def test_a_rediscovered_building_keeps_what_was_worked_out_about_its_address(self):
        old = dict(GALLERY, placed={"lat": 38.8802, "lon": -77.0118, "zip": "20024", "city": "WASHINGTON", "exact": True},
                   placed_for="x", located_at=[38.8802, -77.0118], tract="11001010500", first_seen="2026-11-01")
        merged = discovery.merge([old], {"Greystar": [dict(GALLERY)]}, "2026-11-19")
        self.assertEqual((merged[0]["placed"], merged[0]["placed_for"], merged[0]["located_at"]), (old["placed"], "x", [38.8802, -77.0118]))
        self.assertEqual(merged[0]["lat"], 38.8999)                              # as published again: correct() moves it back


class LocateTests(QuietTestCase):
    def locate_all(self, buildings):
        self.located, self.named = [], []

        def locate(get, lat=None, lon=None, address=None):
            self.located.append((lat, lon))
            return {"lat": lat, "lon": lon, "state": "DC", "county": "11001", "tract": "11001010500"}

        def reverse(get, lat, lon):
            self.named.append((lat, lon))
            return {"neighborhood": "Southwest", "zip": "20024"}
        discovery.locate_all(buildings, None, ["11001"], locate=locate, reverse=reverse)

    def test_a_building_that_moved_is_located_and_named_again(self):
        moved = dict(GALLERY, lat=38.8802, lon=-77.0118, site_lat=38.8999, site_lon=-77.0114, tract="11001004702", county="11001",
                     neighborhood="North Capitol Street", zip="20001")
        self.locate_all([moved])
        self.assertEqual((moved["tract"], moved["neighborhood"], moved["zip"], moved["located_at"]), ("11001010500", "Southwest", "20024", [38.8802, -77.0118]))
        self.locate_all([moved])
        self.assertEqual((self.located, self.named), ([], []))                    # once located there, it is left alone

    def test_a_building_located_before_this_was_tracked_is_assumed_to_be_where_it_is(self):
        old = dict(NEAR, tract="11001001402", county="11001", neighborhood="Chevy Chase", zip="20015")
        self.locate_all([old])
        self.assertEqual((self.located, old["located_at"]), ([], [38.96, -77.07]))

    def test_new_published_coordinates_are_noticed_too(self):
        shifted = dict(NEAR, lat=38.97, tract="11001001402", county="11001", neighborhood="Chevy Chase", zip="20015", located_at=[38.96, -77.07])
        self.locate_all([shifted])
        self.assertEqual(self.located, [(38.97, -77.07)])


class ZipTests(unittest.TestCase):
    PLACED = {"lat": 1, "lon": 1, "zip": "20190", "city": "RESTON", "exact": True}

    def test_the_building_s_own_zip_is_believed_over_the_one_looked_up_from_its_coordinates(self):
        self.assertEqual(area.zip_code({"zip": "22213", "address": {"street": "4650 N Washington Blvd", "zip": "22201"}}), "22201")

    def test_a_published_zip_that_cannot_be_one_gives_way_to_the_address_lookup_then_the_coordinates(self):
        wrong = {"street": "11410 Reston Station Blvd", "city": "Reston", "state": "VA", "zip": "11410"}
        self.assertEqual(area.zip_code({"zip": "20195", "placed": self.PLACED, "address": wrong}), "20190")
        self.assertEqual(area.zip_code({"zip": "20195", "placed": None, "address": wrong}), "20195")
        self.assertEqual(area.zip_code({"zip": "20195", "address": {"street": "13690 Legacy Cir"}, "placed": self.PLACED}), "20190")
        self.assertIsNone(area.zip_code({"address": wrong}))


class CityTests(unittest.TestCase):
    def test_a_company_that_publishes_a_region_for_the_city_takes_the_city_from_the_address(self):
        maa = {"id": "maa", "manager": "MAA", "address": {"street": "1526 Lincoln Circle", "city": "DC Metro", "state": "VA", "zip": "22102"},
               "placed": {"lat": 1, "lon": 1, "zip": "22102", "city": "MC LEAN", "exact": True}}
        other = dict(maa, id="other", manager="Bozzuto", address=dict(maa["address"]))
        unplaced = dict(maa, id="unplaced", placed=None, address=dict(maa["address"]))
        discovery.adopt_cities([maa, other, unplaced], [{"name": "MAA", "city_from_address": True}, {"name": "Bozzuto"}])
        self.assertEqual([b["address"]["city"] for b in (maa, other, unplaced)], ["Mc Lean", "DC Metro", "DC Metro"])


class MovedCacheTests(QuietTestCase):
    def test_what_was_looked_up_once_for_a_place_is_looked_up_again_when_the_building_moves(self):
        building = {"id": "b", "lat": 38.8802, "lon": -77.0118, "county": "99999"}
        before = {"walk": {"b": 12.5, "c": 9}, "noise": {"b": {"air": 50, "road": None, "rail": None}}, "at": {"b": [38.8999, -77.0114]}}
        got = area.collect([building], before, None, "2026-11-19", "now", parts=())
        self.assertEqual((got["walk"], got["noise"], got["at"]), ({"c": 9}, {}, {"b": [38.8802, -77.0118]}))
        again = area.collect([building], dict(got, walk={"b": 14}), None, "2026-11-19", "now", parts=())
        self.assertEqual(again["walk"], {"b": 14})                                # it has not moved since

    def test_a_building_moved_before_places_were_remembered_counts_as_moved(self):
        building = {"id": "b", "lat": 38.8802, "lon": -77.0118, "site_lat": 38.8999, "site_lon": -77.0114}
        got = area.collect([building], {"walk": {"b": 12.5}}, None, "2026-11-19", "now", parts=())
        self.assertEqual(got["walk"], {})


if __name__ == "__main__":
    unittest.main()
