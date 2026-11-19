// Every decision the page makes, as plain functions with no browser in them, so they can be tested with Node.

export const DEFAULT_FILTERS = Object.freeze({
  q: "", beds: [], minSqft: null, maxCost: null, moveBy: null, floorMin: null, floorMax: null, ground: false,
  parking: false, pets: false, nearMetro: false, nearGrocery: false, nearPark: false, dogFriendly: false, minWalk: null, deals: [], highEnd: false, maxViolent: null, maxDrive: null, minRating: null, manager: "", counties: [], showRestricted: false, sort: "picks",
});

export const HIGH_END = 67;                 // a building pricier than this share of its neighbours is "high-end for its area"
export const GROUND_FLOORS = [0, 1];
export const NEAR_MILES = 0.5;                // "near" a Metro station or a grocery store
export const PARK_MILES = 0.25;               // a park has to be closer than that to count as next to home
export const DOG_FRIENDLY = 3;                // dog score, out of 5, that the Dog-friendly filter asks for

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

function searchable(building) {
  const a = building.address || {};
  return [building.name, building.neighborhood, building.manager, a.city, a.zip, a.street, a.full]
    .filter(Boolean).join(" ").toLowerCase();
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
  if (filters.parking && building.parking_from == null && building.parking !== true) return false;
  if (filters.pets && building.pets !== true) return false;
  if (filters.nearMetro && !within(building, "metro", NEAR_MILES)) return false;
  if (filters.nearGrocery && !within(building, "grocery", NEAR_MILES)) return false;
  if (filters.nearPark && !within(building, "park", PARK_MILES)) return false;
  if (filters.dogFriendly && !(building.dog && building.dog.score >= DOG_FRIENDLY)) return false;
  if (filters.minWalk != null && !(building.walk && building.walk.score >= filters.minWalk)) return false;
  const deals = chosenDeals(filters);
  if (deals.length && !deals.includes(unit.tag)) return false;
  if (filters.highEnd && !(building.rank && building.rank.pct >= HIGH_END)) return false;
  if (filters.maxViolent != null && !(building.crime && building.crime.violent <= filters.maxViolent)) return false;
  if (filters.maxDrive != null && !(building.drive != null && building.drive <= filters.maxDrive)) return false;
  if (filters.minRating != null && !(building.rating != null && building.rating >= filters.minRating)) return false;
  if (filters.manager && building.manager !== filters.manager) return false;
  if (filters.nogo && building.zip && filters.nogo.includes(building.zip)) return false;
  if (filters.counties && filters.counties.length && !filters.counties.includes(building.county)) return false;
  const q = filters.q.trim().toLowerCase();
  if (q && !searchable(building).includes(q)) return false;
  return true;
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

const SORTS = {
  picks: chain(by((u) => (u.tag === "check" ? 4 : TAG_ORDER[u.tag] ?? 3)), by((u) => u.own?.pct), by(costPerSqft)),
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
      count: units.length, best: best[0],
      tag: units.reduce((top, unit) => (isSteal(unit.tag) && (TAG_ORDER[unit.tag] ?? 3) < (TAG_ORDER[top] ?? 3) ? unit.tag : top), null),
    }));
}

/** What "follow this building" remembers: the size and price filters in force when it was followed. */
export function criteriaFrom(filters) {
  return { beds: [...filters.beds], minSqft: filters.minSqft, maxCost: filters.maxCost };
}

export function criteriaFilters(criteria) {
  const c = criteria || {};
  return { ...DEFAULT_FILTERS, beds: Array.isArray(c.beds) ? c.beds : [], minSqft: c.minSqft ?? null, maxCost: c.maxCost ?? null };
}

export function criteriaLabel(criteria) {
  const c = criteria || {};
  const parts = [];
  const beds = (Array.isArray(c.beds) ? [...c.beds] : []).sort();
  if (beds.length) {
    const names = beds.map((n) => (n === 0 ? "Studio" : n === 3 ? "3+" : String(n)));
    parts.push(names.join(" or ") + (beds.length === 1 && beds[0] === 0 ? "" : " bed"));
  }
  if (c.minSqft != null) parts.push(`${c.minSqft}+ sqft`);
  if (c.maxCost != null) parts.push(`up to ${money(c.maxCost)}`);
  return parts.join(" · ") || "any unit";
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
    { key: "local", label: "Local value", title: "20% or more below similar units in buildings within one to two miles" }] },
  { name: "Nearby", note: "all of these", tags: [
    { key: "nearMetro", label: "Near Metro", title: "A Metro station within half a mile" },
    { key: "nearGrocery", label: "Grocery nearby", title: "A supermarket within half a mile" },
    { key: "nearPark", label: "Park nearby", title: "A park within a quarter mile" },
    { key: "dogFriendly", label: "Dog-friendly", title: "Pets allowed, plus at least two of: a dog park within half a mile, a park within a quarter mile, a dog run or pet spa on site" }] },
  { name: "Building", note: "all of these", tags: [
    { key: "ground", label: "Ground floor", title: "Units on the ground floor only" },
    { key: "parking", label: "Parking", title: "The building lists parking" },
    { key: "pets", label: "Pets", title: "The building says pets are allowed" },
    { key: "highEnd", label: "High-end", title: "Buildings whose one-bedroom cost per sqft is in the top third of buildings within two miles" }] },
];
const DEAL_KEYS = TAG_GROUPS[0].tags.map((tag) => tag.key);

/** The deal tags a unit must carry one of. Filters saved before the drop-down said only "tagged". */
function chosenDeals(filters) {
  if (Array.isArray(filters.deals)) return filters.deals.filter((key) => DEAL_KEYS.includes(key));
  return filters.tagged ? DEAL_KEYS : [];
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

/** The crime line for a building: counts when known, and why not when unknown. */
export function crimeText(building, crimeCounties) {
  const crime = building.crime;
  if (crime) {
    const month = (day) => `${MONTHS[Number(day.slice(5, 7)) - 1]} ${day.slice(0, 4)}`;
    const when = crime.period ? `${month(crime.period[0])} to ${month(crime.period[1])} (the last year published here)` : "past 12 months";
    return { text: `Within ½ mile, ${when}: ${crime.violent} violent · ${crime.property} property crimes`, known: true };
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

/** "38 min drive to work (no traffic)"; empty when the time is not known. */
export function driveLabel(minutes, evening) {
  if (minutes == null) return "";
  const time = (m) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);
  if (evening === undefined) return `${time(minutes)} drive to work (no traffic)`;
  return `${time(minutes)} to work${evening == null ? "" : `, ${time(evening)} home`} (typical traffic)`;
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
