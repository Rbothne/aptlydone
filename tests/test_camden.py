import json
import os
import re
import unittest

from aptrack.readers import READERS, ReadError, camden

HERE = os.path.join(os.path.dirname(__file__), "fixtures")
with open(os.path.join(HERE, "camden_available.html"), encoding="utf-8") as f:
    HTML = f.read()
B = {"id": "camden-camden-noma", "url": "https://www.camdenliving.com/apartments/washington-dc/camden-noma",
     "platform": "camden", "feed": "https://www.camdenliving.com/apartments/washington-dc/camden-noma/available-apartments"}


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


def edited(change):
    """The fixture page with its embedded data changed by `change(page_props)`."""
    match = re.search(r'(<script id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', HTML, flags=re.S)
    data = json.loads(match.group(2))
    change(data["props"]["pageProps"])
    return HTML[:match.start(2)] + json.dumps(data) + HTML[match.end(2):]


class ParseTests(unittest.TestCase):
    def test_units_from_floor_plans(self):
        u = by_unit(camden.parse(HTML, B))["1215"]
        self.assertEqual((u["plan"], u["beds"], u["baths"], u["sqft"], u["floor"], u["rent"], u["lease"], u["available"]),
                         ("S4", 0, 1, 495, 12, 1829, 15, "2026-12-18"))
        self.assertEqual((u["id"], u["url"]), ("camden-camden-noma:1215", B["url"]))

    def test_every_unit_of_every_plan_is_listed(self):
        self.assertEqual(set(by_unit(camden.parse(HTML, B))), {"515", "815", "1215", "717", "509"})

    def test_one_bedroom_plan(self):
        u = by_unit(camden.parse(HTML, B))["509"]
        self.assertEqual((u["plan"], u["beds"], u["sqft"]), ("A1", 1, 586))

    def test_fees_from_total_rent(self):
        self.assertEqual(by_unit(camden.parse(HTML, B))["1215"]["fees"], 124)

    def test_empty_special_is_none(self):
        self.assertIsNone(by_unit(camden.parse(HTML, B))["1215"]["special"])

    def test_special_joins_title_and_description(self):
        def change(pp):
            pp["specialCtaTitle"], pp["specialCtaDescription"] = "Up to 6 weeks free", "On select homes."
        self.assertEqual(by_unit(camden.parse(edited(change), B))["1215"]["special"],
                         "Up to 6 weeks free. On select homes.")

    def test_building_number_is_part_of_the_unit_label(self):
        def change(pp):
            pp["data"]["availableApartments"][1]["availableUnitRefs"][0]["buildingNumber"] = "3"
        self.assertIn("3-509", by_unit(camden.parse(edited(change), B)))

    def test_page_without_data_raises_read_error(self):
        with self.assertRaises(ReadError):
            camden.parse("<html><body>Access denied</body></html>", B)

    def test_page_without_listing_data_raises_read_error(self):
        def change(pp):
            del pp["data"]["availableApartments"]
        with self.assertRaises(ReadError):
            camden.parse(edited(change), B)

    def test_no_available_units_returns_empty_list(self):
        def change(pp):
            pp["data"]["availableApartments"] = []
        result = camden.parse(edited(change), B)
        self.assertEqual((result["units"], result["fees"], result["amenities"]), ([], [], []))


class ReadTests(unittest.TestCase):
    def test_read_fetches_the_feed_page(self):
        asked = []

        def get(url):
            asked.append(url)
            return HTML.encode()
        self.assertEqual(len(camden.read(B, get)["units"]), 5)
        self.assertEqual(asked, [B["feed"]])

    def test_registered(self):
        self.assertIs(READERS["camden"], camden.read)


if __name__ == "__main__":
    unittest.main()
