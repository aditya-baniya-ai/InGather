import { BrainCircuit, CalendarClock, MapPinned, ShieldCheck, Workflow, type LucideIcon } from "lucide-react";
import type { AgentName, Run, RunEvent } from "./api";

/** The gather pipeline's steps, in the order they run. The Matcher is an ML model; the rest is plain server code. */
export const AGENTS: Record<AgentName, { label: string; icon: LucideIcon; role: string }> = {
  gather: { label: "Gather", icon: Workflow, role: "Runs the steps and saves the proposal for your approval" },
  matcher: { label: "Matcher", icon: BrainCircuit, role: "ML model that scores how well each eligible person fits your plan" },
  scheduler: { label: "Scheduler", icon: CalendarClock, role: "Picks the best group that shares an hour of free time" },
  venue: { label: "Venue", icon: MapPinned, role: "Picks the nearest fitting public place" },
  checks: { label: "Checks", icon: ShieldCheck, role: "Confirms the place is public, everyone is free and nobody excluded is included" },
};
export const AGENT_ORDER: AgentName[] = ["gather", "matcher", "scheduler", "venue", "checks"];

export type AgentState = "waiting" | "working" | "done" | "passed" | "failed";

/** Steps logged by older runs (the former agent orchestra) have names the UI no longer knows. */
export const isStep = (name: string | null | undefined): name is AgentName => !!name && name in AGENTS;

/** Each step's current state, derived only from the logged events (no hidden client state). */
export function agentStates(events: RunEvent[], status: Run["status"]): Record<AgentName, AgentState> {
  const sorted = [...events].sort((a, b) => a.seq - b.seq);
  const steps = AGENT_ORDER.filter((a) => a !== "gather");
  const seen = steps.filter((a) => sorted.some((e) => e.agent === a));
  const current = seen.at(-1);
  const out = { gather: status === "running" ? "working" : "done" } as Record<AgentName, AgentState>;
  for (const a of steps) {
    const mine = sorted.filter((e) => e.agent === a);
    if (!mine.length) out[a] = "waiting";
    else if (mine.some((e) => e.kind === "error")) out[a] = "failed";
    else if (a === "checks" && mine.some((e) => e.kind === "review")) out[a] = "passed";
    else out[a] = status === "running" && a === current ? "working" : "done";
  }
  return out;
}
