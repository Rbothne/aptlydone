import assert from "node:assert/strict";
import { test } from "node:test";

import { driveTimes, geocode, tableUrl } from "../../site/js/commute.js";
import { DEFAULT_FILTERS, driveLabel, unitMatches } from "../../site/js/logic.js";

const work = { lat: 39.1, lon: -76.8 };
const buildings = [
  { id: "a", lat: 38.9, lon: -77.0 }, { id: "b", lat: 38.95, lon: -77.05 }, { id: "nowhere", lat: null, lon: null },
];

test("geocode returns the first match, or null", async () => {
  const asked = [];
  const found = await geocode("123 Example Rd, Jessup MD", async (url) => {
    asked.push(url);
    return [{ lat: "39.1", lon: "-76.8", display_name: "123 Example Rd, Jessup, Maryland" }];
  });
  assert.deepEqual(found, { lat: 39.1, lon: -76.8, label: "123 Example Rd, Jessup, Maryland" });
  assert.ok(asked[0].startsWith("https://nominatim.openstreetmap.org/search?"));
  assert.ok(asked[0].includes("q=123%20Example%20Rd%2C%20Jessup%20MD"));
  assert.equal(await geocode("nowhere at all", async () => []), null);
  assert.equal(await geocode("   ", async () => { throw new Error("should not be asked"); }), null);
});

test("the table address lists the work place first, as longitude,latitude pairs", () => {
  assert.equal(tableUrl(work, buildings.slice(0, 2)),
    "https://router.project-osrm.org/table/v1/driving/-76.8,39.1;-77,38.9;-77.05,38.95?sources=0&annotations=duration");
});

test("drive times are whole minutes per building, and buildings without coordinates are skipped", async () => {
  const times = await driveTimes(work, buildings, async () => ({ code: "Ok", durations: [[0, 2280.4, 2710.9]] }));
  assert.deepEqual(times, { a: 38, b: 45 });
});

test("buildings are asked about in batches", async () => {
  const many = Array.from({ length: 205 }, (_, i) => ({ id: `b${i}`, lat: 38.9 + i / 1000, lon: -77.0 }));
  const sizes = [];
  const times = await driveTimes(work, many, async (url) => {
    const count = url.split("/driving/")[1].split("?")[0].split(";").length - 1;
    sizes.push(count);
    return { code: "Ok", durations: [[0, ...Array(count).fill(600)]] };
  });
  assert.deepEqual(sizes, [90, 90, 25]);
  assert.equal(Object.keys(times).length, 205);
  assert.equal(times.b204, 10);
});

test("a route that cannot be found is left out; a failed batch does not lose the others", async () => {
  let call = 0;
  const many = Array.from({ length: 100 }, (_, i) => ({ id: `b${i}`, lat: 38.9, lon: -77.0 }));
  const times = await driveTimes(work, many, async () => {
    call += 1;
    if (call === 1) throw new Error("server busy");
    return { code: "Ok", durations: [[0, null, ...Array(9).fill(900)]] };
  });
  assert.equal(Object.keys(times).length, 9);
  assert.equal("b90" in times, false);
  assert.equal(times.b91, 15);
});

test("max drive needs a known time at or under it", () => {
  const unit = { id: "u", beds: 1, sqft: 800, rent: 2000, true: 2000 };
  const f = (more) => ({ ...DEFAULT_FILTERS, ...more });
  assert.equal(DEFAULT_FILTERS.maxDrive, null);
  assert.equal(unitMatches(unit, { drive: 38 }, f({ maxDrive: 40 })), true);
  assert.equal(unitMatches(unit, { drive: 41 }, f({ maxDrive: 40 })), false);
  assert.equal(unitMatches(unit, {}, f({ maxDrive: 40 })), false);
  assert.equal(unitMatches(unit, {}, f()), true);
});

test("drive wording", () => {
  assert.equal(driveLabel(38), "38 min drive to work (no traffic)");
  assert.equal(driveLabel(75), "1 h 15 min drive to work (no traffic)");
  assert.equal(driveLabel(null), "");
});

test("shortest drive sort puts unknown times last", async () => {
  const { compareUnits } = await import("../../site/js/logic.js");
  const units = [{ id: "x" }, { id: "far", drive: 55 }, { id: "near", drive: 20 }];
  assert.deepEqual(units.sort(compareUnits("drive")).map((u) => u.id), ["near", "far", "x"]);
});
