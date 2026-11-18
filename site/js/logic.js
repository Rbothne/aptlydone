// Every decision the page makes, as plain functions with no browser in them, so they can be tested with Node.

export const DEFAULT_FILTERS = Object.freeze({
  q: "", beds: [], minSqft: null, maxCost: null, moveBy: null, floorMin: null, floorMax: null, ground: false,
  laundry: false, parking: false, pets: false, tagged: false, maxViolent: null, maxDrive: null, minRating: null, manager: "", county: "", showRestricted: false, sort: "picks",
});

export const GROUND_FLOORS = [0, 1];          // buildings number the ground floor either way
const TAG_ORDER = { absolute: 0, building: 1, local: 2 };
const TAG_LABELS = { absolute: "Absolute steal", building: "Building steal", local: "Local value" };

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
  if (filters.laundry && building.laundry !== "in_unit") return false;
  if (filters.parking && building.parking_from == null) return false;
  if (filters.pets && building.pets !== true) return false;
  if (filters.tagged && !unit.tag) return false;
  if (filters.maxViolent != null && !(building.crime && building.crime.violent <= filters.maxViolent)) return false;
  if (filters.maxDrive != null && !(building.drive != null && building.drive <= filters.maxDrive)) return false;
  if (filters.minRating != null && !(building.rating != null && building.rating >= filters.minRating)) return false;
  if (filters.manager && building.manager !== filters.manager) return false;
  if (filters.county && building.county !== filters.county) return false;
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
  picks: chain(by((u) => TAG_ORDER[u.tag] ?? 3), by((u) => u.own?.pct), by(costPerSqft)),
  cost: by(cost),
  ppsf: by(costPerSqft),
  own: by((u) => u.own?.pct),
  local: by((u) => u.local?.pct),
  newest: by((u) => u.first, true),
  size: by((u) => u.sqft, true),
  drive: by((u) => u.drive),
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
      tag: units.reduce((top, unit) => ((TAG_ORDER[unit.tag] ?? 3) < (TAG_ORDER[top] ?? 3) ? unit.tag : top), null),
    }));
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
    return { text: `Within ½ mile, past 12 months: ${crime.violent} violent · ${crime.property} property crimes`, known: true };
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
export function driveLabel(minutes) {
  if (minutes == null) return "";
  const time = minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  return `${time} drive to work (no traffic)`;
}

export function money(n) {
  return n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US");
}

export function perSqft(unit) {
  const value = costPerSqft(unit);
  return value == null ? "" : `$${value.toFixed(2)}/sqft`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
