"""Crime in Alexandria, VA, from the police department's public "Crime Database Search".

The search answers a plain address with a date range and returns a table of incidents: date, block number,
street and classification, at most 500 per query. There are no coordinates, so each block ("100 KING ST") is
placed with the Census geocoder, once, and remembered.
"""

import datetime
import html as htmllib
import re

URL = "https://apps.alexandriava.gov/CrimeReport/Result.aspx"
LIMIT = 500                     # a query never returns more than this many incidents
VIOLENT = {"homicide", "rape", "robbery", "agg assault", "sex offenses, forcible"}
PROPERTY = {"burglary", "larceny", "stolen auto", "arson"}
ROW = re.compile(r"<tr[^>]*>\s*((?:<td[^>]*>.*?</td>\s*){7})</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
COUNT = re.compile(r"([\d,]+)\s+records? match", re.I)


def classify(text):
    text = (text or "").strip().lower()
    if text in VIOLENT:
        return "violent"
    if text in PROPERTY:
        return "property"
    return None


def count(page_html):
    match = COUNT.search(page_html or "")
    return int(match.group(1).replace(",", "")) if match else None


def rows(page_html):
    """One dict per incident: {"address": "100 KING ST", "kind": "violent" | "property" | None, "day"}."""
    found = []
    for row in ROW.findall(page_html or ""):
        cells = [" ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", cell)).split()) for cell in CELL.findall(row)]
        try:
            day = datetime.datetime.strptime(cells[1], "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        if cells[4] and cells[5]:
            found.append({"address": f"{cells[4]} {cells[5]}", "kind": classify(cells[6]), "day": day})
    return found


def windows(start, end, days=7):
    """(first day, last day) pairs covering start..end in steps of `days`."""
    first, last = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    spans = []
    while first <= last:
        until = min(first + datetime.timedelta(days=days - 1), last)
        spans.append((first.isoformat(), until.isoformat()))
        first = until + datetime.timedelta(days=1)
    return spans


def fetch_window(get, first, last):
    """Every incident row between two days. A query that hits the limit is split in two and asked again."""
    page = get(f"{URL}?&sd={first.replace('-', '')}&ed={last.replace('-', '')}").decode("utf-8", "replace")
    found = rows(page)
    if (count(page) or len(found)) >= LIMIT and first != last:
        a, b = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
        middle = a + (b - a) // 2
        return (fetch_window(get, first, middle.isoformat())
                + fetch_window(get, (middle + datetime.timedelta(days=1)).isoformat(), last))
    return found


def incidents(get, start, end, place, cache):
    """(lat, lon, kind, day) for violent and property incidents. `place(addresses, cache)` returns {address: (lat, lon)}."""
    wanted = []
    for first, last in windows(start, end):
        wanted += [row for row in fetch_window(get, first, last) if row["kind"]]
    where = place({row["address"] for row in wanted}, cache) if wanted else {}
    return [(*where[row["address"]], row["kind"], row["day"]) for row in wanted if row["address"] in where]
