import json
import os
import unittest

from aptrack.area import census, crime, rents
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


class CensusTests(QuietTestCase):
    def test_parse_tract_figures(self):
        tracts = census.parse(json.loads(fixture("censusreporter_tracts.json")))
        self.assertEqual(set(tracts), {"11001001402", "11001010603"})
        self.assertEqual(tracts["11001001402"], {
            "pop": 3521, "income": 176111, "rent": 2409, "age": 50.3, "degree": 89, "renters": 38,
            "race": {"white": 64, "black": 9, "asian": 6, "hispanic": 9, "other": 12}})

    def test_missing_estimates_are_none(self):
        payload = json.loads(fixture("censusreporter_tracts.json"))
        tract = payload["data"]["14000US11001001402"]
        tract["B19013"]["estimate"]["B19013001"] = None
        tract["B25064"]["estimate"]["B25064001"] = -666666666.0          # the census's "not available" marker
        tract["B03002"]["estimate"]["B03002001"] = 0
        got = census.parse(payload)["11001001402"]
        self.assertEqual((got["income"], got["rent"], got["race"]), (None, None, None))

    def test_url_asks_for_every_tract_in_a_county(self):
        url = census.url("11001")
        self.assertTrue(url.startswith("https://api.censusreporter.org/1.0/data/show/latest?table_ids=B01003,"))
        self.assertTrue(url.endswith("&geo_ids=140%7C05000US11001"))

    def test_read_keeps_wanted_tracts_and_survives_a_failed_county(self):
        def get(url):
            if "US11001" in url:
                return fixture("censusreporter_tracts.json").encode()
            raise OSError("down")
        got = census.read(["11001", "51013"], get, wanted={"11001010603"})
        self.assertEqual(set(got), {"11001010603"})


class CrimeTests(unittest.TestCase):
    def test_dc_offences(self):
        for offence in ("HOMICIDE", "SEX ABUSE", "ASSAULT W/DANGEROUS WEAPON", "ROBBERY"):
            self.assertEqual(crime.classify_dc(offence), "violent", offence)
        for offence in ("BURGLARY", "THEFT/OTHER", "THEFT F/AUTO", "MOTOR VEHICLE THEFT", "ARSON"):
            self.assertEqual(crime.classify_dc(offence), "property", offence)
        self.assertIsNone(crime.classify_dc("JAYWALKING"))
        self.assertIsNone(crime.classify_dc(None))

    def test_nibrs_codes(self):
        for code in ("09A", "11A", "11D", "120", "13A"):
            self.assertEqual(crime.classify_nibrs(code), "violent", code)
        for code in ("200", "220", "23A", "23H", "240"):
            self.assertEqual(crime.classify_nibrs(code), "property", code)
        for code in ("13B", "13C", "90Z", "35A", None, ""):
            self.assertIsNone(crime.classify_nibrs(code), code)

    def test_dc_incidents_from_a_page_of_the_feed(self):
        incidents = crime.dc_incidents(json.loads(fixture("dc_crime.json")))
        self.assertEqual(len(incidents), 2)
        lat, lon, kind, day = incidents[0]
        self.assertEqual((round(lat, 4), round(lon, 4), kind, day), (38.8678, -77.0107, "property", "2026-11-18"))

    def test_dc_incidents_without_a_place_or_category_are_dropped(self):
        payload = {"features": [{"attributes": {"OFFENSE": "ROBBERY", "REPORT_DAT": 1794973517000, "LATITUDE": None, "LONGITUDE": None}},
                                {"attributes": {"OFFENSE": "OTHER", "REPORT_DAT": 1794973517000, "LATITUDE": 38.9, "LONGITUDE": -77.0}}]}
        self.assertEqual(crime.dc_incidents(payload), [])

    def test_montgomery_incidents(self):
        rows = [{"start_date": "2026-11-17T20:45:00.000", "nibrs_code": "120", "latitude": "39.01", "longitude": "-77.04"},
                {"start_date": "2026-11-17T20:45:00.000", "nibrs_code": "23F", "latitude": "0.0", "longitude": "0.0"},
                {"start_date": "2026-11-17T20:45:00.000", "nibrs_code": "90Z", "latitude": "39.01", "longitude": "-77.04"}]
        self.assertEqual(crime.montgomery_incidents(rows), [(39.01, -77.04, "violent", "2026-11-17")])

    def test_counts_near_each_building(self):
        mile = 1 / 69.0
        buildings = [{"id": "a", "lat": 38.9, "lon": -77.0}, {"id": "far", "lat": 39.5, "lon": -77.0}, {"id": "nowhere", "lat": None, "lon": None}]
        incidents = [(38.9 + 0.2 * mile, -77.0, "violent", "2026-11-01"), (38.9 + 0.4 * mile, -77.0, "property", "2026-11-01"),
                     (38.9 + 0.45 * mile, -77.0, "property", "2026-10-01"), (38.9 + 0.7 * mile, -77.0, "violent", "2026-11-01")]
        self.assertEqual(crime.near(buildings, incidents),
                         {"a": {"violent": 1, "property": 2}, "far": {"violent": 0, "property": 0}})

    def test_since_drops_older_incidents(self):
        incidents = [(38.9, -77.0, "violent", "2025-11-17"), (38.9, -77.0, "violent", "2025-11-18")]
        self.assertEqual(crime.since(incidents, "2025-11-18"), [(38.9, -77.0, "violent", "2025-11-18")])

    def test_year_ago(self):
        self.assertEqual(crime.year_ago("2026-11-18"), "2025-11-18")
        self.assertEqual(crime.year_ago("2028-02-29"), "2027-02-28")


ZORI = """RegionID,SizeRank,RegionName,RegionType,StateName,State,City,Metro,CountyName,2024-09-30,2024-10-31,2024-11-30,2025-09-30,2025-10-31,2025-11-30
1,1,20015,zip,DC,DC,Washington,"Washington-Arlington-Alexandria, DC-VA-MD-WV",District of Columbia,2400.0,2410.5,2420.0,2500.0,,2541.0
2,2,22201,zip,VA,VA,Arlington,"Washington-Arlington-Alexandria, DC-VA-MD-WV",Arlington County,2600,2610,2620,2700,2710,2720
3,3,77449,zip,TX,TX,Katy,"Houston",Harris County,1500,1500,1500,1600,1600,1600
"""


class RentTrendTests(unittest.TestCase):
    def test_wanted_zips_only_with_latest_and_change_over_a_year(self):
        got = rents.parse(ZORI.splitlines(), {"20015", "20002"})
        self.assertEqual(set(got), {"20015"})
        self.assertEqual((got["20015"]["latest"], got["20015"]["month"], got["20015"]["year_change"]), (2541, "2025-11", 5.0))
        self.assertEqual(got["20015"]["series"], [["2024-09", 2400], ["2024-10", 2410], ["2024-11", 2420], ["2025-09", 2500], ["2025-11", 2541]])

    def test_no_year_ago_value_means_no_change_figure(self):
        text = "RegionID,SizeRank,RegionName,RegionType,StateName,State,City,Metro,CountyName,2025-10-31,2025-11-30\n1,1,20015,zip,DC,DC,W,M,C,,2541\n"
        got = rents.parse(text.splitlines(), {"20015"})
        self.assertEqual((got["20015"]["latest"], got["20015"]["year_change"]), (2541, None))


if __name__ == "__main__":
    unittest.main()


class DcPagingTests(unittest.TestCase):
    def test_dc_reads_every_page_whatever_size_the_server_chooses(self):
        asked = []

        def feature(n):
            return {"attributes": {"OFFENSE": "ROBBERY", "REPORT_DAT": 1794973517000, "LATITUDE": 38.9, "LONGITUDE": -77.0 - n / 1000}}

        def get(url, **options):
            asked.append(url)
            if url.endswith("?f=json"):
                return json.dumps({"layers": [{"id": 41, "name": "Crime Incidents - 2026"}]}).encode()
            offset = int(url.split("resultOffset=")[1].split("&")[0])
            pages = {0: [feature(1), feature(2)], 2: [feature(3)], 3: []}       # the server returns fewer than asked for
            return json.dumps({"features": pages[offset]}).encode()
        incidents = crime.dc(get, "2026-01-01", "2026-11-18")
        self.assertEqual(len(incidents), 3)
        self.assertEqual(len(asked), 4)

    def test_a_feed_that_never_ends_is_an_error_not_an_endless_loop(self):
        def get(url, **options):
            if url.endswith("?f=json"):
                return json.dumps({"layers": [{"id": 41, "name": "Crime Incidents - 2026"}]}).encode()
            return json.dumps({"features": [{"attributes": {"OFFENSE": "ROBBERY", "REPORT_DAT": 1794973517000,
                                                           "LATITUDE": 38.9, "LONGITUDE": -77.0}}]}).encode()
        with self.assertRaises(RuntimeError):
            crime.dc(get, "2026-01-01", "2026-11-18", max_pages=5)


class PrinceGeorgesTests(unittest.TestCase):
    def test_incident_types(self):
        for kind in ("HOMICIDE", "SEX OFFENSE", "ROBBERY, OTHER", "ROBBERY, VEHICLE", "ASSAULT, SHOOTING", "ASSAULT, WEAPON"):
            self.assertEqual(crime.classify_pg(kind), "violent", kind)
        for kind in ("THEFT", "THEFT FROM AUTO", "AUTO, STOLEN", "AUTO, STOLEN & RECOVERED", "B & E, RESIDENTIAL", "B & E, OTHER"):
            self.assertEqual(crime.classify_pg(kind), "property", kind)
        for kind in ("ACCIDENT", "ACCIDENT WITH IMPOUND", "ASSAULT", None, ""):       # plain "ASSAULT" may be a simple assault
            self.assertIsNone(crime.classify_pg(kind), kind)

    def test_incidents(self):
        rows = [{"date": "2026-10-22T00:00:00.000", "clearance_code_inc_type": "THEFT FROM AUTO", "latitude": "38.8673", "longitude": "-76.8384"},
                {"date": "2026-10-22T00:00:00.000", "clearance_code_inc_type": "ACCIDENT", "latitude": "38.8673", "longitude": "-76.8384"},
                {"date": "2026-10-21T00:00:00.000", "clearance_code_inc_type": "ROBBERY, OTHER", "latitude": "0", "longitude": "0"},
                {"date": "2026-10-21T00:00:00.000", "clearance_code_inc_type": "ROBBERY, OTHER"}]
        self.assertEqual(crime.pg_incidents(rows), [(38.8673, -76.8384, "property", "2026-10-22")])

    def test_reader_pages_until_a_short_page_and_is_registered(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            return json.dumps([{"date": "2026-10-22T00:00:00.000", "clearance_code_inc_type": "HOMICIDE", "latitude": "38.9", "longitude": "-76.9"}]).encode()
        incidents = crime.prince_georges(get, "2025-11-18", "2026-11-18")
        self.assertEqual((len(incidents), len(asked)), (1, 1))
        self.assertTrue(asked[0].startswith(crime.PRINCE_GEORGES + "?"))
        self.assertIn("2025-11-18T00:00:00", asked[0])
        self.assertIs(crime.SOURCES["24033"], crime.prince_georges)


class FairfaxTests(unittest.TestCase):
    def feature(self, code, x=-77.3, y=38.85, when=1794973517000):
        return {"attributes": {"IBRCode": code, "DateReported": when}, "geometry": {"x": x, "y": y}}

    def test_incidents_use_the_offence_code_and_the_point(self):
        page = {"features": [self.feature("120"), self.feature("23F"), self.feature("13B"), self.feature("290"),
                             {"attributes": {"IBRCode": "220", "DateReported": 1794973517000}},            # no point
                             {"attributes": {"IBRCode": "13A", "DateReported": None}, "geometry": {"x": -77.3, "y": 38.85}}]}
        self.assertEqual(crime.fairfax_incidents(page), [(38.85, -77.3, "violent", "2026-11-18"), (38.85, -77.3, "property", "2026-11-18")])

    def test_reader_reads_both_layers_page_by_page(self):
        asked = []

        def get(url, **options):
            asked.append(url)
            if url.endswith("FeatureServer?f=json"):
                return json.dumps({"layers": [{"id": 1 if "Person" in url else 0, "name": "x"}]}).encode()
            offset = int(url.split("resultOffset=")[1].split("&")[0])
            if "Person" in url:
                return json.dumps({"features": [self.feature("13A")] if offset == 0 else []}).encode()
            return json.dumps({"features": {0: [self.feature("23F"), self.feature("240")], 2: [self.feature("220")]}.get(offset, [])}).encode()
        incidents = crime.fairfax(get, "2025-11-18", "2026-11-18")
        self.assertEqual(sorted(kind for _, _, kind, _ in incidents), ["property", "property", "property", "violent"])
        self.assertTrue(any("/FeatureServer/1/query" in u and "Person" in u for u in asked))
        self.assertTrue(all("2025-11-18" in u for u in asked if "/query" in u))
        self.assertIs(crime.SOURCES["51059"], crime.fairfax)
