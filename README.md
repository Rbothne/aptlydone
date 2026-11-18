# Apartment tracker

Follows available units at professionally managed apartment buildings across the DC, Maryland and Virginia region and records every price change, so unusually low prices can be spotted against a unit's own history and its neighbors.

Status: tracking (this README) is built. The full page (filters, deal labels, map, commute) is not; `site/index.html` is a status page for now. The design is in `docs/superpowers/specs/`.

## Files

- `managers.json`: the only hand-kept file. One line per management company, plus settings: seconds between requests to one site, sites read at once, and the counties that count as the region (5-digit FIPS codes). Adding a company adds all its buildings.
- `discover.py`: finds every building each company lists in DC, Maryland and Virginia, and looks up each one's census tract, county and neighborhood. Writes `data/buildings.json`. A building that stops being listed is dropped after three discoveries in a row without it.
- `build.py`: reads every building's available units, updates the price history in `data/state.json`, and writes the files the page loads into `site/data/` (`index.json`, and one `units-<county>.json` per county).
- `aptrack/`: the code behind both.
  - `discover/`: one module per company (`bozzuto`, `camden`).
  - `readers/`: one module per listing system (`sightmap`, `camden`). Every reader writes the same unit format (`units.py`).
  - `history.py`: what is remembered: a point each time a unit's rent or concession text changes, when a unit appears and disappears, and each floor plan's lowest and median rent over time.
- `site/`: the page GitHub Pages serves.
- `.github/workflows/`: `update.yml` reads units twice a day and publishes the page; `discover.yml` finds buildings weekly; `probe.yml` (run by hand) checks that GitHub's servers can read the building sites.
- The **`data` branch** holds `buildings.json`, `state.json` and `site-data/` as a single commit that each run replaces. On the first of each month the same commit is also kept as `data-YYYY-MM`.

## Rules the tracking follows

- Nothing about a building is typed in by hand. A fact that cannot be collected automatically is left blank.
- At most one request per second per site. A site that answers "too many requests" is left alone and tried once more at the end of the run.
- A failed read changes nothing: the building keeps its previous units and is marked stale. Units are marked gone only when a successful read no longer lists them.
- A run that would leave under 80% of the previous unit records stops without saving.
- Days are UTC dates. Two runs on one day keep one price point for that day, holding the later price.
- Leased units are kept for 400 days; floor-plan price series are kept indefinitely.

## Run locally

Python 3.12 or later, standard library only.

    py discover.py                  # about ten minutes the first time
    py build.py
    py -m http.server 8000 -d site  # then open http://localhost:8000

    py discover.py --limit 3        # a quick try: three buildings per company
    py build.py --probe             # read one building per listing system, write nothing
    py -m unittest discover -s tests -t .

## Adding a company

Add a line to `managers.json`. If its buildings use a listing system that already has a reader, only a discovery module is needed (`aptrack/discover/`): list the building pages from the company's sitemap and return each building's name, address and feed address. A new listing system also needs a reader (`aptrack/readers/`) that returns units in the common format.
