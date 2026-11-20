"""Stamp the page's own files with the commit being published: `python3 -m aptrack.stamp site <commit>`.

GitHub Pages lets a browser keep each file for ten minutes, each on its own clock. So for ten minutes after a publish a
browser could run the new index.html with the old scripts, or new scripts with an old one they import. The scripts are
moved to a folder named for the commit (they import each other by relative path, so a set stays together) and the pages
point at it; the stylesheet gets the commit as a query. Run on the copy being published, never on the repository's own.
"""
import os
import re
import sys

SCRIPT = 'src="js/app.js"'
STYLE = 'href="app.css"'
PAGES = {"index.html": (SCRIPT, STYLE), "changelog.html": (STYLE,)}


def stamp(site, version):
    if not re.fullmatch(r"[0-9A-Za-z]+", version or ""):
        sys.exit(f"stamp: {version!r} is not a commit")
    marked = {SCRIPT: f'src="js-{version}/app.js"', STYLE: f'href="app.css?v={version}"'}
    pages = {}
    for name, wanted in PAGES.items():
        with open(os.path.join(site, name), encoding="utf-8", newline="") as f:
            text = f.read()
        for old in wanted:
            if text.count(old) != 1:
                sys.exit(f"stamp: {name} should name {old} once, and names it {text.count(old)} times")
            text = text.replace(old, marked[old])
        pages[name] = text
    os.rename(os.path.join(site, "js"), os.path.join(site, f"js-{version}"))
    for name, text in pages.items():
        with open(os.path.join(site, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python3 -m aptrack.stamp <site folder> <commit>")
    stamp(sys.argv[1], sys.argv[2][:10])
