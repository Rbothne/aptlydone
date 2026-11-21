import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_FILTERS, closest, groupBuildings, guessText, mistakes, searchFor, textMatches, unitMatches } from "../../site/js/logic.js";

const place = (id, name, neighborhood, city, zip, more = {}) => ({
  id, name, manager: "Bozzuto", neighborhood, county: "11001", senior: false,
  address: { street: "1 Main St", city, state: "DC", zip }, ...more,
});
const ELM = place("elm", "The Elm", "Bethesda", "Bethesda", "20814");
const LOFTS = place("lofts", "Navy Yard Lofts", "Navy Yard", "Washington", "20003");
const HEIGHTS = place("heights", "Rosslyn Heights", "Rosslyn", "Arlington", "22209");
const DARLING = place("darling", "Darlington House", "Dupont Circle", "Washington", "20036");
const ALL = [ELM, LOFTS, HEIGHTS, DARLING];
const unit = (building) => ({ id: `${building.id}:1`, building: building.id, beds: 1, sqft: 700, rent: 2000, true: 2100, floor: 2, restricted: null });
const f = (more = {}) => ({ ...DEFAULT_FILTERS, ...more });
const found = (q) => { const hit = closest(ALL, q); return hit ? [...hit.ids].sort() : null; };

test("mistakes counts a wrong, missing, extra or swapped letter as one each, against the closest beginning of a word", () => {
  assert.equal(mistakes("bethesda", "bethesda"), 0);
  assert.equal(mistakes("bethseda", "bethesda"), 1);        // two letters swapped
  assert.equal(mistakes("bethesa", "bethesda"), 1);         // one missing
  assert.equal(mistakes("betthesda", "bethesda"), 1);       // one extra
  assert.equal(mistakes("bathesda", "bethesda"), 1);        // one wrong
  assert.equal(mistakes("bethse", "bethesda"), 1);          // still typing: judged against the word's beginning
  assert.ok(mistakes("rosslyn", "bethesda") > 2);
});

test("a search that matches something is left exactly as it was", () => {
  const filters = f({ q: "Bethesda" });
  const searched = searchFor(ALL, filters);
  assert.equal(searched.filters, filters);
  assert.equal(searched.guess, null);
  assert.equal(searchFor(ALL, f()).guess, null);
  assert.equal(searchFor(ALL, f({ q: "   " })).guess, null);
});

test("a mistyped search shows the closest spelling, and says which it took", () => {
  const { filters, guess } = searchFor(ALL, f({ q: " bethseda " }));
  assert.deepEqual(guess, { asked: "bethseda", found: true, words: ["Bethesda"] });
  assert.equal(unitMatches(unit(ELM), ELM, filters), true);
  assert.equal(unitMatches(unit(LOFTS), LOFTS, filters), false);
  assert.deepEqual(groupBuildings(ALL, Object.fromEntries(ALL.map((b) => [b.id, [unit(b)]])), filters).map((g) => g.building.id), ["elm"]);
  assert.equal(guessText(guess), 'Nothing matches "bethseda". Showing the closest match: Bethesda.');
});

test("the other filters still apply to a mistyped search", () => {
  const { filters } = searchFor(ALL, f({ q: "bethseda", maxCost: 1500 }));
  assert.equal(unitMatches(unit(ELM), ELM, filters), false);
});

test("a missing letter, a doubled one, and words run together or split are all found", () => {
  assert.deepEqual(found("roslyn"), ["heights"]);
  assert.deepEqual(found("rossslyn"), ["heights"]);
  assert.deepEqual(found("navyyard"), ["lofts"]);
  assert.deepEqual(found("navy-yard lofts"), ["lofts"]);
  assert.deepEqual(found("navy yrad"), ["lofts"]);
  assert.deepEqual(closest(ALL, "navy yrad").words, ["Navy Yard"]);
});

test("only the closest spelling is shown, not everything within reach", () => {
  assert.deepEqual(found("arlingtn"), ["heights"]);           // Arlington is one letter away, Darlington two
});

test("every word typed has to be found in the same building", () => {
  assert.equal(found("navy bethseda"), null);
  assert.deepEqual(found("elm bethseda"), ["elm"]);
});

test("numbers and short words are never guessed at", () => {
  assert.equal(found("20815"), null);                         // one digit from 20814, and a different place
  assert.equal(found("elk"), null);
  assert.equal(found("zzzzzz"), null);
  assert.deepEqual(found("bethseda 20814"), ["elm"]);
  assert.equal(found("bethseda 20815"), null);
});

test("a search nothing is close to says so and shows nothing", () => {
  const filters = f({ q: "zzzzzz" });
  const searched = searchFor(ALL, filters);
  assert.equal(searched.filters, filters);
  assert.deepEqual(searched.guess, { asked: "zzzzzz", found: false, words: [] });
  assert.equal(unitMatches(unit(ELM), ELM, searched.filters), false);
  assert.equal(guessText(searched.guess), 'Nothing matches "zzzzzz", and nothing tracked is spelled close to it.');
});

test("the note names up to three spellings, or none when the words were only run together", () => {
  assert.equal(guessText(null), "");
  assert.equal(guessText({ asked: "x", found: true, words: ["A", "B"] }), 'Nothing matches "x". Showing the closest matches: A, B.');
  assert.equal(guessText({ asked: "x", found: true, words: ["A", "B", "C", "D"] }), 'Nothing matches "x". Showing the closest matches: A, B, C and more.');
  assert.equal(guessText({ asked: "navyyard", found: true, words: [] }), 'Nothing matches "navyyard" exactly. Showing the closest matches.');
});

test("accents and capitals do not count as mistakes", () => {
  const cafe = place("cafe", "Résidence Élan", "Shaw", "Washington", "20001");
  assert.deepEqual([...closest([cafe], "residense elan").ids], ["cafe"]);
});

test("textMatches is the search box's test for one building, guessed or not", () => {
  assert.equal(textMatches(ELM, f()), true);
  assert.equal(textMatches(ELM, f({ q: "beth" })), true);
  assert.equal(textMatches(LOFTS, f({ q: "beth" })), false);
  const { filters } = searchFor(ALL, f({ q: "bethseda" }));
  assert.equal(textMatches(ELM, filters), true);
  assert.equal(textMatches(LOFTS, filters), false);
});
