import type { MapPerson, VenueOption, VenuePoll } from "./api";

/** Category -> existing activity hue (.cat-*), so venue cards share the app's colour language. */
const CAT_CLASS: Record<string, string> = {
  cafe: "cat-coffee", restaurant: "cat-travel", food_hall: "cat-travel", museum: "cat-study",
  park: "cat-other", library: "cat-conference", conference_venue: "cat-conference", public_venue: "cat-event",
};
export const venueCatClass = (category: string) => CAT_CLASS[category] ?? "cat-other";
/** Stock photo (by activity) when the search found no picture of the venue itself. */
const CAT_PHOTO: Record<string, string> = { cafe: "coffee", restaurant: "travel", food_hall: "event", museum: "travel", park: "other", library: "study" };
export const venuePhotoActivity = (category: string) => CAT_PHOTO[category] ?? "coffee";

export interface TallyRow extends VenueOption { leading: boolean }

/** Options in agent rank order; `leading` follows the backend rule (highest average, ties -> best rank). */
export function tally(poll: VenuePoll): TallyRow[] {
  const leader = poll.options.some((o) => o.average !== null) ? winnerOf(poll.options) : null;
  return [...poll.options].sort((a, b) => a.rank - b.rank).map((o) => ({ ...o, leading: o.id === leader?.id }));
}

export function winnerOf(options: VenueOption[]): VenueOption | null {
  if (!options.length) return null;
  return [...options].sort((a, b) => (b.average ?? 0) - (a.average ?? 0) || a.rank - b.rank)[0];
}

/** The decided winner, only once the server says the vote is over. */
export const decidedWinner = (poll: VenuePoll) =>
  poll.status === "decided" ? poll.options.find((o) => o.id === poll.winner_option_id) ?? null : null;

export const stillVoting = (poll: VenuePoll) => poll.voters.filter((v) => !v.voted).map((v) => v.display_name);

export function votingProgress(poll: VenuePoll): string {
  const done = poll.voters.filter((v) => v.voted).length;
  return `${done} of ${poll.voters.length} rated everything`;
}

// --- distance, travel-time estimates and directions ---------------------------------------------
type Point = { latitude: number; longitude: number };

export function km(a: Point, b: Point): number {
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad, dLng = (b.longitude - a.longitude) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLng / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(Math.min(1, h)));
}

/** Rough door-to-door minutes from straight-line distance: city streets are ~1.3x longer than the crow flies. */
export function travelMinutes(distanceKm: number): { walk: number; drive: number } {
  const road = distanceKm * 1.3;
  return { walk: Math.max(1, Math.round((road / 4.8) * 60)), drive: Math.max(2, Math.round((road / 30) * 60 + 3)) };
}

export const fmtMinutes = (m: number) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60 ? `${m % 60} min` : ""}`.trim());

export function etas(option: VenueOption, people: MapPerson[]): { person: MapPerson; km: number; walk: number; drive: number }[] {
  if (option.latitude === null || option.longitude === null) return [];
  const to = { latitude: option.latitude, longitude: option.longitude };
  return people.map((person) => { const d = km(person, to); return { person, km: d, ...travelMinutes(d) }; });
}

function destination(o: VenueOption, city: string): string {
  return o.latitude !== null && o.longitude !== null ? `${o.latitude},${o.longitude}` : `${o.name}, ${o.area ?? city}`;
}

export const appleMapsUrl = (o: VenueOption, city: string) =>
  `https://maps.apple.com/?daddr=${encodeURIComponent(destination(o, city))}&q=${encodeURIComponent(o.name)}`;
export const googleMapsUrl = (o: VenueOption, city: string) =>
  `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(o.latitude !== null ? destination(o, city) : `${o.name}, ${o.area ?? city}`)}`;

/** Apple devices open Apple Maps; everyone else Google Maps. */
export const prefersAppleMaps = () => typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
