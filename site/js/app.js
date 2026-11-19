// Loads the data files and draws the page. Every decision (what matches, what order, what words) is in logic.js.

import {
  DEFAULT_FILTERS, TAG_GROUPS, affordable, affordableNote, ago, areaFacts, countiesLabel, countyGroups, availability, cost, crimeText, criteriaFilters, criteriaFrom, criteriaLabel, driveLabel, incomeNeeded,
  availableNote, dogText, isSteal, mapPoints, nearbyTags, standing, unitTitle, walkText, groupBuildings, money, perSqft, shortDate, sparkline, tagLabel, tagReason, tagsLabel, chosenTags, setTag, unitMatches,
} from "./logic.js";
import { driveTimes, geocode, trafficTimes } from "./commute.js";
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
  updated: null, index: [], byId: {}, units: {}, unitsById: {}, tracts: {}, zips: {}, crimeCounties: [],
  demographics: store.getSetting("demographics", true),
  income: store.getSetting("income", null),        // yearly household income, used only for the three-times-rent flag
  nogo: store.getSetting("nogo", []),              // ZIP codes the user never wants to see
  work: store.getSetting("work", null),             // {address, lat, lon, label}: kept in this browser only
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
  return [a.city, [a.state, building.zip || a.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
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
      unit.tag && h("span", {
        class: `tag ${unit.tag}`,
        title: unit.tag === "check" ? "30% or more under similar units in its own building, or 40% or more under similar units nearby. That is usually income-restricted housing the building did not label, or a mistake. Ask before counting on it." : null,
      }, tagLabel(unit.tag)),
      h("b", null, unitTitle(unit)), " · ",
      [bedsLabel(unit.beds), unit.baths != null && `${unit.baths} bath`, unit.sqft && `${unit.sqft.toLocaleString("en-US")} sqft`,
        unit.floor != null && `floor ${unit.floor}`].filter(Boolean).join(" · "),
      availableNote(unit) && h("span", {
        class: "note", title: "This building publishes prices per floor plan, not per unit. The price is the lowest for this floor plan.",
      }, availableNote(unit)),
      unit.sqft && unit.sqft < ROOM_SQFT && h("span", { class: "note" }, "room"),
      unit.restricted === true && h("span", { class: "note" }, "income-restricted"),
      affordable(unit, state.income) === false && h("span", {
        class: "note", title: "Most managed buildings ask for yearly income of at least 36 times the monthly rent.",
      }, `needs income of ${money(incomeNeeded(unit))}`),
      !listed && h("span", { class: "note" }, "no longer listed")),
    h("div", { class: "price" },
      unit.count != null && h("small", null, "from "), h("b", null, money(cost(unit))), h("small", null, "/mo "), h("small", null, perSqft(unit)),
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

/** The filters plus the standing no-go ZIP codes. */
function active() {
  return { ...state.filters, nogo: state.nogo };
}

function setNogo(zip, on) {
  state.nogo = on ? [...new Set([...state.nogo, zip])].sort() : state.nogo.filter((z) => z !== zip);
  store.setSetting("nogo", state.nogo);
  draw();
}

function drawNogo() {
  const line = $("nogo");
  line.hidden = !state.nogo.length;
  line.replaceChildren("No-go ZIP codes (hidden everywhere):",
    ...state.nogo.map((zip) => h("button", { type: "button", title: "Show this ZIP code again", onclick: () => setNogo(zip, false) }, `${zip} ✕`)));
}

function facts(building) {
  const items = [];
  if (building.laundry === "in_unit") items.push(["In-unit laundry"]);
  else if (building.laundry === "shared") items.push(["Shared laundry"]);
  if (building.parking_from != null) items.push([`Parking from ${money(building.parking_from)}/mo`]);
  else if (building.parking) items.push(["Parking available, price not stated"]);
  else items.push(["Parking not stated", "unknown"]);
  if (building.pets) items.push(["Pets allowed"]);
  if (building.one_time) items.push([`One-time fees ${money(building.one_time)}`]);
  if (building.drive != null) items.push([building.driveTraffic ? driveLabel(building.drive, building.drivePm) : driveLabel(building.drive)]);
  if (walkText(building.walk)) items.push([walkText(building.walk)]);
  if (dogText(building.dog)) items.push([dogText(building.dog), null, building.dog.reasons.join(" · ")]);
  const crime = crimeText(building, state.crimeCounties);
  items.push([crime.text, crime.known ? null : "unknown"]);
  if (building.rank) items.push([`${standing(building.rank)} (pricier than ${building.rank.pct}% of ${building.rank.n} buildings within 2 miles)`]);
  if (affordableNote(building.affordable)) items.push([affordableNote(building.affordable), "stale"]);
  if (building.coming_soon) items.push(["Coming soon"]);
  if (building.senior) items.push(["Senior housing"]);
  if (building.stale) items.push([`Latest read failed; showing ${building.read ? shortDate(building.read) : "earlier data"}`, "stale"]);
  return h("ul", { class: "facts" }, items.map(([text, kind, title]) => h("li", { class: kind || null, title: title || null }, text)),
    building.zip && h("li", { class: "plain" }, h("button", {
      type: "button", title: `Hide every building in ZIP code ${building.zip}`, onclick: () => setNogo(building.zip, true),
    }, `No-go ZIP ${building.zip}`)));
}

function aboutArea(building) {
  const lines = areaFacts(state.tracts[building.tract], state.zips[building.zip], building.zip, state.demographics);
  if (!lines.length) return null;
  return h("details", { class: "area" }, h("summary", null, "About the area"), h("ul", null, lines.map((line) => h("li", null, line))));
}

function followButton(building) {
  const following = store.isFollowing(building.id);
  const criteria = criteriaFrom(state.filters);
  return h("button", {
    class: "follow", type: "button", "aria-pressed": String(following),
    title: following ? "Stop following this building" : `Follow this building for: ${criteriaLabel(criteria)}. It stays under Followed and shows whatever matches each day.`,
    onclick: () => { store.toggleFollow(building, criteria); draw(); },
  }, following ? "★ Following" : "☆ Follow building");
}

function buildingCard(group, note) {
  const { building, units, best } = group;
  const all = state.expanded.has(building.id);
  const shown = all ? units : best;
  return h("article", { class: "building" },
    h("header", null,
      h("h2", null, h("a", { href: building.url, target: "_blank", rel: "noopener" }, building.name), " ", followButton(building)),
      building.rating != null
        ? h("span", { class: "rating", title: "Rating published on the manager's site" }, `★ ${building.rating}`,
            building.rating_count != null && h("small", null, ` (${building.rating_count.toLocaleString("en-US")})`))
        : h("span", null),
      h("div", { class: "where" }, [building.neighborhood, address(building), building.manager].filter(Boolean).join(" · "))),
    note && h("p", { class: "following" }, note),
    building.special && h("p", { class: "offer" }, building.special,
      h("small", null, "Building-wide offer: it may not apply to every unit.")),
    facts(building),
    nearbyTags(building.near).length ? h("p", { class: "nearby" }, h("b", null, "Nearby: "), nearbyTags(building.near).join(" · ")) : null,
    aboutArea(building),
    h("div", { class: "units" }, shown.flatMap((unit) => unitRow(unit, building))),
    !units.length && h("p", { class: "following" }, "Nothing here matches right now."),
    units.length > best.length && h("button", {
      class: "more", type: "button",
      onclick: () => { if (all) state.expanded.delete(building.id); else state.expanded.add(building.id); draw(); },
    }, all ? `Show only the best ${best.length}` : `Show all ${plural(units.length, "matching unit")}`));
}

function noPrices() {
  const { filters } = state;
  const q = filters.q.trim().toLowerCase();
  const silent = state.index.filter((b) => !(state.units[b.id] || []).length
    && (!filters.counties.length || filters.counties.includes(b.county))
    && (!q || [b.name, b.neighborhood].filter(Boolean).join(" ").toLowerCase().includes(q)));
  if (!silent.length) return null;
  return h("details", { class: "noprices" },
    h("summary", null, `${plural(silent.length, "building")} with no prices published right now`),
    h("ul", null, silent.map((b) => h("li", null,
      h("a", { href: b.url, target: "_blank", rel: "noopener" }, b.name), ` · ${[b.neighborhood, b.manager].filter(Boolean).join(" · ")}`))));
}

// ---------- drawing ----------

function drawBuildings() {
  const groups = groupBuildings(state.index, state.units, active(), BEST);
  const matching = groups.reduce((n, group) => n + group.units.length, 0);
  const tagged = groups.reduce((n, group) => n + group.units.filter((u) => isSteal(u.tag)).length, 0);
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
  return groups;
}

// ---------- map ----------

const TAG_COLOUR = { absolute: "#c0392b", building: "#1f7a52", local: "#2d6fa8" };
const chart = { map: null, layer: null, fitted: false };

function popup(point) {
  const { building, best } = point;
  return h("div", null,
    h("p", null, h("b", null, building.name), building.rating != null && ` ★ ${building.rating}`),
    h("p", null, [building.neighborhood, address(building)].filter(Boolean).join(" · ")),
    h("p", null, `${plural(point.count, "unit")} match`, point.tag && ` · best tag: ${tagLabel(point.tag)}`),
    best && h("p", null, `Best: ${unitTitle(best)} · ${[bedsLabel(best.beds), best.sqft && `${best.sqft} sqft`].filter(Boolean).join(" · ")} · ${money(cost(best))}/mo`),
    h("button", { type: "button", onclick: () => { state.filters.q = building.name; state.tab = "buildings"; changed(); window.scrollTo(0, 0); } },
      "Show in the list"),
    building.zip && h("button", { type: "button", style: "margin-left:6px;background:none;color:#a8321f;border-color:#a8321f",
      onclick: () => setNogo(building.zip, true) }, `No-go ZIP ${building.zip}`));
}

function drawMap(groups) {
  if (state.tab !== "map" || !window.L) return;
  const L = window.L;
  if (!chart.map) {
    chart.map = L.map("mapbox", { scrollWheelZoom: true }).setView([38.9, -77.03], 10);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(chart.map);
    chart.layer = L.layerGroup().addTo(chart.map);
  }
  chart.map.invalidateSize();
  chart.layer.clearLayers();
  if (state.work) {
    L.marker([state.work.lat, state.work.lon], {
      icon: L.divIcon({ className: "workpin", html: "★", iconSize: [22, 22], iconAnchor: [11, 11] }), keyboard: false,
    }).bindTooltip("Work").addTo(chart.layer);
  }
  const points = mapPoints(groups);
  // Draw untagged buildings first so tagged ones sit on top.
  points.sort((a, b) => Number(Boolean(a.tag)) - Number(Boolean(b.tag)));
  for (const point of points) {
    L.circleMarker([point.lat, point.lon], {
      radius: 5 + Math.min(9, Math.sqrt(point.count)), weight: 1.5, color: "#ffffff",
      fillColor: TAG_COLOUR[point.tag] || "#8a8a85", fillOpacity: 0.9,
    }).bindPopup(() => popup(point)).bindTooltip(point.name).addTo(chart.layer);
  }
  if (!chart.fitted && points.length) {
    chart.map.fitBounds(points.map((p) => [p.lat, p.lon]), { padding: [30, 30] });
    chart.fitted = true;
  }
}

function followedBuildings() {
  return store.follows().map((follow) => {
    const building = state.byId[follow.id];
    if (!building) {
      return h("article", { class: "building" }, h("header", null, h("h2", null, follow.name), h("span", null),
        h("div", { class: "where" }, "This building is no longer tracked.")));
    }
    const [group] = groupBuildings([building], state.units, { ...criteriaFilters(follow.criteria), nogo: [] }, BEST);
    return buildingCard(group || { building, units: [], best: [] }, `Following for: ${criteriaLabel(follow.criteria)}`);
  });
}

function drawFollowed() {
  const stars = store.stars();
  const follows = store.follows();
  $("n-followed").textContent = stars.length + follows.length ? String(stars.length + follows.length) : "";
  const section = $("followed");
  if (!stars.length && !follows.length) {
    section.replaceChildren(h("p", { class: "empty" }, "Nothing followed yet. Use the ☆ on a unit to follow that unit, or \"Follow building\" to keep a building here with whatever matches your size and price filters each day."));
    return;
  }
  const groups = new Map();
  for (const star of stars) {
    const building = state.byId[star.unit.building] || star.building || { id: star.unit.building, name: star.unit.building };
    if (!groups.has(building.id)) groups.set(building.id, { building, stars: [] });
    groups.get(building.id).stars.push(star);
  }
  section.replaceChildren(
    follows.length ? h("h3", { class: "group" }, "Buildings you follow") : "",
    ...followedBuildings(),
    stars.length ? h("h3", { class: "group" }, "Units you follow") : "",
    ...[...groups.values()].map(({ building, stars: mine }) => h("article", { class: "building" },
    h("header", null,
      h("h2", null, h("a", { href: building.url, target: "_blank", rel: "noopener" }, building.name)),
      h("span", null),
      h("div", { class: "where" }, [building.neighborhood, address(building), building.manager].filter(Boolean).join(" · "))),
    h("div", { class: "units" }, mine.flatMap((star) => unitRow(star.unit, building, star.listed))))));
}

function draw() {
  drawNogo();
  const groups = drawBuildings();
  drawFollowed();
  $("buildings").hidden = state.tab !== "buildings";
  $("followed").hidden = state.tab !== "followed";
  $("map").hidden = state.tab !== "map";
  drawMap(groups);
  for (const button of document.querySelectorAll(".tabs button")) {
    button.setAttribute("aria-pressed", String(button.dataset.tab === state.tab));
  }
}

// ---------- filters ----------

// ---------- drive times ----------

/** Put known drive times on the buildings and their units (units carry it so they can be sorted by it). */
function applyDrive(times) {
  for (const building of state.index) {
    const time = times && building.id in times ? times[building.id] : null;
    const traffic = time != null && typeof time === "object";             // {am, pm} from Google; a plain number without traffic
    building.drive = traffic ? time.am : time;
    building.drivePm = traffic ? time.pm : null;
    building.driveTraffic = traffic;
    for (const unit of state.units[building.id] || []) unit.drive = building.drive;
  }
}

function driveKey() {
  const key = store.getSetting("googleKey", null);
  const hours = { leave: store.getSetting("leave", "08:00"), back: store.getSetting("back", "17:30") };
  return { key, hours, cache: `${state.work.lat},${state.work.lon}|${key ? `traffic ${hours.leave} ${hours.back}` : "free"}` };
}

function showWork() {
  $("work").value = state.work ? state.work.address : "";
  const cached = store.getSetting("drive", null);
  const known = state.work && cached && cached.key === driveKey().cache ? cached.times : null;
  applyDrive(known);
  const traffic = known && Object.values(known).some((time) => typeof time === "object");
  $("workstatus").textContent = !state.work ? "" : known
    ? `${Object.keys(known).length} buildings timed from ${state.work.label.split(",").slice(0, 2).join(",")}${traffic ? ", with typical traffic" : ", without traffic"}`
    : "Not timed yet: press Time my drive";
  return known;
}

async function timeDrives() {
  const typed = $("work").value.trim();
  if (!typed) {
    state.work = null;
    store.setSetting("work", null);
    store.setSetting("drive", null);
    state.filters.maxDrive = null;
    showWork();
    changed();
    return;
  }
  $("workstatus").textContent = "Finding the address…";
  try {
    const found = await geocode(typed);
    if (!found) { $("workstatus").textContent = "Could not find that address. Try adding the city and state."; return; }
    state.work = { address: typed, ...found };
    store.setSetting("work", state.work);
    const { key, hours, cache } = driveKey();
    let times = null, problem = "";
    if (key) {
      $("workstatus").textContent = "Timing drives in typical traffic…";
      try {
        times = await trafficTimes(state.work, state.index, key, hours);
      } catch (error) {
        problem = `Google did not accept the request (${error.message}), so these are no-traffic times. `;
      }
    }
    if (!times || !Object.keys(times).length) {
      $("workstatus").textContent = "Timing drives…";
      times = await driveTimes(state.work, state.index);
      store.setSetting("drive", { key: `${found.lat},${found.lon}|free`, times });
      if (key) store.setSetting("drive", { key: cache, times });          // do not ask Google again on every page load
    } else {
      store.setSetting("drive", { key: cache, times });
    }
    showWork();
    if (!Object.keys(times).length) $("workstatus").textContent = "The routing service did not answer. Try again in a minute.";
    else if (problem) $("workstatus").textContent = problem + $("workstatus").textContent;
    draw();
  } catch (error) {
    $("workstatus").textContent = `Could not time drives (${error.message}). Try again in a minute.`;
  }
}

const NUMBERS = ["minSqft", "maxCost", "floorMin", "floorMax"];
const ANY_DRIVE = 95;      // the slider's last stop means "any"
const ANY_CRIME = 61;      // the slider's last stop means "any"

function showFilters() {
  const f = state.filters;
  $("q").value = f.q;
  for (const id of NUMBERS) $(id).value = f[id] ?? "";
  $("moveBy").value = f.moveBy || "";
  $("areaslabel").textContent = countiesLabel(f.counties, COUNTY);
  for (const box of document.querySelectorAll("#areaspanel input[data-county]")) box.checked = f.counties.includes(box.dataset.county);
  for (const box of document.querySelectorAll("#areaspanel input[data-state]")) {
    const mine = [...document.querySelectorAll(`#areaspanel input[data-county][data-in="${box.dataset.state}"]`)];
    box.checked = mine.length > 0 && mine.every((county) => county.checked);
    box.indeterminate = !box.checked && mine.some((county) => county.checked);
  }
  const chosen = chosenTags(f);
  $("tagslabel").textContent = tagsLabel(f);
  for (const box of document.querySelectorAll("#tagspanel input[data-tag]")) box.checked = chosen.includes(box.dataset.tag);
  for (const box of document.querySelectorAll("#tagspanel input[data-group]")) {
    const mine = [...document.querySelectorAll(`#tagspanel input[data-tag][data-in="${box.dataset.group}"]`)];
    box.checked = mine.every((tag) => tag.checked);
    box.indeterminate = !box.checked && mine.some((tag) => tag.checked);
  }
  $("manager").value = f.manager;
  $("minRating").value = f.minRating == null ? "" : String(f.minRating);
  $("sort").value = f.sort;
  for (const button of document.querySelectorAll("[data-beds]")) button.setAttribute("aria-pressed", String(f.beds.includes(Number(button.dataset.beds))));
  for (const button of document.querySelectorAll("[data-toggle]")) button.setAttribute("aria-pressed", String(Boolean(f[button.dataset.toggle])));
  $("maxViolent").value = f.maxViolent == null ? ANY_CRIME : Math.min(f.maxViolent, ANY_CRIME - 1);
  $("maxViolentOut").textContent = f.maxViolent == null ? "any" : `${f.maxViolent} or fewer`;
  $("demographics").checked = state.demographics;
  $("minWalk").value = f.minWalk == null ? 0 : f.minWalk;
  $("minWalkOut").textContent = f.minWalk == null ? "any" : `${f.minWalk}+`;
  $("maxDrive").value = f.maxDrive == null ? ANY_DRIVE : f.maxDrive;
  $("maxDriveOut").textContent = f.maxDrive == null ? "any" : `${f.maxDrive} min`;
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
  document.addEventListener("click", (event) => {
    for (const id of ["areas", "tags"]) if (!$(id).contains(event.target)) $(id).open = false;
  });
  buildTags();
  $("manager").addEventListener("change", () => { state.filters.manager = $("manager").value; changed(); });
  $("minRating").addEventListener("change", () => { const v = $("minRating").value; state.filters.minRating = v === "" ? null : Number(v); changed(); });
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
  $("maxViolent").addEventListener("input", () => {
    const value = Number($("maxViolent").value);
    state.filters.maxViolent = value >= ANY_CRIME ? null : value;
    changed();
  });
  $("maxDrive").addEventListener("input", () => {
    const value = Number($("maxDrive").value);
    state.filters.maxDrive = value >= ANY_DRIVE ? null : value;
    changed();
  });
  $("minWalk").addEventListener("input", () => {
    const value = Number($("minWalk").value);
    state.filters.minWalk = value <= 0 ? null : value;
    changed();
  });
  $("setwork").addEventListener("click", timeDrives);
  $("work").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); timeDrives(); } });
  $("demographics").addEventListener("change", () => {
    state.demographics = $("demographics").checked;
    store.setSetting("demographics", state.demographics);
    draw();
  });
  $("reset").addEventListener("click", () => { state.filters = { ...DEFAULT_FILTERS }; changed(); });
  $("filtersbtn").addEventListener("click", () => {
    const open = $("filters").classList.toggle("open");
    $("filtersbtn").setAttribute("aria-expanded", String(open));
  });
  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => {
      state.tab = button.dataset.tab;
      try { history.replaceState(null, "", state.tab === "buildings" ? location.pathname + location.search : "#" + state.tab); } catch { /* no history */ }
      draw();
      window.scrollTo(0, 0);
    });
  }
}

// ---------- area picker: states with their counties, any number chosen ----------

function buildTags() {
  const choose = (keys, on) => {
    for (const key of keys) state.filters = setTag(state.filters, key, on);
    changed();
  };
  $("tagspanel").replaceChildren(...TAG_GROUPS.flatMap((group) => [
    h("label", { class: "state", title: group.name === "Deals" ? "Units carrying any of the chosen deal tags" : "Every chosen one must hold" },
      h("input", { type: "checkbox", "data-group": group.name, onchange: (event) => choose(group.tags.map((tag) => tag.key), event.target.checked) }),
      `${group.name} (all)`),
    ...group.tags.map((tag) => h("label", { class: "county", title: tag.title },
      h("input", { type: "checkbox", "data-tag": tag.key, "data-in": group.name, onchange: (event) => choose([tag.key], event.target.checked) }),
      tag.label)),
  ]));
}

function buildAreas(counts) {
  const panel = $("areaspanel");
  const choose = (fipsList, on) => {
    const chosen = new Set(state.filters.counties);
    for (const fips of fipsList) { if (on) chosen.add(fips); else chosen.delete(fips); }
    state.filters.counties = [...chosen];
    changed();
  };
  panel.replaceChildren(...countyGroups(Object.keys(counts), COUNTY).flatMap((group) => {
    const all = group.counties.map((county) => county.fips);
    const rows = group.counties.map((county) => h("label", { class: "county" },
      h("input", { type: "checkbox", "data-county": county.fips, "data-in": group.state, onchange: (event) => choose([county.fips], event.target.checked) }),
      county.name.replace(/, (VA|MD)$/, ""), h("small", null, String(counts[county.fips].units))));
    if (group.counties.length === 1) { rows[0].className = "state"; return rows; }
    return [h("label", { class: "state" },
      h("input", { type: "checkbox", "data-state": group.state, onchange: (event) => choose(all, event.target.checked) }),
      `${group.state} (all)`, h("small", null, String(all.reduce((n, fips) => n + counts[fips].units, 0)))), ...rows];
  }));
}

// ---------- first-visit setup ----------

function openSetup() {
  const f = state.filters;
  for (const button of document.querySelectorAll("[data-sbeds]")) button.setAttribute("aria-pressed", String(f.beds.includes(Number(button.dataset.sbeds))));
  $("s-minSqft").value = f.minSqft ?? "";
  $("s-maxCost").value = f.maxCost ?? "";
  $("s-moveBy").value = f.moveBy || "";
  $("s-work").value = state.work ? state.work.address : "";
  $("s-maxDrive").value = f.maxDrive ?? "";
  $("s-income").value = state.income ?? "";
  $("s-key").value = store.getSetting("googleKey", "") || "";
  $("s-leave").value = store.getSetting("leave", "08:00");
  $("s-back").value = store.getSetting("back", "17:30");
  $("x-status").textContent = "";
  if (typeof $("setup").showModal === "function") $("setup").showModal();
}

function wireSetup() {
  for (const button of document.querySelectorAll("[data-sbeds]")) {
    button.addEventListener("click", () => button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true")));
  }
  const number = (id) => ($(id).value === "" ? null : Number($(id).value));
  const done = () => { store.setSetting("welcomed", true); $("setup").close(); };
  $("s-skip").addEventListener("click", done);
  $("setupform").addEventListener("submit", (event) => {
    event.preventDefault();
    state.filters.beds = [...document.querySelectorAll('[data-sbeds][aria-pressed="true"]')].map((b) => Number(b.dataset.sbeds));
    state.filters.minSqft = number("s-minSqft");
    state.filters.maxCost = number("s-maxCost");
    state.filters.moveBy = $("s-moveBy").value || null;
    state.income = number("s-income");
    store.setSetting("income", state.income);
    const before = state.work ? driveKey().cache : null;
    store.setSetting("googleKey", $("s-key").value.trim() || null);
    store.setSetting("leave", $("s-leave").value || "08:00");
    store.setSetting("back", $("s-back").value || "17:30");
    const maxDrive = number("s-maxDrive");
    const address = $("s-work").value.trim();
    done();
    changed();
    const retime = state.work && driveKey().cache !== before;             // the key or the hours changed
    if (address && (retime || !state.work || state.work.address !== address)) {
      $("work").value = address;
      timeDrives().then(() => { if (maxDrive != null && state.work) { state.filters.maxDrive = maxDrive; changed(); } });
    } else if (maxDrive != null && state.work) {
      state.filters.maxDrive = maxDrive;
      changed();
    }
  });
  $("setupbtn").addEventListener("click", openSetup);

  // settings as text, to carry to another browser
  $("x-copy").addEventListener("click", async () => {
    const text = store.exportText(new Date().toISOString());
    try {
      await navigator.clipboard.writeText(text);
      $("x-status").textContent = "Copied. Paste it into the box below on the other browser.";
    } catch {
      $("x-text").value = text;
      $("x-text").select();
      $("x-status").textContent = "Could not reach the clipboard; the text is in the box below to copy by hand.";
    }
  });
  $("x-file").addEventListener("click", () => {
    const link = h("a", { href: URL.createObjectURL(new Blob([store.exportText(new Date().toISOString())], { type: "text/plain" })),
      download: "apartment-tracker-settings.txt" });
    document.body.append(link);
    link.click();
    link.remove();
    $("x-status").textContent = "Saved apartment-tracker-settings.txt.";
  });
  $("x-import").addEventListener("click", () => {
    const result = store.importText($("x-text").value);
    if (!result.ok) { $("x-status").textContent = "That is not an export from this page. Nothing was changed."; return; }
    store.setSetting("welcomed", true);
    state.filters = store.getFilters();
    state.nogo = store.getSetting("nogo", []);
    state.income = store.getSetting("income", null);
    state.work = store.getSetting("work", null);
    state.demographics = store.getSetting("demographics", true);
    $("setup").close();
    showWork();
    changed();
    $("workstatus").textContent = `Settings loaded: ${result.stars} followed units, ${result.follows} followed buildings.` + (state.work ? " Press Time my drive to time drives here." : "");
  });
}

// ---------- loading ----------

async function getJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function load() {
  if (["#map", "#followed"].includes(location.hash)) state.tab = location.hash.slice(1);      // a link can open a tab
  wire();
  wireSetup();
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
  state.tracts = index.tracts || {};
  state.zips = index.zips || {};
  state.crimeCounties = index.crime_counties || [];
  if (state.crimeCounties.length) $("crime-counties").textContent = state.crimeCounties.map((fips) => COUNTY[fips] || fips).join("; ");
  const counties = Object.keys(index.counties).sort((a, b) => index.counties[b].units - index.counties[a].units);
  buildAreas(index.counties);
  const managers = [...new Set(index.buildings.map((b) => b.manager).filter(Boolean))].sort();
  for (const name of managers) $("manager").append(h("option", { value: name }, name));
  showFilters();

  const files = await Promise.allSettled(counties.map((fips) => getJson(`data/units-${fips}.json`)));
  for (const file of files) {
    if (file.status !== "fulfilled") continue;
    for (const unit of file.value.units) {
      (state.units[unit.building] ||= []).push(unit);
      state.unitsById[unit.id] = unit;
    }
  }
  for (const building of state.index) {              // units carry the block's walkability so they can be sorted by it
    for (const unit of state.units[building.id] || []) unit.walkScore = building.walk ? building.walk.score : null;
  }
  store.refreshStars(state.unitsById, state.byId);
  showWork();
  draw();
  if (!store.getSetting("welcomed", false)) openSetup();
}

load();

// Kept for the console: which units match right now.
window.aptMatches = () => state.index.flatMap((b) => (state.units[b.id] || []).filter((u) => unitMatches(u, b, active())));
