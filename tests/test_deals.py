import unittest

from aptrack import deals

MILE = 1 / 69.0            # degrees of latitude in a mile, near enough


def b(building_id, north=0.0, name=None):
    """A building `north` miles north of the origin."""
    return {"id": building_id, "name": name or building_id, "lat": 38.9 + north * MILE, "lon": -77.0}


def u(building, number, true, *, sqft=800, beds=1, restricted=None):
    return {"id": f"{building}:{number}", "building": building, "unit": str(number), "beds": beds, "sqft": sqft,
            "true": true, "restricted": restricted}


def block(building, true, count=4, start=1, **more):
    return [u(building, start + i, true, **more) for i in range(count)]


class MilesTests(unittest.TestCase):
    def test_miles(self):
        self.assertAlmostEqual(deals.miles(b("a"), b("c", north=1)), 1.0, places=1)
        self.assertEqual(deals.miles(b("a"), b("c")), 0)


class OwnBuildingTests(unittest.TestCase):
    def test_percent_below_similar_units_in_the_building(self):
        cheap = u("A", 9, 1800)
        units = block("A", 2000) + [cheap]
        deals.score(units, [b("A")])
        self.assertEqual(cheap["own"], {"pct": -10.0, "n": 4})
        self.assertEqual(units[0]["own"], {"pct": 0.0, "n": 4})        # three at 2000 and the one at 1800: median 2000

    def test_cost_is_compared_per_square_foot(self):
        bigger = u("A", 9, 2100, sqft=900)                              # 2.33/sqft against 2.50/sqft
        deals.score(block("A", 2000) + [bigger], [b("A")])
        self.assertEqual(bigger["own"]["pct"], -6.7)

    def test_needs_three_similar_units(self):
        cheap = u("A", 9, 1700)
        deals.score(block("A", 2000, count=2) + [cheap], [b("A")])
        self.assertIsNone(cheap["own"])

    def test_other_bed_counts_and_sizes_do_not_count(self):
        cheap = u("A", 9, 1700)
        others = block("A", 2000, count=2) + block("A", 2000, count=3, start=20, beds=2) + block("A", 2000, count=3, start=40, sqft=1000)
        deals.score(others + [cheap], [b("A")])
        self.assertIsNone(cheap["own"])

    def test_building_steal_at_fifteen_percent(self):
        steal, near_miss = u("A", 8, 1700), u("A", 9, 1702)
        deals.score(block("A", 2000, count=5) + [steal, near_miss], [b("A")])
        self.assertEqual((steal["own"]["pct"], steal["tag"]), (-15.0, "building"))
        self.assertEqual((near_miss["own"]["pct"], near_miss["tag"]), (-14.9, None))


class NeighborTests(unittest.TestCase):
    def neighbors(self, true=2500):
        return block("B", true, count=2) + block("C", true, count=2) + block("D", true, count=1)

    def test_percent_below_similar_units_nearby(self):
        mine = u("A", 1, 2000)
        deals.score(self.neighbors() + [mine], [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertEqual(mine["local"], {"pct": -20.0, "n": 5, "buildings": 3, "miles": 1})
        self.assertEqual(mine["tag"], "local")

    def test_just_short_of_twenty_percent_is_not_local_value(self):
        mine = u("A", 1, 2003)
        deals.score(self.neighbors() + [mine], [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertEqual((mine["local"]["pct"], mine["tag"]), (-19.9, None))

    def test_widens_to_two_miles(self):
        mine = u("A", 1, 2000)
        deals.score(self.neighbors() + [mine], [b("A"), b("B", 0.3), b("C", 0.5), b("D", 1.6)])
        self.assertEqual((mine["local"]["miles"], mine["local"]["buildings"]), (2, 3))

    def test_needs_three_buildings(self):
        mine = u("A", 1, 2000)
        deals.score(block("B", 2500, count=4) + block("C", 2500, count=4) + [mine], [b("A"), b("B", 0.3), b("C", 0.5)])
        self.assertIsNone(mine["local"])

    def test_needs_five_units(self):
        mine = u("A", 1, 2000)
        deals.score(block("B", 2500, count=1) + block("C", 2500, count=1) + block("D", 2500, count=1) + [mine],
                    [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertIsNone(mine["local"])

    def test_beyond_two_miles_does_not_count(self):
        mine = u("A", 1, 2000)
        deals.score(self.neighbors() + [mine], [b("A"), b("B", 0.3), b("C", 0.5), b("D", 2.5)])
        self.assertIsNone(mine["local"])

    def test_own_building_is_not_a_neighbor(self):
        mine = u("A", 1, 2000)
        deals.score(block("A", 2500, count=6, start=10) + block("B", 2500, count=3) + block("C", 2500, count=3) + [mine],
                    [b("A"), b("B", 0.3), b("C", 0.5)])
        self.assertIsNone(mine["local"])

    def test_buildings_at_the_same_spot_are_separate_neighbors(self):
        mine = u("A", 1, 2000)
        deals.score(self.neighbors() + [mine], [b("A"), b("B"), b("C"), b("D")])
        self.assertEqual(mine["local"]["buildings"], 3)

    def test_neighbor_size_band_is_fifteen_percent(self):
        mine = u("A", 1, 2000)
        far_size = block("B", 2500, count=2, sqft=940) + block("C", 2500, count=2, sqft=940) + block("D", 2500, count=1, sqft=940)
        deals.score(far_size + [mine], [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertIsNone(mine["local"])


class AbsoluteTests(unittest.TestCase):
    def test_absolute_needs_both(self):
        mine = u("A", 9, 1800)                                           # 10% under its building, 28% under neighbors
        units = block("A", 2000) + block("B", 2500, count=2) + block("C", 2500, count=2) + block("D", 2500, count=1) + [mine]
        deals.score(units, [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertEqual((mine["own"]["pct"], mine["tag"]), (-10.0, "absolute"))

    def test_big_building_gap_without_neighbors_is_a_building_steal(self):
        mine = u("A", 9, 1600)
        deals.score(block("A", 2000) + [mine], [b("A")])
        self.assertEqual(mine["tag"], "building")

    def test_a_price_too_far_under_its_building_is_marked_for_checking_not_as_a_steal(self):
        # 30% or more under identical neighbours is usually an income-restricted unit or a data error
        suspect, real = u("A", 8, 1400), u("A", 9, 1402)
        units = block("A", 2000, count=5) + block("B", 2500, count=2) + block("C", 2500, count=2) + block("D", 2500, count=1) + [suspect, real]
        deals.score(units, [b("A"), b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertEqual((suspect["own"]["pct"], suspect["tag"]), (-30.0, "check"))
        self.assertEqual((real["own"]["pct"], real["tag"]), (-29.9, "absolute"))


class ExclusionTests(unittest.TestCase):
    def test_restricted_units_are_not_scored_or_used(self):
        restricted = [u("A", n, 1200, restricted=True) for n in (1, 2, 3)]
        market = block("A", 2000, count=2, start=10)
        deals.score(restricted + market, [b("A")])
        self.assertEqual([(x["own"], x["local"], x["tag"]) for x in restricted], [(None, None, None)] * 3)
        self.assertIsNone(market[0]["own"])                                # only one other market unit to compare with

    def test_senior_buildings_are_left_out(self):
        senior = block("S", 1500)
        deals.score(senior, [b("S", name="Carver Senior Apartments")])
        self.assertEqual([(x["own"], x["local"], x["tag"]) for x in senior], [(None, None, None)] * 4)

    def test_senior_building_does_not_count_toward_three_buildings(self):
        mine = u("A", 1, 2000)
        deals.score(block("S", 1500) + block("B", 2500, count=3) + block("C", 2500, count=3) + [mine],
                    [b("A"), b("S", 0.2, name="Hodge on 7th - Senior Living"), b("B", 0.3), b("C", 0.5)])
        self.assertIsNone(mine["local"])

    def test_single_rooms_are_left_out(self):
        rooms = block("A", 1100, sqft=150)
        deals.score(rooms, [b("A")])
        self.assertEqual([(x["own"], x["tag"]) for x in rooms], [(None, None)] * 4)

    def test_units_without_cost_or_size_are_left_out(self):
        odd = [u("A", 1, None), u("A", 2, 2000, sqft=None)]
        deals.score(odd + block("A", 2000, start=10), [b("A")])
        self.assertEqual([(x["own"], x["local"], x["tag"]) for x in odd], [(None, None, None)] * 2)

    def test_building_without_coordinates_gets_no_neighbor_comparison(self):
        mine = u("A", 1, 2000)
        nowhere = {"id": "A", "name": "A", "lat": None, "lon": None}
        deals.score(block("B", 2500, count=3) + block("C", 2500, count=3) + block("D", 2500, count=3) + [mine],
                    [nowhere, b("B", 0.3), b("C", 0.5), b("D", 0.9)])
        self.assertIsNone(mine["local"])


class RankTests(unittest.TestCase):
    def test_rank_among_buildings_within_two_miles(self):
        buildings = [b("A"), b("B", 0.5), b("C", 1.5), b("Z", 10)]
        units = block("A", 3200) + block("B", 2400) + block("C", 1600) + block("Z", 4000)
        deals.rank(units, buildings)
        by_id = {x["id"]: x["rank"] for x in buildings}
        self.assertEqual(by_id["A"], {"pct": 100, "n": 3})
        self.assertEqual(by_id["B"], {"pct": 67, "n": 3})
        self.assertEqual(by_id["C"], {"pct": 33, "n": 3})
        self.assertIsNone(by_id["Z"])

    def test_rank_uses_one_bedrooms_only(self):
        buildings = [b("A"), b("B", 0.5), b("C", 1.5)]
        units = block("A", 3200, beds=2) + block("B", 2400) + block("C", 1600)
        deals.rank(units, buildings)
        self.assertIsNone(buildings[0]["rank"])


if __name__ == "__main__":
    unittest.main()
