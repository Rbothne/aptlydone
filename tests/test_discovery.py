import json
import os
import unittest
from urllib.parse import quote

from tests.quiet import QuietTestCase
from aptrack import discover, discovery, fetch, geo
from aptrack.discover import bozzuto, camden

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


URL = "https://www.bozzuto.com/apartments-for-rent/dc/washington/5333-connecticut"
PAGE, FLOORPLANS = fixture("bozzuto_building.html"), fixture("bozzuto_floorplans.html")
CAMDEN_URL = "https://www.camdenliving.com/apartments/washington-dc/camden-noma/available-apartments"
CAMDEN_PAGE = fixture("camden_available.html")
COUNTIES = ["11001", "51013", "24031"]


class Web:
    """A fake `get`: answers from a dict of address -> text, bytes or exception; anything else is Gone."""

    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def __call__(self, url, **kwargs):
        self.asked.append(url)
        answer = self.pages.get(url)
        if answer is None:
            raise fetch.Gone(url)
        if isinstance(answer, Exception):
            raise answer
        return answer.encode() if isinstance(answer, str) else answer


class BozzutoTests(QuietTestCase):
    def test_bozzuto_urls_only_building_pages(self):
        urls = bozzuto.building_urls(fixture("bozzuto_sitemap.xml"))
        self.assertEqual(len(urls), 8)                         # 3 DC, 3 MD, 2 VA
        self.assertIn(URL, urls)
        self.assertFalse([u for u in urls if "/ny/" in u or "/ca/" in u or u.endswith("/reviews") or u.endswith("/washington")])
        self.assertEqual(len(urls), len(set(urls)))

    def test_bozzuto_parse_reads_location_and_feed(self):
        b = bozzuto.parse(URL, PAGE, FLOORPLANS)
        self.assertEqual((b["id"], b["manager"], b["name"], b["url"], b["platform"], b["feed"]),
                         ("bozzuto-5333-connecticut", "Bozzuto", "5333 Connecticut", URL, "sightmap",
                          "https://sightmap.com/embed/8ywkoe19vlx"))
        self.assertEqual(b["address"], {"street": "5333 Connecticut Ave NW", "city": "Washington", "state": "DC", "zip": "20015"})
        self.assertAlmostEqual(b["lat"], 38.960622, places=5)
        self.assertAlmostEqual(b["lon"], -77.072685, places=5)

    def test_bozzuto_without_embed_is_link(self):
        b = bozzuto.parse(URL, PAGE, "<html>no map here</html>")
        self.assertEqual((b["platform"], b["feed"]), ("link", None))

    def test_bozzuto_page_without_complex_is_none(self):
        self.assertIsNone(bozzuto.parse(URL, "<html></html>", FLOORPLANS))

    def test_bozzuto_discover_skips_a_building_whose_page_fails(self):
        other = "https://www.bozzuto.com/apartments-for-rent/dc/washington/1331"
        web = Web({bozzuto.SITEMAP: fixture("bozzuto_sitemap.xml"), URL: PAGE, URL + "/floor-plans": FLOORPLANS,
                   other: OSError("timed out")})
        found = bozzuto.discover(web, limit=2)
        self.assertEqual([b["id"] for b in found], ["bozzuto-5333-connecticut"])


class CamdenTests(unittest.TestCase):
    def test_camden_urls_region_states_only(self):
        urls = camden.building_urls(fixture("camden_sitemap.xml"))
        self.assertEqual(len(urls), 5)
        self.assertIn(CAMDEN_URL, urls)
        self.assertFalse([u for u in urls if "-fl/" in u])

    def test_camden_parse_reads_name_and_address(self):
        b = camden.parse(CAMDEN_URL, CAMDEN_PAGE)
        self.assertEqual((b["id"], b["manager"], b["name"], b["platform"], b["feed"], b["url"]),
                         ("camden-noma", "Camden", "Camden NoMa", "camden", CAMDEN_URL,
                          "https://www.camdenliving.com/apartments/washington-dc/camden-noma"))
        self.assertEqual(b["address"], {"full": "61 Pierce St NE Washington, DC 20002"})
        self.assertEqual((b["lat"], b["lon"]), (None, None))

    def test_camden_parse_page_without_data_is_none(self):
        self.assertIsNone(camden.parse(CAMDEN_URL, "<html></html>"))

    def test_discoverers_registered(self):
        self.assertLessEqual({"bozzuto", "camden"}, set(discover.DISCOVERERS))


class GeoTests(unittest.TestCase):
    BY_COORDS = (geo.CENSUS + "/coordinates?x=-77.072685&y=38.960622&benchmark=Public_AR_Current"
                 "&vintage=Current_Current&format=json")
    BY_ADDRESS = (geo.CENSUS + "/onelineaddress?address=" + quote("61 Pierce St NE Washington, DC 20002")
                  + "&benchmark=Public_AR_Current&vintage=Current_Current&format=json")

    def test_locate_by_coordinates(self):
        web = Web({self.BY_COORDS: fixture("census_coordinates.json")})
        self.assertEqual(geo.locate(web, lat=38.960622, lon=-77.072685),
                         {"lat": 38.960622, "lon": -77.072685, "state": "DC", "county": "11001", "tract": "11001001402"})

    def test_locate_by_address_returns_coordinates(self):
        web = Web({self.BY_ADDRESS: fixture("census_address.json")})
        where = geo.locate(web, address="61 Pierce St NE Washington, DC 20002")
        self.assertEqual((where["state"], where["county"], where["tract"]), ("DC", "11001", "11001010603"))
        self.assertAlmostEqual(where["lat"], 38.90463, places=4)
        self.assertAlmostEqual(where["lon"], -77.00714, places=4)

    def test_locate_no_match_is_none(self):
        url = self.BY_ADDRESS.replace(quote("61 Pierce St NE Washington, DC 20002"), quote("nowhere"))
        self.assertIsNone(geo.locate(Web({url: fixture("census_nomatch.json")}), address="nowhere"))

    def test_neighborhood_from_reverse_lookup(self):
        url = geo.NOMINATIM + "?format=jsonv2&zoom=16&lat=38.960622&lon=-77.072685"
        self.assertEqual(geo.neighborhood(Web({url: fixture("nominatim_reverse.json")}), 38.960622, -77.072685), "Chevy Chase")

    def test_reverse_gives_the_neighborhood_and_the_zip(self):
        url = geo.NOMINATIM + "?format=jsonv2&zoom=16&lat=38.960622&lon=-77.072685"
        self.assertEqual(geo.reverse(Web({url: fixture("nominatim_reverse.json")}), 38.960622, -77.072685),
                         {"neighborhood": "Chevy Chase", "zip": "20015"})

    def test_neighborhood_prefers_neighbourhood_then_suburb(self):
        self.assertEqual(geo.pick_name({"suburb": "Northwest", "neighbourhood": "Glover Park", "city": "Washington"}), "Glover Park")
        self.assertEqual(geo.pick_name({"suburb": "Clarendon", "city": "Arlington"}), "Clarendon")
        self.assertEqual(geo.pick_name({"city": "Rockville", "state": "Maryland"}), "Rockville")
        self.assertIsNone(geo.pick_name({"state": "Maryland"}))


def b(building_id, manager="Bozzuto", **more):
    return dict({"id": building_id, "manager": manager, "name": building_id, "platform": "sightmap",
                 "feed": "https://sightmap.com/embed/" + building_id, "lat": 38.9, "lon": -77.0}, **more)


class MergeTests(unittest.TestCase):
    def test_new_buildings_get_first_seen(self):
        merged = discovery.merge([], {"Bozzuto": [b("x")]}, "2026-11-18")
        self.assertEqual((merged[0]["first_seen"], merged[0]["missed"]), ("2026-11-18", 0))

    def test_merge_keeps_buildings_when_manager_failed(self):
        previous = [b("x", first_seen="2026-11-01", missed=0), b("c", manager="Camden", first_seen="2026-11-01", missed=0)]
        merged = discovery.merge(previous, {"Bozzuto": None, "Camden": [b("c", manager="Camden")]}, "2026-11-18")
        self.assertEqual({m["id"]: m["missed"] for m in merged}, {"x": 0, "c": 0})

    def test_merge_keeps_buildings_of_managers_not_run(self):
        previous = [b("c", manager="Camden", first_seen="2026-11-01", missed=1)]
        merged = discovery.merge(previous, {"Bozzuto": [b("x")]}, "2026-11-18")
        self.assertEqual({m["id"]: m["missed"] for m in merged}, {"x": 0, "c": 1})

    def test_merge_drops_after_three_misses(self):
        state = [b("x", first_seen="2026-11-01", missed=0), b("y", first_seen="2026-11-01", missed=0)]
        for expected in ({"x": 0, "y": 1}, {"x": 0, "y": 2}, {"x": 0}):
            state = discovery.merge(state, {"Bozzuto": [b("x")]}, "2026-11-18")
            self.assertEqual({m["id"]: m["missed"] for m in state}, expected)

    def test_found_again_resets_missed(self):
        merged = discovery.merge([b("x", first_seen="2026-11-01", missed=2)], {"Bozzuto": [b("x")]}, "2026-11-18")
        self.assertEqual(merged[0]["missed"], 0)

    def test_partial_run_counts_no_misses(self):
        previous = [b("x", first_seen="2026-11-01", missed=0), b("y", first_seen="2026-11-01", missed=0)]
        merged = discovery.merge(previous, {"Bozzuto": [b("x")]}, "2026-11-18", partial=True)
        self.assertEqual({m["id"]: m["missed"] for m in merged}, {"x": 0, "y": 0})

    def test_merge_keeps_first_seen_and_location(self):
        previous = [b("c", manager="Camden", lat=38.9, lon=-77.0, first_seen="2026-11-01", missed=0, state="DC",
                      county="11001", tract="11001010603", neighborhood="NoMa", in_region=True, feed_api="https://api/1")]
        found = b("c", manager="Camden", lat=None, lon=None, name="Renamed")
        m = discovery.merge(previous, {"Camden": [found]}, "2026-11-18")[0]
        self.assertEqual((m["name"], m["first_seen"], m["lat"], m["tract"], m["neighborhood"], m["in_region"], m["feed_api"]),
                         ("Renamed", "2026-11-01", 38.9, "11001010603", "NoMa", True, "https://api/1"))

    def test_changed_feed_forgets_cached_feed_api(self):
        previous = [b("x", first_seen="2026-11-01", missed=0, feed_api="https://api/1")]
        m = discovery.merge(previous, {"Bozzuto": [b("x", feed="https://sightmap.com/embed/new")]}, "2026-11-18")[0]
        self.assertNotIn("feed_api", m)


class LocateAllTests(QuietTestCase):
    def setUp(self):
        self.calls = []

    def locate(self, get, **where):
        self.calls.append(where)
        if where.get("address") == "nowhere":
            return None
        if where.get("lat") == 39.29:
            return {"lat": 39.29, "lon": -76.61, "state": "MD", "county": "24510", "tract": "24510040100"}
        return {"lat": 38.9, "lon": -77.0, "state": "DC", "county": "11001", "tract": "11001010603"}

    def run_it(self, buildings):
        names = []

        def name(get, lat, lon):
            names.append((lat, lon))
            return {"neighborhood": "NoMa", "zip": "20002"}
        discovery.locate_all(buildings, None, COUNTIES, locate=self.locate, reverse=name)
        return names

    def test_in_region(self):
        self.assertTrue(discovery.in_region({"county": "11001"}, COUNTIES))
        self.assertFalse(discovery.in_region({"county": "24510"}, COUNTIES))
        self.assertFalse(discovery.in_region({}, COUNTIES))

    def test_building_with_coordinates_is_located_and_named(self):
        buildings = [b("x")]
        names = self.run_it(buildings)
        self.assertEqual((buildings[0]["county"], buildings[0]["tract"], buildings[0]["in_region"], buildings[0]["neighborhood"]),
                         ("11001", "11001010603", True, "NoMa"))
        self.assertEqual(self.calls, [{"lat": 38.9, "lon": -77.0}])
        self.assertEqual(names, [(38.9, -77.0)])
        self.assertEqual(buildings[0]["zip"], "20002")

    def test_a_named_building_without_a_zip_is_looked_up_once_more(self):
        buildings = [b("x", tract="11001010603", county="11001", in_region=True, neighborhood="Shaw")]
        names = self.run_it(buildings)
        self.assertEqual((names, buildings[0]["neighborhood"], buildings[0]["zip"]), ([(38.9, -77.0)], "Shaw", "20002"))

    def test_building_with_only_an_address_gets_coordinates(self):
        buildings = [b("c", lat=None, lon=None, address={"full": "61 Pierce St NE Washington, DC 20002"})]
        self.run_it(buildings)
        self.assertEqual(self.calls, [{"address": "61 Pierce St NE Washington, DC 20002"}])
        self.assertEqual((buildings[0]["lat"], buildings[0]["lon"]), (38.9, -77.0))

    def test_out_of_region_building_is_marked_and_not_named(self):
        buildings = [b("balt", lat=39.29, lon=-76.61)]
        names = self.run_it(buildings)
        self.assertEqual((buildings[0]["in_region"], names), (False, []))

    def test_unmatched_address_stays_unlocated(self):
        buildings = [b("c", lat=None, lon=None, address={"full": "nowhere"})]
        self.run_it(buildings)
        self.assertEqual((buildings[0].get("tract"), buildings[0]["in_region"]), (None, False))

    def test_already_located_buildings_are_not_looked_up_again(self):
        buildings = [b("x", tract="11001010603", county="11001", in_region=True, neighborhood="NoMa", zip="20002")]
        names = self.run_it(buildings)
        self.assertEqual((self.calls, names), ([], []))

    def test_a_lookup_error_leaves_the_building_for_next_time(self):
        def broken(get, **where):
            raise OSError("down")
        buildings = [b("x")]
        discovery.locate_all(buildings, None, COUNTIES, locate=broken, reverse=lambda *a: {})
        self.assertEqual((buildings[0].get("tract"), buildings[0]["in_region"]), (None, False))


if __name__ == "__main__":
    unittest.main()
