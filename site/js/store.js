// What the page remembers in this browser: filters and starred units. Nothing here leaves the browser.
// Storage can be missing or blocked (a private window); then everything still works, just not across visits.

import { DEFAULT_FILTERS } from "./logic.js";

const FILTERS = "apt.filters";
const STARS = "apt.stars";
const SETTINGS = "apt.settings";
const FOLLOWS = "apt.follows";

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
    return filters;
  }

  function stars() {
    const saved = read(STARS, []);
    return Array.isArray(saved) ? saved.filter((star) => star && star.unit && star.unit.id) : [];
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

    /** Buildings being followed: [{id, name, criteria}]. */
    follows() {
      const saved = read(FOLLOWS, []);
      return Array.isArray(saved) ? saved.filter((follow) => follow && follow.id) : [];
    },
    isFollowing(id) { return this.follows().some((follow) => follow.id === id); },

    /** Follow or stop following a building. Returns true when it is now followed. */
    toggleFollow(building, criteria) {
      const current = this.follows();
      const without = current.filter((follow) => follow.id !== building.id);
      const following = without.length === current.length;
      if (following) without.push({ id: building.id, name: building.name, criteria });
      write(FOLLOWS, without);
      return following;
    },
    isStarred(id) { return stars().some((star) => star.unit.id === id); },

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
