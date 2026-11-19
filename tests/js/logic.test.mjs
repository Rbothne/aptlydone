import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_FILTERS, ago, compareUnits, groupBuildings, money, perSqft, shortDate, sparkline, tagLabel, tagReason,
  unitMatches,
} from "../../site/js/logic.js";

const building = (more = {}) => ({
  id: "b1", name: "The Example", manager: "Bozzuto", neighborhood: "Chevy Chase", county: "11001",
  address: { street: "5333 Connecticut Ave NW", city: "Washington", state: "DC", zip: "20015" },
  laundry: null, parking_from: null, pets: null, senior: false, ...more,
});
const unit = (more = {}) => ({
  id: "b1:101", building: "b1", unit: "101", beds: 1, baths: 1, sqft: 800, floor: 3, rent: 2400, true: 2500,
  available: "2026-12-01", first: "2026-11-18", restricted: null, own: null, local: null, tag: null,
  history: [["2026-11-18", 2400, null, 12, 100]], ...more,
});
const f = (more = {}) => ({ ...DEFAULT_FILTERS, ...more });

test("a plain unit matches the default filters", () => {
  assert.equal(unitMatches(unit(), building(), f()), true);
});

test("beds filter: chosen counts only, and 3 means three or more", () => {
  assert.equal(unitMatches(unit({ beds: 1 }), building(), f({ beds: [0, 2] })), false);
  assert.equal(unitMatches(unit({ beds: 0 }), building(), f({ beds: [0, 2] })), true);
  assert.equal(unitMatches(unit({ beds: 4 }), building(), f({ beds: [3] })), true);
  assert.equal(unitMatches(unit({ beds: 2 }), building(), f({ beds: [3] })), false);
});

test("minimum size", () => {
  assert.equal(unitMatches(unit({ sqft: 699 }), building(), f({ minSqft: 700 })), false);
  assert.equal(unitMatches(unit({ sqft: 700 }), building(), f({ minSqft: 700 })), true);
  assert.equal(unitMatches(unit({ sqft: null }), building(), f({ minSqft: 700 })), false);
});

test("maximum monthly uses true cost, or rent when true cost is unknown", () => {
  assert.equal(unitMatches(unit({ rent: 2400, true: 2600 }), building(), f({ maxCost: 2500 })), false);
  assert.equal(unitMatches(unit({ rent: 2400, true: 2500 }), building(), f({ maxCost: 2500 })), true);
  assert.equal(unitMatches(unit({ rent: 2400, true: null }), building(), f({ maxCost: 2500 })), true);
  assert.equal(unitMatches(unit({ rent: 2600, true: null }), building(), f({ maxCost: 2500 })), false);
});

test("move in by keeps units available on or before the date", () => {
  assert.equal(unitMatches(unit({ available: "2026-12-01" }), building(), f({ moveBy: "2026-12-01" })), true);
  assert.equal(unitMatches(unit({ available: "2026-12-02" }), building(), f({ moveBy: "2026-12-01" })), false);
  assert.equal(unitMatches(unit({ available: null }), building(), f({ moveBy: "2026-12-01" })), false);
});

test("floor range and ground floor", () => {
  assert.equal(unitMatches(unit({ floor: 3 }), building(), f({ floorMin: 4 })), false);
  assert.equal(unitMatches(unit({ floor: 3 }), building(), f({ floorMin: 2, floorMax: 3 })), true);
  assert.equal(unitMatches(unit({ floor: 9 }), building(), f({ floorMax: 8 })), false);
  assert.equal(unitMatches(unit({ floor: null }), building(), f({ floorMin: 2 })), false);
  assert.equal(unitMatches(unit({ floor: 1 }), building(), f({ ground: true })), true);
  assert.equal(unitMatches(unit({ floor: 0 }), building(), f({ ground: true })), true);
  assert.equal(unitMatches(unit({ floor: 2 }), building(), f({ ground: true })), false);
  assert.equal(unitMatches(unit({ floor: null }), building(), f({ ground: true })), false);
});

test("building facts: parking and pets need a known yes; there is no laundry filter", () => {
  assert.equal("laundry" in DEFAULT_FILTERS, false);
  assert.equal(unitMatches(unit(), building({ parking_from: null }), f({ parking: true })), false);
  assert.equal(unitMatches(unit(), building({ parking_from: 225 }), f({ parking: true })), true);
  assert.equal(unitMatches(unit(), building({ pets: null }), f({ pets: true })), false);
  assert.equal(unitMatches(unit(), building({ pets: true }), f({ pets: true })), true);
});

test("all three deal tags chosen is the old tagged-only", () => {
  const all = ["absolute", "building", "local"];
  assert.equal(unitMatches(unit({ tag: null }), building(), f({ deals: all })), false);
  assert.equal(unitMatches(unit({ tag: "local" }), building(), f({ deals: all })), true);
});

test("income-restricted units and senior housing are hidden unless switched on", () => {
  assert.equal(unitMatches(unit({ restricted: true }), building(), f()), false);
  assert.equal(unitMatches(unit({ restricted: true }), building(), f({ showRestricted: true })), true);
  assert.equal(unitMatches(unit({ restricted: false }), building(), f()), true);
  assert.equal(unitMatches(unit(), building({ senior: true }), f()), false);
  assert.equal(unitMatches(unit(), building({ senior: true }), f({ showRestricted: true })), true);
});

test("county filter takes several counties; none chosen means all", () => {
  assert.deepEqual(DEFAULT_FILTERS.counties, []);
  assert.equal(unitMatches(unit(), building({ county: "51013" }), f({ counties: ["11001"] })), false);
  assert.equal(unitMatches(unit(), building({ county: "11001" }), f({ counties: ["11001", "51013"] })), true);
  assert.equal(unitMatches(unit(), building({ county: "51013" }), f({ counties: ["11001", "51013"] })), true);
  assert.equal(unitMatches(unit(), building({ county: "24031" }), f()), true);
});

test("counties are grouped by state, with a label for what is chosen", async () => {
  const { countyGroups, countiesLabel } = await import("../../site/js/logic.js");
  const names = { "11001": "Washington, DC", "51013": "Arlington", "51510": "Alexandria", "24031": "Montgomery" };
  assert.deepEqual(countyGroups(["24031", "51510", "11001", "51013"], names), [
    { state: "DC", counties: [{ fips: "11001", name: "Washington, DC" }] },
    { state: "Virginia", counties: [{ fips: "51510", name: "Alexandria" }, { fips: "51013", name: "Arlington" }] },
    { state: "Maryland", counties: [{ fips: "24031", name: "Montgomery" }] },
  ]);
  assert.equal(countiesLabel([], names), "All areas");
  assert.equal(countiesLabel(["51013"], names), "Arlington");
  assert.equal(countiesLabel(["51013", "51510"], names), "Arlington + 1 more");
});

test("search matches name, neighborhood, manager, city and ZIP", () => {
  for (const q of ["example", "CHEVY", "bozzuto", "washington", "20015", "  chevy chase "]) {
    assert.equal(unitMatches(unit(), building(), f({ q })), true, q);
  }
  assert.equal(unitMatches(unit(), building(), f({ q: "rosslyn" })), false);
});

test("top picks: tag first, then how far under the building, then cost per sqft", () => {
  const units = [
    unit({ id: "plain-cheap", true: 1600 }),
    unit({ id: "local", tag: "local", local: { pct: -22 } }),
    unit({ id: "absolute", tag: "absolute", own: { pct: -11 } }),
    unit({ id: "building-18", tag: "building", own: { pct: -18 } }),
    unit({ id: "building-25", tag: "building", own: { pct: -25 } }),
    unit({ id: "plain-under", own: { pct: -6 } }),
  ];
  assert.deepEqual(units.sort(compareUnits("picks")).map((u) => u.id),
    ["absolute", "building-25", "building-18", "local", "plain-under", "plain-cheap"]);
});

test("cost sort uses true cost, falls back to rent, and puts unknowns last", () => {
  const units = [unit({ id: "c", true: 2600 }), unit({ id: "none", true: null, rent: null }),
    unit({ id: "a", true: 2100 }), unit({ id: "b", true: null, rent: 2300 })];
  assert.deepEqual(units.sort(compareUnits("cost")).map((u) => u.id), ["a", "b", "c", "none"]);
});

test("other sorts put missing values last", () => {
  const by = (sort, units) => units.sort(compareUnits(sort)).map((u) => u.id);
  assert.deepEqual(by("ppsf", [unit({ id: "x", sqft: null }), unit({ id: "b", true: 3000 }), unit({ id: "a", true: 2000 })]), ["a", "b", "x"]);
  assert.deepEqual(by("own", [unit({ id: "x" }), unit({ id: "b", own: { pct: -3 } }), unit({ id: "a", own: { pct: -9 } })]), ["a", "b", "x"]);
  assert.deepEqual(by("local", [unit({ id: "x" }), unit({ id: "b", local: { pct: 4 } }), unit({ id: "a", local: { pct: -9 } })]), ["a", "b", "x"]);
  assert.deepEqual(by("newest", [unit({ id: "old", first: "2026-11-01" }), unit({ id: "new", first: "2026-11-18" })]), ["new", "old"]);
  assert.deepEqual(by("size", [unit({ id: "x", sqft: null }), unit({ id: "s", sqft: 600 }), unit({ id: "l", sqft: 1200 })]), ["l", "s", "x"]);
});

test("buildings are grouped with their best units and ordered by their best unit", () => {
  const index = [building({ id: "A" }), building({ id: "B" }), building({ id: "C" })];
  const units = {
    A: [1, 2, 3, 4, 5, 6, 7].map((n) => unit({ id: `A:${n}`, building: "A", true: 2000 + n * 100 })),
    B: [unit({ id: "B:1", building: "B", true: 1500 }), unit({ id: "B:2", building: "B", true: 4000, beds: 2 })],
    C: [unit({ id: "C:1", building: "C", beds: 2 })],
  };
  const groups = groupBuildings(index, units, f({ beds: [1], sort: "cost" }));
  assert.deepEqual(groups.map((g) => g.building.id), ["B", "A"]);            // C has no one-bedroom: hidden
  assert.equal(groups[0].units.length, 1);
  assert.equal(groups[1].units.length, 7);
  assert.deepEqual(groups[1].best.map((u) => u.id), ["A:1", "A:2", "A:3", "A:4", "A:5"]);
});

test("a building with no units in the data is left out", () => {
  assert.deepEqual(groupBuildings([building({ id: "A" })], {}, f()), []);
});

test("tag wording", () => {
  assert.equal(tagLabel("absolute"), "Absolute steal");
  assert.equal(tagLabel("building"), "Building steal");
  assert.equal(tagLabel("local"), "Local value");
  assert.equal(tagLabel(null), "");
  const u = unit({ own: { pct: -15.2, n: 6 }, local: { pct: -21, n: 14, buildings: 4, miles: 1 } });
  assert.equal(tagReason(u), "15% under 6 similar units in this building · 21% under 14 units in 4 buildings within 1 mile");
  assert.equal(tagReason(unit({ own: { pct: 4.4, n: 3 } })), "4% over 3 similar units in this building");
  assert.equal(tagReason(unit({ local: { pct: -8, n: 9, buildings: 3, miles: 2 } })), "8% under 9 units in 3 buildings within 2 miles");
  assert.equal(tagReason(unit({ own: { pct: 0, n: 5 } })), "in line with 5 similar units in this building");
  assert.equal(tagReason(unit()), "");
});

test("formatting", () => {
  assert.equal(money(2700), "$2,700");
  assert.equal(money(2699.6), "$2,700");
  assert.equal(money(null), "—");
  assert.equal(perSqft(unit({ true: 2500, sqft: 800 })), "$3.13/sqft");
  assert.equal(perSqft(unit({ true: null, rent: 2400, sqft: 800 })), "$3.00/sqft");
  assert.equal(perSqft(unit({ sqft: null })), "");
  assert.equal(shortDate("2026-11-29"), "Nov 29");
  assert.equal(shortDate(null), "");
});

test("how long ago", () => {
  const now = new Date("2026-11-18T20:00:00Z");
  assert.equal(ago("2026-11-18T19:58Z", now), "just now");
  assert.equal(ago("2026-11-18T19:15Z", now), "45 minutes ago");
  assert.equal(ago("2026-11-18T18:05Z", now), "2 hours ago");
  assert.equal(ago("2026-11-17T19:00Z", now), "1 day ago");
  assert.equal(ago("2026-11-15T10:00Z", now), "3 days ago");
});

test("sparkline needs two points and spans the box", () => {
  assert.equal(sparkline([["2026-11-18", 2400, null, 12, 0]], 60, 16), null);
  const path = sparkline([["2026-11-18", 2400, null, 12, 0], ["2026-11-20", 2200, null, 12, 0], ["2026-11-22", 2300, null, 12, 0]], 60, 16);
  assert.match(path, /^M0[ ,]/);
  assert.equal(path.split("L").length, 3);
  assert.ok(path.includes("60"));
});

test("availability wording", async () => {
  const { availability } = await import("../../site/js/logic.js");
  assert.equal(availability("2026-11-29", "2026-11-18"), "Available Nov 29");
  assert.equal(availability("2026-11-18", "2026-11-18"), "Available now");
  assert.equal(availability("2026-11-01", "2026-11-18"), "Available now");
  assert.equal(availability(null, "2026-11-18"), "");
});

test("violent crime limit needs a known count at or under it", async () => {
  const { unitMatches: matches } = await import("../../site/js/logic.js");
  assert.equal(matches(unit(), building({ crime: { violent: 3, property: 40 } }), f({ maxViolent: 3 })), true);
  assert.equal(matches(unit(), building({ crime: { violent: 4, property: 40 } }), f({ maxViolent: 3 })), false);
  assert.equal(matches(unit(), building({ crime: null }), f({ maxViolent: 3 })), false);
  assert.equal(matches(unit(), building({ crime: null }), f()), true);
  assert.equal(DEFAULT_FILTERS.maxViolent, null);
});

test("crime wording says when a county publishes nothing", async () => {
  const { crimeText } = await import("../../site/js/logic.js");
  assert.deepEqual(crimeText(building({ crime: { violent: 3, property: 41 } }), ["11001"]),
    { text: "Within ½ mile, past 12 months: 3 violent · 41 property crimes", known: true });
  assert.deepEqual(crimeText(building({ crime: null, county: "51013" }), ["11001"]),
    { text: "No crime data for this county", known: false });
  assert.deepEqual(crimeText(building({ crime: null, county: "11001" }), ["11001"]),
    { text: "Crime nearby not counted yet", known: false });
});

test("area facts read as sentences, with race only when asked for", async () => {
  const { areaFacts } = await import("../../site/js/logic.js");
  const tract = { pop: 3521, income: 176111, rent: 2409, age: 50.3, degree: 89, renters: 38,
    race: { white: 64, black: 9, asian: 6, hispanic: 9, other: 12 } };
  const trend = { latest: 2541, month: "2025-11", year_change: 5.0 };
  assert.deepEqual(areaFacts(tract, trend, "20015", true), [
    "Typical rent in ZIP 20015: $2,541, up 5% in a year",
    "Median household income $176,111",
    "Median rent paid $2,409",
    "Median age 50",
    "89% of adults have a degree",
    "38% of homes are rented",
    "64% white · 9% Black · 6% Asian · 9% Hispanic · 12% other",
  ]);
  assert.equal(areaFacts(tract, trend, "20015", false).some((line) => line.includes("white")), false);
  assert.deepEqual(areaFacts(null, { latest: 2000, month: "2025-11", year_change: -1.2 }, "22201", true),
    ["Typical rent in ZIP 22201: $2,000, down 1.2% in a year"]);
  assert.deepEqual(areaFacts({ pop: 10, income: null, rent: null, age: null, degree: null, renters: null, race: null }, null, null, true), []);
  assert.deepEqual(areaFacts(null, { latest: 2000, month: "2025-11", year_change: null }, "22201", true), ["Typical rent in ZIP 22201: $2,000"]);
});

test("map points: one per located building, with its best tag, unit count and best unit", async () => {
  const { mapPoints } = await import("../../site/js/logic.js");
  const index = [building({ id: "A", lat: 38.9, lon: -77.0 }), building({ id: "B", lat: 38.95, lon: -77.05 }),
    building({ id: "C", lat: null, lon: null })];
  const units = {
    A: [unit({ id: "A:1", building: "A", tag: "local", true: 2000 }), unit({ id: "A:2", building: "A", tag: "building", own: { pct: -16 }, true: 2600 }),
      unit({ id: "A:3", building: "A", true: 1800 })],
    B: [unit({ id: "B:1", building: "B", true: 2100 })],
    C: [unit({ id: "C:1", building: "C", tag: "absolute" })],
  };
  const points = mapPoints(groupBuildings(index, units, f()));
  assert.deepEqual(points.map((p) => [p.id, p.tag, p.count, p.best.id]), [["A", "building", 3, "A:2"], ["B", null, 1, "B:1"]]);
  assert.deepEqual([points[0].lat, points[0].lon], [38.9, -77.0]);
});

test("minimum rating needs a known rating at or above it", () => {
  assert.equal(DEFAULT_FILTERS.minRating, null);
  assert.equal(unitMatches(unit(), building({ rating: 4.5 }), f({ minRating: 4.5 })), true);
  assert.equal(unitMatches(unit(), building({ rating: 4.4 }), f({ minRating: 4.5 })), false);
  assert.equal(unitMatches(unit(), building({ rating: null }), f({ minRating: 4.5 })), false);
  assert.equal(unitMatches(unit(), building({ rating: null }), f()), true);
});

test("managed-by filter", () => {
  assert.equal(DEFAULT_FILTERS.manager, "");
  assert.equal(unitMatches(unit(), building({ manager: "Bozzuto" }), f({ manager: "Bozzuto" })), true);
  assert.equal(unitMatches(unit(), building({ manager: "Camden" }), f({ manager: "Bozzuto" })), false);
});

test("no-go ZIP codes hide their buildings; a building with no ZIP is never hidden by it", () => {
  assert.equal(unitMatches(unit(), building({ zip: "20002" }), f({ nogo: ["20002", "20020"] })), false);
  assert.equal(unitMatches(unit(), building({ zip: "20015" }), f({ nogo: ["20002"] })), true);
  assert.equal(unitMatches(unit(), building({ zip: null }), f({ nogo: ["20002"] })), true);
  assert.equal(unitMatches(unit(), building({ zip: "20002" }), f()), true);
  assert.equal("nogo" in DEFAULT_FILTERS, false);          // it is a standing choice, not a filter that Reset clears
});

test("a unit marked for checking is not a steal: not in tagged-only, not a top pick, and labelled", async () => {
  const { isSteal, tagLabel: label, compareUnits: compare, mapPoints: points } = await import("../../site/js/logic.js");
  assert.equal(label("check"), "Check price");
  assert.equal(isSteal("check"), false);
  assert.equal(isSteal("local"), true);
  assert.equal(isSteal(null), false);
  assert.equal(unitMatches(unit({ tag: "check" }), building(), f({ deals: ["absolute", "building", "local"] })), false);
  const units = [unit({ id: "check", tag: "check", own: { pct: -45 } }), unit({ id: "local", tag: "local" }), unit({ id: "plain", own: { pct: -5 } })];
  assert.deepEqual(units.sort(compare("picks")).map((u) => u.id), ["local", "plain", "check"]);
  const groups = groupBuildings([building({ id: "A", lat: 1, lon: 1 })], { A: [unit({ id: "A:1", building: "A", tag: "check" })] }, f());
  assert.equal(points(groups)[0].tag, null);
});

test("crime counts from an older year say which year", async () => {
  const { crimeText } = await import("../../site/js/logic.js");
  const old = building({ county: "51013", crime: { violent: 2, property: 30, period: ["2021-06-28", "2022-06-28"] } });
  assert.deepEqual(crimeText(old, ["51013"]),
    { text: "Within ½ mile, Jun 2021 to Jun 2022 (the last year published here): 2 violent · 30 property crimes", known: true });
});

test("follow criteria: taken from the filters, put into words, and turned back into filters", async () => {
  const { criteriaFrom, criteriaLabel, criteriaFilters } = await import("../../site/js/logic.js");
  const criteria = criteriaFrom(f({ beds: [1, 2], minSqft: 700, maxCost: 2600, q: "chevy", deals: ["local"], counties: ["11001"] }));
  assert.deepEqual(criteria, { beds: [1, 2], minSqft: 700, maxCost: 2600 });
  assert.equal(criteriaLabel(criteria), "1 or 2 bed · 700+ sqft · up to $2,600");
  assert.equal(criteriaLabel({ beds: [0], minSqft: null, maxCost: null }), "Studio");
  assert.equal(criteriaLabel({ beds: [3], minSqft: null, maxCost: 4000 }), "3+ bed · up to $4,000");
  assert.equal(criteriaLabel({ beds: [], minSqft: null, maxCost: null }), "any unit");
  assert.equal(criteriaLabel(undefined), "any unit");
  const back = criteriaFilters(criteria);
  assert.deepEqual([back.beds, back.minSqft, back.maxCost, back.q, back.deals, back.counties], [[1, 2], 700, 2600, "", [], []]);
  assert.equal(unitMatches(unit({ beds: 1, sqft: 800, true: 2500 }), building(), back), true);
  assert.equal(unitMatches(unit({ beds: 1, sqft: 650, true: 2500 }), building(), back), false);
});

test("parking filter accepts a building that says it has parking without a price", () => {
  assert.equal(unitMatches(unit(), building({ parking_from: null, parking: true }), f({ parking: true })), true);
  assert.equal(unitMatches(unit(), building({ parking_from: null, parking: null }), f({ parking: true })), false);
});

test("price standing: a plain label for where a building sits among its neighbours", async () => {
  const { standing } = await import("../../site/js/logic.js");
  assert.equal(standing({ pct: 90, n: 20 }), "High-end for its area");
  assert.equal(standing({ pct: 67, n: 9 }), "High-end for its area");
  assert.equal(standing({ pct: 50, n: 9 }), "Mid-priced for its area");
  assert.equal(standing({ pct: 33, n: 9 }), "Lower-priced for its area");
  assert.equal(standing(null), "");
});

test("high-end filter needs a known standing in the top third", () => {
  assert.equal(DEFAULT_FILTERS.highEnd, false);
  assert.equal(unitMatches(unit(), building({ rank: { pct: 80, n: 9 } }), f({ highEnd: true })), true);
  assert.equal(unitMatches(unit(), building({ rank: { pct: 60, n: 9 } }), f({ highEnd: true })), false);
  assert.equal(unitMatches(unit(), building({ rank: null }), f({ highEnd: true })), false);
});

test("income rule of thumb: rent should be no more than a third of monthly income", async () => {
  const { incomeNeeded, affordable } = await import("../../site/js/logic.js");
  assert.equal(incomeNeeded(unit({ rent: 2500 })), 90000);
  assert.equal(affordable(unit({ rent: 2500 }), 90000), true);
  assert.equal(affordable(unit({ rent: 2500 }), 89999), false);
  assert.equal(affordable(unit({ rent: 2500 }), null), null);
  assert.equal(affordable(unit({ rent: null }), 90000), null);
});

test("a floor-plan-level entry is titled by its plan and says how many are available", async () => {
  const { unitTitle, availableNote } = await import("../../site/js/logic.js");
  assert.equal(unitTitle(unit({ unit: "215", count: null })), "#215");
  assert.equal(unitTitle(unit({ unit: "Studio A", plan: "Studio A", count: 3 })), "Studio A");
  assert.equal(availableNote(unit({ count: 3 })), "3 available");
  assert.equal(availableNote(unit({ count: 1 })), "1 available");
  assert.equal(availableNote(unit({ count: null })), "");
});

test("affordable-housing note for a building", async () => {
  const { affordableNote } = await import("../../site/js/logic.js");
  assert.equal(affordableNote({ name: "P", affordable: 40, total: 50 }), "City records: 40 of 50 units here are income-restricted");
  assert.equal(affordableNote({ name: "P", affordable: 12, total: null }), "City records: 12 income-restricted units here");
  assert.equal(affordableNote(null), "");
});

const nearby = { park: [3, 0.1], dog_park: [1, 0.4], community: [0, 0.9], library: [1, 0.3], grocery: [2, 0.2], metro: [0, 0.8], food: [23, 0], gym: [0, null], pharmacy: [1, 0.5] };

test("nearby filters need a known distance within reach", () => {
  for (const key of ["nearMetro", "nearGrocery", "nearPark", "dogFriendly"]) assert.equal(DEFAULT_FILTERS[key], false);
  assert.equal(DEFAULT_FILTERS.minWalk, null);
  assert.equal(unitMatches(unit(), building({ near: nearby }), f({ nearMetro: true })), false);            // 0.8 mi is not "near"
  assert.equal(unitMatches(unit(), building({ near: { ...nearby, metro: [1, 0.5] } }), f({ nearMetro: true })), true);
  assert.equal(unitMatches(unit(), building({ near: nearby }), f({ nearGrocery: true })), true);
  assert.equal(unitMatches(unit(), building({ near: nearby }), f({ nearPark: true })), true);
  assert.equal(unitMatches(unit(), building({ near: { ...nearby, park: [1, 0.4] } }), f({ nearPark: true })), false);   // a park needs to be within a quarter mile
  assert.equal(unitMatches(unit(), building({ near: null }), f({ nearGrocery: true })), false);
  assert.equal(unitMatches(unit(), building({ dog: { score: 3, reasons: [] } }), f({ dogFriendly: true })), true);
  assert.equal(unitMatches(unit(), building({ dog: { score: 2, reasons: [] } }), f({ dogFriendly: true })), false);
  assert.equal(unitMatches(unit(), building({ dog: null }), f({ dogFriendly: true })), false);
  assert.equal(unitMatches(unit(), building({ walk: { score: 16.8 } }), f({ minWalk: 15 })), true);
  assert.equal(unitMatches(unit(), building({ walk: { score: 12 } }), f({ minWalk: 15 })), false);
  assert.equal(unitMatches(unit(), building({ walk: null }), f({ minWalk: 15 })), false);
});

test("nearby tags: what is within reach, nearest first in a fixed order", async () => {
  const { nearbyTags, walkText, dogText } = await import("../../site/js/logic.js");
  assert.deepEqual(nearbyTags(nearby), ["Metro 0.8 mi", "Grocery 0.2 mi", "Park 0.1 mi (3 within ½ mi)", "Dog park 0.4 mi", "Library 0.3 mi",
    "23 places to eat within ½ mi", "Pharmacy 0.5 mi"]);
  assert.deepEqual(nearbyTags({ park: [1, 0], metro: [0, 1.4], food: [0, 1.2] }), ["Park next door"]);
  assert.deepEqual(nearbyTags(null), []);
  assert.equal(walkText({ score: 16.8, label: "Most walkable" }), "Walkability 16.8 of 20 (most walkable)");
  assert.equal(walkText(null), "");
  assert.equal(dogText({ score: 4, reasons: ["pets allowed", "dog park 0.3 mi"] }), "Dog-friendly 4 of 5");
  assert.equal(dogText(null), "");
});

test("most walkable sort", () => {
  const units = [unit({ id: "x" }), unit({ id: "low", walkScore: 9 }), unit({ id: "high", walkScore: 18 })];
  assert.deepEqual(units.sort(compareUnits("walk")).map((u) => u.id), ["high", "low", "x"]);
});

test("deal tags are a choice of any: a unit must carry one of the chosen tags", async () => {
  assert.deepEqual(DEFAULT_FILTERS.deals, []);
  assert.equal(unitMatches(unit({ tag: null }), building(), f({ deals: [] })), true);
  assert.equal(unitMatches(unit({ tag: "local" }), building(), f({ deals: ["absolute", "local"] })), true);
  assert.equal(unitMatches(unit({ tag: "building" }), building(), f({ deals: ["absolute", "local"] })), false);
  assert.equal(unitMatches(unit({ tag: null }), building(), f({ deals: ["absolute"] })), false);
  assert.equal(unitMatches(unit({ tag: "check" }), building(), f({ deals: ["absolute", "building", "local"] })), false);
});

test("filters saved before the tag drop-down still work: tagged-only means any deal tag", () => {
  const old = { ...f(), tagged: true };
  delete old.deals;
  assert.equal(unitMatches(unit({ tag: "building" }), building(), old), true);
  assert.equal(unitMatches(unit({ tag: null }), building(), old), false);
});

test("the tag drop-down: groups, what is chosen, and its label", async () => {
  const { TAG_GROUPS, chosenTags, tagsLabel, setTag } = await import("../../site/js/logic.js");
  assert.deepEqual(TAG_GROUPS.map((g) => [g.name, g.tags.map((t) => t.key)]), [
    ["Deals", ["absolute", "building", "local"]],
    ["Nearby", ["nearMetro", "nearGrocery", "nearPark", "dogFriendly"]],
    ["Building", ["ground", "parking", "pets", "highEnd"]],
  ]);
  assert.equal(tagsLabel(f()), "Any");
  assert.deepEqual(chosenTags(f()), []);
  let filters = setTag(f(), "nearMetro", true);
  assert.equal(filters.nearMetro, true);
  assert.equal(tagsLabel(filters), "Near Metro");
  filters = setTag(filters, "absolute", true);
  filters = setTag(filters, "local", true);
  assert.deepEqual(filters.deals, ["absolute", "local"]);
  assert.deepEqual(chosenTags(filters), ["absolute", "local", "nearMetro"]);
  assert.equal(tagsLabel(filters), "Absolute steal + 2 more");
  filters = setTag(filters, "absolute", false);
  filters = setTag(filters, "nearMetro", false);
  assert.deepEqual([filters.deals, filters.nearMetro, tagsLabel(filters)], [["local"], false, "Local value"]);
  assert.deepEqual(setTag(setTag(f(), "local", true), "local", true).deals, ["local"]);       // choosing twice is choosing once
  assert.equal(tagsLabel({ ...f(), tagged: true, deals: undefined }), "Absolute steal + 2 more");
});

test("a building whose latest read failed says so, since when, and why if known", async () => {
  const { staleText } = await import("../../site/js/logic.js");
  assert.equal(staleText({ stale: false }), "");
  assert.equal(staleText({ stale: true, read: "2026-11-19", why: "HTTP 403" }), "Latest read failed (HTTP 403); showing Nov 19");
  assert.equal(staleText({ stale: true, read: "2026-11-19", why: null }), "Latest read failed; showing Nov 19");
  assert.equal(staleText({ stale: true, read: null }), "Latest read failed; showing earlier data");
});
