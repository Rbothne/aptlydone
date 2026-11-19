"""A company marked "paused" in managers.json is left alone: not searched, not read, not on the page.
Everything known about it is kept, so deleting the mark brings it straight back."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import build
import discover
from aptrack import companies, files, history
from aptrack.discover import DISCOVERERS
from aptrack.readers import READERS
from tests.quiet import QuietTestCase
from tests.test_build import API, CAMDEN_FEED, GOOD, Web, bozzuto, camden

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHY = "its terms of use forbid automated reading"
MANAGERS = [{"name": "Bozzuto", "site": "www.bozzuto.com", "discover": "bozzuto"},
            {"name": "Camden", "site": "www.camdenliving.com", "discover": "camden", "paused": WHY}]
CONFIG = {"settings": {"delay_seconds": 0, "counties": ["11001"]}, "managers": MANAGERS}


class CompaniesTests(unittest.TestCase):
    def test_paused_companies_come_with_their_reason(self):
        self.assertEqual(companies.paused(MANAGERS), {"Camden": WHY})
        self.assertEqual([m["name"] for m in companies.active(MANAGERS)], ["Bozzuto"])

    def test_tracked_buildings_are_those_of_companies_not_paused(self):
        both = [bozzuto(), camden()]
        self.assertEqual([b["id"] for b in companies.tracked(both, MANAGERS)], ["bozzuto-5333-connecticut"])
        self.assertIs(companies.tracked(both, MANAGERS)[0], both[0])            # the same records, not copies
        self.assertEqual(companies.tracked(both, MANAGERS[:1]), both)

    def test_every_company_listed_paused_or_not_can_still_be_searched_and_read(self):
        """Bringing a paused company back is deleting one word: its code has to still be there."""
        listed = files.load(os.path.join(ROOT, "managers.json"), None)["managers"]
        for manager in listed:
            self.assertIn(manager["discover"], DISCOVERERS, manager["name"])
        self.assertIn("equity", READERS)
        self.assertTrue(all(isinstance(reason, str) and reason for reason in companies.paused(listed).values()))


class Folder(QuietTestCase):
    """A scratch copy of the project's data files, with the scripts pointed at it."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.at = lambda *parts: os.path.join(folder.name, *parts)
        files.save(self.at("managers.json"), CONFIG)
        self.web = Web(dict(GOOD))
        for module, names in ((build, ("BUILDINGS", "STATE", "AREA")), (discover, ("BUILDINGS",))):
            for name in names:
                self.patch(module, name, self.at("data", os.path.basename(getattr(module, name))))
            self.patch(module, "MANAGERS", self.at("managers.json"))
            self.patch(module.fetch, "polite", lambda *args, **kwargs: self.web)
            self.patch(module.fetch, "post", self.no_post)
        self.patch(build, "SITE_DATA", self.at("site", "data"))

    def no_post(self, *args, **kwargs):
        raise OSError("nothing is sent anywhere in these tests")

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, module, *arguments):
        with mock.patch.object(sys, "argv", [module.__name__ + ".py", *arguments]):
            module.main()


class BuildTests(Folder):
    def setUp(self):
        super().setUp()
        files.save(self.at("data", "buildings.json"), [bozzuto(), camden()])
        state = history.new_state()
        self.listed = READERS["camden"](camden(), Web(dict(GOOD)))["units"]
        history.record(state, "camden-noma", self.listed, "2026-11-17")
        files.save(self.at("data", "state.json"), state)

    def test_a_paused_company_is_not_read_and_not_on_the_page(self):
        self.main(build)
        self.assertIn(API, self.web.asked)
        self.assertNotIn(CAMDEN_FEED, self.web.asked)
        self.assertEqual([b["id"] for b in files.load(self.at("site", "data", "index.json"), None)["buildings"]],
                         ["bozzuto-5333-connecticut"])

    def test_its_buildings_and_price_history_are_kept_for_when_it_comes_back(self):
        self.main(build)
        self.assertEqual([b["id"] for b in files.load(self.at("data", "buildings.json"), None)],
                         ["bozzuto-5333-connecticut", "camden-noma"])
        units = files.load(self.at("data", "state.json"), None)["units"]
        mine = [units[u["id"]] for u in self.listed]
        self.assertTrue(mine)
        self.assertEqual([u["points"][0][:2] for u in mine], [["2026-11-17", u["rent"]] for u in self.listed])
        self.assertEqual({u["gone"] for u in mine}, {files.today()})                       # no longer counted as listed

    def test_asking_for_a_paused_building_by_name_reads_nothing(self):
        with self.assertRaises(SystemExit):
            self.main(build, "--only", "camden-noma")
        self.assertEqual(self.web.asked, [])


class DiscoverTests(Folder):
    def setUp(self):
        super().setUp()
        files.save(self.at("data", "buildings.json"), [bozzuto(zip="20015"), camden(zip="20002", missed=1)])
        self.searched = []

        def finder(name, found):
            def find(get, limit=None):
                self.searched.append(name)
                return found
            return find
        self.patch(discover, "DISCOVERERS", {"bozzuto": finder("Bozzuto", [bozzuto()]), "camden": finder("Camden", [])})

    def test_a_paused_company_is_not_searched_and_its_buildings_stay_as_they_were(self):
        self.main(discover)
        self.assertEqual(self.searched, ["Bozzuto"])
        kept = {b["id"]: b for b in files.load(self.at("data", "buildings.json"), None)}
        self.assertEqual(kept["camden-noma"], camden(zip="20002", missed=1, located_at=[38.9, -77.0]))     # not counted as missing either

    def test_asking_for_a_paused_company_by_name_says_why_it_is_not_run(self):
        errors = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(errors):
            self.main(discover, "--only", "camden")
        self.assertIn(WHY, errors.getvalue())
        self.assertEqual(self.searched, [])


if __name__ == "__main__":
    unittest.main()
