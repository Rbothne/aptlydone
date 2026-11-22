import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_FILTERS } from "../../site/js/logic.js";
import { createStore } from "../../site/js/store.js";

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
    removeItem: (key) => { delete data[key]; },
  };
}
const brokenStorage = {
  getItem() { throw new Error("blocked"); },
  setItem() { throw new Error("blocked"); },
  removeItem() { throw new Error("blocked"); },
};
const building = { id: "b1", name: "The Example", url: "https://example.test/b1", neighborhood: "Chevy Chase",
  address: { street: "1 Main St", city: "Washington", state: "DC", zip: "20015" } };
const unit = (more = {}) => ({ id: "b1:101", building: "b1", unit: "101", beds: 1, sqft: 800, rent: 2400, true: 2500, ...more });

test("filters start at the defaults and are remembered", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  assert.deepEqual(store.getFilters(), { ...DEFAULT_FILTERS });
  store.setFilters({ ...DEFAULT_FILTERS, beds: [1], minSqft: 700 });
  assert.deepEqual(createStore(storage).getFilters(), { ...DEFAULT_FILTERS, beds: [1], minSqft: 700 });
});

test("saved filters from an older version gain new defaults and drop unknown keys", () => {
  const storage = fakeStorage({ "apt.filters": JSON.stringify({ minSqft: 700, retired: true }) });
  const filters = createStore(storage).getFilters();
  assert.equal(filters.minSqft, 700);
  assert.equal(filters.sort, "picks");
  assert.equal("retired" in filters, false);
});

test("corrupt saved data falls back to the defaults", () => {
  const store = createStore(fakeStorage({ "apt.filters": "{not json", "apt.stars": "[[[" }));
  assert.deepEqual(store.getFilters(), { ...DEFAULT_FILTERS });
  assert.deepEqual(store.stars(), []);
});

test("starring keeps a copy of the unit and its building", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  assert.equal(store.isStarred("b1:101"), false);
  assert.equal(store.toggleStar(unit(), building), true);
  assert.equal(store.isStarred("b1:101"), true);
  const [star] = createStore(storage).stars();
  assert.equal(star.unit.rent, 2400);
  assert.equal(star.building.name, "The Example");
  assert.equal(star.listed, true);
  assert.equal(store.toggleStar(unit(), building), false);
  assert.deepEqual(store.stars(), []);
});

test("refreshing stars updates listed units and marks the rest as no longer listed", () => {
  const store = createStore(fakeStorage());
  store.toggleStar(unit(), building);
  store.toggleStar(unit({ id: "b1:202", unit: "202" }), building);
  store.refreshStars({ "b1:101": unit({ rent: 2300, true: 2400 }) }, { b1: { ...building, name: "Renamed" } });
  const stars = Object.fromEntries(store.stars().map((s) => [s.unit.id, s]));
  assert.equal(stars["b1:101"].unit.rent, 2300);
  assert.equal(stars["b1:101"].listed, true);
  assert.equal(stars["b1:101"].building.name, "Renamed");
  assert.equal(stars["b1:202"].listed, false);
  assert.equal(stars["b1:202"].unit.rent, 2400);
});

test("a unit that comes back is listed again", () => {
  const store = createStore(fakeStorage());
  store.toggleStar(unit(), building);
  store.refreshStars({}, {});
  assert.equal(store.stars()[0].listed, false);
  store.refreshStars({ "b1:101": unit() }, { b1: building });
  assert.equal(store.stars()[0].listed, true);
});

test("works in memory when storage is blocked or missing", () => {
  for (const storage of [brokenStorage, null, undefined]) {
    const store = createStore(storage);
    assert.deepEqual(store.getFilters(), { ...DEFAULT_FILTERS });
    store.setFilters({ ...DEFAULT_FILTERS, minSqft: 900 });
    assert.equal(store.getFilters().minSqft, 900);
    assert.equal(store.toggleStar(unit(), building), true);
    assert.equal(store.isStarred("b1:101"), true);
  }
});

test("settings are remembered, with a fallback", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  assert.equal(store.getSetting("demographics", true), true);
  store.setSetting("demographics", false);
  assert.equal(createStore(storage).getSetting("demographics", true), false);
  assert.equal(createStore(brokenStorage).getSetting("demographics", true), true);
});

test("following a building remembers which building, and nothing about the filters of the day", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  assert.equal(store.isFollowing("b1"), false);
  assert.equal(store.toggleFollow(building), true);
  assert.equal(store.isFollowing("b1"), true);
  const [follow] = createStore(storage).follows();
  assert.deepEqual(follow, { id: "b1", name: "The Example" });
  assert.equal(store.toggleFollow(building), false);
  assert.deepEqual(store.follows(), []);
  assert.equal(createStore(brokenStorage).toggleFollow(building), true);
});

test("everything can be exported as text and imported in another browser", () => {
  const here = createStore(fakeStorage());
  here.setFilters({ ...DEFAULT_FILTERS, beds: [1], minSqft: 700 });
  here.toggleStar(unit(), building);
  here.toggleFollow(building);
  here.setSetting("nogo", ["20002"]);
  here.setSetting("income", 90000);
  here.setSetting("work", { address: "1 Main St", lat: 39.1, lon: -76.8, label: "1 Main St" });
  here.setSetting("googleKey", "SECRET-KEY");
  const text = here.exportText("2026-11-18T20:00Z");
  assert.equal(typeof text, "string");
  assert.equal(text.includes("SECRET-KEY"), false);                // the key never leaves this browser
  const parsed = JSON.parse(text);
  assert.equal(parsed.app, "apartment-tracker");
  assert.equal(parsed.exported, "2026-11-18T20:00Z");

  const there = createStore(fakeStorage());
  there.setSetting("googleKey", "OTHER-KEY");
  assert.deepEqual(there.importText(text), { ok: true, stars: 1, follows: 1 });
  assert.equal(there.getFilters().minSqft, 700);
  assert.equal(there.stars()[0].unit.id, "b1:101");
  assert.equal(there.follows()[0].id, "b1");
  assert.deepEqual(there.getSetting("nogo", []), ["20002"]);
  assert.equal(there.getSetting("income", null), 90000);
  assert.equal(there.getSetting("work", null).address, "1 Main St");
  assert.equal(there.getSetting("googleKey", null), "OTHER-KEY");   // importing does not touch this browser's key
});

test("importing text that is not an export changes nothing", () => {
  const store = createStore(fakeStorage());
  store.setFilters({ ...DEFAULT_FILTERS, minSqft: 900 });
  for (const text of ["", "hello", "{}", '{"app":"something-else"}', "[1,2,3]"]) {
    assert.equal(store.importText(text).ok, false, text);
  }
  assert.equal(store.getFilters().minSqft, 900);
});

// ---------- new tagged units in followed buildings ----------

const tagged = (n, more = {}) => unit({ id: `b1:${n}`, unit: String(n), tag: "local", first: "2026-11-21", url: `https://example.test/b1/${n}`, ...more });
const listing = (...units) => ({ b1: units });
const known = { b1: building };

test("following a building starts from what it lists now: nothing is announced", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  assert.deepEqual(store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21"), []);
  assert.deepEqual(store.arrivals(), []);
});

test("a tagged unit that appears in a followed building is announced, once", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  const fresh = tagged(102, { tag: "absolute", beds: 2, sqft: 950, rent: 2400, true: 2500 });
  store.noteArrivals(listing(tagged(101), fresh), known, "2026-11-21");
  assert.deepEqual(createStore(storage).arrivals(), [{
    id: "b1:102", building: "b1", name: "The Example", title: "#102", tag: "absolute", beds: 2, sqft: 950, cost: 2500,
    url: "https://example.test/b1/102", first: "2026-11-21", day: "2026-11-21", kind: "new", drop: null,
  }]);
  store.noteArrivals(listing(tagged(101), fresh), known, "2026-11-22");
  assert.equal(store.arrivals().length, 1);
});

test("a new unit without a tag is not announced until it gains one", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101), tagged(102, { tag: null })), known, "2026-11-21");
  assert.deepEqual(store.arrivals(), []);
  const cut = { was: 2600, by: 200, pct: -7.7, day: "2026-11-22" };
  store.noteArrivals(listing(tagged(101), tagged(102, { tag: "local", drop: cut })), known, "2026-11-22");
  const [note, ...rest] = store.arrivals();
  assert.deepEqual(rest, []);
  assert.equal(note.id, "b1:102");
  assert.equal(note.kind, "tagged");
  assert.equal(note.day, "2026-11-22");
  assert.equal(note.drop, "Down $200 (8%) since Nov 22, from $2,600");
});

test("a unit listed without a tag when its building was followed is announced when it gains one", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101, { tag: null })), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101, { tag: "building" })), known, "2026-11-21");
  assert.deepEqual(store.arrivals().map((note) => [note.id, note.kind, note.tag]), [["b1:101", "tagged", "building"]]);
  store.noteArrivals(listing(tagged(101, { tag: "building" })), known, "2026-11-22");
  assert.equal(store.arrivals().length, 1);
});

test("a tag that turns into another tag is not announced", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101, { tag: "local" })), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101, { tag: "absolute" })), known, "2026-11-21");
  assert.deepEqual(store.arrivals(), []);
});

test("a unit that loses its tag and gains it back is announced again, in place of the older announcement", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101, { tag: null })), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101)), known, "2026-11-21");
  store.noteArrivals(listing(tagged(101, { tag: null })), known, "2026-11-22");
  store.noteArrivals(listing(tagged(101)), known, "2026-11-23");
  assert.deepEqual(store.arrivals().map((note) => [note.id, note.day]), [["b1:101", "2026-11-23"]]);
});

test("a tag gained while a building could not be read is announced when it reads again", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101, { tag: null }), tagged(102)), known, "2026-11-20");
  store.noteArrivals(listing(), { b1: { ...building, stale: true, expired: true } }, "2026-11-25");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-26");
  assert.deepEqual(store.arrivals().map((note) => [note.id, note.kind]), [["b1:101", "tagged"]]);
});

test("a building kept under Followed by a starred unit is watched too", () => {
  const store = createStore(fakeStorage());
  store.toggleStar(tagged(101), building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102"]);
});

test("a building nobody follows announces nothing", () => {
  const store = createStore(fakeStorage());
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21");
  assert.deepEqual(store.arrivals(), []);
});

test("a unit that leaves and is listed again is announced again", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101)), known, "2026-11-21");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-22");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102"]);
});

test("units that vanish while a building cannot be read are not announced when they return", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-20");
  store.noteArrivals(listing(), { b1: { ...building, stale: true, expired: true } }, "2026-11-25");
  store.noteArrivals(listing(tagged(101), tagged(102), tagged(103)), known, "2026-11-26");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:103"]);
});

test("a followed building missing from the data for a while announces nothing when it returns", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals({}, {}, "2026-11-21");
  store.noteArrivals(listing(tagged(101)), known, "2026-11-22");
  assert.deepEqual(store.arrivals(), []);
});

test("announcements are kept two weeks, newest first, sixty at most", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(), known, "2026-11-01");
  store.noteArrivals(listing(tagged(101)), known, "2026-11-02");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-10");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102", "b1:101"]);
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-16");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102", "b1:101"]);       // fourteen days old: still there
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-17");
  assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102"]);
  const many = Array.from({ length: 70 }, (_, i) => tagged(200 + i));
  store.noteArrivals(listing(tagged(101), tagged(102), ...many), known, "2026-11-18");
  assert.equal(store.arrivals().length, 60);
});

test("unfollowing a building drops its announcements, and following again starts afresh", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21");
  store.toggleFollow(building);
  assert.deepEqual(store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21"), []);
  store.toggleFollow(building);
  assert.deepEqual(store.noteArrivals(listing(tagged(101), tagged(102), tagged(103)), known, "2026-11-22"), []);
});

test("clearing the announcements does not bring them back", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
  store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21");
  store.clearArrivals();
  assert.deepEqual(store.arrivals(), []);
  assert.deepEqual(store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-22"), []);
});

test("announcements work in memory when storage is blocked, and survive corrupt saved data", () => {
  for (const storage of [brokenStorage, fakeStorage({ "apt.news": "{not json" }), fakeStorage({ "apt.news": "[1,2]" }),
    fakeStorage({ "apt.news": JSON.stringify({ seen: "x", notes: [null, 3, { id: "b1:9" }] }) })]) {
    const store = createStore(storage);
    assert.deepEqual(store.arrivals(), []);
    store.toggleFollow(building);
    store.noteArrivals(listing(tagged(101)), known, "2026-11-20");
    store.noteArrivals(listing(tagged(101), tagged(102)), known, "2026-11-21");
    assert.deepEqual(store.arrivals().map((note) => note.id), ["b1:102"]);
  }
});

test("a unit priced by floor plan is announced under its plan's name", () => {
  const store = createStore(fakeStorage());
  store.toggleFollow(building);
  store.noteArrivals(listing(), known, "2026-11-20");
  store.noteArrivals(listing(tagged(102, { plan: "Adams", count: 3, true: null, rent: 2836 })), known, "2026-11-21");
  const [note] = store.arrivals();
  assert.equal(note.title, "Adams");
  assert.equal(note.cost, 2836);
});
