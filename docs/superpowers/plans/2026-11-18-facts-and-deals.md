# Facts and Deals Implementation Plan (plan 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect the extra facts the sources already publish, compute each unit's true monthly cost, and tag units BUILDING STEAL, LOCAL VALUE or ABSOLUTE STEAL.

**Architecture:** Readers gain a few fields; a per-manager "facts" reader reads the building page daily; two pure modules (`costs.py`, `deals.py`) turn units and building facts into true monthly cost, comparisons and tags; `output.py` writes them into the files the page loads. Nothing here changes how history is recorded except one new dated series per building for its concession text.

**Tech Stack:** Python standard library only, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-18-apartment-tracker-design.md`, section 15 (which overrides sections 6, 7 and 10 where they differ).

## Global Constraints

- Standard library only. Nothing typed in by hand; an uncollectable fact is `None`.
- At most one request per second per site.
- A failed facts read never fails the unit read; the building keeps its previous facts.
- Thresholds are named constants in `deals.py`: `BUILDING_STEAL = 15`, `LOCAL_VALUE = 20`, `ABSOLUTE_OWN = 10`, `ABSOLUTE_LOCAL = 15`, `OWN_SIZE_BAND = 0.20`, `LOCAL_SIZE_BAND = 0.15`, `OWN_MIN = 3`, `LOCAL_MIN_UNITS = 5`, `LOCAL_MIN_BUILDINGS = 3`, `LOCAL_MILES = (1, 2)`, `ROOM_SQFT = 300`, `RANK_MILES = 2`.
- Tests: `py -m unittest discover -s tests -t .`

## Review Focus

1. A concession written in words ("two months free", "half month free", "6 weeks free"): expected to parse like its digit form. Test in Task 3.
2. A concession longer than the lease, or a unit with no lease term: expected to yield no net figure rather than a negative or absurd one. Test in Task 3.
3. A unit whose only comparable units are income-restricted, senior or single rooms: expected to get no comparison. Test in Task 4.
4. A building page that loads but lacks the facts block (site redesign): expected to return `None` facts and keep yesterday's. Test in Task 2.
5. Two buildings at the same coordinates (phases of one development): expected to count as separate neighbors without dividing by zero. Test in Task 4.

---

### Task 1: More fields from the readers

**Files:** Modify `aptrack/units.py`, `aptrack/readers/sightmap.py`, `aptrack/readers/camden.py`, tests and the two reader fixtures.

**Produces:**
- `make_unit(..., restricted=None, plan_image=None)`: two new keys at the end of the common format. `restricted` is `True`, `False` or `None`.
- `units.looks_restricted(plan_name) -> bool`: true for names containing ADU, WDU, MPDU, IZ, "affordable", "workforce" or "income" as whole words (case-insensitive).
- SightMap: `restricted` = the unit's `affordable_housing_info.is_affordable_housing_unit` when present, or `True` when the plan name looks restricted; `plan_image` = the floor plan's `image_url`; each fee gains `"refundable": bool` (`is_refundable`).
- Camden: `plan_image` = the plan's `media.floorPlanImage`; `restricted` from the plan name only (`True` or `None`); the result gains `"facts": {"features": [plain text of data.metaDescription]}`.

- [ ] Tests first: `test_restricted_from_feed_flag`, `test_restricted_from_plan_name`, `test_plan_image`, `test_fee_refundable_flag`, `test_looks_restricted` (true: "2 Bed/2 Bath ADU-B9", "A1 WDU", "MPDU 1BR"; false: "A1", "Studio", "B4*", "Wizard"), Camden `test_plan_image`, `test_facts_features_text`. Run, fail, implement, pass, commit.

### Task 2: Building facts, read daily

**Files:** Create `aptrack/facts/__init__.py`, `aptrack/facts/bozzuto.py`, `aptrack/facts/laundry.py`, `tests/test_facts.py`, `tests/fixtures/bozzuto_page.html`. Modify `build.py`, `aptrack/history.py`, `aptrack/output.py`.

**Produces:**
- `facts.bozzuto.parse(page_html) -> dict | None`: `{"special": str | None (specialOfferText when hasSpecialOffer), "rating": float | None, "rating_count": int | None, "neighborhood": str | None, "coming_soon": bool, "features": [str]}` read from the page's embedded data; `None` when the block is missing.
- `facts.bozzuto.read(building, get) -> dict | None`: fetches `building["url"]`.
- `facts.FACTS = {"Bozzuto": bozzuto.read}` keyed by manager name.
- `facts.laundry.detect(texts: list[str]) -> "in_unit" | "shared" | None`: "in_unit" when any text mentions a washer or in-unit/in-home laundry; "shared" when it mentions only a laundry room/facility/on-site laundry; else `None`.
- `build.read_one`: after a successful unit read, a manager with a facts reader gets `result["facts"]`; a reader's own `facts` (Camden) is kept; any error there leaves `facts` as `None`. `RateLimited` from a facts read is treated as an error for that building only.
- `history.record_special(state, building_id, text, day)`: `state["buildings"][id]["specials"]` is a `[[day, text]]` series with the same change-only, same-day-overwrite rule as price points.
- `output`: each building entry gains `special`, `rating`, `rating_count`, `coming_soon`, `features`, `laundry`, and `neighborhood` prefers the manager's name over the map lookup. A building whose facts are `None` this run keeps the previous entry's values.

- [ ] Fixture from the live 5333 Connecticut page (keep the script blocks holding the facts and feature lists). Tests first: `test_parse_reads_offer_rating_neighborhood`, `test_parse_without_offer_has_no_special`, `test_parse_missing_block_is_none`, `test_features_listed`, laundry cases, `test_facts_failure_keeps_units`, `test_special_series_changes_only`, `test_previous_facts_kept_when_read_fails`. Run, fail, implement, pass, commit.

### Task 3: True monthly cost

**Files:** Create `aptrack/costs.py`, `tests/test_costs.py`.

**Produces:**
- `costs.free_months(text) -> float | None`: months of free rent a concession text promises: "N months free", "N weeks free" (weeks ÷ 4.345), with N as digits, a decimal, a fraction ("1/2") or a word (half, one … twelve); "up to N" counts as N; `None` when no pattern matches.
- `costs.one_time(fees) -> float`: sum of fees that are required, not refundable, charged once (`when == "additional"`), with a numeric amount, excluding types containing "deposit".
- `costs.parking_from(fees) -> float | None`: lowest monthly amount among fees whose type or label mentions parking (excluding motorcycle); `costs.pets_allowed(fees) -> bool | None`.
- `costs.true_monthly(unit, fees, special=None) -> float | None`: `rent × (lease − free) ÷ lease + (unit fees or 0) + one_time ÷ lease`, where `free = free_months(special)` (0 when there is none), rounded to whole dollars. `None` when `lease` is missing or `free ≥ lease`. Lease defaults to 12 only when the unit has none **and** there is no concession.
- `costs.apply(unit, fees, building_special) -> None`: sets `unit["true"]` using the unit's own special, and `unit["true_offer"]` using the building's special when the unit has none of its own and the text parses (else `None`).

- [ ] Tests first, including the Review Focus cases and: 2,400 rent, 12 months, "1 month free" → 2,200; plus fees 100 → 2,300; plus a required one-time 600 → 2,350. Run, fail, implement, pass, commit.

### Task 4: Comparisons, tags and the building rank

**Files:** Create `aptrack/deals.py`, `tests/test_deals.py`. Modify `aptrack/output.py`, `build.py`.

**Produces:**
- `deals.miles(a, b) -> float` between two `{"lat", "lon"}`.
- `deals.comparable(unit, building) -> bool`: has `true` and `sqft`, `sqft ≥ ROOM_SQFT`, not restricted, building not senior (`"senior" in name.lower()`).
- `deals.score(units, buildings) -> None`: mutates every unit, adding
  - `own`: `{"pct": float, "n": int}` or `None`: percent difference of its true cost per sqft from the median of comparable units in the same building (same beds, size within `OWN_SIZE_BAND`, excluding itself, at least `OWN_MIN`);
  - `local`: `{"pct", "n", "buildings", "miles"}` or `None`: the same against comparable units in other buildings within `LOCAL_MILES`, widening;
  - `tag`: `"absolute"`, `"building"`, `"local"` or `None`, by the thresholds, with absolute taking precedence.
  Units that are not comparable get `None` for all three.
- `deals.rank(units, buildings) -> None`: sets `building["rank"] = {"pct": int, "n": int}`: where the building's median one-bedroom true cost per sqft falls among buildings within `RANK_MILES` (100 = most expensive); `None` with fewer than three such buildings.
- `output.write_site` calls `costs.apply`, `deals.score` and `deals.rank` on the assembled units (fresh and carried-over) before saving, and each building entry gains `one_time`, `parking_from`, `pets`, `senior`, `rank`.
- `build.py` exits 1 after saving when more than 20% of the chosen buildings failed (`FAIL_SHARE = 0.2`).

- [ ] Tests first with small made-up sets: own-building percent and minimum count; self excluded; neighbor widening from one to two miles; needs three buildings; restricted, senior and room units neither scored nor used; same-coordinate buildings; each tag at its boundary (−15.0 tags, −14.9 does not); rank percentile; `test_too_many_failures_exits_nonzero`. Run, fail, implement, pass, commit.

### Task 5: Live run and push

- [ ] `py build.py`; check counts of each tag against the exploration (58 / 143 / 42 before exclusions and concessions), list the top ten of each tag and confirm none is restricted, senior or a single room.
- [ ] Commit, merge to `main`, push, and confirm the GitHub run succeeds.

## Not in this plan

- The 30-days-of-history condition on ABSOLUTE STEAL (needs history; add with the page plan or later).
- Camden amenity lists from the building home page.
- Per-lease-term price tables and review text.
