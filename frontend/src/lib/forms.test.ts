import { describe, expect, it } from "vitest";
import type { PlanDraft } from "./api";
import { draftToForm, passwordCheck } from "./forms";

describe("passwordCheck", () => {
  it("does not flag a mismatch before the confirmation is typed", () => {
    expect(passwordCheck("longenough", "")).toEqual({ tooShort: false, mismatch: false, ok: false });
  });
  it("flags a mismatch live and blocks submit", () => {
    expect(passwordCheck("longenough", "longenou")).toMatchObject({ mismatch: true, ok: false });
  });
  it("requires at least 8 characters even when both match", () => {
    expect(passwordCheck("short", "short")).toEqual({ tooShort: true, mismatch: false, ok: false });
  });
  it("is ok when long enough and identical", () => {
    expect(passwordCheck("longenough", "longenough").ok).toBe(true);
  });
});

const draft = (over: Partial<PlanDraft> = {}): PlanDraft => ({
  activity_type: "conference", title: "Philly conference evenings", goal_text: "Explore after 5pm", city: "Philadelphia",
  timezone: "America/New_York", start_date: "2027-01-17", end_date: "2027-01-19", intent: "friends", interests: ["Food", "museums"],
  group_min: 3, group_max: 4, group_only: true, windows: [], missing: [], notes: "", mode: "live", ...over,
});

describe("draftToForm", () => {
  it("turns UTC windows into wall-clock times in the plan's timezone, across midnight UTC", () => {
    const { patch } = draftToForm(draft({ windows: [{ starts_at: "2027-01-17T22:00:00Z", ends_at: "2027-01-18T02:00:00Z" }] }), { timezone: "America/Chicago", goal: "" });
    expect(patch.windows).toEqual([{ date: "2027-01-17", from: "17:00", to: "21:00" }]);
  });
  it("never keeps the placeholder time when the draft has dates but no free times", () => {
    const { patch } = draftToForm(draft({ start_date: "2026-10-25", end_date: "2026-10-28", windows: [] }), { timezone: "America/Chicago", goal: "" });
    expect(patch.windows).toEqual([{ date: "2026-10-25", from: "", to: "" }]);
  });
  it("falls back to the form's timezone and derives dates from windows", () => {
    const { patch, filled } = draftToForm(draft({ timezone: null, start_date: null, end_date: null, windows: [
      { starts_at: "2027-03-02T01:00:00Z", ends_at: "2027-03-02T03:00:00Z" },
      { starts_at: "2027-03-01T01:00:00Z", ends_at: "2027-03-01T03:00:00Z" },
    ] }), { timezone: "America/Los_Angeles", goal: "" });
    expect(patch.windows?.[0]).toEqual({ date: "2027-03-01", from: "17:00", to: "19:00" });
    expect([patch.startDate, patch.endDate]).toEqual(["2027-02-28", "2027-03-01"]);
    expect(filled).not.toContain("timezone");
  });
  it("only marks fields the agent actually filled, and drops unknown values", () => {
    const { patch, filled } = draftToForm(draft({ city: null, activity_type: "skydiving", intent: null, goal_text: "", interests: [] }), { timezone: "America/Chicago", goal: "my words" });
    expect(patch.goal).toBe("my words");
    for (const k of ["city", "activity", "intent", "goal", "interests"]) expect(filled).not.toContain(k);
    expect(filled).toEqual(expect.arrayContaining(["title", "timezone", "startDate", "endDate", "size", "groupOnly"]));
    expect(patch.size).toEqual([3, 4]);
  });
  it("normalizes interests", () => {
    expect(draftToForm(draft(), { timezone: "UTC", goal: "" }).patch.interests).toEqual(["food", "museums"]);
  });
});
