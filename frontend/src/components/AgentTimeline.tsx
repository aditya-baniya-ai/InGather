import { AlertTriangle, CircleDot, Sparkles, Wrench } from "lucide-react";
import type { Run, RunEvent } from "../lib/api";
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

function EventRow({ e, tz, mode }: { e: RunEvent; tz: string; mode: Run["mode"] }) {
  const icon = {
    tool: <Wrench className="size-3.5 text-ink" aria-hidden />,
    model: <Sparkles className="size-3.5 text-violet" aria-hidden />,
    system: <CircleDot className="size-3.5 text-muted" aria-hidden />,
    error: <AlertTriangle className="size-3.5 text-danger" aria-hidden />,
  }[e.kind];
  const who = { tool: "Tool call", model: mode === "live" ? "Muse Spark" : "Agent", system: "System", error: "Error" }[e.kind];
  return (
    <li className="rise relative flex gap-3 pb-4 last:pb-0">
      <span className={cx("relative z-10 mt-0.5 grid size-7 shrink-0 place-items-center rounded-full",
        e.kind === "tool" ? "bg-sunk" : e.kind === "model" ? "bg-violet-soft" : e.kind === "error" ? "bg-danger-soft" : "bg-raised")}>{icon}</span>
      <div className="min-w-0 flex-1 pt-1">
        <span className="sr-only">{who}: </span>
        {e.kind === "tool" && e.tool_name && (
          <code className="mb-1 inline-block rounded-md bg-ink px-1.5 py-0.5 font-mono text-[12px] leading-5 text-white">{e.tool_name}</code>
        )}
        {e.kind === "model" && <span className="block text-[12.5px] font-medium text-violet-ink" aria-hidden>{who}</span>}
        <p className={cx("text-[14.5px] leading-snug break-words",
          e.kind === "system" && "text-muted", e.kind === "error" && "text-danger")}>{e.summary}</p>
      </div>
      <time className="num shrink-0 pt-1 text-[12px] text-muted" dateTime={e.created_at}>{formatTime(e.created_at, tz)}</time>
    </li>
  );
}

/** The agent's real work: tool executions vs model narration vs system notes, as the backend logged them. */
export function AgentTimeline({ run, tz }: { run: Run; tz: string }) {
  const events = [...run.events].sort((a, b) => a.seq - b.seq);
  const tools = events.filter((e) => e.kind === "tool").length;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ModeBadge run={run} />
        <span className="text-[13px] text-muted">{TRIGGER[run.trigger] ?? run.trigger} · <span className="num">{tools}</span> tool {tools === 1 ? "call" : "calls"}</span>
      </div>
      <ol className="relative before:absolute before:left-[13.5px] before:top-2 before:bottom-2 before:w-px before:bg-line" aria-live="polite" aria-label="Agent activity">
        {events.map((e) => <EventRow key={e.seq} e={e} tz={tz} mode={run.mode} />)}
        {run.status === "running" && (
          <li className="relative flex items-center gap-3 pt-1">
            <span className="relative z-10 grid size-7 place-items-center rounded-full bg-violet-soft"><span className="live-dot size-2 rounded-full bg-violet" /></span>
            <span className="text-[14px] text-muted">Working…</span>
          </li>
        )}
      </ol>
      {run.status === "failed" && <p role="alert" className="mt-3 text-[14px] text-danger">The agent stopped: {run.error ?? "unknown error"}. Nothing was sent to anyone.</p>}
      <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted">
        <span className="inline-flex items-center gap-1.5"><Wrench className="size-3" aria-hidden /> Tool call = a real backend action</span>
        <span className="inline-flex items-center gap-1.5"><Sparkles className="size-3" aria-hidden /> Narration = model text</span>
      </p>
    </div>
  );
}
