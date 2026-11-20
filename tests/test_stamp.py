"""Publishing stamps the page's own files with the commit, so a browser never runs a mix of old and new ones.

GitHub Pages lets a browser keep each file for ten minutes. Without the stamp, a browser that fetched the new
index.html could still be holding the old scripts (a new control that does nothing), or new scripts with an old one
they import (a page that does not load at all)."""
import os
import tempfile
import unittest

from aptrack import stamp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


class StampTest(unittest.TestCase):
    def site(self, folder):
        write(os.path.join(folder, "index.html"),
              '<link rel="stylesheet" href="vendor/leaflet/leaflet.css">\n<link rel="stylesheet" href="app.css">\n'
              '<script src="vendor/leaflet/leaflet.js"></script>\n<script type="module" src="js/app.js"></script>\n')
        write(os.path.join(folder, "changelog.html"), '<link rel="stylesheet" href="app.css">\n')
        write(os.path.join(folder, "app.css"), "body {}")
        write(os.path.join(folder, "js", "app.js"), 'import { a } from "./logic.js";\n')
        write(os.path.join(folder, "js", "logic.js"), "export const a = 1;\n")

    def test_the_scripts_move_to_a_folder_named_for_the_commit_and_the_pages_point_there(self):
        with tempfile.TemporaryDirectory() as folder:
            self.site(folder)
            stamp.stamp(folder, "abc1234")
            self.assertFalse(os.path.exists(os.path.join(folder, "js")))
            # the scripts import each other by relative path, so moving the folder keeps a set together
            self.assertEqual(read(os.path.join(folder, "js-abc1234", "app.js")), 'import { a } from "./logic.js";\n')
            self.assertTrue(os.path.exists(os.path.join(folder, "js-abc1234", "logic.js")))
            index = read(os.path.join(folder, "index.html"))
            self.assertIn('<script type="module" src="js-abc1234/app.js"></script>', index)
            self.assertIn('<link rel="stylesheet" href="app.css?v=abc1234">', index)
            self.assertIn('href="vendor/leaflet/leaflet.css"', index)              # the bundled library is left alone
            self.assertIn('src="vendor/leaflet/leaflet.js"', index)
            self.assertEqual(read(os.path.join(folder, "changelog.html")), '<link rel="stylesheet" href="app.css?v=abc1234">\n')

    def test_a_page_that_no_longer_names_its_script_stops_the_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            self.site(folder)
            write(os.path.join(folder, "index.html"), '<script type="module" src="scripts/main.js"></script>\n')
            with self.assertRaises(SystemExit):
                stamp.stamp(folder, "abc1234")

    def test_a_version_that_is_not_a_plain_word_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            self.site(folder)
            for bad in ("", "../x", "a b", 'x"y'):
                with self.assertRaises(SystemExit):
                    stamp.stamp(folder, bad)
            self.assertTrue(os.path.exists(os.path.join(folder, "js", "app.js")))

    def test_the_real_page_can_be_stamped(self):
        index = read(os.path.join(ROOT, "site", "index.html"))
        self.assertEqual(index.count(stamp.SCRIPT), 1)
        self.assertEqual(index.count(stamp.STYLE), 1)
        self.assertEqual(read(os.path.join(ROOT, "site", "changelog.html")).count(stamp.STYLE), 1)


if __name__ == "__main__":
    unittest.main()
