# Tracking Pipeline Implementation Plan (plan 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find Bozzuto and Camden buildings across the region automatically, read their available units, and record price history from the first run.

**Architecture:** A standard-library Python package (`aptrack`) with one discovery module per management company and one reader per listing system, all writing a common unit format. `discover.py` (weekly) generates `data/buildings.json`; `build.py` (twice daily) reads units, updates `data/state.json` and writes per-county files for the page under `site/data/`. GitHub Actions runs both and keeps the data on a single-commit `data` branch.

**Tech Stack:** Python 3.12+ standard library only (`urllib`, `json`, `gzip`, `re`, `concurrent.futures`, `unittest`). No third-party packages. GitHub Actions and Pages.

**Spec:** `docs/superpowers/specs/2026-11-18-apartment-tracker-design.md` (sections 5, 6, 11 and steps 1–2 of section 12).

Later plans: 2 the page; 3 net rent, building facts and Deal score; 4 area data, map and no-go regions; 5 setup, commute and Match.

## Global Constraints

- Standard library only. Run Python as `py` on Windows, `python3` in workflows.
- Nothing about a building is typed in by hand. `managers.json` is the only hand-kept file.
- At most one request per second per site; a 429 answer is never retried in a tight loop.
- A failed read never marks units gone and never replaces good history.
- Days are UTC dates as `YYYY-MM-DD` strings.
- Region counties (5-digit FIPS): `11001` DC; `51013` Arlington, `51510` Alexandria, `51059` Fairfax, `51600` Fairfax City, `51610` Falls Church, `51107` Loudoun, `51153` Prince William, `51683` Manassas, `51685` Manassas Park; `24031` Montgomery, `24033` Prince George's, `24027` Howard, `24003` Anne Arundel.
- The served page lives in `site/`. `data/` and `site/data/` are generated and git-ignored on `main`.
- Tests: `py -m unittest discover -s tests -v`.

## Review Focus

1. A feed that lists units but hides every price: expected to count as a failed read (units kept, marked stale), not as "all units leased". Test in Task 2.
2. Two units with the same number in a multi-building property: expected to get distinct ids. Test in Task 2.
3. Two runs on the same day with different prices: expected to keep one point for that day, holding the later price. Test in Task 4.
4. A company's sitemap failing during discovery: expected to keep that company's previously found buildings. Test in Task 5.
5. A studio (`bedroom_count` 0 or `"Studio"`) or a unit with no sqft: expected to be kept with `beds` 0 or `sqft` null, not dropped or crashed on. Tests in Tasks 2 and 3.

---

## File Structure

```
managers.json                 companies and settings (hand-kept)
discover.py                   CLI: generate data/buildings.json
build.py                      CLI: read units, update history, write site data
aptrack/fetch.py              polite HTTP: get(), Throttle, Gone, RateLimited
aptrack/units.py              make_unit(): the common unit format
aptrack/readers/__init__.py   READERS registry, ReadError
aptrack/readers/sightmap.py   SightMap feed reader
aptrack/readers/camden.py     Camden page reader
aptrack/history.py            price-history rules and the save guard
aptrack/geo.py                Census geocoder and OpenStreetMap neighborhood lookup
aptrack/discover/bozzuto.py   Bozzuto sitemap and building pages
aptrack/discover/camden.py    Camden sitemap and building pages
aptrack/discovery.py          region filter and merge with the previous list
aptrack/output.py             files the page loads
site/index.html               status page until plan 2
tests/                        unittest files and tests/fixtures/
.github/workflows/            probe.yml, update.yml, discover.yml
```

---

### Task 1: Project skeleton and polite fetching

**Files:** Create `.gitignore`, `managers.json`, `aptrack/__init__.py`, `aptrack/fetch.py`, `tests/test_fetch.py`.

**Interfaces — Produces:**
- `fetch.get(url: str, *, timeout: int = 25, tries: int = 3, opener=urllib.request.urlopen) -> bytes`. Sends a browser-style `User-Agent` and `Accept-Encoding: gzip`; returns the body decompressed when it starts with the gzip magic bytes. Raises `fetch.Gone` on 404/410, `fetch.RateLimited` on 429 (no retry), and the last error after `tries` attempts on other failures (waits 2 s then 4 s between attempts; `sleep` injectable for tests).
- `fetch.Throttle(delay: float = 1.0)` with `wait(url)`: blocks so that calls for the same host are at least `delay` apart. Thread-safe.
- `managers.json`: `{"settings": {"delay_seconds": 1.0, "workers": 4, "counties": [...the FIPS list above...]}, "managers": [{"name": "Bozzuto", "site": "www.bozzuto.com", "discover": "bozzuto"}, {"name": "Camden", "site": "www.camdenliving.com", "discover": "camden"}]}`

- [ ] **Step 1:** `git init -b main`; write `.gitignore` (`data/`, `site/data/`, `__pycache__/`) and `managers.json`.
- [ ] **Step 2: Failing tests** in `tests/test_fetch.py`, using a fake `opener`:

```python
def test_gzip_body_is_decompressed(self):      # opener returns gzip.compress(b'{"a":1}')
    self.assertEqual(fetch.get("https://x.test/a", opener=op), b'{"a":1}')
def test_404_raises_gone(self):                # opener raises HTTPError 404
    with self.assertRaises(fetch.Gone): fetch.get("https://x.test/a", opener=op)
def test_429_raises_rate_limited_without_retry(self):
    with self.assertRaises(fetch.RateLimited): fetch.get("https://x.test/a", opener=op, sleep=lambda s: None)
    self.assertEqual(op.calls, 1)
def test_500_is_retried_then_succeeds(self):   # fails twice, then returns b"ok"
    self.assertEqual(fetch.get("https://x.test/a", opener=op, sleep=lambda s: None), b"ok"); self.assertEqual(op.calls, 3)
def test_throttle_spaces_same_host(self):      # Throttle(0.2): two waits on one host take >= 0.2 s; a different host does not wait
```

- [ ] **Step 3:** Run the tests; expect failures (module missing).
- [ ] **Step 4:** Implement `aptrack/fetch.py`.
- [ ] **Step 5:** Run the tests; expect all pass. Commit `Skeleton, managers list and polite fetching`.

### Task 2: Common unit format and the SightMap reader

**Files:** Create `aptrack/units.py`, `aptrack/readers/__init__.py`, `aptrack/readers/sightmap.py`, `tests/test_sightmap.py`, `tests/fixtures/sightmap_embed.html`, `tests/fixtures/sightmap_feed.json`.

**Interfaces — Produces:**
- `units.make_unit(building_id, unit, *, rent, plan=None, beds=None, baths=None, sqft=None, floor=None, fees=None, lease=None, available=None, special=None, notes=None, url=None) -> dict | None`. Returns `None` unless `rent` is a number above 0. `id` is `f"{building_id}:{unit}"`. `beds`: `"Studio"`/`0` → `0`, numeric strings → numbers. `sqft` 0 or missing → `None`. `available` is trimmed to `YYYY-MM-DD`. Keys are exactly the spec's common format: `id, building, unit, floor, plan, beds, baths, sqft, rent, fees, lease, available, special, notes, url`.
- `readers.ReadError(Exception)`.
- `sightmap.feed_url(embed_html: str) -> str | None`: the first `https://sightmap.com/app/api/v1/<asset>/sightmaps/<n>` address in the embed page (slashes may be escaped as `\/`).
- `sightmap.parse(feed: dict, building: dict) -> dict` returning `{"units": [unit...], "fees": [fee...], "amenities": [str...]}`; `feed` is the decoded JSON (its `data` member is used when present).
  - Unit fields: `unit_number`, `area` → sqft, `price` → rent, `available_on`, `specials_description` → special, `display_lease_term` → lease (leading number), floor plan `name`/`bedroom_count`/`bathroom_count` via `floor_plan_id`, floor from the unit's `floor_id` looked up in the feed's floors (a number when the floor's label is numeric, else `None`), `fees` = `total_price[0] − price` when `total_price` is present and not below `price`.
  - When two units share a `unit_number`, their unit label becomes `f"{building}-{unit_number}"` using the unit's `building` value.
  - Fee: `{"label", "type", "category", "required": bool, "when": classification, "amount": float | None, "text": display_amount}` from `expenses`, with amounts from the first unit's `expense_amounts` and `static_expense_amounts`.
  - Amenities: stripped `title` values.
  - Raises `ReadError` when the feed has units but none has a usable price.
- `sightmap.read(building: dict, get) -> dict`: uses `building["feed_api"]` when present, otherwise fetches `building["feed"]` (the embed address) and resolves it; on `Gone` from a cached `feed_api`, re-resolves once. Returns `parse(...)` plus `"feed_api"` so the caller can cache it.
- `readers.READERS: dict[str, callable]` maps `"sightmap"` to `sightmap.read`.

- [ ] **Step 1:** Capture fixtures: save the embed page for `https://sightmap.com/embed/8ywkoe19vlx` and its feed; trim the feed to 4 units (keep their floor plans, the floors, expenses and amenities) and add one hand-made duplicate-number unit in a second building and one unit with `price` null.
- [ ] **Step 2: Failing tests:**

```python
def test_feed_url_found_in_embed_page(self):
    self.assertRegex(sightmap.feed_url(EMBED), r"^https://sightmap\.com/app/api/v1/\w+/sightmaps/\d+$")
def test_units_use_common_format(self):
    u = by_unit(parse(FEED, B))["215"]
    self.assertEqual((u["id"], u["sqft"], u["rent"], u["beds"], u["baths"], u["available"]),
                     ("bozzuto-5333-connecticut:215", 827, 2700, 1, 1, "2026-11-29"))
def test_unpriced_unit_is_skipped(self): ...            # the null-price unit is absent
def test_duplicate_unit_numbers_get_distinct_ids(self): # both present, ids differ
def test_all_units_unpriced_raises_read_error(self): ...
def test_fees_list_marks_required_and_amount(self):     # reserved parking: required False, amount 225.0
def test_amenities_are_stripped_titles(self):           # "Business Center" has no trailing tab
def test_studio_and_missing_sqft_are_kept(self):        # make_unit(..., beds="Studio", sqft=0) -> beds 0, sqft None
def test_read_resolves_and_returns_feed_api(self):      # fake get; cached feed_api skips the embed fetch
```

- [ ] **Step 3:** Run; expect failures. **Step 4:** Implement. **Step 5:** Run; expect pass. Commit `Common unit format and SightMap reader`.

### Task 3: Camden reader

**Files:** Create `aptrack/readers/camden.py`, `tests/test_camden.py`, `tests/fixtures/camden_available.html`. Modify `aptrack/readers/__init__.py`.

**Interfaces — Produces:**
- `camden.page_data(html: str) -> dict`: the `props.pageProps` object from the page's `__NEXT_DATA__` script; raises `ReadError` when absent.
- `camden.parse(html: str, building: dict) -> dict`, same return shape as `sightmap.parse`. Floor plans are `data.availableApartments[]` (`name`, `bedrooms`, `bathrooms`, `squareFeet`, `monthlyRent`, `totalMonthlyRent`); units are each plan's `availableUnitRefs[]` (`unitNumber`, `buildingNumber`, `floorNumber`, `squareFeet`, `monthlyRent`, `moveInDate`, `leaseTerm`). Unit `fees` = the plan's `totalMonthlyRent − monthlyRent` when both exist and the result is not negative. `special` = `specialCtaTitle` and `specialCtaDescription` joined, or `None` when both are empty. A unit with a `buildingNumber` is labelled `f"{buildingNumber}-{unitNumber}"`. `fees` and `amenities` lists are empty.
- `camden.read(building, get) -> dict`: fetches `building["feed"]` and parses.
- `READERS["camden"]`.

- [ ] **Step 1:** Fixture: save `https://www.camdenliving.com/apartments/washington-dc/camden-noma/available-apartments`, keeping the `__NEXT_DATA__` script with two floor plans (one studio).
- [ ] **Step 2: Failing tests:**

```python
def test_units_from_floor_plans(self):
    u = by_unit(parse(HTML, B))["1215"]
    self.assertEqual((u["plan"], u["beds"], u["baths"], u["sqft"], u["floor"], u["rent"], u["lease"], u["available"]),
                     ("S4", 0, 1, 495, 12, 1829, 15, "2026-12-18"))
def test_fees_from_total_rent(self):          # 1773 - 1649 = 124
def test_empty_special_is_none(self): ...
def test_page_without_data_raises_read_error(self): ...
def test_no_available_units_returns_empty_list(self):   # availableApartments [] -> units [] and no error
```

- [ ] **Step 3–5:** Run (fail), implement, run (pass). Commit `Camden reader`.

### Task 4: Price history

**Files:** Create `aptrack/history.py`, `tests/test_history.py`.

**Interfaces — Produces:**
- `history.new_state() -> dict`: `{"version": 1, "units": {}, "plans": {}, "buildings": {}}`.
- `history.record(state, building_id, units, day) -> None` for a successful read.
  - `state["units"][id]`: `{"building", "plan", "beds", "baths", "sqft", "first", "last", "gone", "points": [[day, rent, special]], "past": []}`.
  - New unit: `first = last = day`, one point. Seen again: `last = day`; when rent or special differs from the last point, append a point, except that a last point dated `day` is overwritten, and a point that then equals the one before it is removed.
  - A unit of this building absent from `units` gets `gone = day` (once).
  - A unit present while `gone` is set: its `first`, `last` and `points` move into `past`, `gone` clears, and a new listing starts.
  - `state["plans"][f"{building_id}|{plan}"]`: `{"beds", "points": [[day, low, median, count]]}`, appended when the triple changes, with the same same-day overwrite rule. A plan with no units today gets `[day, None, None, 0]` once.
  - `state["buildings"][building_id] = {"ok": day, "failed": None}`.
- `history.record_failure(state, building_id, day) -> None`: sets `failed = day`, keeps `ok`, touches no unit.
- `history.prune(state, day) -> None`: removes units whose `gone` is more than `UNIT_KEEP_DAYS = 400` days before `day`.
- `history.safe_to_save(before: dict, after: dict) -> bool`: false when `after` has fewer than 80% of `before`'s unit records.

- [ ] **Step 1: Failing tests:**

```python
def test_new_unit_gets_first_point(self): ...
def test_unchanged_rent_adds_no_point(self): ...
def test_changed_rent_appends_point(self): ...
def test_changed_special_appends_point(self): ...
def test_same_day_change_overwrites_point(self):        # 2700 then 2650 on one day -> one point, 2650
def test_same_day_return_to_previous_drops_point(self): # day1 2700; day2 2650 then 2700 -> one point
def test_absent_unit_marked_gone_once(self): ...
def test_other_buildings_units_untouched(self): ...
def test_returning_unit_starts_new_listing(self):       # past has 1 entry, gone None, first == return day
def test_failure_touches_no_unit(self): ...
def test_plan_series_low_median_count(self):            # rents 2000, 2200, 2600 -> [day, 2000, 2200, 3]
def test_plan_with_no_units_gets_empty_point_once(self): ...
def test_prune_drops_units_gone_over_400_days(self): ...
def test_safe_to_save_refuses_big_drop(self):           # 100 -> 79 False; 100 -> 80 True; 0 -> 0 True
```

- [ ] **Step 2–4:** Run (fail), implement, run (pass). Commit `Price history rules`.

### Task 5: Discovery

**Files:** Create `aptrack/geo.py`, `aptrack/discover/__init__.py`, `aptrack/discover/bozzuto.py`, `aptrack/discover/camden.py`, `aptrack/discovery.py`, `discover.py`, `tests/test_discovery.py`, fixtures `bozzuto_sitemap.xml`, `bozzuto_building.html`, `bozzuto_floorplans.html`, `camden_sitemap.xml`, `census_coordinates.json`, `census_address.json`, `nominatim_reverse.json`.

**Interfaces — Produces:**
- `bozzuto.building_urls(sitemap_xml: str) -> list[str]`: addresses matching `/apartments-for-rent/(dc|md|va)/<city>/<slug>` exactly (no deeper path), de-duplicated, from `https://www.bozzuto.com/sitemap/properties_sitemap.xml` (`bozzuto.SITEMAP`).
- `bozzuto.parse(url, page_html, floorplans_html) -> dict | None`: from the `ApartmentComplex` node of the page's `application/ld+json`: `name`, `address` `{"street", "city", "state", "zip"}`, `lat`, `lon`; from the floor-plans page (`url + "/floor-plans"`): `feed` = the `https://sightmap.com/embed/<id>` address (quotes may be escaped). Returns `{"id": "bozzuto-<slug>", "manager": "Bozzuto", "name", "url", "platform": "sightmap", "feed", "address", "lat", "lon"}`; `platform` is `"link"` and `feed` `None` when no embed address is found; `None` when the page has no `ApartmentComplex`.
- `bozzuto.discover(get) -> list[dict]`: sitemap, then two pages per building. A building page that fails is skipped.
- `camden.building_urls(sitemap_xml) -> list[str]`: addresses matching `/apartments/<city>-(dc|md|va)/<slug>/available-apartments` from `https://www.camdenliving.com/sitemap/available-apartment-pages.xml`.
- `camden.parse(url, html) -> dict | None`: `{"id": "camden-<slug>", "manager": "Camden", "name", "url" (without `/available-apartments`), "platform": "camden", "feed": url, "address": {"full": community.address}, "lat": None, "lon": None}`.
- `camden.discover(get) -> list[dict]`.
- `discover.DISCOVERERS = {"bozzuto": bozzuto.discover, "camden": camden.discover}`.
- `geo.locate(get, *, lat=None, lon=None, address=None) -> dict | None`: Census geocoder (`https://geocoding.geo.census.gov/geocoder/geographies/coordinates` with `x`, `y`, or `/onelineaddress` with `address`; `benchmark=Public_AR_Current`, `vintage=Current_Current`, `format=json`). Returns `{"lat", "lon", "state": "DC", "county": "11001", "tract": "11001001402"}` or `None` when there is no match.
- `geo.neighborhood(get, lat, lon) -> str | None`: Nominatim reverse lookup (`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&lat=..&lon=..`); first of `neighbourhood`, `suburb`, `quarter`, `city_district`, `town`, `city` in its `address`.
- `discovery.merge(previous: list[dict], found: dict[str, list[dict] | None], day: str) -> list[dict]`, keyed by manager name. A manager whose value is `None` (sitemap failed) keeps all its previous buildings unchanged. For a manager that succeeded: found buildings keep their previous `first_seen`, `feed_api` and location fields and get `missed = 0`; previous buildings not found get `missed + 1` and are dropped once `missed` reaches 3 (`MISS_LIMIT = 3`). New buildings get `first_seen = day`.
- `discovery.in_region(building, counties) -> bool`.
- `discover.py`: for each manager run its discoverer (exception → `None`), `merge` with `data/buildings.json`, then for each building without a `tract` call `geo.locate` and `geo.neighborhood` (throttled), and write `data/buildings.json` holding all located buildings with `"in_region": bool`. Flags: `--only <manager>`, `--limit <n>` (per manager, for testing). Prints a line per manager: found, in region, unreadable.

- [ ] **Step 1:** Capture fixtures from the live sites and services (one building each; trim the sitemaps to about ten entries including one Baltimore-area and one out-of-state address).
- [ ] **Step 2: Failing tests:**

```python
def test_bozzuto_urls_only_building_pages(self):   # /reviews and /floor-plans paths and non-dc/md/va states excluded
def test_bozzuto_parse_reads_location_and_feed(self):
    b = bozzuto.parse(URL, PAGE, FLOORPLANS)
    self.assertEqual((b["id"], b["platform"], b["address"]["zip"], b["feed"]),
                     ("bozzuto-5333-connecticut", "sightmap", "20015", "https://sightmap.com/embed/8ywkoe19vlx"))
    self.assertAlmostEqual(b["lat"], 38.960622, places=4)
def test_bozzuto_without_embed_is_link(self): ...
def test_camden_urls_region_states_only(self): ...
def test_camden_parse_reads_name_and_address(self): ...
def test_locate_by_coordinates(self):              # fixture -> county "11001", 11-digit tract
def test_locate_by_address_returns_coordinates(self): ...
def test_locate_no_match_is_none(self): ...
def test_neighborhood_prefers_neighbourhood_then_suburb(self): ...
def test_merge_keeps_buildings_when_manager_failed(self): ...
def test_merge_drops_after_three_misses(self): ...
def test_merge_keeps_first_seen_and_location(self): ...
def test_in_region(self): ...
```

- [ ] **Step 3–5:** Run (fail), implement, run (pass). Commit `Automatic building discovery`.

### Task 6: The build

**Files:** Create `aptrack/output.py`, `build.py`, `site/index.html`, `tests/test_build.py`.

**Interfaces — Consumes:** `READERS`, `ReadError`, `history.*`, `fetch.get`, `fetch.Throttle`, `fetch.RateLimited`.

**Produces:**
- `output.write_site(buildings: list[dict], results: dict[str, dict], state: dict, out_dir: str, now: str) -> None`. Writes `index.json` `{"updated": now, "counties": {fips: {"buildings", "units"}}, "buildings": [...]}` where each building carries its discovery fields plus `"units"` (count), `"fees"`, `"amenities"`, `"stale"` (last read failed) and `"read"` (day of last good read); and `units-<fips>.json` `{"units": [...]}` where each unit is the common format plus `"first"` and `"history"` (its points). Stale buildings' units come from the previous `units-<fips>.json`.
- `build.run(buildings, state, get, day, *, workers=4, delay=1.0) -> dict[str, dict]`: reads every in-region building whose platform has a reader; buildings are grouped by feed host, one host per worker, in order, throttled. Success → `history.record`; `ReadError` or any fetch error → `history.record_failure`. A host that raises `RateLimited` is abandoned for this pass and its remaining buildings are retried once after all other hosts finish, after a 60 s wait (`sleep` injectable); still-limited ones count as failures. Returns results by building id (successful reads only). Caches `feed_api` on the building dict.
- `build.py` CLI: loads `managers.json`, `data/buildings.json`, `data/state.json` (missing → `new_state()`); runs; `prune`; if not `safe_to_save(before, after)` prints why and exits 2 without writing; otherwise writes `data/state.json`, `data/buildings.json` (for cached `feed_api`) and the site files. Flags: `--only <building id>`, `--limit <n>`, `--probe` (read one SightMap and one Camden building, print unit counts, write nothing, exit 1 if either fails). Prints totals: buildings read, failed, units listed, new, gone, price changes.
- `site/index.html`: loads `data/index.json` and shows the update time and a table of counties with building and unit counts.

- [ ] **Step 1: Failing tests** (fake `get` serving fixtures by address):

```python
def test_run_records_success_and_failure(self):       # one good building, one whose get raises -> ok/failed set, units recorded for the good one
def test_rate_limited_host_is_retried_after_others(self): ...
def test_failed_building_keeps_previous_units_in_output(self): ...
def test_write_site_splits_units_by_county(self): ...
def test_out_of_region_and_link_buildings_are_not_read(self): ...
```

- [ ] **Step 2–4:** Run (fail), implement, run (pass). Commit `Build: read units, update history, write site data`.

### Task 7: First live run

- [ ] **Step 1:** `py discover.py --limit 5`; check `data/buildings.json` has located buildings with tracts and neighborhoods. Fix what the live sites reveal (add a regression test for each fix).
- [ ] **Step 2:** `py discover.py` (full).
- [ ] **Step 3:** `py build.py`; expect non-zero units for most buildings. Investigate every failing building; fix or record why.
- [ ] **Step 4:** Run `py build.py` a second time; expect "0 new, 0 gone" or near it, and no duplicate points.
- [ ] **Step 5:** `py -m http.server 8000 -d site`; open the status page and check the counts. Commit fixes.

### Task 8: Scheduled runs

**Files:** Create `.github/workflows/probe.yml`, `.github/workflows/update.yml`, `.github/workflows/discover.yml`, `README.md`.

- `probe.yml`: manual trigger only; runs `python3 build.py --probe` after fetching `buildings.json` from the `data` branch (or running `python3 discover.py --limit 2` when the branch does not exist).
- `update.yml`: cron `20 11 * * *` and `20 23 * * *`, manual trigger, and pushes to `main` touching `site/**`, `aptrack/**`, `build.py`, `managers.json`. Steps: checkout; fetch the `data` branch into `data/` and `site/data/` (first run: discover); `python3 build.py`; replace the `data` branch with one fresh commit holding `buildings.json`, `state.json` and `site-data/`; on the first day of a month also push the same commit to `data-YYYY-MM`; upload `site/` and deploy Pages. A push that only touches `site/**` skips the build. Concurrency group `tracking`, never cancelled.
- `discover.yml`: cron `40 9 * * 1` and manual; runs `python3 discover.py` then saves the `data` branch the same way; same concurrency group.
- `README.md`: what the project is, the file list, how to run locally, how the data branch works.

- [ ] **Step 1:** Write the three workflows and the README.
- [ ] **Step 2:** Validate what can be validated locally: each workflow file parses as YAML-shaped text with the expected job names (no GitHub repository exists yet, so the workflows are untested until the owner creates one and runs `probe`).
- [ ] **Step 3:** Commit `Scheduled runs and README`.
