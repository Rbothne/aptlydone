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
