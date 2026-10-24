import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, RotateCcw, Check, CircleDot, ClipboardCheck, Sparkles, Undo2, Wrench } from "lucide-react";
import { detailCopy, type AgentName, type Run, type RunEvent } from "../lib/api";
import { AGENTS, agentStates, reviewVerdict, type AgentState } from "../lib/agents";
import { formatTime } from "../lib/time";
import { cx, Pill } from "./ui";

export function ModeBadge({ run }: { run: Pick<Run, "mode" | "model"> }) {
  if (run.mode === "live") {
    const model = run.model?.replace(/^muse-spark-/i, "Muse Spark ") ?? "Muse Spark 1.3";
    return <Pill tone="violet"><span className="size-1.5 rounded-full bg-violet" aria-hidden /> Live · {model}</Pill>;
  }
  return <Pill tone="amber">Rules-based (offline) — not Muse Spark</Pill>;
}

const TRIGGER: Record<string, string> = {
  user: "You asked",
  pass: "Replanning after you passed",
  decline: "Replanning after a decline",
  feedback: "Replanning with your feedback",
};

const STATE: Record<AgentState, { label: string; cls: string }> = {
  waiting: { label: "Waiting", cls: "text-muted" },
  working: { label: "Working", cls: "text-violet-ink" },
  done: { label: "Done", cls: "text-muted" },
  approved: { label: "Approved", cls: "text-emerald-ink" },
  sent_back: { label: "Sent back", cls: "text-amber-ink" },
};

function AgentAvatar({ agent, dim }: { agent: AgentName; dim?: boolean }) {
  const Icon = AGENTS[agent].icon;
  return (
    <span className={cx("relative z-10 grid size-7 shrink-0 place-items-center rounded-full transition-colors duration-200", dim ? "bg-raised" : "bg-violet-soft")}>
      <Icon className={cx("size-3.5", dim ? "text-muted" : "text-violet-ink")} aria-hidden />
    </span>
  );
}

function AgentChip({ agent, state }: { agent: AgentName; state: AgentState }) {
  const s = STATE[state];
  return (
    <li className="flex min-h-9 items-center gap-2 rounded-full bg-surface py-1 pr-3 pl-1 ring-1 ring-line" title={AGENTS[agent].role}>
      <AgentAvatar agent={agent} dim={state === "waiting"} />
      <span className="text-[13.5px] font-medium">{AGENTS[agent].label}</span>
      <span className={cx("inline-flex items-center gap-1 text-[12.5px]", s.cls)}>
        {state === "working" && <span className="live-dot size-1.5 rounded-full bg-violet" aria-hidden />}
        {(state === "done" || state === "approved") && <Check className="size-3" aria-hidden />}
        {s.label}
      </span>
    </li>
  );
}

/** Who's doing what right now. Scheduler and Planner sit together because they run in parallel. */
function Orchestra({ states }: { states: Record<AgentName, AgentState> }) {
  return (
    <div aria-label="Agents" role="group" className="mb-5 flex flex-wrap items-center gap-2">
      <ul className="contents">
        <AgentChip agent="orchestrator" state={states.orchestrator} />
        <AgentChip agent="matchmaker" state={states.matchmaker} />
      </ul>
      <div className="flex flex-wrap items-center gap-2 rounded-[22px] border border-dashed border-violet/35 p-1">
        <span className="pl-2 text-[11.5px] font-medium tracking-wide text-violet-ink uppercase">In parallel</span>
        <ul className="contents">
          <AgentChip agent="scheduler" state={states.scheduler} />
          <AgentChip agent="planner" state={states.planner} />
        </ul>
      </div>
      <ul className="contents"><AgentChip agent="reviewer" state={states.reviewer} /></ul>
    </div>
  );
}

const KIND_ICON = {
  tool: <Wrench className="size-3.5 text-ink" aria-hidden />,
  model: <Sparkles className="size-3.5 text-violet" aria-hidden />,
  system: <CircleDot className="size-3.5 text-muted" aria-hidden />,
  error: <AlertTriangle className="size-3.5 text-danger" aria-hidden />,
  review: <ClipboardCheck className="size-3.5 text-violet-ink" aria-hidden />,
};
const KIND_BG = { tool: "bg-sunk", model: "bg-violet-soft", system: "bg-raised", error: "bg-danger-soft", review: "bg-violet-soft" };

function EventRow({ e, tz, mode }: { e: RunEvent; tz: string; mode: Run["mode"] }) {
  const agent = e.agent ? AGENTS[e.agent].label : null;
  const kindLabel = { tool: "Tool call", model: mode === "live" ? "Muse Spark" : "Agent", system: "System", error: "Error", review: "Review" }[e.kind];
  const verdict = e.kind === "review" ? reviewVerdict(e) : null;
  return (
    <li className="rise relative flex gap-3 pb-4 last:pb-0">
      {e.agent ? (
        <span className="relative mt-0.5 h-fit shrink-0">
          <AgentAvatar agent={e.agent} />
          {(e.kind === "error" || verdict) && (
            // Kind badge so errors and verdicts stay recognizable when the agent avatar leads the row.
            <span className={cx("absolute -right-1 -bottom-1 z-20 grid size-4 place-items-center rounded-full ring-2 ring-surface",
              e.kind === "error" ? "bg-danger-soft text-danger" : verdict?.approved ? "bg-emerald-soft text-emerald-ink" : "bg-amber-soft text-amber-ink")}>
              {e.kind === "error" ? <AlertTriangle className="size-2.5" aria-hidden /> : verdict?.approved ? <Check className="size-2.5" aria-hidden /> : <Undo2 className="size-2.5" aria-hidden />}
            </span>
          )}
        </span>
      ) : <span className={cx("relative z-10 mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", KIND_BG[e.kind])}>{KIND_ICON[e.kind]}</span>}
      <div className="min-w-0 flex-1 pt-1">
        {(agent || e.kind !== "model") && <span className="sr-only">{kindLabel}: </span>}
        <div className="mb-1 flex flex-wrap items-center gap-1.5 empty:hidden">
          {(agent || e.kind === "model") && <span className="text-[12.5px] font-medium text-violet-ink">{agent ?? kindLabel}</span>}
          {e.kind === "tool" && e.tool_name && <code className="rounded-md bg-ink px-1.5 py-0.5 font-mono text-[12px] leading-5 text-white">{e.tool_name}</code>}
          {verdict && (verdict.approved
            ? <Pill tone="emerald"><Check className="size-3" aria-hidden /> Approved{verdict.target && ` · ${AGENTS[verdict.target].label}`}</Pill>
            : <Pill tone="amber">Sent back to {verdict.target ? AGENTS[verdict.target].label : "an agent"}</Pill>)}
        </div>
        <p className={cx("text-[14.5px] leading-snug break-words", e.kind === "system" && "text-muted", e.kind === "error" && "text-danger")}>
          {verdict ? verdict.reason || e.summary : e.summary}
        </p>
      </div>
      <time className="num shrink-0 pt-1 text-[12px] text-muted" dateTime={e.created_at}>{formatTime(e.created_at, tz)}</time>
    </li>
  );
}

/** The agents' real work as the backend logged it: who did what, tool executions vs narration vs reviewer verdicts. */
export function AgentTimeline({ run, tz, onRetry }: { run: Run; tz: string; onRetry?: () => void }) {
  const events = [...run.events].sort((a, b) => a.seq - b.seq);
  const tools = events.filter((e) => e.kind === "tool").length;
  const orchestra = events.some((e) => e.agent);
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ModeBadge run={run} />
        <span className="text-[13px] text-muted">{TRIGGER[run.trigger] ?? run.trigger} · <span className="num">{tools}</span> tool {tools === 1 ? "call" : "calls"}</span>
      </div>
      {orchestra && <Orchestra states={agentStates(events, run.status)} />}
      <ol className="relative before:absolute before:left-[13.5px] before:top-2 before:bottom-2 before:w-px before:bg-line" aria-live="polite" aria-label="Agent activity">
        {events.map((e) => <EventRow key={e.seq} e={e} tz={tz} mode={run.mode} />)}
        {run.status === "running" && (
          <li className="relative flex items-center gap-3 pt-1">
            <span className="relative z-10 grid size-7 place-items-center rounded-full bg-violet-soft"><span className="live-dot size-2 rounded-full bg-violet" /></span>
            <span className="text-[14px] text-muted">Working…</span>
          </li>
        )}
      </ol>
      {run.status === "failed" && (
        <div role="alert" className="mt-3 text-[14px] text-danger">
          <p>The agent stopped: {(run.error ? detailCopy(run.error) : "unknown error").replace(/[^.!?]$/, "$&.")} Nothing was sent to anyone.</p>
          {run.error === "not_eligible" && (
            <Link to="/verify" className="inline-flex min-h-11 items-center gap-1.5 font-medium text-ink underline-offset-4 hover:underline">Verify your account <ArrowRight className="size-4" aria-hidden /></Link>
          )}
          {onRetry && run.error !== "not_eligible" && (
            <button type="button" onClick={onRetry} className="press mt-1 inline-flex min-h-11 items-center gap-1.5 font-medium text-ink underline-offset-4 hover:underline">
              <RotateCcw className="size-4" aria-hidden /> Try again
            </button>
          )}
        </div>
      )}
      <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted">
        <span className="inline-flex items-center gap-1.5"><Wrench className="size-3" aria-hidden /> Tool call = a real backend action</span>
        <span className="inline-flex items-center gap-1.5"><Sparkles className="size-3" aria-hidden /> Narration = model text</span>
        {orchestra && <span className="inline-flex items-center gap-1.5"><ClipboardCheck className="size-3" aria-hidden /> Review = the Reviewer's verdict</span>}
      </p>
    </div>
  );
}
