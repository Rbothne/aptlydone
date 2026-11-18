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
