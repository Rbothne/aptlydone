import os
import unittest

from aptrack import fetch, geo
from aptrack.area import alexandria, crime
from tests.quiet import QuietTestCase

HERE = os.path.join(os.path.dirname(__file__), "fixtures")
with open(os.path.join(HERE, "alexandria_results.html"), encoding="utf-8") as f:
    RESULTS = f.read()
ROBBERY = "<tr><td>26-1</td><td>11/05/2026</td><td>01:00 AM</td><td>OPEN</td><td>100</td><td>KING ST</td><td>Robbery</td></tr>"


def page(rows, count=None):
    body = "".join(rows)
    return (f'<span id="x_labelRecordCount"><b>{count if count is not None else len(rows)} records match your query.</b></span>'
            f'<table class="sortable"><thead><tr><th>Case No.</th></tr></thead><tbody>{body}</tbody></table>')


class ParseTests(unittest.TestCase):
    def test_classification(self):
        for text in ("Homicide", "Rape", "Robbery", "Agg Assault", "Sex Offenses, Forcible", "ROBBERY"):
            self.assertEqual(alexandria.classify(text), "violent", text)
        for text in ("Burglary", "Larceny", "Stolen Auto", "Arson", "LARCENY"):
            self.assertEqual(alexandria.classify(text), "property", text)
        for text in ("Assault Offenses", "All Other Offenses", "Fraud Offenses", "DWI", "Destruction/Vandalism", "Sex Offenses, Nonforcible", "", None):
            self.assertIsNone(alexandria.classify(text), text)

    def test_rows_and_count(self):
        rows = alexandria.rows(RESULTS)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0], {"address": "5700 DOW AVE", "kind": "property", "day": "2026-11-04"})
        self.assertIsNone(rows[2]["kind"])                                  # a simple assault
        self.assertEqual(alexandria.count(RESULTS), 212)
        self.assertEqual(alexandria.count("<html></html>"), None)

    def test_weekly_windows_cover_the_period(self):
        windows = alexandria.windows("2026-11-01", "2026-11-18")
        self.assertEqual(windows, [("2026-11-01", "2026-11-07"), ("2026-11-08", "2026-11-14"), ("2026-11-15", "2026-11-18")])


class ReaderTests(QuietTestCase):
    def test_incidents_are_placed_by_geocoding_their_blocks_once(self):
        asked, geocoded = [], []

        def get(url, **options):
            asked.append(url)
            return page([ROBBERY, ROBBERY.replace("26-1", "26-2"), ROBBERY.replace("Robbery", "DWI").replace("KING ST", "DUKE ST")]).encode()

        def place(addresses, cache):
            geocoded.append(sorted(addresses))
            return {"100 KING ST": (38.8048, -77.0469)}
        incidents = alexandria.incidents(get, "2026-11-01", "2026-11-07", place=place, cache={})
        self.assertEqual(incidents, [(38.8048, -77.0469, "violent", "2026-11-05")] * 2)
        self.assertEqual(geocoded, [["100 KING ST"]])                      # the DWI's street was never looked up
        self.assertEqual(asked, [alexandria.URL + "?&sd=20261101&ed=20261107"])

    def test_a_window_that_hits_the_500_limit_is_split(self):
        asked = []

        def get(url, **options):
            asked.append(url.split("?&")[1])
            full = "sd=20261101&ed=20261107" in url
            return page([ROBBERY], count=500 if full else 1).encode()
        alexandria.incidents(get, "2026-11-01", "2026-11-07", place=lambda addresses, cache: {}, cache={})
        self.assertEqual(asked, ["sd=20261101&ed=20261107", "sd=20261101&ed=20261104", "sd=20261105&ed=20261107"])

    def test_unplaced_addresses_drop_out(self):
        get = lambda url, **options: page([ROBBERY]).encode()
        self.assertEqual(alexandria.incidents(get, "2026-11-01", "2026-11-07", place=lambda a, c: {}, cache={}), [])

    def test_a_block_the_geocoder_cannot_place_is_tried_once_more_one_door_along(self):
        bodies = []

        def get(url, **options):
            return page([ROBBERY]).encode()                                 # every week: a robbery in the 100 block of King St

        def post(url, body, headers=None, **options):
            bodies.append(body)
            if b'"100 KING ST"' in body:
                return b'"1","100 KING ST, Alexandria, VA, ","No_Match"\n'
            return b'"1","101 KING ST, Alexandria, VA, ","Match","Exact","101 KING ST, ALEXANDRIA, VA, 22314","-77.0469,38.8048","1","L"\n'
        cache = {}
        incidents = crime.alexandria(get, "2026-11-01", "2026-11-07", post=post, cache=cache)
        self.assertEqual(incidents, [(38.8048, -77.0469, "violent", "2026-11-05")])
        self.assertEqual(len(bodies), 2)
        self.assertIn(b'"101 KING ST"', bodies[1])

    def test_registered_as_alexandrias_crime_source(self):
        self.assertIn("51510", crime.SOURCES)


class BatchGeocodeTests(QuietTestCase):
    ANSWER = ('"1","100 KING ST, Alexandria, VA, ","Match","Exact","100 KING ST, ALEXANDRIA, VA, 22314","-77.0469,38.8048","1","L"\n'
              '"2","5700 DOW AVE, Alexandria, VA, ","No_Match"\n')

    def test_batch_posts_a_csv_and_reads_coordinates(self):
        sent = []

        def post(url, body, headers=None, **options):
            sent.append((url, body, headers))
            return self.ANSWER.encode()
        cache = {}
        found = geo.batch(["100 KING ST", "5700 DOW AVE"], "Alexandria", "VA", post, cache)
        self.assertEqual(found, {"100 KING ST": (38.8048, -77.0469)})
        self.assertEqual(cache, {"100 KING ST, Alexandria, VA": [38.8048, -77.0469], "5700 DOW AVE, Alexandria, VA": None})
        url, body, headers = sent[0]
        self.assertEqual(url, geo.CENSUS_BATCH)
        self.assertIn(b'"1","100 KING ST","Alexandria","VA",""', body)
        self.assertIn(b"Public_AR_Current", body)
        self.assertTrue(headers["Content-Type"].startswith("multipart/form-data; boundary="))

    def test_cached_addresses_are_not_sent_again(self):
        def post(url, body, headers=None, **options):
            raise AssertionError("nothing new to look up")
        cache = {"100 KING ST, Alexandria, VA": [38.8048, -77.0469], "5700 DOW AVE, Alexandria, VA": None}
        self.assertEqual(geo.batch(["100 KING ST", "5700 DOW AVE"], "Alexandria", "VA", post, cache), {"100 KING ST": (38.8048, -77.0469)})

    def test_a_failed_batch_caches_nothing(self):
        def post(url, body, headers=None, **options):
            raise OSError("down")
        cache = {}
        self.assertEqual(geo.batch(["100 KING ST"], "Alexandria", "VA", post, cache), {})
        self.assertEqual(cache, {})


class PostTests(unittest.TestCase):
    def test_post_sends_the_body_and_returns_the_answer(self):
        seen = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"ok"

        def opener(request, timeout=None):
            seen.append((request.get_method(), request.data, request.get_header("Content-type")))
            return Response()
        self.assertEqual(fetch.post("https://x.test/a", b"body", {"Content-Type": "text/plain"}, opener=opener), b"ok")
        self.assertEqual(seen, [("POST", b"body", "text/plain")])


if __name__ == "__main__":
    unittest.main()
