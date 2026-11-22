// What the page remembers in this browser: filters, followed units and buildings, and which units each followed
// building listed at the last visit, with their tags. Nothing here leaves the browser.
// Storage can be missing or blocked (a private window); then everything still works, just not across visits.

import { DEFAULT_FILTERS, cost, dropText, unitTitle } from "./logic.js";

const FILTERS = "apt.filters";
const STARS = "apt.stars";
const SETTINGS = "apt.settings";
const FOLLOWS = "apt.follows";
const NEWS = "apt.news";
const NEWS_DAYS = 14;         // how long a newly tagged unit stays announced...
const NEWS_MOST = 60;         // ...and how many are kept at once

const daysApart = (from, to) => Math.round((Date.parse(to) - Date.parse(from)) / 864e5);

export function createStore(storage) {
  const memory = {};

  function read(key, fallback) {
    try {
      const text = storage ? storage.getItem(key) : null;
      if (text != null) return JSON.parse(text);
    } catch { /* blocked or corrupt: fall through */ }
    return key in memory ? memory[key] : fallback;
  }

  function write(key, value) {
    memory[key] = value;
    try {
      if (storage) storage.setItem(key, JSON.stringify(value));
    } catch { /* blocked: kept in memory only */ }
  }

  function getFilters() {
    const saved = read(FILTERS, {});
    const filters = { ...DEFAULT_FILTERS };
    if (saved && typeof saved === "object") {
      for (const key of Object.keys(DEFAULT_FILTERS)) {
        if (key in saved) filters[key] = saved[key];
      }
    }
    if (!Array.isArray(filters.beds)) filters.beds = [];
    if (!Array.isArray(filters.counties)) filters.counties = [];
    if (!filters.area || typeof filters.area !== "object" || Array.isArray(filters.area)) filters.area = {};
    return filters;
  }

  function stars() {
    const saved = read(STARS, []);
    return Array.isArray(saved) ? saved.filter((star) => star && star.unit && star.unit.id) : [];
  }

  /** {seen: {building id: {unit id listed at the last visit: its tag, or ""}}, notes: [newly tagged units, newest first]}. */
  function news() {
    const saved = read(NEWS, {});
    const good = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    return {
      seen: good.seen && typeof good.seen === "object" && !Array.isArray(good.seen) ? good.seen : {},
      notes: Array.isArray(good.notes) ? good.notes.filter((note) => note && note.id && note.building && note.day) : [],
    };
  }

  const slim = (building) => building && {
    id: building.id, name: building.name, url: building.url, neighborhood: building.neighborhood, address: building.address,
  };

  return {
    getFilters,
    getSetting(key, fallback) {
      const saved = read(SETTINGS, {});
      return saved && typeof saved === "object" && key in saved ? saved[key] : fallback;
    },
    setSetting(key, value) {
      const saved = read(SETTINGS, {});
      write(SETTINGS, { ...(saved && typeof saved === "object" ? saved : {}), [key]: value });
    },
    setFilters(filters) { write(FILTERS, filters); },
    stars,

    /** Everything except the Google key, as text that importText() accepts in another browser. */
    exportText(when) {
      const settings = { ...(read(SETTINGS, {}) || {}) };
      delete settings.googleKey;
      delete settings.drive;                                   // a cache; it is rebuilt
      return JSON.stringify({
        app: "apartment-tracker", version: 1, exported: when,
        filters: getFilters(), stars: stars(), follows: this.follows(), settings,
      }, null, 1);
    },

    /** Replace this browser's filters, followed things and settings with an export. The Google key here is kept. */
    importText(text) {
      let data;
      try { data = JSON.parse(text); } catch { return { ok: false }; }
      if (!data || typeof data !== "object" || data.app !== "apartment-tracker") return { ok: false };
      const key = (read(SETTINGS, {}) || {}).googleKey;
      const settings = data.settings && typeof data.settings === "object" ? { ...data.settings } : {};
      delete settings.googleKey;
      if (key) settings.googleKey = key;
      write(SETTINGS, settings);
      write(FILTERS, data.filters && typeof data.filters === "object" ? data.filters : {});
      write(STARS, Array.isArray(data.stars) ? data.stars : []);
      write(FOLLOWS, Array.isArray(data.follows) ? data.follows : []);
      return { ok: true, stars: stars().length, follows: this.follows().length };
    },

    /** Buildings being followed: [{id, name}]. */
    follows() {
      const saved = read(FOLLOWS, []);
      return Array.isArray(saved) ? saved.filter((follow) => follow && follow.id) : [];
    },
    isFollowing(id) { return this.follows().some((follow) => follow.id === id); },

    /** Follow or stop following a building. Returns true when it is now followed. */
    toggleFollow(building) {
      const current = this.follows();
      const without = current.filter((follow) => follow.id !== building.id);
      const following = without.length === current.length;
      if (following) without.push({ id: building.id, name: building.name });
      write(FOLLOWS, without);
      return following;
    },
    isStarred(id) { return stars().some((star) => star.unit.id === id); },

    /**
     * Newly tagged units in followed buildings, newest first:
     * [{id, building, name, title, tag, kind, drop, beds, sqft, cost, url, first, day}]. `kind` is "new" for a unit
     * that was not listed before and "tagged" for one that was listed without a tag; `drop` is its price drop in words.
     */
    arrivals() { return news().notes; },
    clearArrivals() { write(NEWS, { ...news(), notes: [] }); },

    /**
     * Compare what each followed building (followed itself, or holding a followed unit) lists now with what it listed
     * at the last call, and announce every unit that carries a tag and did not then: one that is newly listed, or one
     * that was listed without a tag (a tag appears when a price moves). A tag that turns into another is not news.
     * A building's first call only records what it lists. While a building cannot be read, or is missing from the
     * data, nothing it listed is forgotten, so a failed read never announces old units as new. A unit announced
     * again replaces its older announcement. `today` is a YYYY-MM-DD day. Returns arrivals().
     */
    noteArrivals(unitsByBuilding, buildingsById, today) {
      const before = news();
      const watched = new Set([...this.follows().map((follow) => follow.id), ...stars().map((star) => star.unit.building)]);
      const seen = {};
      const found = [];
      for (const id of watched) {
        const building = buildingsById[id];
        const was = before.seen[id];
        const known = was && typeof was === "object" && !Array.isArray(was) ? was : null;
        if (!building) { if (known) seen[id] = known; continue; }
        const live = unitsByBuilding[id] || [];
        if (known) {
          for (const unit of live) {
            if (!unit.tag || known[unit.id]) continue;             // no tag, or it carried one already
            found.unshift({
              id: unit.id, building: id, name: building.name, title: unitTitle(unit), tag: unit.tag, beds: unit.beds,
              sqft: unit.sqft, cost: cost(unit), url: unit.url, first: unit.first, day: today,
              kind: Object.hasOwn(known, unit.id) ? "tagged" : "new", drop: dropText(unit) || null,
            });
          }
        }
        const listed = Object.fromEntries(live.map((unit) => [unit.id, unit.tag || ""]));
        seen[id] = known && (building.stale || building.expired) ? { ...known, ...listed } : listed;
      }
      const again = new Set(found.map((note) => note.id));
      const notes = [...found, ...before.notes.filter((note) => !again.has(note.id))]
        .filter((note) => watched.has(note.building) && daysApart(note.day, today) <= NEWS_DAYS).slice(0, NEWS_MOST);
      write(NEWS, { seen, notes });
      return notes;
    },

    /** Star or unstar a unit. Returns true when it is now starred. */
    toggleStar(unit, building) {
      const current = stars();
      const without = current.filter((star) => star.unit.id !== unit.id);
      const starring = without.length === current.length;
      if (starring) without.push({ unit, building: slim(building), listed: true });
      write(STARS, without);
      return starring;
    },

    /** Bring starred copies up to date: units still in the data are refreshed, the rest stay as last seen. */
    refreshStars(unitsById, buildingsById) {
      write(STARS, stars().map((star) => {
        const fresh = unitsById[star.unit.id];
        if (!fresh) return { ...star, listed: false };
        return { unit: fresh, building: slim(buildingsById[fresh.building]) || star.building, listed: true };
      }));
    },
  };
}
