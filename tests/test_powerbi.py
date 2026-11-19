"""Public Power BI reports (the Howard and Loudoun crime dashboards): asking for rows and decoding the reply."""
import gzip
import json
import unittest

from aptrack import area
from aptrack.area import crime, powerbi
from tests.quiet import QuietTestCase

VIEW = "https://app.powerbigov.us/view?r=eyJrIjoiZTgyMTFiZjktMDg4MC00MmZjLTlmZGQtMjg1YjQ5ODY3NmNhIiwidCI6IjU5MGYxNzAyLThhMzYtNDkzMS04ZjJmLWQzNWEwNmRkYzRjOCJ9"
KEY = "e8211bf9-0880-42fc-9fdd-285b498676ca"
PAGE = "<script>var resolvedClusterUri = 'https://wabi-us-gov-virginia-redirect.analysis.usgovcloudapi.net/';</script>"
API = "https://wabi-us-gov-virginia-api.analysis.usgovcloudapi.net"
MODELS = json.dumps({"models": [{"id": 1686780, "name": "x"}], "exploration": {}})
DAY = 1763424000000                 # 2025-11-18 00:00 UTC, in milliseconds


def reply(rows, restart=None, dicts=None):
    ds = {"PH": [{"DM0": rows}]}
    if restart:
        ds["RT"] = restart
    if dicts:
        ds["ValueDicts"] = dicts
    return {"results": [{"result": {"data": {"dsr": {"DS": [ds]}}}}]}


class PiecesTests(unittest.TestCase):
    def test_the_report_key_is_inside_the_link(self):
        self.assertEqual(powerbi.key(VIEW), KEY)
        with self.assertRaises(ValueError):
            powerbi.key("https://app.powerbigov.us/view?r=not-a-key")

    def test_the_data_host_is_named_in_the_page(self):
        self.assertEqual(powerbi.api_host(PAGE), API)
        with self.assertRaises(ValueError):
            powerbi.api_host("<html>Please verify you are human</html>")

    def test_a_query_names_tables_columns_the_first_day_and_how_many_rows(self):
        q = powerbi.query(7, {"p": "POINTS", "c": "CHARGES"}, [("p", "ID"), ("p", "LAT"), ("c", "CODE")], ("p", "WHEN"), "2025-11-18", count=500)
        self.assertEqual(q["modelId"], 7)
        command = q["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]
        self.assertEqual(command["Query"]["From"], [{"Name": "p", "Entity": "POINTS", "Type": 0}, {"Name": "c", "Entity": "CHARGES", "Type": 0}])
        self.assertEqual([s["Name"] for s in command["Query"]["Select"]], ["POINTS.ID", "POINTS.LAT", "CHARGES.CODE"])
        self.assertEqual(command["Query"]["Select"][2]["Column"], {"Expression": {"SourceRef": {"Source": "c"}}, "Property": "CODE"})
        condition = command["Query"]["Where"][0]["Condition"]["Comparison"]
        self.assertEqual((condition["ComparisonKind"], condition["Left"]["Column"]["Property"], condition["Right"]["Literal"]["Value"]),
                         (2, "WHEN", "datetime'2025-11-18T00:00:00'"))
        self.assertEqual(command["Binding"]["Primary"]["Groupings"], [{"Projections": [0, 1, 2]}])
        self.assertEqual(command["Binding"]["DataReduction"]["Primary"]["Window"], {"Count": 500})
        again = powerbi.query(7, {"p": "POINTS"}, [("p", "ID")], ("p", "WHEN"), "2025-11-18", restart=[["'9'"]])
        window = again["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Binding"]["DataReduction"]["Primary"]["Window"]
        self.assertEqual(window["RestartTokens"], [["'9'"]])

    def test_rows_repeat_values_from_the_row_above_leave_blanks_and_look_text_up(self):
        schema = [{"N": "G0", "T": 1}, {"N": "G1", "T": 7}, {"N": "G2", "T": 3}, {"N": "G3", "T": 1, "DN": "D0"}]
        rows = [{"S": schema, "C": ["a", DAY, 39.1, 0]},
                {"C": ["b", 1], "R": 0b0110},                 # same day and latitude as above
                {"C": ["c", DAY + 5], "Ø": 0b1100},           # no latitude, no code
                {"C": [38.9], "R": 0b1011}]                   # only the latitude changes
        got, restart = powerbi.decode(reply(rows, restart=[["'c'"]], dicts={"D0": ["13A", "23C"]}))
        self.assertEqual(got, [["a", DAY, 39.1, "13A"], ["b", DAY, 39.1, "23C"], ["c", DAY + 5, None, None], ["c", DAY + 5, 38.9, None]])
        self.assertEqual(restart, [["'c'"]])
        self.assertEqual(powerbi.decode(reply([])), ([], None))

    def test_a_reply_that_is_an_error_is_not_an_empty_year(self):
        with self.assertRaises(ValueError):
            powerbi.decode({"error": {"code": "QueryUserError"}})
        with self.assertRaises(ValueError):
            powerbi.decode({"results": [{"result": {"data": {"dsr": {"DataShapes": [{"odata.error": {"code": "x"}}]}}}}]})


class RowsTests(QuietTestCase):
    def web(self, replies, compress=False):
        self.gets, self.posts, self.slept = [], [], []
        queue = list(replies)

        def get(url, **options):
            self.gets.append((url, options.get("headers")))
            return (PAGE if url == VIEW else MODELS).encode()

        def post(url, body, headers=None, **options):
            self.posts.append((url, json.loads(body), headers))
            raw = json.dumps(queue.pop(0)).encode()
            return gzip.compress(raw) if compress else raw
        return get, post

    def ask(self, get, post):
        return powerbi.rows(get, post, VIEW, {"t": "T"}, [("t", "ID")], ("t", "WHEN"), "2025-11-18", sleep=self.slept.append)

    def test_one_window_is_one_request(self):
        get, post = self.web([reply([{"S": [{"N": "G0", "T": 1}], "C": ["a"]}, {"C": ["b"]}])])
        self.assertEqual(self.ask(get, post), [["a"], ["b"]])
        self.assertEqual([url for url, _ in self.gets], [VIEW, f"{API}/public/reports/{KEY}/modelsAndExploration?preferReadOnlySession=true"])
        self.assertEqual(self.gets[1][1]["X-PowerBI-ResourceKey"], KEY)
        url, body, headers = self.posts[0]
        self.assertEqual((url, body["modelId"], headers["X-PowerBI-ResourceKey"], headers["Content-Type"]),
                         (f"{API}/public/reports/querydata?synchronous=true", 1686780, KEY, "application/json"))

    def test_more_rows_than_one_window_are_asked_for_in_turn(self):
        schema = [{"N": "G0", "T": 1}]
        get, post = self.web([reply([{"S": schema, "C": ["a"]}], restart=[["'a'"]]), reply([{"S": schema, "C": ["b"]}])])
        self.assertEqual(self.ask(get, post), [["a"], ["b"]])
        window = self.posts[1][1]["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Binding"]["DataReduction"]["Primary"]["Window"]
        self.assertEqual(window["RestartTokens"], [["'a'"]])
        self.assertEqual(len(self.slept), 2)                  # a pause before each request

    def test_a_report_that_never_ends_is_stopped(self):
        schema = [{"N": "G0", "T": 1}]
        get, post = self.web([reply([{"S": schema, "C": ["a"]}], restart=[["'a'"]])] * 5)
        with self.assertRaises(RuntimeError):
            powerbi.rows(get, post, VIEW, {"t": "T"}, [("t", "ID")], ("t", "WHEN"), "2025-11-18", sleep=self.slept.append, max_pages=3)

    def test_a_compressed_reply_is_read(self):
        get, post = self.web([reply([{"S": [{"N": "G0", "T": 1}], "C": ["a"]}])], compress=True)
        self.assertEqual(self.ask(get, post), [["a"]])


class CrimeTests(QuietTestCase):
    def test_howard_counts_an_incident_once_by_its_most_serious_charge(self):
        rows = [["250113958", DAY + 1000, 39.289, -76.824, "13A"], ["250113958", DAY + 1000, 39.289, -76.824, "90D"],      # assault and DUI: violent
                ["250083950", DAY + 86400000, 39.275, -76.803, "23D"], ["250083950", DAY + 86400000, 39.275, -76.803, "90Z"],   # theft: property
                ["250074732", DAY, 39.115, -76.833, "90Z"],                                                                  # not counted
                ["250000001", DAY, None, None, "13A"],                                                                       # no location
                ["250000002", DAY, 39.2, -76.8, "23C"], ["250000002", DAY, 39.2, -76.8, "120"]]                              # theft and robbery: violent
        self.assertEqual(sorted(crime.howard_incidents(rows)),
                         [(39.2, -76.8, "violent", "2025-11-18"), (39.275, -76.803, "property", "2025-11-19"), (39.289, -76.824, "violent", "2025-11-18")])

    def test_coordinates_sent_as_text_are_read_as_numbers_and_nonsense_is_skipped(self):
        rows = [["1", DAY, "39.2", "-76.8", "13A"], ["2", DAY, "n/a", "-76.8", "13A"], ["3", str(DAY), 39.3, -76.9, "23C"]]
        self.assertEqual(sorted(crime.howard_incidents(rows)), [(39.2, -76.8, "violent", "2025-11-18"), (39.3, -76.9, "property", "2025-11-18")])

    def test_one_countys_bad_data_does_not_stop_the_others(self):
        def get(url, **options):
            return (PAGE if "view?r=" in url else MODELS).encode()

        def post(url, body, headers=None, **options):
            schema = [{"N": f"G{n}", "T": 1} for n in range(5)]
            return json.dumps(reply([{"S": schema, "C": ["250113958", DAY + 1000, 39.2, -76.8, "13A"]}])).encode()
        buildings = [{"id": "h", "county": "24027", "lat": "not a number", "lon": -76.8, "tract": "1", "in_region": True},
                     {"id": "l", "county": "51107", "lat": 39.2, "lon": -76.8, "tract": "1", "in_region": True}]
        got = area.collect(buildings, {}, get, "2026-11-18", "now", parts=("crime",), post=post, sleep=lambda s: None)
        self.assertEqual(got["crime_counties"], ["51107"])

    def test_loudoun_counts_each_incident_once_per_kind(self):
        rows = [["Offense v4 SO170017201 1 UNSECURED", DAY, 39.009, -77.438, "23C"], ["Offense v4 SO170017201 2 UNSECURED", DAY, 39.009, -77.438, "13B"],
                ["Offense v4 SO180004849 0 UNSECURED", DAY, None, None, "23C"],
                ["Offense v4 SO250000001 0 UNSECURED", DAY, 39.03, -77.42, "120"], ["Offense v4 SO250000001 1 UNSECURED", DAY, 39.03, -77.42, "13A"],
                ["Offense v4 SO250000001 2 UNSECURED", DAY, 39.03, -77.42, "240"]]
        self.assertEqual(sorted(crime.loudoun_incidents(rows)),
                         [(39.009, -77.438, "property", "2025-11-18"), (39.03, -77.42, "property", "2025-11-18"), (39.03, -77.42, "violent", "2025-11-18")])

    def test_both_are_registered_and_asked_for_through_post(self):
        self.assertEqual((crime.SOURCES["24027"], crime.SOURCES["51107"]), (crime.howard, crime.loudoun))
        self.assertTrue({"24027", "51107"} <= crime.NEEDS_POST)
        asked = []

        def get(url, **options):
            return (PAGE if "view?r=" in url else MODELS).encode()

        def post(url, body, headers=None, **options):
            asked.append(json.loads(body))
            schema = [{"N": f"G{n}", "T": 1} for n in range(5)]
            return json.dumps(reply([{"S": schema, "C": ["250113958", DAY + 1000, 39.2, -76.8, "13A"]}])).encode()
        buildings = [{"id": "h", "county": "24027", "lat": 39.2, "lon": -76.8, "tract": "1", "in_region": True}]
        got = area.collect(buildings, {}, get, "2026-11-18", "now", parts=("crime",), post=post, sleep=lambda s: None)
        self.assertEqual(got["crime"]["h"]["violent"], 1)
        self.assertEqual(got["crime_counties"], ["24027"])
        command = asked[0]["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Query"]
        self.assertEqual([entity["Entity"] for entity in command["From"]], ["LW_LOCATIONS_POINT_CA", "LW_Charges"])
        self.assertEqual(command["Where"][0]["Condition"]["Comparison"]["Right"]["Literal"]["Value"], "datetime'2025-11-18T00:00:00'")


if __name__ == "__main__":
    unittest.main()
