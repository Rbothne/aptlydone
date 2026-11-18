import unittest

from aptrack import history
from aptrack.units import make_unit

D1, D2, D3, D4 = "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21"


def unit(number, rent, *, building="b1", plan="A1", special=None, beds=1, lease=None, fees=None):
    return make_unit(building, number, rent=rent, plan=plan, beds=beds, baths=1, sqft=700, special=special,
                     lease=lease, fees=fees)


def pt(day, rent, special=None, lease=None, fees=None):
    """A price point as stored: [day, rent, special, lease, fees]."""
    return [day, rent, special, lease, fees]


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.state = history.new_state()

    def record(self, day, *units, building="b1"):
        history.record(self.state, building, list(units), day)

    def u(self, number="101", building="b1"):
        return self.state["units"][f"{building}:{number}"]

    def test_new_state_shape(self):
        self.assertEqual(self.state, {"version": 1, "units": {}, "plans": {}, "buildings": {}})

    def test_new_unit_gets_first_point(self):
        self.record(D1, unit("101", 2700))
        u = self.u()
        self.assertEqual((u["first"], u["last"], u["gone"], u["points"], u["past"]), (D1, D1, None, [pt(D1, 2700, None)], []))
        self.assertEqual((u["building"], u["plan"], u["beds"], u["baths"], u["sqft"]), ("b1", "A1", 1, 1, 700))

    def test_unchanged_rent_adds_no_point(self):
        self.record(D1, unit("101", 2700))
        self.record(D2, unit("101", 2700))
        self.assertEqual((self.u()["last"], self.u()["points"]), (D2, [pt(D1, 2700, None)]))

    def test_changed_rent_appends_point(self):
        self.record(D1, unit("101", 2700))
        self.record(D2, unit("101", 2650))
        self.assertEqual(self.u()["points"], [pt(D1, 2700, None), pt(D2, 2650, None)])

    def test_changed_special_appends_point(self):
        self.record(D1, unit("101", 2700))
        self.record(D2, unit("101", 2700, special="1 month free"))
        self.assertEqual(self.u()["points"], [pt(D1, 2700, None), pt(D2, 2700, "1 month free")])

    def test_changed_lease_or_fees_appends_point(self):
        self.record(D1, unit("101", 2700, lease=12, fees=100))
        self.record(D2, unit("101", 2700, lease=15, fees=100))
        self.record(D3, unit("101", 2700, lease=15, fees=140))
        self.assertEqual(self.u()["points"], [pt(D1, 2700, None, 12, 100), pt(D2, 2700, None, 15, 100), pt(D3, 2700, None, 15, 140)])

    def test_record_keeps_the_latest_available_date(self):
        self.record(D1, dict(unit("101", 2700), available="2026-12-01"))
        self.record(D2, dict(unit("101", 2700), available="2026-12-15"))
        self.assertEqual(self.u()["available"], "2026-12-15")

    def test_same_day_change_overwrites_point(self):
        self.record(D1, unit("101", 2700))
        self.record(D1, unit("101", 2650))
        self.assertEqual(self.u()["points"], [pt(D1, 2650, None)])

    def test_same_day_return_to_previous_drops_point(self):
        self.record(D1, unit("101", 2700))
        self.record(D2, unit("101", 2650))
        self.record(D2, unit("101", 2700))
        self.assertEqual(self.u()["points"], [pt(D1, 2700, None)])

    def test_absent_unit_marked_gone_once(self):
        self.record(D1, unit("101", 2700), unit("102", 2800))
        self.record(D2, unit("102", 2800))
        self.record(D3, unit("102", 2800))
        self.assertEqual((self.u("101")["gone"], self.u("101")["last"]), (D2, D1))
        self.assertIsNone(self.u("102")["gone"])

    def test_other_buildings_units_untouched(self):
        self.record(D1, unit("101", 2700))
        self.record(D2, unit("5", 1900, building="b2"), building="b2")
        self.assertIsNone(self.u("101")["gone"])

    def test_returning_unit_starts_new_listing(self):
        self.record(D1, unit("101", 2700))
        self.record(D2)
        self.record(D4, unit("101", 2500))
        u = self.u()
        self.assertEqual((u["first"], u["last"], u["gone"], u["points"]), (D4, D4, None, [pt(D4, 2500, None)]))
        self.assertEqual(u["past"], [{"first": D1, "last": D1, "gone": D2, "points": [pt(D1, 2700, None)]}])

    def test_building_marked_ok(self):
        self.record(D1, unit("101", 2700))
        self.assertEqual(self.state["buildings"]["b1"], {"ok": D1, "failed": None})

    def test_failure_touches_no_unit(self):
        self.record(D1, unit("101", 2700))
        before = repr(self.state["units"])
        history.record_failure(self.state, "b1", D2)
        self.assertEqual(repr(self.state["units"]), before)
        self.assertEqual(self.state["buildings"]["b1"], {"ok": D1, "failed": D2})

    def test_failure_before_any_success(self):
        history.record_failure(self.state, "b9", D1)
        self.assertEqual(self.state["buildings"]["b9"], {"ok": None, "failed": D1})

    def test_success_clears_failure(self):
        history.record_failure(self.state, "b1", D1)
        self.record(D2, unit("101", 2700))
        self.assertEqual(self.state["buildings"]["b1"], {"ok": D2, "failed": None})


class PlanSeriesTests(unittest.TestCase):
    def setUp(self):
        self.state = history.new_state()

    def plan(self, name="A1"):
        return self.state["plans"][f"b1|{name}"]

    def test_plan_series_low_median_count(self):
        history.record(self.state, "b1", [unit("1", 2000), unit("2", 2200), unit("3", 2600)], D1)
        self.assertEqual(self.plan(), {"beds": 1, "points": [[D1, 2000, 2200, 3]]})

    def test_plan_point_added_only_when_changed(self):
        history.record(self.state, "b1", [unit("1", 2000)], D1)
        history.record(self.state, "b1", [unit("1", 2000)], D2)
        history.record(self.state, "b1", [unit("1", 1950)], D3)
        self.assertEqual(self.plan()["points"], [[D1, 2000, 2000, 1], [D3, 1950, 1950, 1]])

    def test_plan_same_day_change_overwrites(self):
        history.record(self.state, "b1", [unit("1", 2000)], D1)
        history.record(self.state, "b1", [unit("1", 1900)], D1)
        self.assertEqual(self.plan()["points"], [[D1, 1900, 1900, 1]])

    def test_plan_with_no_units_gets_empty_point_once(self):
        history.record(self.state, "b1", [unit("1", 2000), unit("9", 3000, plan="B2", beds=2)], D1)
        history.record(self.state, "b1", [unit("9", 3000, plan="B2", beds=2)], D2)
        history.record(self.state, "b1", [unit("9", 3000, plan="B2", beds=2)], D3)
        self.assertEqual(self.plan()["points"], [[D1, 2000, 2000, 1], [D2, None, None, 0]])
        self.assertEqual(self.plan("B2")["points"], [[D1, 3000, 3000, 1]])

    def test_units_without_a_plan_name_share_a_series_per_bed_count(self):
        history.record(self.state, "b1", [unit("1", 2000, plan=None), unit("2", 2100, plan=None)], D1)
        self.assertEqual(self.state["plans"]["b1|1 bed"]["points"], [[D1, 2000, 2050, 2]])


class PruneAndGuardTests(unittest.TestCase):
    def test_prune_drops_units_gone_over_400_days(self):
        state = history.new_state()
        history.record(state, "b1", [unit("old", 2000), unit("recent", 2000), unit("listed", 2000)], "2025-01-01")
        history.record(state, "b1", [unit("recent", 2000), unit("listed", 2000)], "2025-01-02")   # "old" gone 2025-01-02
        history.record(state, "b1", [unit("listed", 2000)], "2026-01-01")                         # "recent" gone 2026-01-01
        history.prune(state, "2026-02-07")                                                        # 401 days after 2025-01-02
        self.assertEqual(set(state["units"]), {"b1:recent", "b1:listed"})

    def test_prune_keeps_units_gone_exactly_400_days(self):
        state = history.new_state()
        history.record(state, "b1", [unit("old", 2000)], "2025-01-01")
        history.record(state, "b1", [], "2025-01-02")
        history.prune(state, "2026-02-06")
        self.assertIn("b1:old", state["units"])

    def test_retire_marks_units_of_dropped_buildings_gone(self):
        state = history.new_state()
        history.record(state, "kept", [unit("1", 2000, building="kept")], D1)
        history.record(state, "dropped", [unit("1", 2000, building="dropped"), unit("2", 2100, building="dropped")], D1)
        history.record(state, "dropped", [unit("1", 2000, building="dropped")], D2)       # unit 2 already gone on D2
        history.retire(state, {"kept"}, D3)
        self.assertEqual((state["units"]["dropped:1"]["gone"], state["units"]["dropped:2"]["gone"]), (D3, D2))
        self.assertIsNone(state["units"]["kept:1"]["gone"])

    def test_safe_to_save_refuses_big_drop(self):
        def state(n):
            return {"units": {str(i): {} for i in range(n)}}
        self.assertFalse(history.safe_to_save(state(100), state(79)))
        self.assertTrue(history.safe_to_save(state(100), state(80)))
        self.assertTrue(history.safe_to_save(state(0), state(0)))
        self.assertTrue(history.safe_to_save(state(0), state(50)))


if __name__ == "__main__":
    unittest.main()
