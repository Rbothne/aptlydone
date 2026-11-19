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

test("following a building remembers the criteria it was followed with", () => {
  const storage = fakeStorage();
  const store = createStore(storage);
  assert.equal(store.isFollowing("b1"), false);
  assert.equal(store.toggleFollow(building, { beds: [1], minSqft: 700, maxCost: 2600 }), true);
  assert.equal(store.isFollowing("b1"), true);
  const [follow] = createStore(storage).follows();
  assert.deepEqual(follow, { id: "b1", name: "The Example", criteria: { beds: [1], minSqft: 700, maxCost: 2600 } });
  assert.equal(store.toggleFollow(building, {}), false);
  assert.deepEqual(store.follows(), []);
  assert.equal(createStore(brokenStorage).toggleFollow(building, {}), true);
});

test("everything can be exported as text and imported in another browser", () => {
  const here = createStore(fakeStorage());
  here.setFilters({ ...DEFAULT_FILTERS, beds: [1], minSqft: 700 });
  here.toggleStar(unit(), building);
  here.toggleFollow(building, { beds: [1], minSqft: 700, maxCost: null });
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
