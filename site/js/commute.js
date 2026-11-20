// Drive times from a work place to every building, using two free public services that need no key:
// OpenStreetMap's Nominatim to turn an address into coordinates, and the public OSRM server for drive times.
// OSRM knows nothing about traffic, so these are free-flow times: honest for comparing buildings with each
// other, optimistic for a rush-hour commute.

const NOMINATIM = "https://nominatim.openstreetmap.org/search";
const OSRM = "https://router.project-osrm.org/table/v1/driving/";
const BATCH = 90;          // the public server limits how many places one request may name

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} from ${new URL(url).host}`);
  return response.json();
}

/** Coordinates for an address: {lat, lon, label}, or null when nothing matches. */
export async function geocode(address, getJson = fetchJson) {
  const q = (address || "").trim();
  if (!q) return null;
  const found = await getJson(`${NOMINATIM}?format=jsonv2&limit=1&countrycodes=us&q=${encodeURIComponent(q)}`);
  if (!Array.isArray(found) || !found.length) return null;
  return { lat: Number(found[0].lat), lon: Number(found[0].lon), label: found[0].display_name };
}

export function tableUrl(work, buildings) {
  const places = [work, ...buildings].map((place) => `${place.lon},${place.lat}`).join(";");
  return `${OSRM}${places}?sources=0&annotations=duration`;
}

/** {building id: minutes} from the work place to each building that has coordinates. */
export async function driveTimes(work, buildings, getJson = fetchJson) {
  const located = buildings.filter((b) => b.lat != null && b.lon != null);
  const times = {};
  for (let start = 0; start < located.length; start += BATCH) {
    const batch = located.slice(start, start + BATCH);
    let answer;
    try {
      answer = await getJson(tableUrl(work, batch));
    } catch {
      continue;                                   // this batch is lost; keep the rest
    }
    const seconds = answer && answer.code === "Ok" && answer.durations ? answer.durations[0] : null;
    if (!seconds) continue;
    batch.forEach((building, i) => {
      if (seconds[i + 1] != null) times[building.id] = Math.round(seconds[i + 1] / 60);
    });
  }
  return times;
}

// ---------- one trip, for drawing on the map ----------

const OSRM_ROUTE = "https://router.project-osrm.org/route/v1/driving/";

export function routeUrl(home, work) {
  return `${OSRM_ROUTE}${home.lon},${home.lat};${work.lon},${work.lat}?overview=full&geometries=geojson`;
}

/** The usual drive from a home to the work place, without traffic: {line: [[lat, lon], ...], minutes}; null when there is none to show. */
export async function route(home, work, getJson = fetchJson) {
  if (!home || !work || home.lat == null || home.lon == null || work.lat == null || work.lon == null) return null;
  let answer;
  try {
    answer = await getJson(routeUrl(home, work));
  } catch {
    return null;
  }
  const found = answer && answer.code === "Ok" && Array.isArray(answer.routes) ? answer.routes[0] : null;
  const points = found && found.geometry && Array.isArray(found.geometry.coordinates) ? found.geometry.coordinates : [];
  if (points.length < 2) return null;
  return { line: points.map(([lon, lat]) => [lat, lon]), minutes: Math.round(found.duration / 60) };
}

// ---------- with a Google key: typical traffic at the hours you actually drive ----------

const ROUTES = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix";
const ROUTES_BATCH = 600;      // Google allows 625 origin-destination pairs per request

async function postJson(url, body, headers) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
  if (!response.ok) {
    let detail = "";
    try { detail = (await response.json())[0]?.error?.message || ""; } catch { /* no detail */ }
    throw new Error(`${response.status} ${detail}`.trim());
  }
  return response.json();
}

/** The next Tuesday, Wednesday or Thursday at "HH:MM" local time: an ordinary commuting day, in the future. */
export function nextWeekday(now, hhmm) {
  const [hours, minutes] = hhmm.split(":").map(Number);
  const when = new Date(now);
  when.setHours(hours, minutes, 0, 0);
  while (when <= now || ![2, 3, 4].includes(when.getDay())) {
    when.setDate(when.getDate() + 1);
    when.setHours(hours, minutes, 0, 0);
  }
  return when;
}

const waypoint = (place) => ({ waypoint: { location: { latLng: { latitude: place.lat, longitude: place.lon } } } });

/** {building id: {am, pm}}: minutes to work at the morning hour and home at the evening hour, in typical traffic. */
export async function trafficTimes(work, buildings, key, hours, post = postJson, now = new Date()) {
  const located = buildings.filter((b) => b.lat != null && b.lon != null);
  const headers = { "X-Goog-Api-Key": key, "X-Goog-FieldMask": "originIndex,destinationIndex,duration,condition,status" };
  const times = {};
  const ask = async (batch, toWork, departure) => {
    const body = {
      origins: toWork ? batch.map(waypoint) : [waypoint(work)],
      destinations: toWork ? [waypoint(work)] : batch.map(waypoint),
      travelMode: "DRIVE", routingPreference: "TRAFFIC_AWARE", departureTime: departure.toISOString(),
    };
    for (const element of await post(ROUTES, body, headers)) {
      const building = batch[toWork ? element.originIndex ?? 0 : element.destinationIndex ?? 0];
      if (!building || element.condition !== "ROUTE_EXISTS" || !element.duration) continue;
      (times[building.id] ||= {})[toWork ? "am" : "pm"] = Math.round(parseInt(element.duration, 10) / 60);
    }
  };
  const morning = nextWeekday(now, hours.leave), evening = nextWeekday(now, hours.back);
  for (let start = 0; start < located.length; start += ROUTES_BATCH) {
    const batch = located.slice(start, start + ROUTES_BATCH);
    await ask(batch, true, morning);
    await ask(batch, false, evening);
  }
  for (const id of Object.keys(times)) {
    if (times[id].am == null) delete times[id];          // without a morning time there is nothing to sort or filter by
    else if (times[id].pm == null) times[id].pm = null;
  }
  return times;
}
