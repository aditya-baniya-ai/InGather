import { describe, expect, it } from "vitest";
import { formatDay, localToUtcIso, utcToLocal, windowsToUtc } from "./time";

describe("localToUtcIso", () => {
  it("converts Philadelphia wall-clock (EST, UTC-5) to UTC", () => {
    expect(localToUtcIso("2027-01-17", "17:00", "America/New_York")).toBe("2027-01-17T22:00:00Z");
  });
  it("handles summer time (EDT, UTC-4)", () => {
    expect(localToUtcIso("2027-07-04", "09:30", "America/New_York")).toBe("2027-07-04T13:30:00Z");
  });
  it("handles zones ahead of UTC and date rollover", () => {
    expect(localToUtcIso("2027-01-17", "07:00", "Asia/Tokyo")).toBe("2027-01-16T22:00:00Z");
    expect(localToUtcIso("2027-01-17", "05:30", "Asia/Kolkata")).toBe("2027-01-17T00:00:00Z");
  });
  it("lands after the spring-forward gap", () => {
    // 02:30 does not exist on 2027-03-14 in New York; result must still be a valid instant near it.
    const iso = localToUtcIso("2027-03-14", "03:30", "America/New_York");
    expect(iso).toBe("2027-03-14T07:30:00Z");
  });
  it("round-trips through utcToLocal", () => {
    const iso = localToUtcIso("2027-01-18", "18:45", "America/Chicago");
    expect(utcToLocal(iso, "America/Chicago")).toEqual({ date: "2027-01-18", time: "18:45" });
  });
});

describe("windowsToUtc", () => {
  it("maps windows and runs past midnight when the end is earlier than the start", () => {
    expect(windowsToUtc([
      { date: "2027-01-17", from: "17:00", to: "21:00" },
      { date: "2027-01-18", from: "22:00", to: "01:00" },
    ], "America/New_York")).toEqual([
      { starts_at: "2027-01-17T22:00:00Z", ends_at: "2027-01-18T02:00:00Z" },
      { starts_at: "2027-01-19T03:00:00Z", ends_at: "2027-01-19T06:00:00Z" },
    ]);
  });
});

describe("formatDay", () => {
  it("does not shift plain calendar dates across timezones", () => {
    expect(formatDay("2027-01-17")).toBe("Sun, Jan 17");
  });
});
