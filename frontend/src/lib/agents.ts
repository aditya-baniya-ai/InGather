import { CalendarClock, ClipboardCheck, MapPinned, UsersRound, Workflow, type LucideIcon } from "lucide-react";
import type { AgentName, Run, RunEvent } from "./api";

export const AGENTS: Record<AgentName, { label: string; icon: LucideIcon; role: string }> = {
  orchestrator: { label: "Orchestrator", icon: Workflow, role: "Coordinates the agents and makes the final, validated proposal" },
  matchmaker: { label: "Matchmaker", icon: UsersRound, role: "Finds eligible, opted-in people" },
  scheduler: { label: "Scheduler", icon: CalendarClock, role: "Checks the group has free time in common" },
  planner: { label: "Planner", icon: MapPinned, role: "Picks the activity and a public place" },
  reviewer: { label: "Reviewer", icon: ClipboardCheck, role: "Checks the draft against the policy" },
};
export const AGENT_ORDER: AgentName[] = ["orchestrator", "matchmaker", "scheduler", "planner", "reviewer"];
/** Agents in the same stage run in parallel. */
const STAGE: Record<AgentName, number> = { orchestrator: 0, matchmaker: 1, scheduler: 2, planner: 2, reviewer: 3 };

/** Agents with no tools: their single note is their finished output. */
const TOOLLESS = new Set<AgentName>(["planner"]);

export type AgentState = "waiting" | "working" | "done" | "approved" | "sent_back";

/** Who a reviewer verdict is about. "Sent back to <agent>: …" names one; "Approved: …" applies to the agent it names, else to all. */
export function reviewVerdict(e: RunEvent): { approved: boolean; target: AgentName | null; reason: string } {
  const sent = /^sent back to (\w+)\s*:?\s*/i.exec(e.summary);
  if (sent) {
    const name = sent[1].toLowerCase() as AgentName;
    return { approved: false, target: name in AGENTS ? name : null, reason: e.summary.slice(sent[0].length) };
  }
  const rest = e.summary.replace(/^approved\s*:?\s*/i, "");
  const named = /^(matchmaker|scheduler|planner)\b\s*[—–:-]?\s*/i.exec(rest);
  return { approved: true, target: named ? (named[1].toLowerCase() as AgentName) : null, reason: named ? rest.slice(named[0].length) : rest };
}

/** Each agent's current state, derived only from the logged events (no hidden client state). */
export function agentStates(events: RunEvent[], status: Run["status"]): Record<AgentName, AgentState> {
  const sorted = [...events].sort((a, b) => a.seq - b.seq);
  const last: Partial<Record<AgentName, number>> = {};
  for (const e of sorted) if (e.agent) last[e.agent] = e.seq;
  const out = {} as Record<AgentName, AgentState>;
  for (const a of AGENT_ORDER) {
    const mine = last[a];
    if (mine === undefined) {
      // The toolless Planner logs only when it finishes; it's busy as soon as its parallel peer starts.
      out[a] = a === "planner" && status === "running" && last.scheduler !== undefined ? "working" : "waiting";
      continue;
    }
    if (a === "orchestrator") { out[a] = status === "running" ? "working" : "done"; continue; }
    const later = sorted.filter((e) => e.seq > mine);
    // Done once a different stage has spoken after it (parallel peers don't count), or, for the toolless Planner, once it has spoken.
    const movedOn = TOOLLESS.has(a) || later.some((e) => e.agent && STAGE[e.agent] !== STAGE[a]);
    out[a] = status === "running" && !movedOn ? "working" : "done";
    if (a !== "reviewer") {
      const verdict = later.filter((e) => e.kind === "review").map(reviewVerdict).filter((v) => v.target === a || (v.approved && v.target === null)).at(-1);
      if (verdict) out[a] = verdict.approved ? "approved" : "sent_back";
    }
  }
  return out;
}
