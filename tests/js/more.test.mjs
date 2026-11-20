import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CRIME_STOPS, DEFAULT_FILTERS, TAG_GROUPS, TRADEOFFS, compareUnits, crimeStopLabel, crimeText, dropText, noiseTags, relateCrime, setTag, tagsLabel,
  typicalOf, unitMatches, worksTags, worth, worthText,
} from "../../site/js/logic.js";

const building = (more = {}) => ({
  id: "b1", name: "The Example", manager: "Bozzuto", neighborhood: "Chevy Chase", county: "11001",
  address: { street: "5333 Connecticut Ave NW", city: "Washington", state: "DC", zip: "20015" },
  laundry: null, parking_from: null, pets: null, senior: false, ...more,
});
const unit = (more = {}) => ({
  id: "b1:101", building: "b1", unit: "101", beds: 1, baths: 1, sqft: 800, floor: 3, rent: 2400, true: 2500,
  available: "2026-12-01", first: "2026-11-18", restricted: null, own: null, local: null, tag: null, drop: null,
  outdoor: null, own_door: false, history: [["2026-11-18", 2400, null, 12, 100]], ...more,
});
const f = (more = {}) => ({ ...DEFAULT_FILTERS, ...more });
const DROP = { was: 2500, by: 100, pct: -4, day: "2026-11-15" };

// ---------- price drops ----------

test("price drop is a deal tag of its own, alongside whatever steal tag the unit has", () => {
  assert.deepEqual(TAG_GROUPS[0].tags.map((t) => t.key), ["absolute", "building", "local", "drop"]);
  assert.equal(unitMatches(unit({ drop: DROP }), building(), f({ deals: ["drop"] })), true);
  assert.equal(unitMatches(unit({ tag: "local" }), building(), f({ deals: ["drop"] })), false);
  assert.equal(unitMatches(unit({ tag: "local" }), building(), f({ deals: ["drop", "local"] })), true);
  assert.equal(unitMatches(unit({ drop: DROP }), building(), f({ deals: ["local"] })), false);
  assert.deepEqual(setTag(setTag(f(), "drop", true), "absolute", true).deals, ["absolute", "drop"]);
  assert.equal(tagsLabel(f({ deals: ["drop"] })), "Price drop");
});

test("filters saved as tagged-only still mean the three steal tags, not price drops", () => {
  const old = { ...f(), tagged: true };
  delete old.deals;
  assert.equal(unitMatches(unit({ drop: DROP }), building(), old), false);
  assert.equal(unitMatches(unit({ tag: "building" }), building(), old), true);
});

test("sorting by biggest price drop: largest percentage first, units without one last", () => {
  const units = [unit({ id: "none" }), unit({ id: "small", drop: { ...DROP, pct: -2.5 } }), unit({ id: "big", drop: { ...DROP, pct: -9 } })];
  assert.deepEqual(units.sort(compareUnits("drop")).map((u) => u.id), ["big", "small", "none"]);
});

test("a drop in words", () => {
  assert.equal(dropText(unit({ drop: DROP })), "Down $100 (4%) since Nov 15, from $2,500");
  assert.equal(dropText(unit()), "");
});

// ---------- crime against the typical building ----------

test("the typical building is the median of those with counts, and each building is measured against it", () => {
  const all = [building({ id: "a", crime: { violent: 10, property: 100 } }), building({ id: "b", crime: { violent: 20, property: 300 } }),
    building({ id: "c", crime: { violent: 50, property: 200 } }), building({ id: "d", crime: null })];
  const typical = relateCrime(all);
  assert.deepEqual(typical, { violent: 20, property: 200, buildings: 3 });
  assert.deepEqual(all.map((b) => b.crime && b.crime.x), [0.5, 1, 2.5, null]);
  assert.equal(relateCrime([building({ crime: null })]), null);
  const none = [building({ crime: { violent: 0, property: 0 } })];
  assert.equal(relateCrime(none), null);                                  // nothing to measure against
  assert.equal(none[0].crime.x, null);
});

test("the violent-crime limit is a multiple of the typical building's count", () => {
  assert.equal(DEFAULT_FILTERS.maxViolentX, null);
  assert.equal("maxViolent" in DEFAULT_FILTERS, false);
  const at = (x) => building({ crime: { violent: 1, property: 1, x } });
  assert.equal(unitMatches(unit(), at(0.5), f({ maxViolentX: 0.5 })), true);
  assert.equal(unitMatches(unit(), at(0.6), f({ maxViolentX: 0.5 })), false);
  assert.equal(unitMatches(unit(), building({ crime: null }), f({ maxViolentX: 2 })), false);      // unknown is not "low"
  assert.equal(unitMatches(unit(), building({ crime: null }), f()), true);
  assert.equal(unitMatches(unit(), at(9), { ...f(), maxViolent: 3 }), true);                         // the old fixed limit is forgotten
});

test("the slider's stops, in words that carry the real number", () => {
  assert.deepEqual(CRIME_STOPS, [0.25, 0.5, 0.75, 1, 1.5, 2, 3]);
  const typical = { violent: 20, property: 200, buildings: 3 };
  assert.equal(crimeStopLabel(0.5, typical), "half the typical or less (10 or fewer)");
  assert.equal(crimeStopLabel(1, typical), "the typical or less (20 or fewer)");
  assert.equal(crimeStopLabel(1.5, typical), "up to 1.5× the typical (30 or fewer)");
  assert.equal(crimeStopLabel(0.25, typical), "a quarter of the typical or less (5 or fewer)");
  assert.equal(crimeStopLabel(null, typical), "any");
  assert.equal(crimeStopLabel(2, null), "up to 2× the typical");
});

test("the crime line says how the building compares", () => {
  assert.deepEqual(crimeText(building({ crime: { violent: 10, property: 41, x: 0.5 } }), ["11001"], { violent: 20 }),
    { text: "Within ½ mile, past 12 months: 10 violent (half the typical building's 20) · 41 property crimes", known: true });
  assert.equal(crimeText(building({ crime: { violent: 50, property: 41, x: 2.5 } }), ["11001"], { violent: 20 }).text,
    "Within ½ mile, past 12 months: 50 violent (2.5× the typical building's 20) · 41 property crimes");
  assert.equal(crimeText(building({ crime: { violent: 21, property: 41, x: 1.05 } }), ["11001"], { violent: 20 }).text,
    "Within ½ mile, past 12 months: 21 violent (about typical) · 41 property crimes");
});

// ---------- what the unit's own listing says ----------

test("the Unit tags: ground floor, own front door, balcony or terrace", () => {
  assert.deepEqual(TAG_GROUPS.map((g) => [g.name, g.tags.map((t) => t.key)]).slice(1), [
    ["Unit", ["ground", "ownDoor", "balcony"]],
    ["Nearby", ["nearMetro", "nearGrocery", "nearPark", "dogFriendly"]],
    ["Quiet", ["quietAir", "noSites"]],
    ["Building", ["parking", "pets", "highEnd"]],
  ]);
  assert.equal(unitMatches(unit({ own_door: true }), building(), f({ ownDoor: true })), true);
  assert.equal(unitMatches(unit(), building(), f({ ownDoor: true })), false);
  assert.equal(unitMatches(unit({ outdoor: "Terrace" }), building(), f({ balcony: true })), true);
  assert.equal(unitMatches(unit(), building(), f({ balcony: true })), false);
  assert.equal(unitMatches(unit({ own_door: true, floor: 1 }), building(), f({ ownDoor: true, ground: true })), true);
  assert.equal(unitMatches(unit({ own_door: true, floor: 4 }), building(), f({ ownDoor: true, ground: true })), false);
});

// ---------- noise and construction ----------

test("quiet tags hide what is known to be loud, never what is unknown", () => {
  const air = (decibels) => building({ noise: { air: decibels, road: null, rail: null } });
  assert.equal(unitMatches(unit(), air(55), f({ quietAir: true })), false);
  assert.equal(unitMatches(unit(), air(50), f({ quietAir: true })), false);
  assert.equal(unitMatches(unit(), air(45), f({ quietAir: true })), true);
  assert.equal(unitMatches(unit(), air(null), f({ quietAir: true })), true);
  assert.equal(unitMatches(unit(), building({ noise: null }), f({ quietAir: true })), true);
  const site = { kind: "New building", day: "2026-06-01", miles: 0.06, address: "9 Side St SE", what: "New 10-story building" };
  assert.equal(unitMatches(unit(), building({ works: { next: [site], here: [] } }), f({ noSites: true })), false);
  assert.equal(unitMatches(unit(), building({ works: { next: [], here: [{ ...site, kind: "Major work" }] } }), f({ noSites: true })), false);
  assert.equal(unitMatches(unit(), building({ works: { next: [], here: [] } }), f({ noSites: true })), true);
  assert.equal(unitMatches(unit(), building({ works: null }), f({ noSites: true })), true);
});

test("noise in words: only what is loud enough to mention", () => {
  assert.deepEqual(noiseTags({ air: 55, road: 60, rail: 45 }), [
    { text: "Aircraft noise 55–60 dB", loud: true }, { text: "Road noise 60–70 dB", loud: true }]);
  assert.deepEqual(noiseTags({ air: 50, road: 55, rail: null }), [{ text: "Aircraft noise 50–55 dB", loud: false }]);
  assert.deepEqual(noiseTags({ air: 90, road: null, rail: 70 }), [{ text: "Aircraft noise 90+ dB", loud: true }, { text: "Rail noise 70–80 dB", loud: true }]);
  assert.deepEqual(noiseTags({ air: null, road: null, rail: null }), []);
  assert.deepEqual(noiseTags(null), []);
});

test("construction in words", () => {
  const site = { kind: "New building", day: "2026-06-01", miles: 0.06, address: "9 Side St SE", what: "New 10-story building" };
  assert.deepEqual(worksTags({ next: [site, { ...site, kind: "Demolition", address: "7 Other St", miles: 0.09 }], here: [] }), [
    { text: "Building site next door: new building at 9 Side St SE (permit Jun 2026) + 1 more", title: "New building, 9 Side St SE, 0.06 mi, permit Jun 2026: New 10-story building\nDemolition, 7 Other St, 0.09 mi, permit Jun 2026: New 10-story building" }]);
  assert.deepEqual(worksTags({ next: [], here: [{ ...site, kind: "Major work", day: "2026-03-02", what: "Renovate 40 units" }] }), [
    { text: "Major work in this building (permit Mar 2026)", title: "Major work, 9 Side St SE, 0.06 mi, permit Mar 2026: Renovate 40 units" }]);
  assert.deepEqual(worksTags({ next: [], here: [] }), []);
  assert.deepEqual(worksTags(null), []);
});

// ---------- top picks in dollars ----------

const PREFS = { commute: 100, crime: 200, walk: 50, quiet: 100 };
const TYPICAL = { drive: 30, walk: 14 };

test("each question asks for dollars against a concrete difference", () => {
  assert.deepEqual(TRADEOFFS.map((t) => t.key), ["commute", "crime", "walk", "quiet"]);
  for (const t of TRADEOFFS) {
    assert.match(t.ask, /per month/);
    assert.deepEqual(t.options[0], 0);
    assert.ok(t.options.every((n, i) => i === 0 || n > t.options[i - 1]));
    assert.ok(t.means.length > 20);
  }
});

test("a unit's worth is its saving against similar units plus what its place is worth to you", () => {
  const u = unit({ true: 2000, local: { pct: -20 }, own: { pct: -10 } });
  const b = building({ drive: 20, crime: { violent: 10, property: 1, x: 0.5 }, walk: { score: 18.75 }, noise: { air: null, road: null, rail: null }, works: { next: [], here: [] } });
  const got = worth(u, b, PREFS, TYPICAL);
  // 20% under neighbours is $500 (2,000 is 80% of 2,500); 10% under its building is $222; the saving is their average
  assert.deepEqual(got.parts, [
    { label: "under similar units", dollars: 361 },
    { label: "10 min shorter drive than typical", dollars: 100 },
    { label: "half the typical violent crime", dollars: 200 },
    { label: "more walkable than typical", dollars: 50 },
  ]);
  assert.equal(got.total, 711);
  assert.equal(got.share, 0.3555);                 // of its own monthly cost: what Top picks sorts on, so dear homes do not win on size alone
});

test("worth counts against a unit too, and never past twice the stated amount", () => {
  const u = unit({ true: 2200, own: { pct: 10 } });
  const b = building({ drive: 75, crime: { violent: 90, property: 1, x: 4.5 }, walk: { score: 2 },
    noise: { air: 55, road: 60, rail: null }, works: { next: [{ kind: "New building" }], here: [] } });
  const got = worth(u, b, PREFS, TYPICAL);
  assert.deepEqual(got.parts, [
    { label: "over similar units", dollars: -200 },
    { label: "45 min longer drive than typical", dollars: -200 },
    { label: "4.5× the typical violent crime", dollars: -400 },
    { label: "less walkable than typical", dollars: -100 },
    { label: "aircraft noise", dollars: -100 },
    { label: "road or rail noise", dollars: -50 },
    { label: "building site next door", dollars: -100 },
  ]);
  assert.equal(got.total, -1150);
});

test("what is unknown or not asked about counts for nothing, and a price to check has no saving", () => {
  assert.deepEqual(worth(unit(), building(), PREFS, TYPICAL), { total: 0, share: 0, parts: [] });
  assert.deepEqual(worth(unit({ true: 2000, local: { pct: -20 } }), building({ drive: 10 }), {}, TYPICAL).parts, [{ label: "under similar units", dollars: 500 }]);
  assert.deepEqual(worth(unit({ true: 1000, tag: "check", local: { pct: -50 } }), building(), PREFS, TYPICAL), { total: 0, share: 0, parts: [] });
  assert.equal(worth(unit({ true: 2000, local: { pct: -20 } }), building(), null, null).total, 500);
});

test("a discount past 25% counts as 25%: beyond that it is more likely a mismatch than a bargain", () => {
  assert.equal(worth(unit({ true: 3000, local: { pct: -38 } }), building(), null, null).total, 1000);       // 3,000 is 75% of 4,000
  assert.equal(worth(unit({ true: 3000, local: { pct: -25 } }), building(), null, null).total, 1000);
});

test("worth in words", () => {
  assert.equal(worthText({ total: 461, parts: [{ label: "under similar units", dollars: 361 }, { label: "10 min shorter drive than typical", dollars: 100 }] }),
    "About $461 a month in its favour: $361 under similar units · +$100 for 10 min shorter drive than typical");
  assert.equal(worthText({ total: -150, parts: [{ label: "over similar units", dollars: -50 }, { label: "aircraft noise", dollars: -100 }] }),
    "About $150 a month against it: $50 over similar units · −$100 for aircraft noise");
  assert.equal(worthText({ total: 500, share: 0.25, parts: [{ label: "under similar units", dollars: 500 }] }),
    "About $500 a month in its favour (25% of its cost): $500 under similar units");
  assert.equal(worthText({ total: 0, share: 0, parts: [] }), "");
});

test("the typical drive and walkability are medians over buildings that have them", () => {
  assert.deepEqual(typicalOf([building({ drive: 10, walk: { score: 10 } }), building({ drive: 30, walk: { score: 16 } }),
    building({ drive: 50, walk: null }), building({ drive: null, walk: { score: 12 } })]), { drive: 30, walk: 12 });
  assert.deepEqual(typicalOf([building()]), { drive: null, walk: null });
});

test("top picks: the most worth first; prices to check last; ties fall back to the old order", () => {
  const units = [unit({ id: "low", worth: 50 }), unit({ id: "high", worth: 400 }), unit({ id: "check", tag: "check", worth: 900 }),
    unit({ id: "negative", worth: -100 }), unit({ id: "unknown" })];
  assert.deepEqual(units.sort(compareUnits("picks")).map((u) => u.id), ["high", "low", "negative", "unknown", "check"]);
});

// ---------- the map's pop-up, and finding a building in the list ----------

test("the best deal in a building is the unit furthest under similar units, never a price to check", async () => {
  const { bestDeal } = await import("../../site/js/logic.js");
  const units = [unit({ id: "plain" }), unit({ id: "own", own: { pct: -12 } }), unit({ id: "both", own: { pct: -10 }, local: { pct: -20 } }),
    unit({ id: "check", tag: "check", own: { pct: -45 } }), unit({ id: "over", local: { pct: 8 } })];
  assert.equal(bestDeal(units).id, "both");                              // 15% on average beats 12%
  assert.equal(bestDeal([unit({ id: "dear", true: 3000 }), unit({ id: "cheap", true: 2000 })]).id, "cheap");     // nothing to compare: the cheapest
  assert.equal(bestDeal([unit({ id: "check", tag: "check", own: { pct: -45 } }), unit({ id: "over", local: { pct: 8 } })]).id, "over");
  assert.equal(bestDeal([]), null);
});

test("the pop-up's lines about the place: walkability, median age, and race only when asked for", async () => {
  const { popupFacts } = await import("../../site/js/logic.js");
  const tract = { age: 33.6, income: 120000, race: { white: 55, black: 20, asian: 10, hispanic: 10, other: 5 } };
  const b = building({ walk: { score: 17.5, label: "Most walkable" } });
  assert.deepEqual(popupFacts(b, tract, true), ["Walkability 17.5 of 20 (most walkable)", "Median age 34", "55% white · 20% Black · 10% Asian · 10% Hispanic · 5% other"]);
  assert.deepEqual(popupFacts(b, tract, false), ["Walkability 17.5 of 20 (most walkable)", "Median age 34"]);
  assert.deepEqual(popupFacts(building(), null, true), []);
});

test("finding a building in the list: which page of the list it is on", async () => {
  const { pageFor } = await import("../../site/js/logic.js");
  const groups = ["a", "b", "c", "d", "e"].map((id) => ({ building: { id } }));
  assert.equal(pageFor(groups, "a", 2), 2);
  assert.equal(pageFor(groups, "c", 2), 4);                              // enough shown to include it, in whole pages
  assert.equal(pageFor(groups, "e", 2), 6);
  assert.equal(pageFor(groups, "zzz", 2), null);                         // filtered out: not in the list at all
});

// ---------- the Followed tab ----------

test("followed: the buildings list narrowed to followed buildings, with the same filters and order", async () => {
  const { followedGroups } = await import("../../site/js/logic.js");
  const index = [building(), building({ id: "b2", name: "Second" }), building({ id: "b3", name: "Third" })];
  const units = {
    b1: [unit({ true: 2500 }), unit({ id: "b1:102", unit: "102", beds: 2, true: 3100 })],
    b2: [unit({ id: "b2:1", building: "b2", true: 2000 })],
    b3: [unit({ id: "b3:1", building: "b3", true: 1500 })],
  };
  const groups = followedGroups(index, units, f({ sort: "cost" }), 5, [{ id: "b1", name: "The Example" }, { id: "b2", name: "Second" }], []);
  assert.deepEqual(groups.map((g) => g.building.id), ["b2", "b1"]);                    // cheapest first, b3 is not followed
  assert.deepEqual(groups[1].units.map((u) => u.id), ["b1:101", "b1:102"]);
  const oneBed = followedGroups(index, units, f({ sort: "cost", beds: [2] }), 5, [{ id: "b1" }, { id: "b2" }], []);
  assert.deepEqual(oneBed.map((g) => [g.building.id, g.units.map((u) => u.id)]), [["b1", ["b1:102"]], ["b2", []]]);   // followed, nothing matching: kept, last
});

test("followed: a followed unit adds its building, and shows first even when the filters would hide it", async () => {
  const { followedGroups } = await import("../../site/js/logic.js");
  const index = [building()];
  const live = [unit({ true: 2500 }), unit({ id: "b1:102", unit: "102", true: 2300 }), unit({ id: "b1:103", unit: "103", beds: 2, true: 3100 })];
  const stars = [{ unit: { ...live[2], true: 9999 }, building: { id: "b1", name: "The Example" }, listed: true }];
  const [group, ...rest] = followedGroups(index, { b1: live }, f({ sort: "cost", beds: [1] }), 1, [], stars);
  assert.equal(rest.length, 0);
  assert.equal(group.building, index[0]);
  assert.deepEqual(group.units.map((u) => u.id), ["b1:103", "b1:102", "b1:101"]);
  assert.equal(group.units[0], live[2]);                                 // today's copy of the unit, not the one saved with the star
  assert.deepEqual(group.best.map((u) => u.id), ["b1:103"]);
  assert.deepEqual(group.unlisted, []);
  const two = followedGroups(index, { b1: live }, f({ sort: "cost" }), 1, [{ id: "b1" }], [...stars, { unit: live[0], listed: true }]);
  assert.equal(two.length, 1);                                           // followed twice over is still one building
  assert.deepEqual(two[0].best.map((u) => u.id), ["b1:101", "b1:103"]);   // every followed unit is in the short list
});

test("followed: a unit that is gone stays as last seen, and so does a building that is no longer tracked", async () => {
  const { followedGroups } = await import("../../site/js/logic.js");
  const gone = unit({ id: "b1:999", unit: "999" });
  const [group] = followedGroups([building()], { b1: [unit()] }, f(), 5, [], [{ unit: gone, building: { id: "b1" }, listed: false }]);
  assert.deepEqual(group.units.map((u) => u.id), ["b1:999", "b1:101"]);
  assert.deepEqual(group.unlisted, ["b1:999"]);
  const lost = followedGroups([building()], { b1: [unit()] }, f(), 5, [{ id: "zz", name: "Old Place" }],
    [{ unit: unit({ id: "yy:1", building: "yy" }), building: { id: "yy", name: "Other Old Place" }, listed: false }]);
  assert.deepEqual(lost.map((g) => [g.building.name, g.tracked, g.units.length]), [["Old Place", false, 0], ["Other Old Place", false, 1]]);
});

test("followed: a no-go ZIP does not hide a building you chose to follow", async () => {
  const { followedGroups } = await import("../../site/js/logic.js");
  const index = [building({ zip: "20015" })];
  const [group] = followedGroups(index, { b1: [unit()] }, f({ nogo: ["20015"] }), 5, [{ id: "b1" }], []);
  assert.equal(group.units.length, 1);
});

// ---------- who lives nearby: median age, degrees, race and ethnicity ----------

const PLACE = { age: 38.6, degree: 81, race: { white: 65, black: 6, asian: 20, hispanic: 4, other: 5 } };

test("area limits: a building is kept when its tract is inside every limit that is set", async () => {
  const { areaMatches } = await import("../../site/js/logic.js");
  assert.equal(areaMatches(PLACE, {}), true);
  assert.equal(areaMatches(PLACE, undefined), true);
  assert.equal(areaMatches(PLACE, { age: [30, 40] }), true);
  assert.equal(areaMatches(PLACE, { age: [39, null] }), true);            // shown as "Median age 39", so 39 and up keeps it
  assert.equal(areaMatches(PLACE, { age: [40, null] }), false);
  assert.equal(areaMatches(PLACE, { age: [null, 38] }), false);
  assert.equal(areaMatches(PLACE, { degree: [80, null] }), true);
  assert.equal(areaMatches(PLACE, { degree: [82, null] }), false);
  assert.equal(areaMatches(PLACE, { asian: [15, null], white: [null, 70] }), true);
  assert.equal(areaMatches(PLACE, { asian: [15, null], white: [null, 60] }), false);
  assert.equal(areaMatches(PLACE, { black: [null, 6] }), true);
});

test("area limits: a building with no figure for something that is limited is hidden", async () => {
  const { areaMatches } = await import("../../site/js/logic.js");
  assert.equal(areaMatches(null, { age: [30, null] }), false);
  assert.equal(areaMatches({ age: 30 }, { white: [10, null] }), false);
  assert.equal(areaMatches({ age: null, degree: 50 }, { age: [null, 50] }), false);
  assert.equal(areaMatches(null, {}), true);
});

test("area limits narrow the list like any other filter", () => {
  const here = building({ place: PLACE });
  assert.equal(unitMatches(unit(), here, f({ area: { degree: [80, null] } })), true);
  assert.equal(unitMatches(unit(), here, f({ area: { degree: [90, null] } })), false);
  assert.equal(unitMatches(unit(), building(), f({ area: { degree: [90, null] } })), false);
  assert.equal(unitMatches(unit(), building(), f()), true);
  assert.deepEqual(DEFAULT_FILTERS.area, {});
});

test("area limits: setting, clearing, and putting them into words", async () => {
  const { AREA_MEASURES, setBound, areaLabel } = await import("../../site/js/logic.js");
  assert.deepEqual(AREA_MEASURES.map((m) => m.key), ["age", "degree", "white", "black", "asian", "hispanic", "other"]);
  assert.deepEqual(AREA_MEASURES.filter((m) => m.race).map((m) => m.key), ["white", "black", "asian", "hispanic", "other"]);
  const none = {};
  const one = setBound(none, "age", 0, 30);
  assert.deepEqual(none, {});                                           // never changed in place: the defaults share it
  assert.deepEqual(one, { age: [30, null] });
  assert.deepEqual(setBound(one, "age", 1, 40), { age: [30, 40] });
  assert.deepEqual(setBound(setBound(one, "age", 1, 40), "age", 0, null), { age: [null, 40] });
  assert.deepEqual(setBound(one, "age", 0, null), {});
  assert.deepEqual(setBound(one, "nonsense", 0, 5), one);
  assert.equal(areaLabel({}), "Any");
  assert.equal(areaLabel(undefined), "Any");
  assert.equal(areaLabel({ age: [30, 40] }), "Median age 30 to 40");
  assert.equal(areaLabel({ age: [null, 40] }), "Median age up to 40");
  assert.equal(areaLabel({ degree: [70, null] }), "Degree 70%+");
  assert.equal(areaLabel({ degree: [70, null], asian: [10, 30] }), "Degree 70%+ · Asian 10 to 30%");
  assert.equal(areaLabel({ age: [30, null], degree: [70, null], asian: [10, 30] }), "3 limits");
});

test("area limits: with race and ethnicity switched off, those limits do nothing", async () => {
  const { withoutRace } = await import("../../site/js/logic.js");
  assert.deepEqual(withoutRace({ age: [30, null], white: [null, 50], other: [1, 2] }), { age: [30, null] });
  assert.deepEqual(withoutRace(undefined), {});
});
