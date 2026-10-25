import { describe, expect, it } from "vitest";
import type { MapPerson, VenueOption, VenuePoll } from "./api";
import { appleMapsUrl, decidedWinner, etas, fmtMinutes, googleMapsUrl, hostOf, hoursOn, km, photoOf, stillVoting, tally, travelMinutes, votingProgress, weekdayOf } from "./venueVote";

const opt = (id: string, rank: number, average: number | null, over: Partial<VenueOption> = {}): VenueOption => ({
  id, rank, name: `Place ${id}`, area: "E 6th St", category: "cafe", why: "", description: "", latitude: null, longitude: null,
  image_url: null, reservation_url: null, source_url: null, verified: true, average, ratings: average === null ? 0 : 1, my_score: null, ...over,
});
const poll = (options: VenueOption[], over: Partial<VenuePoll> = {}): VenuePoll => ({
  status: "open", round: 1, rerolls_left: 3, source: "grounded", options, people: [], i_shared_location: false,
  voters: [{ user_id: "a", display_name: "Alice", voted: true, rated: 3 }, { user_id: "b", display_name: "Maya", voted: false, rated: 1 }],
  winner_option_id: null, proposal_version: 1, ...over,
});

describe("tally", () => {
  it("orders by agent rank and marks the highest average as leading (ties -> better rank)", () => {
    const rows = tally(poll([opt("c", 3, 8.5), opt("a", 1, 7), opt("b", 2, 8.5)]));
    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(rows.find((r) => r.leading)?.id).toBe("b");
    expect(tally(poll([opt("a", 1, null), opt("b", 2, null)])).some((r) => r.leading)).toBe(false);
  });
  it("progress and who's still rating", () => {
    const p = poll([opt("a", 1, 5)]);
    expect(votingProgress(p)).toBe("1 of 2 rated everything");
    expect(stillVoting(p)).toEqual(["Maya"]);
    expect(decidedWinner(p)).toBeNull();
    expect(decidedWinner({ ...p, status: "decided", winner_option_id: "a" })?.id).toBe("a");
  });
});

describe("travel times and directions", () => {
  const me: MapPerson = { user_id: "a", display_name: "Alice", avatar_url: null, latitude: 30.267, longitude: -97.743, is_me: true };
  const venue = opt("v", 1, null, { latitude: 30.286, longitude: -97.739 });
  it("estimates walking and driving minutes from distance", () => {
    const d = km(me, { latitude: 30.286, longitude: -97.739 });
    expect(d).toBeGreaterThan(2); expect(d).toBeLessThan(2.4);
    const t = travelMinutes(d);
    expect(t.walk).toBeGreaterThan(30); expect(t.drive).toBeLessThan(t.walk);
    expect(etas(venue, [me])[0].walk).toBe(t.walk);
    expect(etas(opt("x", 1, null), [me])).toEqual([]);  // no pin, no estimate
    expect(fmtMinutes(45)).toBe("45 min");
    expect(fmtMinutes(125)).toBe("2 h 5 min");
  });
  it("links to Apple and Google Maps directions", () => {
    expect(appleMapsUrl(venue, "Austin")).toBe("https://maps.apple.com/?daddr=30.286%2C-97.739&q=Place%20v");
    expect(googleMapsUrl(venue, "Austin")).toBe("https://www.google.com/maps/dir/?api=1&destination=30.286%2C-97.739");
    expect(googleMapsUrl(opt("y", 1, null, { name: "Joe's" }), "Austin")).toContain(encodeURIComponent("Joe's, E 6th St"));
  });
});

describe("place details", () => {
  it("prefers the Google photo, then the searched one, else stock", () => {
    const place = { type: "Café", rating: 4.6, rating_count: 812, price: "$$", open_now: true, hours: [], phone: null, website: null, maps_url: null, summary: null,
      photos: [{ url: "/api/venue-photos/x/0", author: "Sam" }] };
    expect(photoOf(opt("x", 1, null, { place, image_url: "https://a.com/p.jpg" }))).toBe("/api/venue-photos/x/0");
    expect(photoOf(opt("x", 1, null, { image_url: "https://a.com/p.jpg" }))).toBe("https://a.com/p.jpg");
    expect(photoOf(opt("x", 1, null))).toBeNull();
  });
  it("reads one day's hours and the meetup weekday", () => {
    const hours = ["Monday: 7:00 AM – 6:00 PM", "Sunday: Closed"];
    expect(hoursOn(hours, "Monday")).toBe("7:00 AM – 6:00 PM");
    expect(hoursOn(hours, "sunday")).toBe("Closed");
    expect(hoursOn(hours, "Friday")).toBeNull();
    expect(weekdayOf("2026-10-25T15:00:00Z", "America/Chicago")).toBe("Sunday");
    expect(weekdayOf("2026-10-27", "America/Chicago")).toBe("Tuesday");  // date only: not shifted to Monday evening
    expect(hostOf("https://www.example.com/menu")).toBe("example.com");
  });
});
