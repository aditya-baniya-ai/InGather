import { describe, expect, it } from "vitest";
import type { RunEvent } from "./api";
import { agentStates, reviewVerdict } from "./agents";

let seq = 0;
const ev = (agent: RunEvent["agent"], kind: RunEvent["kind"] = "model", summary = "…"): RunEvent =>
  ({ seq: ++seq, agent, kind, summary, tool_name: kind === "tool" ? "x" : null, created_at: "2027-01-17T22:00:00Z" });

describe("agentStates", () => {
  it("everyone waits before any event", () => {
    expect(Object.values(agentStates([], "running"))).toEqual(["waiting", "waiting", "waiting", "waiting", "waiting"]);
  });
  it("scheduler works in parallel with the planner; matchmaker is done once they start", () => {
    const s = agentStates([ev("orchestrator", "system"), ev("matchmaker", "tool"), ev("scheduler", "tool"), ev("planner"), ev("scheduler")], "running");
    expect(s).toMatchObject({ orchestrator: "working", matchmaker: "done", scheduler: "working", planner: "done", reviewer: "waiting" });
  });
  it("the toolless planner is working while the scheduler is, and done once it reports", () => {
    expect(agentStates([ev("matchmaker", "tool"), ev("scheduler", "tool")], "running").planner).toBe("working");
    expect(agentStates([ev("matchmaker", "tool"), ev("planner")], "running").planner).toBe("done");
  });
  it("applies reviewer verdicts, and a sent-back agent works again after rework", () => {
    const base = [ev("matchmaker", "tool"), ev("scheduler", "tool"), ev("planner"), ev("reviewer", "review", "Sent back to scheduler: time outside window")];
    expect(agentStates(base, "running")).toMatchObject({ scheduler: "sent_back", planner: "done", reviewer: "working" });
    const rework = [...base, ev("scheduler", "tool")];
    expect(agentStates(rework, "running")).toMatchObject({ scheduler: "working", reviewer: "done" });
    const approved = [...rework, ev("reviewer", "review", "Approved: draft meets the policy")];
    expect(agentStates(approved, "completed")).toMatchObject({ matchmaker: "approved", scheduler: "approved", planner: "approved", reviewer: "done", orchestrator: "waiting" });
  });
  it("per-agent approvals only approve the agent they name", () => {
    const s = agentStates([ev("matchmaker", "tool"), ev("scheduler"), ev("planner"), ev("reviewer", "review", "Approved: planner — public venue")], "running");
    expect(s).toMatchObject({ planner: "approved", scheduler: "done", matchmaker: "done" });
  });
  it("nobody is working once the run is over", () => {
    expect(agentStates([ev("matchmaker", "tool")], "failed").matchmaker).toBe("done");
  });
});

describe("reviewVerdict", () => {
  it("parses targets and strips the prefix", () => {
    expect(reviewVerdict(ev("reviewer", "review", "Sent back to planner: venue is not public"))).toEqual({ approved: false, target: "planner", reason: "venue is not public" });
    expect(reviewVerdict(ev("reviewer", "review", "Approved: scheduler — time fits"))).toEqual({ approved: true, target: "scheduler", reason: "time fits" });
  });
});
