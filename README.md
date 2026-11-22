# Apartment tracker

Follows available units at professionally managed apartment buildings across the DC, Maryland and Virginia region and records every price change, so unusually low prices can be spotted against a unit's own history and its neighbors.

Status: tracking for twenty-one companies (Mill Creek is paused), true monthly cost, deal tags, the page (with a first-visit setup, a map, followed units and buildings, no-go ZIP codes), area data (census, crime for nine counties, ZIP rent trend, nearby places, walkability, a dog-friendly score), settings export and import, and drive times (no traffic by default, rush hour with your own Google key) are built. Crime for Anne Arundel, Falls Church, Fairfax City, Manassas and Manassas Park is not: none of them publishes incidents with locations. The Google drive times follow Google's documentation but have not been run against the live service, because that needs a key. `site/changelog.html` is a temporary, plain-language log of changes. The design is in `docs/superpowers/specs/`.

## Files

- `managers.json`: the only hand-kept file. One line per management company, plus settings: seconds between requests to one site (with per-site exceptions; a site that asks for a crawl delay in its robots file gets it here, as Gables does with five seconds), and the counties that count as the region (5-digit FIPS codes). Adding a company adds all its buildings.
- `discover.py`: finds every building each company lists in DC, Maryland and Virginia, and looks up each one's census tract, county and neighborhood. Writes `data/buildings.json`. A building that stops being listed is dropped after three discoveries in a row without it.
- `area.py`: collects what changes slowly around the buildings into `data/area.json`: census figures per tract (through Census Reporter, no key), reported crime within half a mile of each building (one reader per county in `aptrack/area/crime.py`: DC, Montgomery, Prince George's, Fairfax County, Prince William, Alexandria, Howard, Loudoun, and Arlington for the last year it published locations, mid-2021 to mid-2022), Zillow's rent index per ZIP code, what is near each building (parks, dog parks, community centers, libraries, supermarkets, places to eat, gyms and pharmacies from OpenStreetMap, Metro stations from the transit authority's own list: how many within half a mile and how far the nearest is), and the EPA's National Walkability Index for the building's block group. Alexandria publishes block addresses, not map points, so `aptrack/area/alexandria.py` reads its police search form a week at a time and places the blocks with the Census batch geocoder; placed blocks are remembered in `area.json`. Howard and Loudoun publish only Power BI dashboards; `aptrack/area/powerbi.py` asks the dashboard's own public data service for the rows behind its charts (incident, day, map point, offence code). Runs weekly with discovery; `py area.py --only crime` (or `census`, `rents`, `affordable`, `places`) runs one part. OpenStreetMap's places are read from the state files Geofabrik publishes daily, not from the public query servers (Overpass), which are often at capacity and ask automated users to stay away: `aptrack/area/extract.py` downloads only the two small place layers out of each state's zip by byte range (a few megabytes of a file of several hundred) and reads the shapefiles inside.
- `build.py`: reads every building's available units, updates the price history in `data/state.json`, and writes the files the page loads into `site/data/` (`index.json`, and one `units-<county>.json` per county).
- `aptrack/`: the code behind both.
  - `discover/`: one module per company (`bozzuto`, `camden`, `windsor`, `willowbridge`, `greystar`, `avalon`, `equity`, `udr`, `jbgsmith`) or per site type, each described by one `managers.json` line: `rentpress` (WC Smith; `rentpress_list` for Polinger, whose RentPress page lists buildings that live on their own sites), `generic` (company pages with schema.org data: Cortland, Gables, LyvWell, MAA, Simpson, Keener), `cards` (one page of building cards described by a regular expression: AIR Communities, B.F. Saul) and `wpjson` (the WordPress REST API: Mill Creek). `common.py` holds what they share: reading a page's structured description, and `site_feed`, which looks through a building's own website for a listing system with a reader.
  - `readers/`: one module per listing system (`sightmap`, `camden`, `avalon`, `rentpress`, `equity`, `udr`, `jonah`, `g5`, `offers`, `appfolio`). Readers never import from `discover/`; the dependency runs the other way. RentPress sites publish prices per floor plan, not per unit: each available floor plan is one entry at its lowest rent, with `count` saying how many units are available. A reader may also return facts about the building (rating, features, promotions) when the same page carries them. Every reader writes the same unit format (`units.py`).
  - `history.py`: what is remembered: a point each time a unit's rent, concession text, quoted lease length or monthly fees change, when a unit appears and disappears, and each floor plan's lowest and median rent over time.
  - `facts/`: one module per company that publishes more about a building on its own page (concession, rating, neighborhood, feature lists), read daily; `laundry.py` works out in-unit laundry from that text.
  - `costs.py`: true monthly cost (rent after free months, plus required monthly fees, plus required one-time fees spread over the lease) and the reading of concession wording.
  - `deals.py`: compares each unit's cost per sqft with similar units in its building and in nearby buildings, and tags it. The thresholds are constants at the top of the file.
- `site/`: the page GitHub Pages serves. `js/logic.js` holds every decision the page makes (what matches the filters, the order, the wording) as plain functions; `js/store.js` keeps filters, followed units and settings in the browser, and turns them into text and back for moving to another browser (the Google key is never part of that text); `js/commute.js` turns a work address into no-traffic drive times using two free public services (OpenStreetMap's Nominatim and the public OSRM server), or, when a Google Maps key has been pasted into Setup, into morning and evening rush-hour times from Google's Routes service, sent straight from the browser; `js/app.js` loads the data and draws. `vendor/leaflet/` is the Leaflet map library (BSD 2-Clause, licence alongside), bundled so the page loads nothing from a CDN; map tiles come from OpenStreetMap, with satellite (Esri World Imagery), transit (memomaps.de) and rail-line (OpenRailwayMap) layers to switch to.
- `.github/workflows/`: `update.yml` reads units twice a day and publishes the page; `discover.yml` finds buildings weekly; `probe.yml` (run by hand) checks that GitHub's servers can read the building sites.
- The **`data` branch** holds `buildings.json`, `state.json` and `site-data/` as a single commit that each run replaces. On the first of each month the same commit is also kept as `data-YYYY-MM`.

## Rules the tracking follows

- Nothing about a building is typed in by hand. A fact that cannot be collected automatically is left blank.
- At most one request per second per site, unless `site_delays` in `managers.json` gives a site its own spacing. SightMap and Bozzuto are set to four a second: a ramp test on 2026-11-18 (short bursts up to 15 and 23 requests a second) drew no refusals or slowdown from either. No site here publishes a crawl delay or rate-limit headers, so these are tested guesses, and the circle-back rule below is the safety net. OpenStreetMap's lookup service stays at one a second because its usage policy says so.
- Every site has a lane of its own and all lanes run at once, each at its own site's spacing, so the run is always asking someone: while a slow site is made to wait, the others are being read. The same goes for companies during discovery and for counties when crime is collected. No site is ever asked faster for it. (An optional `workers` setting caps the lanes.)
- A site that stops answering is not hammered. When a site says "too many requests", or fails three times in a row (timeouts, errors, or pages that load without their data), the run leaves it alone, carries on with the other sites, and comes back to it once at the end after a minute's wait, at the default one request a second even if the site was set faster. If it is still silent then, its buildings keep yesterday's units and are marked stale.
- Discovery works the same way: a company whose site fails or starts returning empty pages is come back to once after the others. A company that suddenly lists under half the buildings it had is not believed, and its known buildings are kept.
- A failed read changes nothing: the building keeps its previous units and is marked stale. Units are marked gone only when a successful read no longer lists them.
- A run that would leave under 80% of the previous unit records stops without saving.
- Days are UTC dates. Two runs on one day keep one price point for that day, holding the later price.
- Leased units are kept for 400 days; floor-plan price series are kept indefinitely.

## Run locally

Python 3.12 or later, standard library only.

    py discover.py                  # about ten minutes the first time
    py area.py                      # census, crime, rent trends, places, noise, permits (optional; several minutes)
    py build.py
    py -m http.server 8000 -d site  # then open http://localhost:8000

    py discover.py --limit 3        # a quick try: three buildings per company
    py build.py --probe             # read one building per listing system, write nothing
    py -m unittest discover -s tests -t .
    node --test "tests/js/*.test.mjs"

To exercise the page in a real browser, copy `tests/js/smoke.html` to `site/_smoke.html`, serve `site/`, and open `/_smoke.html`: it clicks through details, stars and every filter and prints what it saw.

## Reading a few buildings at a time

`"spread": {"rentcafe": 6}` in the settings of `managers.json` takes RentCafe buildings out of the ordinary runs and reads them in six shares (`aptrack/spread.py`). `spread.yml` runs `build.py --spread` every two hours: it reads the next share, in the order of the buildings' ids, and keeps the id it stopped at in `state["spread"]`, so late or missed runs lose nothing. All RentCafe sites also share one clock (`"rentcafe": 2` in `site_delays`): one request every two seconds across all of them. `build.py --all` reads everything in one go, for a full read from a home machine. A spread run never ends in failure because of refusals: its sites refuse often, and a share is small.

## Publishing the page

`update.yml` publishes `site/`. Just before it does, `python3 -m aptrack.stamp site <commit>` moves `site/js` to `site/js-<commit>` and points `index.html` at it (the stylesheet gets `?v=<commit>`). GitHub Pages lets a browser keep each file for ten minutes, so without this a browser could run a new page with old scripts for a while after each publish. The repository's own `site/js` is never renamed; only the copy being published.

## Where a building is

Each week `discover.py` sends every building's street address to the Census Bureau's batch address service (`discovery.check_addresses`, one request) and keeps the answer on the building as `placed`. An address is asked about once.

- **ZIP code** (`area.zip_code`): the building's own published ZIP when it could be one here; else the Census Bureau's for the address; else the one looked up from its coordinates. An audit on 2026-11-19 found the published ZIP right 444 times out of 444 and the coordinate lookup wrong for 246 of 564.
- **Coordinates** (`discovery.correct`): the site's own, unless an exactly matched address is more than a quarter mile away; then the address's, with the published pair kept as `site_lat`/`site_lon`. A loose match never moves a building.
- A building whose coordinates change is located again (`located_at`), and what is looked up once per place (walkability, noise) is looked up again (`area["at"]`).
- A company line with `"city_from_address": true` (MAA) publishes a region where the city belongs; its buildings take the city of their address.

## Noise, construction, and what a listing says about a unit

- `aptrack/area/noise.py` reads the US DOT National Transportation Noise Map (2020) for aircraft, road and rail noise at each building. The map is published only as coloured tiles, so it fetches the tile a building falls on (`aptrack/area/png.py` decodes it with the standard library) and looks the pixel's colour up in the map's own legend. A building is looked up once (`py area.py --only noise`).
- `aptrack/area/works.py` reads DC's building permits (one map layer per year): new buildings and demolition within a block in two years, and alteration work on the building's own lot that paid $5,000 or more in fees in the last year (`py area.py --only works`). DC only.
- `aptrack/traits.py` marks a unit `outdoor` ("Balcony", "Terrace"...) and `own_door` from the floor plan's name and the unit's own feature list, never from building amenities. The SightMap reader now passes a unit map's per-unit feature list through as the unit's notes.
- `history.drop` marks a price drop: at least 2% below the highest rent that stood in the last 30 days, the latest move down, same lease length.
- On the page (`site/js/logic.js`): `relateCrime` measures each building's violent count against the median building; `worth` adds up, in dollars a month, how far a unit is priced under similar units (capped at 25%) and the user's own values from Setup for drive, crime, walkability and quiet. Top picks sorts on that sum as a share of the unit's cost.

## Pausing a company, and bringing it back

Add `"paused": "<why>"` to the company's line in `managers.json`. A paused company is not searched for buildings, not read, not given area data and not on the page. Nothing about it is deleted: its discoverer and reader stay in the code (a test keeps them registered), its buildings stay in `data/buildings.json` with their locations, and its price history stays in `data/state.json` with every unit marked as no longer listed. Delete the `"paused"` entry and the next run searches and reads it again, picking each unit's history back up.

Equity Residential was paused on 2026-11-19 and brought back on 2026-11-20 at the owner's instruction. Its terms of use forbid automated reading without written consent, and its site refuses GitHub's servers (HTTP 403) while answering a home connection, so its prices refresh only when `build.py` is run from a home machine and the data branch saved; between such runs GitHub's runs mark its buildings stale. To pause it again, put `"paused": "<why>"` back on its line.

## A building's own website

Many company pages only link to each building's own website. Discovery then looks through that site (`common.site_feed`): first `/floorplans` and `/floor-plans`, then the home page, then the floor-plans and availability pages the site links to, and `/availability`, seven pages at most. It stops at the first page that names a listing system with a reader:

- a SightMap unit map (`sightmap`), also when a G5 widget names one;
- Jonah Digital's floor-plans data (`jonah`: base rent and required monthly fees for each apartment);
- G5's "Floor Plans Plus" widget (`g5`: the reader asks G5's public inventory service, the same one the page asks, for each floor plan's units);
- schema.org offers on floor-plan pages (`offers`: Greystar's own building sites, where each plan page lists an `OfferForLease` per unit, and AIR Communities' sites, which list the plan's apartments with a starting price that includes required fees);
- RentPress floor plans (`rentpress`).

AppFolio listing pages (`appfolio`) are read from a company's line (`"appfolio": "<company>.appfolio.com/listings"`). One page lists every apartment, it is fetched once a run, and each building keeps the listings at its street address. AppFolio's robots file allows `/listings` at ten seconds a request.

A website that refuses one week keeps the listing found before (`discovery.merge`). Many building sites sit behind a Cloudflare check that turns automated visitors away part of the time. The tracker does not try to get past it.

Read at the owner's instruction (20 November 2026), although the source's terms discourage it: RentCafe (Yardi) building sites, whose terms of use forbid "any robot, spider, site search/retrieval application, or other automated device" (`readers/rentcafe.py`; they answer the tracker's ordinary requests and their robots files allow the floor-plan pages); and Kettler's building list, which its own search returns when asked with the site number its communities page hands every visitor (`discover/kettler.py`). Equity Residential, whose terms forbid automated reading without written consent, is read on the same footing. All are read under the tracker's own name at its usual pace.

Not read: any site that refuses. Entrata and RealPage's online leasing turn automated visitors away, as do Mill Creek's and Paradigm's building sites (Cloudflare), Daro's site and Bernstein Management's (HTTP 403 on its home page, so no list of its buildings can be read). Van Metre's portfolio site answers some days and refuses others; on a day it refuses, the buildings found before are kept. A refusal is never worked around: no disguised requests, no proxies, no solving of bot checks.

## Adding a company

Add a line to `managers.json`. If the company's building pages carry schema.org data (name and street address) and embed a SightMap unit map, the line is all it takes:

    {"name": "Example Living", "site": "www.example.com", "discover": "generic",
     "sitemap": "https://www.example.com/sitemap.xml",
     "pattern": "https://www\\.example\\.com/apartments/(?:va|md|dc)/[^/<\\s]+/[^/<\\s]+",
     "map_paths": ["", "/floorplans"]}

`sitemap` may be a list; `pattern` is a regular expression matching building pages in it; `map_paths` are the sub-pages to look on for the unit map. In place of `sitemap`, `list` names a page (a company's page for this region, say) whose links are matched against the pattern. `name_from_slug: true` names buildings from their page address when the page's own name is a marketing title. Otherwise, if its buildings use a listing system that already has a reader, only a discovery module is needed (`aptrack/discover/`): list the building pages from the company's sitemap and return each building's name, address and feed address. A new listing system also needs a reader (`aptrack/readers/`) that returns units in the common format.

## Where the data comes from

Few of these are official APIs: most are the data a site's own pages already load, read under the rules above.

| Source | Used for |
|---|---|
| Management companies' sitemaps and building pages | Finding every building each company runs, with its name and address |
| SightMap unit-map feed | Unit rent, size, floor, availability, fees and amenities (most buildings) |
| Company sites (Camden, AvalonBay, Equity, UDR) | Unit listings embedded in their own pages |
| RentCafe, RentPress, AppFolio, Jonah, G5, schema.org offers | Unit or floor-plan prices for buildings on those listing systems |
| Census Bureau batch address service | Placing each address: coordinates, ZIP code, census tract, county |
| Census Reporter (ACS 5-year figures) | Demographics per tract: income, age, education, median rent |
| County open crime data, Alexandria's police search form, Howard's and Loudoun's public dashboards | Violent and property crime within half a mile of each building (nine counties) |
| Zillow rent index | Rent trend per ZIP code |
| OpenStreetMap (Geofabrik's state files) | Nearby parks, dog parks, supermarkets, gyms, places to eat, pharmacies, libraries |
| Transit authority station list (DC's open map service) | Distance to the nearest Metro station |
| EPA National Walkability Index | Walkability of each building's block group |
| US DOT National Transportation Noise Map | Aircraft, road and rail noise at each building |
| DC building permits | Construction next door or on the building's own lot (DC only) |
| DC affordable-housing list | Flagging income-restricted buildings |
| OpenStreetMap's Nominatim and the public OSRM server | Turning a work address into drive times without traffic |
| Google Routes (optional, your own key) | Rush-hour drive times |
| Leaflet with OpenStreetMap tiles; Esri World Imagery, memomaps.de (ÖPNVKarte) and OpenRailwayMap tiles | The map view, and its satellite, transit and rail-line layers |
| GitHub Actions and GitHub Pages | Running the scheduled reads and hosting the page |
