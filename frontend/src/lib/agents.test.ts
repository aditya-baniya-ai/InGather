import { describe, expect, it } from "vitest";
import type { RunEvent } from "./api";
import { agentStates, isStep } from "./agents";

let seq = 0;
const ev = (agent: RunEvent["agent"], kind: RunEvent["kind"] = "tool", summary = "…"): RunEvent =>
  ({ seq: ++seq, agent, kind, summary, tool_name: kind === "tool" ? "x" : null, created_at: "2027-01-17T22:00:00Z" });

describe("agentStates", () => {
  it("every step waits before any event", () => {
    expect(agentStates([], "running")).toEqual({ gather: "working", matcher: "waiting", scheduler: "waiting", venue: "waiting", checks: "waiting" });
  });
  it("the latest step is working and earlier ones are done", () => {
    const s = agentStates([ev("gather", "system"), ev("matcher"), ev("matcher"), ev("scheduler")], "running");
    expect(s).toMatchObject({ gather: "working", matcher: "done", scheduler: "working", venue: "waiting", checks: "waiting" });
  });
  it("passed checks and a finished run", () => {
    const s = agentStates([ev("matcher"), ev("scheduler"), ev("venue", "system"), ev("checks", "review"), ev("gather")], "completed");
    expect(s).toEqual({ gather: "done", matcher: "done", scheduler: "done", venue: "done", checks: "passed" });
  });
  it("a step that logged an error failed", () => {
    expect(agentStates([ev("matcher"), ev("checks", "error")], "failed").checks).toBe("failed");
  });
  it("nobody is working once the run is over", () => {
    expect(agentStates([ev("matcher")], "failed").matcher).toBe("done");
  });
});

describe("isStep", () => {
  it("knows the current steps and ignores names from older runs", () => {
    expect(isStep("matcher")).toBe(true);
    expect(isStep("matchmaker")).toBe(false);
    expect(isStep(null)).toBe(false);
  });
});
