import json
import os
import tempfile
import unittest

from aptrack import area, history, output
from aptrack.area import census, crime, rents
from tests.quiet import QuietTestCase
from tests.test_area import ZORI, fixture

TODAY = "2026-11-18"


def building(building_id, county="11001", tract="11001001402", zip_code="20015", lat=38.8678, lon=-77.0107, **more):
    return dict({"id": building_id, "name": building_id, "county": county, "tract": tract, "lat": lat, "lon": lon,
                 "in_region": True, "address": {"street": "1 Main St", "city": "Washington", "state": "DC", "zip": zip_code}}, **more)


def web(montgomery_fails=False):
    layers = {"layers": [{"id": 7, "name": "Crime Incidents - 2025"}, {"id": 41, "name": "Crime Incidents - 2026"},
                         {"id": 39, "name": "Crime Incidents - Last 30 Days"}]}

    def get(url, **options):
        if url.startswith(census.API):
            return fixture("censusreporter_tracts.json").encode()
        if url == crime.DC_SERVICE + "?f=json":
            return json.dumps(layers).encode()
        if url.startswith(crime.DC_SERVICE + "/41/"):                  # one page of incidents, then no more
            return fixture("dc_crime.json").encode() if "resultOffset=0&" in url else b'{"features": []}'
        if url.startswith(crime.DC_SERVICE + "/7/"):
            return b'{"features": []}'
        if url.startswith(crime.MONTGOMERY):
            if montgomery_fails:
                raise OSError("down")
            return json.dumps([{"start_date": "2026-11-01T10:00:00.000", "nibrs_code": "120", "latitude": "39.0", "longitude": "-77.1"}]).encode()
        if url == rents.SOURCE:
            return ZORI.encode()
        if url.startswith(crime.ARLINGTON):
            return json.dumps([{"offenseDsc": "ROBBERY", "latitudeCrd": "38.89", "longitudeCrd": "-77.08",
                                "firstReportDtm": "2022-03-01T07:45:00.000Z"}]).encode()
        if url.startswith((crime.PRINCE_GEORGES, crime.FAIRFAX)):
            raise OSError("not part of this test")
        raise AssertionError("unexpected request: " + url)
    return get


class ZipTests(unittest.TestCase):
    def test_zip_from_parts_or_from_a_one_line_address(self):
        self.assertEqual(area.zip_code({"address": {"zip": "20015"}}), "20015")
        self.assertEqual(area.zip_code({"address": {"full": "61 Pierce St NE Washington, DC 20002"}}), "20002")
        self.assertEqual(area.zip_code({"address": {"zip": "20015-1234"}}), "20015")
        self.assertIsNone(area.zip_code({"address": {"full": "Somewhere"}}))
        self.assertIsNone(area.zip_code({}))

    def test_the_looked_up_zip_wins_and_an_implausible_one_is_ignored(self):
        # Some managers put the street number where the ZIP belongs. Every ZIP in DC, Maryland and Virginia starts with 2.
        wrong = {"street": "11410 Reston Station Blvd", "city": "Reston", "state": "VA", "zip": "11410"}
        self.assertIsNone(area.zip_code({"address": wrong}))
        self.assertEqual(area.zip_code({"zip": "20190", "address": wrong}), "20190")


class CollectTests(QuietTestCase):
    def test_collects_census_crime_and_rent_trend(self):
        buildings = [building("dc"), building("moco", county="24031", tract="24031700000", zip_code="20814", lat=39.0, lon=-77.1),
                     building("va", county="51013", tract="51013101701", zip_code="22201", lat=38.89, lon=-77.08)]
        got = area.collect(buildings, {}, web(), TODAY, "2026-11-18T12:00Z")
        self.assertEqual(set(got["tracts"]), {"11001001402"})
        self.assertEqual(got["crime"], {"dc": {"violent": 0, "property": 1}, "moco": {"violent": 1, "property": 0},
                                        "va": {"violent": 1, "property": 0, "period": ["2021-06-28", "2022-06-28"]}})
        self.assertEqual(got["crime_counties"], ["11001", "24031", "51013"])
        self.assertEqual(set(got["zips"]), {"20015", "22201"})
        self.assertEqual(got["updated"], "2026-11-18T12:00Z")

    def test_a_failed_source_keeps_what_was_there(self):
        previous = {"crime": {"moco": {"violent": 4, "property": 9}}, "crime_counties": ["24031"], "tracts": {"x": {}}, "zips": {"1": {}}}
        buildings = [building("dc"), building("moco", county="24031", lat=39.0, lon=-77.1)]
        got = area.collect(buildings, previous, web(montgomery_fails=True), TODAY, "now")
        self.assertEqual(got["crime"]["moco"], {"violent": 4, "property": 9})
        self.assertEqual(got["crime"]["dc"], {"violent": 0, "property": 1})
        self.assertEqual(got["crime_counties"], ["11001", "24031"])

    def test_parts_can_be_run_alone(self):
        got = area.collect([building("dc")], {"zips": {"old": {}}}, web(), TODAY, "now", parts=("crime",))
        self.assertEqual((set(got["crime"]), got["zips"], "tracts" in got), ({"dc"}, {"old": {}}, False))

    def test_counties_without_buildings_are_not_fetched(self):
        asked = []
        inner = web()

        def get(url, **options):
            asked.append(url)
            return inner(url, **options)
        area.collect([building("dc")], {}, get, TODAY, "now", parts=("crime",))
        self.assertFalse([u for u in asked if u.startswith(crime.MONTGOMERY)])


class OutputTests(QuietTestCase):
    def test_area_data_is_written_for_the_page(self):
        with tempfile.TemporaryDirectory() as out:
            b = building("dc", manager="X", platform="link", url="https://x.test", neighborhood="Navy Yard", first_seen=TODAY, state="DC")
            collected = area.collect([b], {}, web(), TODAY, "2026-11-18T12:00Z")
            output.write_site([b], {}, history.new_state(), out, "2026-11-18T13:00Z", area=collected)
            with open(os.path.join(out, "index.json"), encoding="utf-8") as f:
                index = json.load(f)
        entry = index["buildings"][0]
        self.assertEqual((entry["crime"], entry["zip"]), ({"violent": 0, "property": 1}, "20015"))
        self.assertEqual(index["tracts"]["11001001402"]["income"], 176111)
        self.assertEqual(index["zips"]["20015"]["latest"], 2541)
        self.assertEqual((index["crime_counties"], index["area_updated"]), (["11001"], "2026-11-18T12:00Z"))

    def test_without_area_data_the_page_files_say_so(self):
        with tempfile.TemporaryDirectory() as out:
            b = building("dc", manager="X", platform="link", url="https://x.test", neighborhood="Navy Yard", first_seen=TODAY, state="DC")
            output.write_site([b], {}, history.new_state(), out, "now")
            with open(os.path.join(out, "index.json"), encoding="utf-8") as f:
                index = json.load(f)
        self.assertEqual((index["buildings"][0]["crime"], index["tracts"], index["zips"], index["crime_counties"]), (None, {}, {}, []))


if __name__ == "__main__":
    unittest.main()
