"""Fields added after the first live run: income-restricted flag, floor-plan drawing, refundable fees, feature text."""
import copy
import unittest

from aptrack import units
from aptrack.readers import camden, sightmap
from tests import test_camden, test_sightmap

FEED, B = test_sightmap.FEED, test_sightmap.B


def by_unit(result):
    return {u["unit"]: u for u in result["units"]}


def feed_with(change):
    feed = copy.deepcopy(FEED)
    change(feed["data"])
    return feed


class LooksRestrictedTests(unittest.TestCase):
    def test_looks_restricted(self):
        for name in ("2 Bed/2 Bath ADU-B9", "A1 WDU", "MPDU 1BR", "2 Bed/2 Bath WDU80-316", "1 Bed IZ", "Affordable 1 Bed",
                     "Workforce Housing A2", "Income Restricted Studio"):
            self.assertTrue(units.looks_restricted(name), name)
        for name in ("A1", "Studio", "B4*", "Wizard", "1 Bed/1 Bath Den - Alula - B09", "Plaza Suite", None, ""):
            self.assertFalse(units.looks_restricted(name), name)


class SightmapFieldTests(unittest.TestCase):
    def unit204(self, data):
        return next(u for u in data["units"] if u["unit_number"] == "204")

    def test_restricted_from_feed_flag(self):
        def change(data):
            self.unit204(data)["affordable_housing_info"] = {"is_affordable_housing_unit": True}
            next(u for u in data["units"] if u["unit_number"] == "014")["affordable_housing_info"] = {"is_affordable_housing_unit": False}
        got = by_unit(sightmap.parse(feed_with(change), B))
        self.assertIs(got["204"]["restricted"], True)
        self.assertIs(got["014"]["restricted"], False)

    def test_restricted_unknown_without_flag_or_name(self):
        self.assertIsNone(by_unit(sightmap.parse(FEED, B))["221"]["restricted"])

    def test_restricted_from_plan_name(self):
        def change(data):
            plan_id = self.unit204(data)["floor_plan_id"]
            next(p for p in data["floor_plans"] if p["id"] == plan_id)["name"] = "1 Bed/1 Bath WDU80"
            self.unit204(data)["affordable_housing_info"] = {"is_affordable_housing_unit": False}
        self.assertIs(by_unit(sightmap.parse(feed_with(change), B))["204"]["restricted"], True)

    def test_plan_image(self):
        def change(data):
            plan_id = self.unit204(data)["floor_plan_id"]
            next(p for p in data["floor_plans"] if p["id"] == plan_id)["image_url"] = "https://cdn.sightmap.com/plan.jpg"
        got = by_unit(sightmap.parse(feed_with(change), B))
        self.assertEqual(got["204"]["plan_image"], "https://cdn.sightmap.com/plan.jpg")
        self.assertIsNone(got["221"]["plan_image"])

    def test_fee_refundable_flag(self):
        fees = {f["label"]: f for f in sightmap.parse(FEED, B)["fees"]}
        self.assertIs(fees["Pet Deposit (refundable)"]["refundable"], True)
        self.assertIs(fees["Amenity Fee - First Lease"]["refundable"], False)


class CamdenFieldTests(unittest.TestCase):
    B = test_camden.B

    def test_plan_image(self):
        def change(pp):
            pp["data"]["availableApartments"][0]["media"] = {"floorPlanImage": "https://images.ctfassets.net/s4.jpg"}
        got = by_unit(camden.parse(test_camden.edited(change), self.B))
        self.assertEqual(got["1215"]["plan_image"], "https://images.ctfassets.net/s4.jpg")
        self.assertIsNone(got["509"]["plan_image"])

    def test_restricted_from_plan_name_only(self):
        def change(pp):
            pp["data"]["availableApartments"][1]["name"] = "A1 MPDU"
        got = by_unit(camden.parse(test_camden.edited(change), self.B))
        self.assertIs(got["509"]["restricted"], True)
        self.assertIsNone(got["1215"]["restricted"])

    def test_facts_features_text(self):
        def change(pp):
            pp["data"]["metaDescription"] = "<p>Homes feature <b>full-size washer and dryer</b> &amp; USB outlets.</p>"
        result = camden.parse(test_camden.edited(change), self.B)
        self.assertEqual(result["facts"], {"features": ["Homes feature full-size washer and dryer & USB outlets."]})

    def test_facts_without_description(self):
        self.assertEqual(camden.parse(test_camden.HTML, self.B)["facts"], {"features": []})


if __name__ == "__main__":
    unittest.main()
