# Apartment tracker

Follows available units at professionally managed apartment buildings across the DC, Maryland and Virginia region and records every price change, so unusually low prices can be spotted against a unit's own history and its neighbors.

Status: tracking for seven companies, true monthly cost, deal tags, the page (with a first-visit setup, a map, followed units and buildings, no-go ZIP codes), area data (census, crime for seven counties, ZIP rent trend, nearby places, walkability, a dog-friendly score), settings export and import, and drive times (no traffic by default, rush hour with your own Google key) are built. Crime for Howard, Loudoun, Anne Arundel, Falls Church and Manassas Park is not: none of them publishes incidents with locations. The Google drive times follow Google's documentation but have not been run against the live service, because that needs a key. `site/changelog.html` is a temporary, plain-language log of changes. The design is in `docs/superpowers/specs/`.

## Files

- `managers.json`: the only hand-kept file. One line per management company, plus settings: seconds between requests to one site (with per-site exceptions), sites read at once, and the counties that count as the region (5-digit FIPS codes). Adding a company adds all its buildings.
- `discover.py`: finds every building each company lists in DC, Maryland and Virginia, and looks up each one's census tract, county and neighborhood. Writes `data/buildings.json`. A building that stops being listed is dropped after three discoveries in a row without it.
- `area.py`: collects what changes slowly around the buildings into `data/area.json`: census figures per tract (through Census Reporter, no key), reported crime within half a mile of each building (one reader per county in `aptrack/area/crime.py`: DC, Montgomery, Prince George's, Fairfax County, Prince William, Alexandria, and Arlington for the last year it published locations, mid-2021 to mid-2022), Zillow's rent index per ZIP code, what is near each building from OpenStreetMap (parks, dog parks, community centers, libraries, supermarkets, Metro stations, places to eat, gyms, pharmacies: how many within half a mile and how far the nearest is), and the EPA's National Walkability Index for the building's block group. Alexandria publishes block addresses, not map points, so `aptrack/area/alexandria.py` reads its police search form a week at a time and places the blocks with the Census batch geocoder; placed blocks are remembered in `area.json`. Runs weekly with discovery; `py area.py --only crime` (or `census`, `rents`, `affordable`, `places`) runs one part.
- `build.py`: reads every building's available units, updates the price history in `data/state.json`, and writes the files the page loads into `site/data/` (`index.json`, and one `units-<county>.json` per county).
- `aptrack/`: the code behind both.
  - `discover/`: one module per company (`bozzuto`, `camden`, `windsor`, `willowbridge`, `greystar`, `avalon`) or per site type (`rentpress`, used for WC Smith; `generic`, for any company whose building pages describe themselves in schema.org data and embed a SightMap unit map); `common.py` holds what they share (reading a page's structured description, finding a SightMap unit map, looking on a building's own website).
  - `readers/`: one module per listing system (`sightmap`, `camden`, `avalon`, `rentpress`). RentPress sites publish prices per floor plan, not per unit: each available floor plan is one entry at its lowest rent, with `count` saying how many units are available. A reader may also return facts about the building (rating, features, promotions) when the same page carries them. Every reader writes the same unit format (`units.py`).
  - `history.py`: what is remembered: a point each time a unit's rent, concession text, quoted lease length or monthly fees change, when a unit appears and disappears, and each floor plan's lowest and median rent over time.
  - `facts/`: one module per company that publishes more about a building on its own page (concession, rating, neighborhood, feature lists), read daily; `laundry.py` works out in-unit laundry from that text.
  - `costs.py`: true monthly cost (rent after free months, plus required monthly fees, plus required one-time fees spread over the lease) and the reading of concession wording.
  - `deals.py`: compares each unit's cost per sqft with similar units in its building and in nearby buildings, and tags it. The thresholds are constants at the top of the file.
- `site/`: the page GitHub Pages serves. `js/logic.js` holds every decision the page makes (what matches the filters, the order, the wording) as plain functions; `js/store.js` keeps filters, followed units and settings in the browser, and turns them into text and back for moving to another browser (the Google key is never part of that text); `js/commute.js` turns a work address into no-traffic drive times using two free public services (OpenStreetMap's Nominatim and the public OSRM server), or, when a Google Maps key has been pasted into Setup, into morning and evening rush-hour times from Google's Routes service, sent straight from the browser; `js/app.js` loads the data and draws. `vendor/leaflet/` is the Leaflet map library (BSD 2-Clause, licence alongside), bundled so the page loads nothing from a CDN; map tiles come from OpenStreetMap.
- `.github/workflows/`: `update.yml` reads units twice a day and publishes the page; `discover.yml` finds buildings weekly; `probe.yml` (run by hand) checks that GitHub's servers can read the building sites.
- The **`data` branch** holds `buildings.json`, `state.json` and `site-data/` as a single commit that each run replaces. On the first of each month the same commit is also kept as `data-YYYY-MM`.

## Rules the tracking follows

- Nothing about a building is typed in by hand. A fact that cannot be collected automatically is left blank.
- At most one request per second per site, unless `site_delays` in `managers.json` gives a site its own spacing. SightMap and Bozzuto are set to four a second: a ramp test on 2026-11-18 (short bursts up to 15 and 23 requests a second) drew no refusals or slowdown from either. No site here publishes a crawl delay or rate-limit headers, so these are tested guesses, and the circle-back rule below is the safety net. OpenStreetMap's lookup service stays at one a second because its usage policy says so.
- A site that stops answering is not hammered. When a site says "too many requests", or fails three times in a row (timeouts, errors, or pages that load without their data), the run leaves it alone, carries on with the other sites, and comes back to it once at the end after a minute's wait, at the default one request a second even if the site was set faster. If it is still silent then, its buildings keep yesterday's units and are marked stale.
- Discovery works the same way: a company whose site fails or starts returning empty pages is come back to once after the others. A company that suddenly lists under half the buildings it had is not believed, and its known buildings are kept.
- A failed read changes nothing: the building keeps its previous units and is marked stale. Units are marked gone only when a successful read no longer lists them.
- A run that would leave under 80% of the previous unit records stops without saving.
- Days are UTC dates. Two runs on one day keep one price point for that day, holding the later price.
- Leased units are kept for 400 days; floor-plan price series are kept indefinitely.

## Run locally

Python 3.12 or later, standard library only.

    py discover.py                  # about ten minutes the first time
    py area.py                      # census, crime, rent trends (optional; a couple of minutes)
    py build.py
    py -m http.server 8000 -d site  # then open http://localhost:8000

    py discover.py --limit 3        # a quick try: three buildings per company
    py build.py --probe             # read one building per listing system, write nothing
    py -m unittest discover -s tests -t .
    node --test "tests/js/*.test.mjs"

To exercise the page in a real browser, copy `tests/js/smoke.html` to `site/_smoke.html`, serve `site/`, and open `/_smoke.html`: it clicks through details, stars and every filter and prints what it saw.

## Adding a company

Add a line to `managers.json`. If the company's building pages carry schema.org data (name and street address) and embed a SightMap unit map, the line is all it takes:

    {"name": "Example Living", "site": "www.example.com", "discover": "generic",
     "sitemap": "https://www.example.com/sitemap.xml",
     "pattern": "https://www\\.example\\.com/apartments/(?:va|md|dc)/[^/<\\s]+/[^/<\\s]+",
     "map_paths": ["", "/floorplans"]}

`sitemap` may be a list; `pattern` is a regular expression matching building pages in it; `map_paths` are the sub-pages to look on for the unit map. Otherwise, if its buildings use a listing system that already has a reader, only a discovery module is needed (`aptrack/discover/`): list the building pages from the company's sitemap and return each building's name, address and feed address. A new listing system also needs a reader (`aptrack/readers/`) that returns units in the common format.
