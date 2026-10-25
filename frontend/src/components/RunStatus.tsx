import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, RotateCcw, Sparkles } from "lucide-react";
import { detailCopy, type Run } from "../lib/api";

const STEPS = ["Finding people who share your plans…", "Checking when everyone's free…", "Picking a good public spot…"];

/** What a search is doing, in plain words: a moving status while it runs, a short message if it stops, nothing once done. */
export function RunStatus({ run, onRetry }: { run: Run; onRetry?: () => void }) {
  const [step, setStep] = useState(0);
  const running = run.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1600);
    return () => clearInterval(t);
  }, [running]);

  if (running) {
    return (
      <p role="status" className="flex items-center gap-3 rounded-2xl bg-violet-soft/70 px-4 py-3 text-[15px] font-medium text-violet-ink">
        <Sparkles className="size-5 shrink-0 animate-pulse motion-reduce:animate-none" aria-hidden />
        <span key={step} className="rise">{STEPS[step]}</span>
      </p>
    );
  }
  if (run.status !== "failed") return null;
  return (
    <div role="alert" className="text-[14px] text-danger">
      <p>The search stopped: {(run.error ? detailCopy(run.error) : "unknown error").replace(/[^.!?]$/, "$&.")} Nothing was sent to anyone.</p>
      {run.error === "not_eligible" ? (
        <Link to="/verify" className="inline-flex min-h-11 items-center gap-1.5 font-medium text-ink underline-offset-4 hover:underline">Verify your account <ArrowRight className="size-4" aria-hidden /></Link>
      ) : onRetry && (
        <button type="button" onClick={onRetry} className="press mt-1 inline-flex min-h-11 items-center gap-1.5 font-medium text-ink underline-offset-4 hover:underline">
          <RotateCcw className="size-4" aria-hidden /> Try again
        </button>
      )}
    </div>
  );
}
