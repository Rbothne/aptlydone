"""Some listing systems are read a few buildings at a time, through the day, instead of all at once.

RentCafe hosts many buildings' websites behind one service. Asked for all of them in one run, the tracker arrives as
a burst. `"spread": {"rentcafe": 6}` in managers.json settings splits those buildings into six shares: the ordinary
runs leave them out, and each run of `build.py --spread` reads the next share, remembering where it stopped."""
import unittest

from aptrack import spread


def building(n, platform="rentcafe", in_region=True):
    return {"id": f"b{n:02d}", "platform": platform, "in_region": in_region, "feed": f"https://site{n}.test/floorplans"}


class SpreadTest(unittest.TestCase):
    def test_the_ordinary_run_leaves_spread_systems_out(self):
        buildings = [building(1), building(2, "sightmap"), building(3, "equity")]
        self.assertEqual([b["id"] for b in spread.rest(buildings, {"rentcafe": 6})], ["b02", "b03"])
        self.assertEqual(spread.rest(buildings, {}), buildings)

    def test_each_turn_reads_the_next_share_and_remembers_where_it_stopped(self):
        buildings = [building(n) for n in (5, 3, 1, 4, 2, 7, 6)] + [building(9, "sightmap")]
        state = {}
        turns = [[b["id"] for b in spread.turn(buildings, state, {"rentcafe": 3})] for _ in range(4)]
        self.assertEqual(turns, [["b01", "b02", "b03"], ["b04", "b05", "b06"], ["b07", "b01", "b02"], ["b03", "b04", "b05"]])
        self.assertEqual(state["spread"], {"rentcafe": "b05"})

    def test_buildings_that_come_and_go_do_not_lose_the_place(self):
        state = {"spread": {"rentcafe": "b03"}}
        buildings = [building(n) for n in (1, 2, 4, 5)]                  # b03, where the last turn stopped, is gone
        self.assertEqual([b["id"] for b in spread.turn(buildings, state, {"rentcafe": 2})], ["b04", "b05"])
        self.assertEqual([b["id"] for b in spread.turn(buildings + [building(6)], state, {"rentcafe": 2})], ["b06", "b01", "b02"])

    def test_one_share_covers_everything_and_nothing_to_read_is_nothing(self):
        buildings = [building(n) for n in (1, 2)]
        self.assertEqual(len(spread.turn(buildings, {}, {"rentcafe": 1})), 2)
        self.assertEqual(spread.turn([building(1, "sightmap")], {}, {"rentcafe": 6}), [])
        self.assertEqual(spread.turn(buildings, {}, {}), [])

    def test_buildings_outside_the_region_take_no_place_in_the_shares(self):
        buildings = [building(1), building(2, in_region=False), building(3)]
        self.assertEqual([b["id"] for b in spread.turn(buildings, {}, {"rentcafe": 1})], ["b01", "b03"])

    def test_settings_name_the_systems_and_their_shares(self):
        self.assertEqual(spread.shares({"spread": {"rentcafe": 6}}), {"rentcafe": 6})
        self.assertEqual(spread.shares({}), {})
        self.assertEqual(spread.shares({"spread": {"rentcafe": 0, "g5": "x"}}), {})       # nonsense is ignored, not obeyed


if __name__ == "__main__":
    unittest.main()
