// Every decision the page makes, as plain functions with no browser in them, so they can be tested with Node.

export const DEFAULT_FILTERS = Object.freeze({
  q: "", beds: [], minSqft: null, maxCost: null, moveBy: null, floorMin: null, floorMax: null, ground: false,
  ownDoor: false, balcony: false, quietAir: false, noSites: false,
  parking: false, pets: false, nearMetro: false, nearGrocery: false, nearPark: false, dogFriendly: false, minWalk: null, deals: [], highEnd: false, maxViolentX: null, maxDrive: null, minRating: null, manager: "", counties: [], showRestricted: false, sort: "picks",
  area: {},        // limits on who lives nearby: {age: [from, to], degree: [...], white: [...], ...}; see AREA_MEASURES
});

export const HIGH_END = 67;                 // a building pricier than this share of its neighbours is "high-end for its area"
export const GROUND_FLOORS = [0, 1];
export const NEAR_MILES = 0.5;                // "near" a Metro station or a grocery store
export const PARK_MILES = 0.25;               // a park has to be closer than that to count as next to home
export const DOG_FRIENDLY = 3;                // dog score, out of 5, that the Dog-friendly filter asks for
export const AIR_MENTION = 50, AIR_LOUD = 55; // decibels of aircraft noise (24-hour average) worth a note, and worth a warning
export const GROUND_LOUD = 60;                // road or rail noise worth a warning
export const CRIME_STOPS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];   // the violent-crime limit, as multiples of the typical building's count
export const WALK_BAND = 4.75;                // points between the EPA index's bands (20 points, four bands)
export const MOST_DISCOUNT = 25;              // Top picks counts a unit as at most this many percent under similar units

function within(building, kind, miles) {
  const nearest = building.near && building.near[kind] ? building.near[kind][1] : null;
  return nearest != null && nearest <= miles;
}          // buildings number the ground floor either way
const TAG_ORDER = { absolute: 0, building: 1, local: 2 };
const TAG_LABELS = { absolute: "Absolute steal", building: "Building steal", local: "Local value", check: "Check price" };

/** The three steal tags. "check" is not one: it marks a price too low to believe without asking. */
export function isSteal(tag) {
  return tag in TAG_ORDER;
}

/** What a unit costs per month for comparing: the true monthly cost, or the rent when that is unknown. */
export function cost(unit) {
  return unit.true ?? unit.rent ?? null;
}

/** What the search box looks through for a building: its name, neighborhood, company and address. */
function searchFields(building) {
  const a = building.address || {};
  return [building.name, building.neighborhood, building.manager, a.city, a.zip, a.street, a.full].filter(Boolean).map(String);
}

function searchable(building) {
  return searchFields(building).join(" ").toLowerCase();
}

/** Does the search box let this building through? `among` is set by searchFor when the text had to be guessed at. */
export function textMatches(building, filters) {
  if (filters.among) return filters.among.has(building.id);
  const q = (filters.q || "").trim().toLowerCase();
  return !q || searchable(building).includes(q);
}

// ---------- a mistyped search ----------

const unaccented = (text) => String(text).normalize("NFD").replace(/[̀-ͯ]/g, "");
const RUN_TOGETHER = 5;                       // letters a search needs before "navyyard" may match "Navy Yard"

/** How many typing mistakes a searched word may hold: none in a number or a short word, where one letter changes the place. */
function slack(word) {
  if (/\d/.test(word) || word.length < 4) return 0;
  return word.length < 8 ? 1 : 2;
}

/**
 * Typing mistakes between what was typed and the closest beginning of a word: a letter wrong, missing or extra, or two
 * swapped, count one each. Judged against the word's beginning so that a search still being typed finds its word.
 */
export function mistakes(typed, word) {
  let before = null, last = Array.from({ length: word.length + 1 }, (_, j) => j);
  for (let i = 1; i <= typed.length; i++) {
    const row = [i];
    for (let j = 1; j <= word.length; j++) {
      const same = typed[i - 1] === word[j - 1];
      row[j] = Math.min(last[j] + 1, row[j - 1] + 1, last[j - 1] + (same ? 0 : 1));
      if (before && j > 1 && typed[i - 1] === word[j - 2] && typed[i - 2] === word[j - 1]) row[j] = Math.min(row[j], before[j - 2] + 1);
    }
    before = last;
    last = row;
  }
  return Math.min(...last);
}

/**
 * The buildings a mistyped search most likely meant: {ids, words}, or null when nothing is close. Every word typed has
 * to be found in the same building, within its allowance of mistakes; only the buildings with the fewest mistakes are
 * kept. `words` are the spellings that were taken, for telling the user ("Bethesda"); empty when the search only ran
 * words together or split them ("navyyard").
 */
export function closest(index, q) {
  const typed = unaccented(q).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (!typed.length) return null;
  const run = typed.join("");
  let least = Infinity, ids = [];
  const taken = new Map();
  for (const building of index) {
    const fields = searchFields(building).map(unaccented);
    let total = 0, phrase = [];
    if (run.length >= RUN_TOGETHER && fields.some((field) => field.toLowerCase().replace(/[^a-z0-9]+/g, "").includes(run))) phrase = null;
    else {
      const have = fields.flatMap((field) => field.split(/[^A-Za-z0-9]+/).filter(Boolean));
      for (const word of typed) {
        let best = Infinity, spelling = null;
        for (const candidate of have) {
          const off = mistakes(word, candidate.toLowerCase());
          if (off < best) [best, spelling] = [off, candidate];
        }
        if (best > slack(word)) { total = Infinity; break; }
        total += best;
        phrase.push(spelling);
      }
    }
    if (total === Infinity || total > least) continue;
    if (total < least) { least = total; ids = []; taken.clear(); }
    ids.push(building.id);
    if (phrase) taken.set(phrase.join(" ").toLowerCase(), phrase.join(" "));
  }
  return ids.length ? { ids: new Set(ids), words: [...taken.values()] } : null;
}

/**
 * The filters as the search box should apply them, and what had to be guessed. A search that matches some building's
 * text is left alone (guess null). One that matches none is taken as mistyped: the filters gain `among`, the closest
 * buildings, and guess says what was asked and which spellings were taken; found is false when nothing is close.
 */
export function searchFor(index, filters) {
  const asked = (filters.q || "").trim();
  if (!asked || index.some((building) => searchable(building).includes(asked.toLowerCase()))) return { filters, guess: null };
  const hit = closest(index, asked);
  if (!hit) return { filters, guess: { asked, found: false, words: [] } };
  return { filters: { ...filters, among: hit.ids }, guess: { asked, found: true, words: hit.words } };
}

/** The line under the count that owns up to a guessed search. */
export function guessText(guess) {
  if (!guess) return "";
  const nothing = `Nothing matches "${guess.asked}"`;
  if (!guess.found) return `${nothing}, and nothing tracked is spelled close to it.`;
  if (!guess.words.length) return `${nothing} exactly. Showing the closest matches.`;
  const more = guess.words.length > 3 ? " and more" : "";
  return `${nothing}. Showing the closest ${guess.words.length > 1 ? "matches" : "match"}: ${guess.words.slice(0, 3).join(", ")}${more}.`;
}

export function unitMatches(unit, building, filters) {
  if (!filters.showRestricted && (unit.restricted === true || building.senior)) return false;
  if (filters.beds.length) {
    const beds = unit.beds == null ? null : Math.min(unit.beds, 3);
    if (!filters.beds.includes(beds)) return false;
  }
  if (filters.minSqft != null && !(unit.sqft >= filters.minSqft)) return false;
  if (filters.maxCost != null && !(cost(unit) <= filters.maxCost)) return false;
  if (filters.moveBy && !(unit.available && unit.available <= filters.moveBy)) return false;
  if (filters.floorMin != null && !(unit.floor != null && unit.floor >= filters.floorMin)) return false;
  if (filters.floorMax != null && !(unit.floor != null && unit.floor <= filters.floorMax)) return false;
  if (filters.ground && !GROUND_FLOORS.includes(unit.floor)) return false;
  if (filters.ownDoor && !unit.own_door) return false;
  if (filters.balcony && !unit.outdoor) return false;
  if (filters.quietAir && building.noise && building.noise.air >= AIR_MENTION) return false;
  if (filters.noSites && building.works && (building.works.next.length || building.works.here.length)) return false;
  if (filters.parking && building.parking_from == null && building.parking !== true) return false;
  if (filters.pets && building.pets !== true) return false;
  if (filters.nearMetro && !within(building, "metro", NEAR_MILES)) return false;
  if (filters.nearGrocery && !within(building, "grocery", NEAR_MILES)) return false;
  if (filters.nearPark && !within(building, "park", PARK_MILES)) return false;
  if (filters.dogFriendly && !(building.dog && building.dog.score >= DOG_FRIENDLY)) return false;
  if (filters.minWalk != null && !(building.walk && building.walk.score >= filters.minWalk)) return false;
  if (!areaMatches(building.place, filters.area)) return false;
  const deals = chosenDeals(filters);
  if (deals.length && !(deals.includes(unit.tag) || (deals.includes("drop") && unit.drop))) return false;
  if (filters.highEnd && !(building.rank && building.rank.pct >= HIGH_END)) return false;
  if (filters.maxViolentX != null && !(building.crime && building.crime.x != null && building.crime.x <= filters.maxViolentX)) return false;
  if (filters.maxDrive != null && !(building.drive != null && building.drive <= filters.maxDrive)) return false;
  if (filters.minRating != null && !(building.rating != null && building.rating >= filters.minRating)) return false;
  if (filters.manager && building.manager !== filters.manager) return false;
  if (filters.nogo && building.zip && filters.nogo.includes(building.zip)) return false;
  if (filters.counties && filters.counties.length && !filters.counties.includes(building.county)) return false;
  return textMatches(building, filters);
}

/**
 * What can be limited about the people of a building's census tract. Each limit is [from, to], either end open (null).
 * These narrow the list and nothing else: none of them feeds a deal tag or Top picks.
 */
export const AREA_MEASURES = [
  { key: "age", label: "Median age", short: "Median age", unit: "" },
  { key: "degree", label: "Adults with a degree", short: "Degree", unit: "%" },
  { key: "white", label: "White", short: "White", unit: "%", race: true },
  { key: "black", label: "Black", short: "Black", unit: "%", race: true },
  { key: "asian", label: "Asian", short: "Asian", unit: "%", race: true },
  { key: "hispanic", label: "Hispanic", short: "Hispanic", unit: "%", race: true },
  { key: "other", label: "Other", short: "Other", unit: "%", race: true },
];

const limited = (area) => AREA_MEASURES.filter((m) => area && Array.isArray(area[m.key]) && area[m.key].some((end) => end != null));

/** Does a tract sit inside every limit that is set? A figure that is missing fails a limit on it. Compared as shown: rounded. */
export function areaMatches(place, area) {
  for (const measure of limited(area)) {
    const raw = !place ? null : measure.race ? place.race && place.race[measure.key] : place[measure.key];
    if (raw == null) return false;
    const value = Math.round(raw);
    const [from, to] = area[measure.key];
    if (from != null && value < from) return false;
    if (to != null && value > to) return false;
  }
  return true;
}

/** The limits with one end changed (side 0 is "from", 1 is "to"); a limit with both ends open is dropped. Never changes `area`. */
export function setBound(area, key, side, value) {
  if (!AREA_MEASURES.some((m) => m.key === key)) return area;
  const next = { ...(area || {}) };
  const ends = Array.isArray(next[key]) ? [next[key][0] ?? null, next[key][1] ?? null] : [null, null];
  ends[side] = value;
  if (ends[0] == null && ends[1] == null) delete next[key];
  else next[key] = ends;
  return next;
}

/** The limits that still apply when race and ethnicity are switched off. */
export function withoutRace(area) {
  return Object.fromEntries(limited(area).filter((m) => !m.race).map((m) => [m.key, area[m.key]]));
}

/** The limits in a few words for the picker: "Any", "Median age 30 to 40", "Degree 70%+ · Asian 10 to 30%", "3 limits". */
export function areaLabel(area) {
  const set = limited(area);
  if (!set.length) return "Any";
  if (set.length > 2) return `${set.length} limits`;
  return set.map(({ key, short, unit }) => {
    const [from, to] = area[key];
    if (from != null && to != null) return `${short} ${from} to ${to}${unit}`;
    return from != null ? `${short} ${from}${unit}+` : `${short} up to ${to}${unit}`;
  }).join(" · ");
}

// Compare two values that may be missing: missing always goes last, whichever way the sort runs.
function by(value, descending = false) {
  return (a, b) => {
    const x = value(a), y = value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (x < y) return descending ? 1 : -1;
    if (x > y) return descending ? -1 : 1;
    return 0;
  };
}

function chain(...comparisons) {
  return (a, b) => {
    for (const compare of comparisons) {
      const result = compare(a, b);
      if (result) return result;
    }
    return 0;
  };
}

const costPerSqft = (u) => (cost(u) != null && u.sqft ? cost(u) / u.sqft : null);

// Top picks: what each unit has in its favour for this user, as a share of its cost (see worth()), most first;
// a price too low to believe goes last. Units nobody has valued yet fall back to: steal tag, then furthest under its building, then cost per sqft.
const SORTS = {
  picks: chain(by((u) => (u.tag === "check" ? 1 : 0)), by((u) => u.worth, true),
    by((u) => TAG_ORDER[u.tag] ?? 3), by((u) => u.own?.pct), by(costPerSqft)),
  drop: by((u) => u.drop?.pct),
  cost: by(cost),
  ppsf: by(costPerSqft),
  own: by((u) => u.own?.pct),
  local: by((u) => u.local?.pct),
  newest: by((u) => u.first, true),
  size: by((u) => u.sqft, true),
  drive: by((u) => u.drive),
  walk: by((u) => u.walkScore, true),
};

export function compareUnits(sort) {
  return chain(SORTS[sort] || SORTS.picks, by((u) => u.id));
}

export function groupBuildings(index, unitsByBuilding, filters, bestCount = 5) {
  const compare = compareUnits(filters.sort);
  const groups = [];
  for (const building of index) {
    const units = (unitsByBuilding[building.id] || []).filter((unit) => unitMatches(unit, building, filters));
    if (!units.length) continue;
    units.sort(compare);
    groups.push({ building, units, best: units.slice(0, bestCount) });
  }
  return groups.sort((a, b) => compare(a.best[0], b.best[0]));
}

/** One point per building that has coordinates: where it is, its best tag, how many units match, and its best unit. */
export function mapPoints(groups) {
  return groups
    .filter(({ building }) => building.lat != null && building.lon != null)
    .map(({ building, units, best }) => ({
      id: building.id, name: building.name, lat: building.lat, lon: building.lon, building,
      count: units.length, best: best[0], deal: bestDeal(units),
      tag: units.reduce((top, unit) => (isSteal(unit.tag) && (TAG_ORDER[unit.tag] ?? 3) < (TAG_ORDER[top] ?? 3) ? unit.tag : top), null),
    }));
}

/** How far under similar units a unit is priced, in percent (negative is under): the average of what it has; null when unknown. */
function discount(unit) {
  const known = [unit.own, unit.local].filter(Boolean).map((vs) => vs.pct);
  return known.length ? known.reduce((sum, pct) => sum + pct, 0) / known.length : null;
}

/**
 * The unit in a building that is the best deal: furthest under similar units in its building and nearby. A price
 * marked for checking is passed over while anything else is on offer; with nothing to compare, the cheapest.
 */
export function bestDeal(units) {
  const sound = units.filter((unit) => unit.tag !== "check");
  const pool = sound.length ? sound : units;
  if (!pool.length) return null;
  return [...pool].sort(chain(by(discount), by(cost), by((u) => u.id)))[0];
}

/** Lines about the place for the map's pop-up: walkability, the tract's median age, and race when asked for. */
export function popupFacts(building, tract, showRace) {
  const lines = [];
  if (walkText(building.walk)) lines.push(walkText(building.walk));
  if (tract && tract.age != null) lines.push(`Median age ${Math.round(tract.age)}`);
  if (showRace && tract && tract.race) {
    const r = tract.race;
    lines.push(`${r.white}% white · ${r.black}% Black · ${r.asian}% Asian · ${r.hispanic}% Hispanic · ${r.other}% other`);
  }
  return lines;
}

/** How many buildings the list must show, in whole pages, for this building to be drawn; null when it is filtered out. */
export function pageFor(groups, buildingId, pageSize) {
  const at = groups.findIndex((group) => group.building.id === buildingId);
  return at < 0 ? null : (Math.floor(at / pageSize) + 1) * pageSize;
}

/**
 * The Followed tab: the buildings list narrowed to the buildings that are followed or hold a followed unit, under the same
 * filters and in the same order. What was followed never drops out: a followed unit shows first in its building even when
 * the filters would hide it (as last seen once it is no longer listed), a followed building stays when nothing in it
 * matches, and a no-go ZIP does not hide either. Returns [{building, units, best, unlisted, tracked}].
 */
export function followedGroups(index, unitsByBuilding, filters, bestCount, follows, stars) {
  const compare = compareUnits(filters.sort);
  const open = { ...filters, nogo: [] };
  const byId = Object.fromEntries(index.map((building) => [building.id, building]));
  const wanted = new Map();                       // building id -> {known, stars}
  const want = (id, known) => {
    if (!wanted.has(id)) wanted.set(id, { known: null, stars: [] });
    const entry = wanted.get(id);
    entry.known = entry.known || known;
    return entry;
  };
  for (const follow of follows) want(follow.id, follow);
  for (const star of stars) want(star.unit.building, star.building).stars.push(star);

  const groups = [];
  for (const [id, { known, stars: mine }] of wanted) {
    const building = byId[id];
    const live = building ? unitsByBuilding[id] || [] : [];
    const starred = new Set(mine.map((star) => star.unit.id));
    const listed = live.filter((unit) => starred.has(unit.id)).sort(compare);
    const here = new Set(listed.map((unit) => unit.id));
    const gone = mine.filter((star) => !here.has(star.unit.id)).map((star) => star.unit);
    const matching = live.filter((unit) => !starred.has(unit.id) && unitMatches(unit, building, open)).sort(compare);
    const pinned = [...listed, ...gone];
    const units = [...pinned, ...matching];
    groups.push({
      building: building || { ...known, id, name: (known && known.name) || id },
      units, best: units.slice(0, Math.max(bestCount, pinned.length)),
      unlisted: gone.map((unit) => unit.id), tracked: Boolean(building),
      top: [...listed, ...matching].sort(compare)[0] || null,
    });
  }
  return groups.sort((a, b) => {
    if (a.top && b.top) return compare(a.top, b.top);
    if (a.top || b.top) return a.top ? -1 : 1;
    return String(a.building.name).localeCompare(String(b.building.name));
  });
}

/** Where a building's one-bedroom cost per sqft sits among buildings within two miles, in plain words. */
export function standing(rank) {
  if (!rank) return "";
  if (rank.pct >= HIGH_END) return "High-end for its area";
  if (rank.pct > 100 - HIGH_END) return "Mid-priced for its area";
  return "Lower-priced for its area";
}

/** The yearly income most managed buildings ask for: three times the rent, every month. */
export function incomeNeeded(unit) {
  return unit.rent == null ? null : unit.rent * 36;
}

/** true / false against a yearly income, or null when either side is unknown. */
export function affordable(unit, income) {
  const needed = incomeNeeded(unit);
  return needed == null || income == null ? null : income >= needed;
}

/** "#215" for a unit; the plan's name when the source prices by floor plan and not by unit. */
export function unitTitle(unit) {
  return unit.count != null ? unit.plan || unit.unit : `#${unit.unit}`;
}

export function availableNote(unit) {
  return unit.count != null ? `${unit.count} available` : "";
}

/** What the city's affordable-housing list says about a building, in words. */
export function affordableNote(project) {
  if (!project || !project.affordable) return "";
  return project.total
    ? `City records: ${project.affordable} of ${project.total} units here are income-restricted`
    : `City records: ${project.affordable} income-restricted units here`;
}

const STATES = [["11", "DC"], ["51", "Virginia"], ["24", "Maryland"]];

/** Counties (FIPS codes) grouped by state, each list in name order: for the area picker. */
export function countyGroups(fipsCodes, names) {
  return STATES.map(([prefix, state]) => ({
    state,
    counties: fipsCodes.filter((fips) => fips.startsWith(prefix))
      .map((fips) => ({ fips, name: names[fips] || fips }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  })).filter((group) => group.counties.length);
}

/** The tag drop-down. Deal tags are alternatives (a unit carries one tag); the rest are each a requirement. */
export const TAG_GROUPS = [
  { name: "Deals", note: "any of these", tags: [
    { key: "absolute", label: "Absolute steal", title: "10% or more below its building and 15% or more below its neighbors" },
    { key: "building", label: "Building steal", title: "15% or more below similar units in the same building" },
    { key: "local", label: "Local value", title: "20% or more below similar units in buildings within one to two miles" },
    { key: "drop", label: "Price drop", title: "At least 2% below the highest price it stood at in the last 30 days, and still falling or holding" }] },
  { name: "Unit", note: "all of these", tags: [
    { key: "ground", label: "Ground floor", title: "Units on the ground floor only" },
    { key: "ownDoor", label: "Own front door", title: "The unit's own listing says it has a private entrance to the outside, or is a townhome. Most listings do not say, so this hides most units" },
    { key: "balcony", label: "Balcony or terrace", title: "The unit's own listing names a balcony, terrace, patio, deck or yard. A building that only says \"balconies in select homes\" does not count" }] },
  { name: "Nearby", note: "all of these", tags: [
    { key: "nearMetro", label: "Near Metro", title: "A Metro station within half a mile" },
    { key: "nearGrocery", label: "Grocery nearby", title: "A supermarket within half a mile" },
    { key: "nearPark", label: "Park nearby", title: "A park within a quarter mile" },
    { key: "dogFriendly", label: "Dog-friendly", title: "Pets allowed, plus at least two of: a dog park within half a mile, a park within a quarter mile, a dog run or pet spa on site" }] },
  { name: "Quiet", note: "all of these", tags: [
    { key: "quietAir", label: "No aircraft noise", title: "Under 50 decibels of aircraft noise, averaged over the day, on the US Department of Transportation's noise map" },
    { key: "noSites", label: "No building site next door", title: "No new-building or demolition permit within a block in the last two years, and no big renovation permit on the building itself in the last year. Permits are checked in DC only; buildings elsewhere are not hidden" }] },
  { name: "Building", note: "all of these", tags: [
    { key: "parking", label: "Parking", title: "The building lists parking" },
    { key: "pets", label: "Pets", title: "The building says pets are allowed" },
    { key: "highEnd", label: "High-end", title: "Buildings whose one-bedroom cost per sqft is in the top third of buildings within two miles" }] },
];
const DEAL_KEYS = TAG_GROUPS[0].tags.map((tag) => tag.key);
const STEAL_KEYS = DEAL_KEYS.filter((key) => key in TAG_ORDER);

/** The deal tags a unit must carry one of. Filters saved before the drop-down said only "tagged". */
function chosenDeals(filters) {
  if (Array.isArray(filters.deals)) return filters.deals.filter((key) => DEAL_KEYS.includes(key));
  return filters.tagged ? STEAL_KEYS : [];
}

/** Keys of every chosen tag, in the drop-down's order. */
export function chosenTags(filters) {
  const deals = chosenDeals(filters);
  return TAG_GROUPS.flatMap((group) => group.tags.map((tag) => tag.key))
    .filter((key) => (DEAL_KEYS.includes(key) ? deals.includes(key) : Boolean(filters[key])));
}

export function tagsLabel(filters) {
  const chosen = chosenTags(filters);
  if (!chosen.length) return "Any";
  const first = TAG_GROUPS.flatMap((group) => group.tags).find((tag) => tag.key === chosen[0]).label;
  return chosen.length === 1 ? first : `${first} + ${chosen.length - 1} more`;
}

/** The filters with one tag switched on or off. */
export function setTag(filters, key, on) {
  if (!DEAL_KEYS.includes(key)) return { ...filters, [key]: Boolean(on) };
  const rest = chosenDeals(filters).filter((deal) => deal !== key);
  const next = { ...filters, deals: DEAL_KEYS.filter((deal) => rest.includes(deal) || (on && deal === key)) };
  delete next.tagged;
  return next;
}

export function countiesLabel(selected, names) {
  if (!selected || !selected.length) return "All areas";
  const first = names[selected[0]] || selected[0];
  return selected.length === 1 ? first : `${first} + ${selected.length - 1} more`;
}

const NEARBY = [["metro", "Metro", 1.0], ["grocery", "Grocery", 0.5], ["park", "Park", 0.5], ["dog_park", "Dog park", 0.5],
  ["community", "Community center", 0.5], ["library", "Library", 0.5], ["food", null, 0.5], ["gym", "Gym", 0.5], ["pharmacy", "Pharmacy", 0.5]];

/** Short tags for what is within reach of a building: "Metro 0.3 mi", "Park 0.1 mi (3 within ½ mi)", "23 places to eat within ½ mi". */
export function nearbyTags(near) {
  if (!near) return [];
  const tags = [];
  for (const [kind, name, reach] of NEARBY) {
    const [count, nearest] = near[kind] || [0, null];
    if (kind === "food") {
      if (count > 0) tags.push(`${count} place${count === 1 ? "" : "s"} to eat within ½ mi`);
      continue;
    }
    if (nearest == null || nearest > reach) continue;
    const where = nearest === 0 ? `${name} next door` : `${name} ${nearest} mi`;
    tags.push(kind === "park" && count > 1 ? `${where} (${count} within ½ mi)` : where);
  }
  return tags;
}

export function walkText(walk) {
  return walk && walk.score != null ? `Walkability ${walk.score} of 20${walk.label ? ` (${walk.label.toLowerCase()})` : ""}` : "";
}

export function dogText(dog) {
  return dog && dog.score != null ? `Dog-friendly ${dog.score} of 5` : "";
}

export function tagLabel(tag) {
  return TAG_LABELS[tag] || "";
}

function versus(pct) {
  const whole = Math.round(Math.abs(pct));
  if (whole === 0) return "in line with";
  return `${whole}% ${pct < 0 ? "under" : "over"}`;
}

export function tagReason(unit) {
  const parts = [];
  if (unit.own) parts.push(`${versus(unit.own.pct)} ${unit.own.n} similar units in this building`);
  if (unit.local) {
    const l = unit.local;
    parts.push(`${versus(l.pct)} ${l.n} units in ${l.buildings} buildings within ${l.miles} mile${l.miles === 1 ? "" : "s"}`);
  }
  return parts.join(" · ");
}

const median = (numbers) => {
  const sorted = [...numbers].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = sorted.length >> 1;
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

/**
 * The typical building's crime counts (the median over buildings that have counts), or null when there is nothing
 * to measure against. Also writes each building's `crime.x`: its violent count as a multiple of the typical one.
 */
export function relateCrime(buildings) {
  const counted = buildings.filter((b) => b.crime);
  const violent = median(counted.map((b) => b.crime.violent));
  for (const b of counted) b.crime.x = violent ? Math.round((b.crime.violent / violent) * 100) / 100 : null;
  if (!violent) return null;
  return { violent, property: median(counted.map((b) => b.crime.property)), buildings: counted.length };
}

/** A multiple of the typical in words: "half", "a quarter of", "60% of", "2.5×"; null when it is about the same. */
function times(x) {
  if (Math.abs(x - 1) <= 0.1) return null;
  if (Math.abs(x - 0.5) <= 0.05) return "half";
  if (Math.abs(x - 0.25) <= 0.05) return "a quarter of";
  if (Math.abs(x - 0.75) <= 0.03) return "three quarters of";
  return x < 1 ? `${Math.round(x * 100)}% of` : `${Math.round(x * 10) / 10}×`;
}

/** One stop of the violent-crime limit: "half the typical or less (10 or fewer)". */
export function crimeStopLabel(x, typical) {
  if (x == null) return "any";
  const count = typical ? ` (${Math.floor(x * typical.violent)} or fewer)` : "";
  if (x > 1) return `up to ${x}× the typical${count}`;
  return `${x === 1 ? "the typical" : `${times(x)} the typical`} or less${count}`;
}

/** The crime line for a building: counts when known (and how they compare, given the typical), and why not when unknown. */
export function crimeText(building, crimeCounties, typical) {
  const crime = building.crime;
  if (crime) {
    const month = (day) => `${MONTHS[Number(day.slice(5, 7)) - 1]} ${day.slice(0, 4)}`;
    const when = crime.period ? `${month(crime.period[0])} to ${month(crime.period[1])} (the last year published here)` : "past 12 months";
    const against = typical && crime.x != null
      ? ` (${times(crime.x) ? `${times(crime.x)} the typical building's ${typical.violent}` : "about typical"})` : "";
    return { text: `Within ½ mile, ${when}: ${crime.violent} violent${against} · ${crime.property} property crimes`, known: true };
  }
  const covered = (crimeCounties || []).includes(building.county);
  return { text: covered ? "Crime nearby not counted yet" : "No crime data for this county", known: false };
}

/** Sentences about the census tract and ZIP code a building is in. Race is included only when asked for. */
export function areaFacts(tract, trend, zip, showRace) {
  const lines = [];
  if (trend && trend.latest != null) {
    const change = trend.year_change;
    const moved = change == null ? "" : `, ${change < 0 ? "down" : "up"} ${Math.abs(change)}% in a year`;
    lines.push(`Typical rent in ZIP ${zip}: ${money(trend.latest)}${moved}`);
  }
  if (tract) {
    if (tract.income != null) lines.push(`Median household income ${money(tract.income)}`);
    if (tract.rent != null) lines.push(`Median rent paid ${money(tract.rent)}`);
    if (tract.age != null) lines.push(`Median age ${Math.round(tract.age)}`);
    if (tract.degree != null) lines.push(`${tract.degree}% of adults have a degree`);
    if (tract.renters != null) lines.push(`${tract.renters}% of homes are rented`);
    if (showRace && tract.race) {
      const r = tract.race;
      lines.push(`${r.white}% white · ${r.black}% Black · ${r.asian}% Asian · ${r.hispanic}% Hispanic · ${r.other}% other`);
    }
  }
  return lines;
}

/** "Down $100 (4%) since Nov 15, from $2,500"; empty when the price has not dropped lately. */
export function dropText(unit) {
  const drop = unit.drop;
  return drop ? `Down ${money(drop.by)} (${Math.round(Math.abs(drop.pct))}%) since ${shortDate(drop.day)}, from ${money(drop.was)}` : "";
}

const BAND_TOP = { 45: 50, 50: 55, 55: 60, 60: 70, 70: 80, 80: 90 };
const band = (decibels) => (BAND_TOP[decibels] ? `${decibels}–${BAND_TOP[decibels]} dB` : `${decibels}+ dB`);

/** Notes about transport noise loud enough to mention: [{text, loud}]. Levels are day-long averages from the US DOT's map. */
export function noiseTags(noise) {
  if (!noise) return [];
  const tags = [];
  if (noise.air >= AIR_MENTION) tags.push({ text: `Aircraft noise ${band(noise.air)}`, loud: noise.air >= AIR_LOUD });
  if (noise.road >= GROUND_LOUD) tags.push({ text: `Road noise ${band(noise.road)}`, loud: true });
  if (noise.rail >= GROUND_LOUD) tags.push({ text: `Rail noise ${band(noise.rail)}`, loud: true });
  return tags;
}

const monthYear = (day) => `${MONTHS[Number(day.slice(5, 7)) - 1]} ${day.slice(0, 4)}`;

/** Notes about construction from building permits: a site next door, big work in the building. [{text, title}] */
export function worksTags(works) {
  if (!works) return [];
  const line = (w) => `${w.kind}, ${w.address}, ${w.miles} mi, permit ${monthYear(w.day)}: ${w.what}`;
  const tags = [];
  if (works.next.length) {
    const [first, ...rest] = works.next;
    tags.push({
      text: `Building site next door: ${first.kind.toLowerCase()} at ${first.address} (permit ${monthYear(first.day)})${rest.length ? ` + ${rest.length} more` : ""}`,
      title: works.next.map(line).join("\n"),
    });
  }
  if (works.here.length) {
    const [first] = works.here;
    tags.push({
      text: `${first.kind === "Demolition" ? "Demolition work" : first.kind} in this building (permit ${monthYear(first.day)})`,
      title: works.here.map(line).join("\n"),
    });
  }
  return tags;
}

/**
 * The setup's trade-off questions. Each asks for dollars a month against one concrete difference, so that an
 * answer means the same thing to everyone; Top picks adds those dollars up for every home (see worth()).
 */
export const TRADEOFFS = [
  { key: "commute", title: "Your commute",
    ask: "How much more rent per month would you pay to cut your drive to work by 10 minutes each way?",
    means: "Every 10 minutes shorter than the typical building's drive from your work address counts for this much; every 10 minutes longer counts against. Needs a work address.",
    options: [0, 25, 50, 100, 200, 300] },
  { key: "crime", title: "Violent crime nearby",
    ask: "How much more per month would you pay to live where violent crime within half a mile is half the typical building's, instead of typical?",
    means: "Typical is the middle building of those tracked. Half the typical counts for this much; twice the typical counts against by twice this much.",
    options: [0, 50, 100, 200, 300, 500] },
  { key: "walk", title: "Walkability",
    ask: "How much more per month would you pay for a block one step more walkable: say from \"some errands on foot\" to \"most errands on foot\"?",
    means: "One step is one band on the EPA's walkability index (it has four). Each band above the typical building's block counts for this much; each band below counts against.",
    options: [0, 25, 50, 100, 200] },
  { key: "quiet", title: "Quiet",
    ask: "How much more per month would you pay to be rid of one source of noise: aircraft overhead, or a building site next door?",
    means: "Each of these counts against a home by this much: aircraft noise of 55 decibels or more (half for 50 to 55), a building site within a block, big renovation in the building. Heavy road or rail noise counts half.",
    options: [0, 50, 100, 200, 300] },
];

const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));

/** The typical building's drive and walkability (medians over buildings that have them): what worth() measures against. */
export function typicalOf(buildings) {
  return {
    drive: median(buildings.filter((b) => b.drive != null).map((b) => b.drive)),
    walk: median(buildings.filter((b) => b.walk && b.walk.score != null).map((b) => b.walk.score)),
  };
}

/**
 * What a unit is worth to this user, in dollars a month, against an ordinary match: how far under similar units
 * it is priced, plus the user's own dollar value for its drive, its crime, its walkability and its quiet
 * (`prefs`, from the setup questions; a missing one counts for nothing). {total, share, parts: [{label, dollars}]};
 * `share` is the total as a share of the unit's own monthly cost, which is what Top picks sorts on: sorted on
 * dollars alone, the dearest homes would always come first.
 * Each of the user's values is capped at twice the amount they named, so one extreme cannot drown the rest.
 */
export function worth(unit, building, prefs, typical) {
  const p = prefs || {}, t = typical || {};
  const parts = [];
  const add = (label, dollars) => { if (Math.round(dollars)) parts.push({ label, dollars: Math.round(dollars) }); };

  const price = cost(unit);
  // what it would take to reach the others' price; a discount past MOST_DISCOUNT is more likely a mismatch than a bargain
  const shares = [unit.own, unit.local].filter(Boolean).map((vs) => Math.max(vs.pct, -MOST_DISCOUNT)).map((pct) => -pct / (100 + pct));
  if (price != null && shares.length && unit.tag !== "check") {
    const saving = (price * shares.reduce((sum, share) => sum + share, 0)) / shares.length;
    add(saving >= 0 ? "under similar units" : "over similar units", saving);
  }
  if (p.commute && building.drive != null && t.drive != null) {
    const minutes = Math.round(t.drive - building.drive);
    add(`${Math.abs(minutes)} min ${minutes >= 0 ? "shorter" : "longer"} drive than typical`, clamp((minutes / 10) * p.commute, 2 * p.commute));
  }
  if (p.crime && building.crime && building.crime.x != null) {
    const x = building.crime.x;
    add(`${times(x) || "about"} the typical violent crime`, clamp(((1 - x) / 0.5) * p.crime, 2 * p.crime));
  }
  if (p.walk && building.walk && building.walk.score != null && t.walk != null) {
    const bands = (building.walk.score - t.walk) / WALK_BAND;
    add(`${bands >= 0 ? "more" : "less"} walkable than typical`, clamp(bands * p.walk, 2 * p.walk));
  }
  if (p.quiet) {
    const noise = building.noise || {};
    if (noise.air >= AIR_LOUD) add("aircraft noise", -p.quiet);
    else if (noise.air >= AIR_MENTION) add("some aircraft noise", -p.quiet / 2);
    if (noise.road >= GROUND_LOUD || noise.rail >= GROUND_LOUD) add("road or rail noise", -p.quiet / 2);
    const works = building.works || { next: [], here: [] };
    if (works.next.length) add("building site next door", -p.quiet);
    if (works.here.length) add("big work in the building", -p.quiet);
  }
  const total = parts.reduce((sum, part) => sum + part.dollars, 0);
  return { total, share: price ? Math.round((total / price) * 10000) / 10000 : 0, parts };
}

/** "About $461 a month in its favour: $361 under similar units · +$100 for 10 min shorter drive than typical". */
export function worthText(value) {
  if (!value || !value.parts.length) return "";
  const said = value.parts.map((part) => (/^(under|over) /.test(part.label)
    ? `${money(Math.abs(part.dollars))} ${part.label}`
    : `${part.dollars > 0 ? "+" : "−"}${money(Math.abs(part.dollars))} for ${part.label}`));
  const head = value.total > 0 ? `About ${money(value.total)} a month in its favour`
    : value.total < 0 ? `About ${money(-value.total)} a month against it` : "Evens out";
  const share = value.share ? ` (${Math.round(Math.abs(value.share) * 100)}% of its cost)` : "";
  return `${head}${share}: ${said.join(" · ")}`;
}

/** "38 min drive to work (no traffic)"; empty when the time is not known. */
export function driveLabel(minutes, evening) {
  if (minutes == null) return "";
  const time = (m) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);
  if (evening === undefined) return `${time(minutes)} drive to work (no traffic)`;
  return `${time(minutes)} to work${evening == null ? "" : `, ${time(evening)} home`} (typical traffic)`;
}

/** The drive to work, for the map's pop-up: the time when it is known, and what to do when it is not. */
export function tripText(building, hasWork) {
  if (!hasWork) return "Set a work address to see the drive from here";
  if (building.drive == null) return "Drive to work not timed yet: press Time my drive";
  return building.driveTraffic ? driveLabel(building.drive, building.drivePm) : driveLabel(building.drive);
}

export function money(n) {
  return n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US");
}

export function perSqft(unit) {
  const value = costPerSqft(unit);
  return value == null ? "" : `$${value.toFixed(2)}/sqft`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The note on a building whose latest read failed: since when its figures date, and why if the run recorded it. */
export function staleText(building) {
  if (!building.stale) return "";
  if (building.expired && building.read) {
    return `Not read since ${shortDate(building.read)}${building.why ? ` (${building.why})` : ""}; prices withdrawn until it reads again`;
  }
  return `Latest read failed${building.why ? ` (${building.why})` : ""}; showing ${building.read ? shortDate(building.read) : "earlier data"}`;
}

export function shortDate(day) {
  if (!day) return "";
  const [, month, date] = day.split("-").map(Number);
  return `${MONTHS[month - 1]} ${date}`;
}

/** "Available now" for a date that has passed, "Available Nov 29" for one ahead; `today` is a YYYY-MM-DD day. */
export function availability(day, today) {
  if (!day) return "";
  return day <= today ? "Available now" : `Available ${shortDate(day)}`;
}

export function ago(isoTime, now = new Date()) {
  const minutes = Math.floor((now - new Date(isoTime)) / 60000);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"} ago`;
  if (minutes < 5) return "just now";
  if (minutes < 60) return plural(minutes, "minute");
  if (minutes < 60 * 24) return plural(Math.round(minutes / 60), "hour");
  return plural(Math.round(minutes / (60 * 24)), "day");
}

/** SVG path data for a unit's rent over time, or null when there is nothing to draw yet. */
export function sparkline(history, width, height) {
  if (!history || history.length < 2) return null;
  const times = history.map((point) => Date.parse(point[0]));
  const rents = history.map((point) => point[1]);
  const t0 = times[0], span = times[times.length - 1] - t0 || 1;
  const low = Math.min(...rents), range = Math.max(...rents) - low || 1;
  return history.map((_, i) => {
    const x = ((times[i] - t0) / span) * width;
    const y = height - ((rents[i] - low) / range) * height;
    return `${i ? "L" : "M"}${+x.toFixed(1)} ${+y.toFixed(1)}`;
  }).join("");
}

/**
 * Where a building's rating comes from, for the small label beside its stars: Google's (the same scale for every
 * building, refreshed weekly), else the one the manager publishes on its own site. Null without a rating.
 */
export function ratingSource(building) {
  if (!building || building.rating == null || !(building.rating > 0)) return null;
  if (building.rating_source === "google") {
    const own = building.manager_rating > 0
      ? ` The manager's own site says ${building.manager_rating}${building.manager_rating_count != null ? ` from ${building.manager_rating_count.toLocaleString("en-US")} reviews` : ""}.`
      : "";
    return { label: "Google", url: building.rating_url || null,
      title: `Rating on Google${building.rating_at ? `, as of ${shortDate(building.rating_at)}` : ""}.${own}` };
  }
  return { label: "manager's site", url: null, title: "Rating published on the manager's own site. Google has none for this building yet." };
}

/**
 * A building's colour comes from its rating, in the same five tiers as the owner's catalogue: 3.5+, 4.0+, 4.4+,
 * 4.7+ and 4.9+, cool to hot. `light` is the hex used on the map, whose tiles do not change with the page's theme;
 * the page itself uses the --heat-N tokens in app.css, which have a dark-mode set.
 */
export const RATING_TIERS = [
  { tier: 1, at: 3.5, label: "3.5+", light: "#1f6fb2" },
  { tier: 2, at: 4.0, label: "4.0+", light: "#0f7f6f" },
  { tier: 3, at: 4.4, label: "4.4+", light: "#a05a00" },
  { tier: 4, at: 4.7, label: "4.7+", light: "#c2410c" },
  { tier: 5, at: 4.9, label: "4.9+", light: "#b0177a" },
];
export const LOW_RATING_COLOUR = "#6b6862";

/** 0 to 5: how many tier thresholds the rating reaches. Null without a rating (or a rating of 0, which no reviewer gives). */
export function ratingTier(rating) {
  if (rating == null || !(rating > 0)) return null;
  return RATING_TIERS.filter((t) => rating >= t.at).length;
}

/** The ring round a building's dot on the map: its tier's colour, grey below 3.5, null without a rating. */
export function ratingColour(rating) {
  const tier = ratingTier(rating);
  if (tier == null) return null;
  return tier ? RATING_TIERS[tier - 1].light : LOW_RATING_COLOUR;
}
