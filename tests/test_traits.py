"""What a listing says about one unit: outdoor space of its own, a front door of its own, and a recent price drop."""
import json
import os
import unittest

from aptrack import history, traits
from aptrack.readers import sightmap

HERE = os.path.join(os.path.dirname(__file__), "fixtures")
B = {"id": "gables-x", "url": "https://www.gables.com/community/1"}


def unit(plan=None, notes=None):
    return {"plan": plan, "notes": notes}


class OutdoorTests(unittest.TestCase):
    def test_the_listing_naming_a_balcony_terrace_or_patio(self):
        self.assertEqual(traits.outdoor(unit(notes="Washer and Dryer, Balcony, Walk-in Closet")), "Balcony")
        self.assertEqual(traits.outdoor(unit(notes="Oversized Terrace, North View")), "Terrace")
        self.assertEqual(traits.outdoor(unit(notes="Patio / Balcony")), "Patio or balcony")
        self.assertEqual(traits.outdoor(unit(plan="B2 with Patio")), "Patio")
        self.assertEqual(traits.outdoor(unit(notes="Private Rooftop Deck")), "Roof deck")
        self.assertEqual(traits.outdoor(unit(notes="Fenced Yard")), "Yard")

    def test_things_that_only_sound_like_outdoor_space(self):
        self.assertIsNone(traits.outdoor(unit(notes="Juliet Balcony, Scenic View")))        # a railing, not a place to sit
        self.assertIsNone(traits.outdoor(unit(plan="Terrace Level 1 Bed")))               # a floor's name
        self.assertIsNone(traits.outdoor(unit(notes="Courtyard View, Terrace View, Balcony View")))
        self.assertIsNone(traits.outdoor(unit(notes="No Balcony")))
        self.assertIsNone(traits.outdoor(unit()))

    def test_a_real_balcony_beside_a_juliet_one_counts(self):
        self.assertEqual(traits.outdoor(unit(notes="Juliet Balcony, Terrace")), "Terrace")


class OwnDoorTests(unittest.TestCase):
    def test_wording_that_means_a_door_to_the_outside(self):
        for text in ("Private Entrance", "private entry", "Direct street access", "Street-Level Entry", "Townhome",
                     "2 Bed Townhouse", "Walk-out patio", "Private stoop", "Separate exterior entrance", "Direct-entry home"):
            self.assertTrue(traits.own_door(unit(notes=text)), text)

    def test_wording_that_does_not(self):
        for text in ("Direct access to garage", "Controlled access entry", "Entry closet", "Private bath", "Townhome-style finishes in lobby", None):
            self.assertFalse(traits.own_door(unit(notes=text)), text)

    def test_apply_marks_the_unit(self):
        u = {"plan": "TH1 Townhome", "notes": "Patio, Washer and Dryer"}
        traits.apply(u)
        self.assertEqual((u["outdoor"], u["own_door"]), ("Patio", True))
        u = {"plan": "A1", "notes": None}
        traits.apply(u)
        self.assertEqual((u["outdoor"], u["own_door"]), (None, False))


class UnitMapNotesTests(unittest.TestCase):
    def test_a_unit_map_s_per_unit_feature_list_becomes_the_unit_s_notes(self):
        with open(os.path.join(HERE, "sightmap_feed.json"), encoding="utf-8") as f:
            feed = json.load(f)
        data = feed.get("data", feed)
        first, second = data["units"][0], data["units"][1]
        data["unit_descriptions"] = [
            {"id": 71, "label": "Unit Features", "description": "### Unit Features\n* 2nd Floor\n* Terrace\n* North View", "units": [first["id"]]},
            {"id": 72, "label": "Amenities", "description": "* Private Entrance", "units": [first["id"]]}]
        first["descriptions"] = [71, 72]
        units = {u["unit"]: u for u in sightmap.parse(feed, B)["units"]}
        self.assertEqual(units[str(first["unit_number"])]["notes"], "2nd Floor, Terrace, North View, Private Entrance")
        self.assertIsNone(units[str(second["unit_number"])]["notes"])


class DropTests(unittest.TestCase):
    def points(self, *pairs, lease=12):
        return [[day, rent, None, lease, None] for day, rent in pairs]

    def test_a_cut_from_the_recent_high_is_a_drop(self):
        got = history.drop(self.points(("2026-11-01", 2000), ("2026-11-10", 1990), ("2026-11-15", 1900)), "2026-11-19")
        self.assertEqual(got, {"was": 2000, "by": 100, "pct": -5.0, "day": "2026-11-15"})

    def test_small_wobbles_are_not(self):
        self.assertIsNone(history.drop(self.points(("2026-11-01", 2000), ("2026-11-15", 1975)), "2026-11-19"))      # 1.25%
        self.assertIsNone(history.drop(self.points(("2026-11-15", 2000)), "2026-11-19"))                               # nothing to compare

    def test_a_price_on_its_way_back_up_is_not(self):
        self.assertIsNone(history.drop(self.points(("2026-11-01", 2000), ("2026-11-10", 1800), ("2026-11-15", 1900)), "2026-11-19"))

    def test_only_the_last_thirty_days_count(self):
        old = self.points(("2026-09-01", 2400), ("2026-10-01", 2000), ("2026-11-15", 1950))
        self.assertEqual(history.drop(old, "2026-11-19"), {"was": 2000, "by": 50, "pct": -2.5, "day": "2026-11-15"})   # 2,000 still stood inside the window
        self.assertIsNone(history.drop(self.points(("2026-09-01", 2400), ("2026-10-01", 2000)), "2026-11-19"))          # the cut itself is old

    def test_a_different_lease_term_is_a_different_price(self):
        points = [["2026-11-01", 2000, None, 12, None], ["2026-11-15", 1800, None, 18, None]]
        self.assertIsNone(history.drop(points, "2026-11-19"))


if __name__ == "__main__":
    unittest.main()
