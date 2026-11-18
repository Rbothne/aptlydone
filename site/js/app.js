// Loads the data files and draws the page. Every decision (what matches, what order, what words) is in logic.js.

import {
  DEFAULT_FILTERS, ago, availability, cost, groupBuildings, money, perSqft, shortDate, sparkline, tagLabel, tagReason, unitMatches,
} from "./logic.js";
import { createStore } from "./store.js";

const COUNTY = {
  "11001": "Washington, DC", "51013": "Arlington, VA", "51510": "Alexandria, VA", "51059": "Fairfax County, VA",
  "51600": "Fairfax City, VA", "51610": "Falls Church, VA", "51107": "Loudoun, VA", "51153": "Prince William, VA",
  "51683": "Manassas, VA", "51685": "Manassas Park, VA", "24031": "Montgomery, MD", "24033": "Prince George's, MD",
  "24027": "Howard, MD", "24003": "Anne Arundel, MD",
};
const PAGE = 30;          // buildings drawn at a time
const BEST = 5;           // units shown per building before "show all"
const ROOM_SQFT = 300;

let storage = null;
try { storage = window.localStorage; } catch { /* blocked: the store works in memory */ }
const store = createStore(storage);

const state = {
  updated: null, index: [], byId: {}, units: {}, unitsById: {},
  filters: store.getFilters(), tab: "buildings", shown: PAGE, expanded: new Set(), open: new Set(),
};

const $ = (id) => document.getElementById(id);

/** Build an element: h("div", {class: "x"}, child, "text", ...). Null and false children are skipped. */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(child));
  }
  return el;
}

function svg(pathData) {
  const ns = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(ns, "svg");
  el.setAttribute("class", "spark");
  el.setAttribute("viewBox", "0 0 60 18");
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", "Rent over time");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", pathData);
  el.append(path);
  return el;
}

const bedsLabel = (beds) => (beds === 0 ? "Studio" : beds == null ? "" : `${beds} bed`);
const plural = (n, word) => `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`;

function address(building) {
  const a = building.address || {};
  if (a.full) return a.full;
  return [a.city, [a.state, a.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
}

// ---------- unit rows ----------

function comparison(unit) {
  const parts = [];
  const one = (pct, label) => h("span", { class: pct <= -5 ? "under" : null }, `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(Math.round(pct))}% ${label}`);
  if (unit.own) parts.push(one(unit.own.pct, "vs building"));
  if (unit.local) parts.push(one(unit.local.pct, "vs nearby"));
  return parts.flatMap((part, i) => (i ? [" · ", part] : [part]));
}

function unitRow(unit, building, listed = true) {
  const starred = store.isStarred(unit.id);
  const spark = sparkline(unit.history, 60, 18);
  const row = h("div", { class: "unit" + (listed ? "" : " gone"), role: "button", tabindex: "0", "aria-expanded": state.open.has(unit.id) ? "true" : "false" },
    h("button", {
      class: "star", type: "button", "aria-pressed": String(starred), title: starred ? "Stop following" : "Follow this unit",
      "aria-label": starred ? "Stop following" : "Follow this unit",
      onclick: (event) => { event.stopPropagation(); store.toggleStar(unit, building); draw(); },
    }, starred ? "★" : "☆"),
    h("div", { class: "what" },
      unit.tag && h("span", { class: `tag ${unit.tag}` }, tagLabel(unit.tag)),
      h("b", null, `#${unit.unit}`), " · ",
      [bedsLabel(unit.beds), unit.baths != null && `${unit.baths} bath`, unit.sqft && `${unit.sqft.toLocaleString("en-US")} sqft`,
        unit.floor != null && `floor ${unit.floor}`].filter(Boolean).join(" · "),
      unit.sqft && unit.sqft < ROOM_SQFT && h("span", { class: "note" }, "room"),
      unit.restricted === true && h("span", { class: "note" }, "income-restricted"),
      !listed && h("span", { class: "note" }, "no longer listed")),
    h("div", { class: "price" },
      h("b", null, money(cost(unit))), h("small", null, "/mo "), h("small", null, perSqft(unit)),
      unit.true_offer != null && h("small", { class: "if" }, `${money(unit.true_offer)} if the building's offer applies`)),
    h("div", { class: "vs" }, comparison(unit)),
    h("div", { class: "when" },
      [listed && availability(unit.available, new Date().toISOString().slice(0, 10)), unit.lease && `${unit.lease}-month lease`]
        .filter(Boolean).join(" · ")),
    spark ? svg(spark) : h("span", null));

  const toggle = () => {
    if (state.open.has(unit.id)) state.open.delete(unit.id); else state.open.add(unit.id);
    const next = row.nextElementSibling;
    if (next && next.classList.contains("detail")) next.remove();
    else row.after(detail(unit, building));
    row.setAttribute("aria-expanded", String(state.open.has(unit.id)));
  };
  row.addEventListener("click", toggle);
  row.addEventListener("keydown", (event) => {
    if (event.target === row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); toggle(); }
  });
  return state.open.has(unit.id) ? [row, detail(unit, building)] : [row];
}

function detail(unit, building) {
  const fees = unit.fees || 0;
  const lease = unit.lease || 12;
  const oneTime = building.one_time || 0;
  const rows = [["Rent", money(unit.rent)]];
  if (fees) rows.push(["Required monthly fees", money(fees)]);
  if (oneTime) rows.push([`One-time fees (${money(oneTime)}) over ${lease} months`, money(oneTime / lease)]);
  if (unit.special) rows.push(["Concession on this unit", unit.special]);
  const history = unit.history || [];

  return h("div", { class: "detail" },
    h("div", { class: "plan" },
      unit.plan_image
        ? h("img", { src: unit.plan_image, alt: `Floor plan ${unit.plan || ""}`, loading: "lazy", referrerpolicy: "no-referrer" })
        : h("p", { class: "muted" }, "No floor-plan drawing published."),
      unit.plan && h("small", null, `Floor plan ${unit.plan}`)),
    h("div", null,
      h("section", null,
        h("h3", null, "Monthly cost"),
        h("table", null,
          rows.map(([label, value]) => h("tr", null, h("td", null, label), h("td", null, value))),
          h("tr", { class: "total" }, h("td", null, "True monthly cost"), h("td", null, unit.true != null ? money(unit.true) : "not known")),
          unit.true_offer != null && h("tr", null, h("td", null, "If the building's offer applies"), h("td", null, money(unit.true_offer)))),
        building.parking_from != null && h("small", null, `Parking is extra, from ${money(building.parking_from)}/mo. `),
        h("small", null, "Optional fees and usage-based utilities are not included.")),
      tagReason(unit) && h("section", null, h("h3", null, "How it compares"), h("p", { style: "margin:0" }, tagReason(unit) + ".")),
      h("section", null,
        h("h3", null, "Price history"),
        h("ul", null, history.map((point) => h("li", null,
          `${shortDate(point[0])}: ${money(point[1])}`, point[3] ? ` on ${point[3]} months` : "", point[2] ? ` · ${point[2]}` : ""))),
        h("small", null, unit.first ? `Tracked since ${shortDate(unit.first)}. ` : "",
          building.read ? `Last read ${shortDate(building.read)}.` : "")),
      h("section", null, h("a", { href: unit.url || building.url, target: "_blank", rel: "noopener" }, "Open the building's site ↗"))));
}

// ---------- building cards ----------

function facts(building) {
  const items = [];
  if (building.laundry === "in_unit") items.push(["In-unit laundry"]);
  else if (building.laundry === "shared") items.push(["Shared laundry"]);
  else items.push(["Laundry not stated", "unknown"]);
  if (building.parking_from != null) items.push([`Parking from ${money(building.parking_from)}/mo`]);
  else items.push(["Parking not stated", "unknown"]);
  if (building.pets) items.push(["Pets allowed"]);
  if (building.one_time) items.push([`One-time fees ${money(building.one_time)}`]);
  if (building.rank) items.push([`Pricier than ${building.rank.pct}% of ${building.rank.n} buildings within 2 miles`]);
  if (building.coming_soon) items.push(["Coming soon"]);
  if (building.senior) items.push(["Senior housing"]);
  if (building.stale) items.push([`Latest read failed; showing ${building.read ? shortDate(building.read) : "earlier data"}`, "stale"]);
  return h("ul", { class: "facts" }, items.map(([text, kind]) => h("li", { class: kind || null }, text)));
}

function buildingCard(group) {
  const { building, units, best } = group;
  const all = state.expanded.has(building.id);
  const shown = all ? units : best;
  return h("article", { class: "building" },
    h("header", null,
      h("h2", null, h("a", { href: building.url, target: "_blank", rel: "noopener" }, building.name)),
      building.rating != null
        ? h("span", { class: "rating", title: "Rating published on the manager's site" }, `★ ${building.rating}`,
            building.rating_count != null && h("small", null, ` (${building.rating_count.toLocaleString("en-US")})`))
        : h("span", null),
      h("div", { class: "where" }, [building.neighborhood, address(building), building.manager].filter(Boolean).join(" · "))),
    building.special && h("p", { class: "offer" }, building.special,
      h("small", null, "Building-wide offer: it may not apply to every unit.")),
    facts(building),
    h("div", { class: "units" }, shown.flatMap((unit) => unitRow(unit, building))),
    units.length > best.length && h("button", {
      class: "more", type: "button",
      onclick: () => { if (all) state.expanded.delete(building.id); else state.expanded.add(building.id); draw(); },
    }, all ? `Show only the best ${best.length}` : `Show all ${plural(units.length, "matching unit")}`));
}

function noPrices() {
  const { filters } = state;
  const q = filters.q.trim().toLowerCase();
  const silent = state.index.filter((b) => !(state.units[b.id] || []).length
    && (!filters.county || b.county === filters.county)
    && (!q || [b.name, b.neighborhood].filter(Boolean).join(" ").toLowerCase().includes(q)));
  if (!silent.length) return null;
  return h("details", { class: "noprices" },
    h("summary", null, `${plural(silent.length, "building")} with no prices published right now`),
    h("ul", null, silent.map((b) => h("li", null,
      h("a", { href: b.url, target: "_blank", rel: "noopener" }, b.name), ` · ${[b.neighborhood, b.manager].filter(Boolean).join(" · ")}`))));
}

// ---------- drawing ----------

function drawBuildings() {
  const groups = groupBuildings(state.index, state.units, state.filters, BEST);
  const matching = groups.reduce((n, group) => n + group.units.length, 0);
  const tagged = groups.reduce((n, group) => n + group.units.filter((u) => u.tag).length, 0);
  $("count").replaceChildren(
    state.updated ? `Updated ${ago(state.updated)} · ` : "",
    h("b", null, plural(groups.length, "building")), " · ", h("b", null, plural(matching, "unit")), " match",
    tagged ? ` · ${tagged.toLocaleString("en-US")} tagged` : "");
  $("n-buildings").textContent = groups.length.toLocaleString("en-US");

  const section = $("buildings");
  section.replaceChildren(...[
    ...groups.slice(0, state.shown).map(buildingCard),
    groups.length > state.shown && h("button", {
      class: "pill pager", type: "button", onclick: () => { state.shown += PAGE; draw(); },
    }, `Show ${Math.min(PAGE, groups.length - state.shown)} more buildings`),
    !groups.length && h("p", { class: "empty" }, "No units match these filters."),
    noPrices(),
  ].filter(Boolean));
}

function drawFollowed() {
  const stars = store.stars();
  $("n-followed").textContent = stars.length ? String(stars.length) : "";
  const section = $("followed");
  if (!stars.length) {
    section.replaceChildren(h("p", { class: "empty" }, "Nothing followed yet. Use the ☆ on any unit to follow it; it stays here even after it stops being listed."));
    return;
  }
  const groups = new Map();
  for (const star of stars) {
    const building = state.byId[star.unit.building] || star.building || { id: star.unit.building, name: star.unit.building };
    if (!groups.has(building.id)) groups.set(building.id, { building, stars: [] });
    groups.get(building.id).stars.push(star);
  }
  section.replaceChildren(...[...groups.values()].map(({ building, stars: mine }) => h("article", { class: "building" },
    h("header", null,
      h("h2", null, h("a", { href: building.url, target: "_blank", rel: "noopener" }, building.name)),
      h("span", null),
      h("div", { class: "where" }, [building.neighborhood, address(building), building.manager].filter(Boolean).join(" · "))),
    h("div", { class: "units" }, mine.flatMap((star) => unitRow(star.unit, building, star.listed))))));
}

function draw() {
  drawBuildings();
  drawFollowed();
  $("buildings").hidden = state.tab !== "buildings";
  $("followed").hidden = state.tab !== "followed";
  for (const button of document.querySelectorAll(".tabs button")) {
    button.setAttribute("aria-pressed", String(button.dataset.tab === state.tab));
  }
}

// ---------- filters ----------

const NUMBERS = ["minSqft", "maxCost", "floorMin", "floorMax"];

function showFilters() {
  const f = state.filters;
  $("q").value = f.q;
  for (const id of NUMBERS) $(id).value = f[id] ?? "";
  $("moveBy").value = f.moveBy || "";
  $("county").value = f.county;
  $("sort").value = f.sort;
  for (const button of document.querySelectorAll("[data-beds]")) button.setAttribute("aria-pressed", String(f.beds.includes(Number(button.dataset.beds))));
  for (const button of document.querySelectorAll("[data-toggle]")) button.setAttribute("aria-pressed", String(Boolean(f[button.dataset.toggle])));
}

function changed() {
  state.shown = PAGE;
  store.setFilters(state.filters);
  showFilters();
  draw();
}

function wire() {
  let typing;
  $("q").addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(() => { state.filters.q = $("q").value; state.shown = PAGE; store.setFilters(state.filters); draw(); }, 150);
  });
  for (const id of NUMBERS) {
    $(id).addEventListener("change", () => { const v = $(id).value; state.filters[id] = v === "" ? null : Number(v); changed(); });
  }
  $("moveBy").addEventListener("change", () => { state.filters.moveBy = $("moveBy").value || null; changed(); });
  $("county").addEventListener("change", () => { state.filters.county = $("county").value; changed(); });
  $("sort").addEventListener("change", () => { state.filters.sort = $("sort").value; changed(); });
  for (const button of document.querySelectorAll("[data-beds]")) {
    button.addEventListener("click", () => {
      const beds = Number(button.dataset.beds);
      const chosen = state.filters.beds;
      state.filters.beds = chosen.includes(beds) ? chosen.filter((b) => b !== beds) : [...chosen, beds];
      changed();
    });
  }
  for (const button of document.querySelectorAll("[data-toggle]")) {
    button.addEventListener("click", () => { state.filters[button.dataset.toggle] = !state.filters[button.dataset.toggle]; changed(); });
  }
  $("reset").addEventListener("click", () => { state.filters = { ...DEFAULT_FILTERS }; changed(); });
  $("filtersbtn").addEventListener("click", () => {
    const open = $("filters").classList.toggle("open");
    $("filtersbtn").setAttribute("aria-expanded", String(open));
  });
  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => { state.tab = button.dataset.tab; draw(); window.scrollTo(0, 0); });
  }
}

// ---------- loading ----------

async function getJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function load() {
  wire();
  showFilters();
  let index;
  try {
    index = await getJson("data/index.json");
  } catch {
    $("count").textContent = "No data yet. The tracker has not published its first run.";
    return;
  }
  state.updated = index.updated;
  state.index = index.buildings;
  state.byId = Object.fromEntries(index.buildings.map((b) => [b.id, b]));
  const counties = Object.keys(index.counties).sort((a, b) => index.counties[b].units - index.counties[a].units);
  for (const fips of counties) $("county").append(h("option", { value: fips }, COUNTY[fips] || fips));
  showFilters();

  const files = await Promise.allSettled(counties.map((fips) => getJson(`data/units-${fips}.json`)));
  for (const file of files) {
    if (file.status !== "fulfilled") continue;
    for (const unit of file.value.units) {
      (state.units[unit.building] ||= []).push(unit);
      state.unitsById[unit.id] = unit;
    }
  }
  store.refreshStars(state.unitsById, state.byId);
  draw();
}

load();

// Kept for the console: which units match right now.
window.aptMatches = () => state.index.flatMap((b) => (state.units[b.id] || []).filter((u) => unitMatches(u, b, state.filters)));
