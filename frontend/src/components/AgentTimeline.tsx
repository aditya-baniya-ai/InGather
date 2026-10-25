import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, BrainCircuit, RotateCcw, Check, ChevronRight, CircleDot, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { detailCopy, type AgentName, type Run, type RunEvent } from "../lib/api";
import { AGENT_ORDER, AGENTS, agentStates, isStep, type AgentState } from "../lib/agents";
import { formatTime } from "../lib/time";
import { cx, Pill } from "./ui";

export function ModeBadge({ run }: { run: Pick<Run, "mode" | "model"> }) {
  if (run.mode === "ml") {
    return <Pill tone="emerald"><BrainCircuit className="size-3" aria-hidden /> ML matcher{run.model && ` · ${run.model}`} · no AI chat model</Pill>;
  }
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
  passed: { label: "Passed", cls: "text-emerald-ink" },
  failed: { label: "Failed", cls: "text-danger" },
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
    <li className={cx("flex min-h-9 items-center gap-2 rounded-full bg-surface py-1 pr-3 pl-1 ring-1 transition-shadow", state === "working" ? "agent-pulse ring-violet/40" : "ring-line")} title={AGENTS[agent].role}>
      <AgentAvatar agent={agent} dim={state === "waiting"} />
      <span className="text-[13.5px] font-medium">{AGENTS[agent].label}</span>
      <span className={cx("inline-flex items-center gap-1 text-[12.5px]", s.cls)}>
        {state === "working" && <span className="live-dot size-1.5 rounded-full bg-violet" aria-hidden />}
        {(state === "done" || state === "passed") && <Check className="size-3" aria-hidden />}
        {s.label}
      </span>
    </li>
  );
}

/** The pipeline's steps in order, each with its live state. */
function Pipeline({ states }: { states: Record<AgentName, AgentState> }) {
  return (
    <ol aria-label="Steps" className="mb-5 flex flex-wrap items-center gap-1.5">
      {AGENT_ORDER.map((a, i) => (
        <li key={a} className="contents">
          <ul className="contents"><AgentChip agent={a} state={states[a]} /></ul>
          {i < AGENT_ORDER.length - 1 && <ChevronRight className="size-3.5 text-muted" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

const KIND_ICON = {
  tool: <Wrench className="size-3.5 text-ink" aria-hidden />,
  model: <Sparkles className="size-3.5 text-violet" aria-hidden />,
  system: <CircleDot className="size-3.5 text-muted" aria-hidden />,
  error: <AlertTriangle className="size-3.5 text-danger" aria-hidden />,
  review: <ShieldCheck className="size-3.5 text-emerald-ink" aria-hidden />,
};
const KIND_BG = { tool: "bg-sunk", model: "bg-violet-soft", system: "bg-raised", error: "bg-danger-soft", review: "bg-emerald-soft" };

function EventRow({ e, tz, mode }: { e: RunEvent; tz: string; mode: Run["mode"] }) {
  const step = isStep(e.agent) ? e.agent : null;
  const kindLabel = { tool: "Step", model: mode === "live" ? "Muse Spark" : "Agent", system: "Note", error: "Error", review: "Checks" }[e.kind];
  return (
    <li className="rise relative flex gap-3 pb-4 last:pb-0">
      {step ? (
        <span className="relative mt-0.5 h-fit shrink-0">
          <AgentAvatar agent={step} />
          {(e.kind === "error" || e.kind === "review") && (
            // Kind badge so errors and passed checks stay recognizable when the step avatar leads the row.
            <span className={cx("absolute -right-1 -bottom-1 z-20 grid size-4 place-items-center rounded-full ring-2 ring-surface",
              e.kind === "error" ? "bg-danger-soft text-danger" : "bg-emerald-soft text-emerald-ink")}>
              {e.kind === "error" ? <AlertTriangle className="size-2.5" aria-hidden /> : <Check className="size-2.5" aria-hidden />}
            </span>
          )}
        </span>
      ) : <span className={cx("relative z-10 mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", KIND_BG[e.kind])}>{KIND_ICON[e.kind]}</span>}
      <div className="min-w-0 flex-1 pt-1">
        <span className="sr-only">{kindLabel}: </span>
        <div className="mb-1 flex flex-wrap items-center gap-1.5 empty:hidden">
          {(step || e.kind === "model") && <span className="text-[12.5px] font-medium text-violet-ink">{step ? AGENTS[step].label : kindLabel}</span>}
          {e.kind === "tool" && e.tool_name && <code className="rounded-md bg-violet-ink px-1.5 py-0.5 font-mono text-[12px] leading-5 text-white">{e.tool_name}</code>}
        </div>
        <p className={cx("text-[14.5px] leading-snug break-words", e.kind === "system" && "text-muted", e.kind === "error" && "text-danger")}>{e.summary}</p>
      </div>
      <time className="num shrink-0 pt-1 text-[12px] text-muted" dateTime={e.created_at}>{formatTime(e.created_at, tz)}</time>
    </li>
  );
}

/** The pipeline's real work as the backend logged it: which step did what, backend actions vs notes vs checks. */
export function AgentTimeline({ run, tz, onRetry }: { run: Run; tz: string; onRetry?: () => void }) {
  const events = [...run.events].sort((a, b) => a.seq - b.seq);
  const tools = events.filter((e) => e.kind === "tool").length;
  const pipeline = events.some((e) => isStep(e.agent));
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ModeBadge run={run} />
        <span className="text-[13px] text-muted">{TRIGGER[run.trigger] ?? run.trigger} · <span className="num">{tools}</span> {tools === 1 ? "step" : "steps"}</span>
      </div>
      {pipeline && <Pipeline states={agentStates(events, run.status)} />}
      <ol className="relative before:absolute before:left-[13.5px] before:top-2 before:bottom-2 before:w-[2px] before:bg-gradient-to-b before:from-ig-orange/50 before:via-ig-pink/40 before:to-ig-blue/40" aria-live="polite" aria-label="Gather activity">
        {events.map((e) => <EventRow key={e.seq} e={e} tz={tz} mode={run.mode} />)}
        {run.status === "running" && (
          <li className="relative flex items-center gap-3 pt-1">
            <span className="relative z-10 grid size-7 place-items-center rounded-full bg-violet-soft"><span className="live-dot size-2 rounded-full bg-violet" /></span>
            <span className="flex-1"><span className="text-[14px] text-muted">Working…</span><span aria-hidden className="mt-1.5 block h-1 max-w-[220px] overflow-hidden rounded-full bg-violet-soft"><span className="grad-flow ig-grad-full block h-full w-full" /></span></span>
          </li>
        )}
      </ol>
      {run.status === "failed" && (
        <div role="alert" className="mt-3 text-[14px] text-danger">
          <p>The search stopped: {(run.error ? detailCopy(run.error) : "unknown error").replace(/[^.!?]$/, "$&.")} Nothing was sent to anyone.</p>
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
        <span className="inline-flex items-center gap-1.5"><Wrench className="size-3" aria-hidden /> Step = a real backend action</span>
        <span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3" aria-hidden /> Checks = server safety checks</span>
        {run.mode !== "ml" && <span className="inline-flex items-center gap-1.5"><Sparkles className="size-3" aria-hidden /> Narration = model text</span>}
      </p>
    </div>
  );
}
