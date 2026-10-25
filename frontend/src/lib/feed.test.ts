import { describe, expect, it } from "vitest";
import { matchesDay } from "./feed";

// Wednesday, Oct 28 2026 (local time)
const wed = new Date(2026, 9, 28, 10);

describe("matchesDay", () => {
  it("any, today and tomorrow", () => {
    expect(matchesDay("2026-11-02", "any", wed)).toBe(true);
    expect(matchesDay("2026-10-28", "today", wed)).toBe(true);
    expect(matchesDay("2026-10-29", "today", wed)).toBe(false);
    expect(matchesDay("2026-10-29", "tomorrow", wed)).toBe(true);
  });
  it("this weekend is the coming Saturday and Sunday", () => {
    expect(matchesDay("2026-10-31", "weekend", wed)).toBe(true);
    expect(matchesDay("2026-11-01", "weekend", wed)).toBe(true);
    expect(matchesDay("2026-11-02", "weekend", wed)).toBe(false);
    expect(matchesDay("2026-10-30", "weekend", wed)).toBe(false);
  });
  it("on Sunday, this weekend is just today", () => {
    const sun = new Date(2026, 10, 1, 9);
    expect(matchesDay("2026-11-01", "weekend", sun)).toBe(true);
    expect(matchesDay("2026-10-31", "weekend", sun)).toBe(false);
    expect(matchesDay("2026-11-07", "weekend", sun)).toBe(false);
  });
});
