import { useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ImagePlus, Lock, Pause, Play, RotateCcw } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { RunStatus } from "../components/RunStatus";
import { Cover } from "../components/Brand";
import { CandidateList } from "../components/CandidateList";
import { PublicLocation } from "../components/PublicLocation";
import { Button, EmptyState, ErrorState, InlineError, LoadingBlock, Pill } from "../components/ui";
import { api, ApiError, type Plan, type Proposal, type Run } from "../lib/api";
import { useAuth } from "../lib/auth";
import { keys, useFollowRun, usePlan, usePlans, useProposal } from "../lib/hooks";
import { formatDateRange } from "../lib/time";
import { activityLabel, DISCOVERY, PROPOSAL_STATUS } from "../lib/vocab";

/** "Already invited: Sofia (accepted), Taylor (pending)" for proposals that are partway through. */
function invitedLine(p: Proposal): string | null {
  const out = p.members.filter((m) => !m.is_initiator && (m.status === "invited" || m.status === "accepted"));
  if (!out.length) return null;
  return `Already invited: ${out.map((m) => `${m.display_name} (${m.status === "accepted" ? "accepted" : "pending"})`).join(", ")}.`;
}

function AgentGuardrails() {
  return (
    <div className="rounded-[20px] bg-raised p-5 text-[14px]">
      <h2 className="text-[15px] font-semibold">What matching can do</h2>
      <ul className="mt-2 flex flex-col gap-1.5">
        <li>Search only opted-in, eligible plans</li>
        <li>Score fit with an ML model trained on real group data</li>
        <li>Check if a group's times overlap, without showing anyone's schedule</li>
        <li>Suggest people and explain why</li>
      </ul>
      <h2 className="mt-4 text-[15px] font-semibold">What it can't do</h2>
      <ul className="mt-2 flex flex-col gap-1.5">
        <li>Invite anyone without your approval</li>
        <li>Confirm a meetup for you</li>
        <li>Show your itinerary to anyone</li>
      </ul>
      <p className="mt-4 text-[13px] text-muted">These limits are enforced by the server's checks, whatever the model scores.</p>
    </div>
  );
}

function PlanHeader({ plan }: { plan: Plan }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"cover" | "pause" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [coverOff, setCoverOff] = useState(false);
  const run = async (kind: "cover" | "pause", fn: () => Promise<Plan>) => {
    setBusy(kind); setError(null);
    try { qc.setQueryData(keys.plan(plan.id), await fn()); qc.invalidateQueries({ queryKey: keys.plans }); }
    catch (e) { if (kind === "cover" && e instanceof ApiError && e.status === 503) setCoverOff(true); else setError(e); }
    finally { setBusy(null); }
  };
  const paused = plan.discovery_mode === "paused";
  return (
    <header className="mb-6">
      <div className="flex gap-4">
        <span className="size-20 shrink-0 overflow-hidden rounded-[20px] bg-sunk sm:size-24">
          <Cover activity={plan.activity_type} city={plan.city} src={plan.cover_image_url} className="size-full" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] text-muted">{activityLabel(plan.activity_type)} · {plan.city} · {formatDateRange(plan.start_date, plan.end_date)}</p>
          <h1 className="page-title mt-1">{plan.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Pill tone={paused ? "amber" : "neutral"}><Lock className="size-3" aria-hidden /> {DISCOVERY[plan.discovery_mode].label}</Pill>
            {plan.ai_consent && <Pill tone="violet">AI processing on</Pill>}
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {!plan.cover_image_url && !coverOff && (
          <Button variant="secondary" size="sm" loading={busy === "cover"} onClick={() => run("cover", () => api.generateCover(plan.id))} icon={<ImagePlus className="size-4" aria-hidden />}>
            {busy === "cover" ? "Muse Image is painting… about 15 seconds" : "Generate cover with Muse Image"}
          </Button>
        )}
        <Button variant="secondary" size="sm" loading={busy === "pause"} icon={paused ? <Play className="size-4" aria-hidden /> : <Pause className="size-4" aria-hidden />}
          onClick={() => run("pause", () => api.setDiscovery(plan.id, paused ? "private_browse" : "paused"))}>
          {paused ? "Resume discovery" : "Pause discovery"}
        </Button>
      </div>
      {coverOff && <p className="mt-2 text-[13px] text-muted">Muse Image isn't available right now. Your plan uses a generated pattern instead. Covers use only the activity and city.</p>}
      <InlineError error={error} />
    </header>
  );
}

function ConsentCard({ plan, onRun }: { plan: Plan; onRun: (r: Run) => void }) {
  const qc = useQueryClient();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const allow = async () => {
    setBusy(true); setError(null);
    try {
      const saved = await api.setDiscovery(plan.id, plan.discovery_mode, true);
      qc.setQueryData(keys.plan(plan.id), saved);
      if (saved.discovery_mode !== "paused") onRun(await api.startRun(plan.id));  // start looking right away
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-2xl bg-violet-soft/70 p-4">
      <label className="flex cursor-pointer gap-3">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-1 size-4 shrink-0 accent-[var(--color-violet)]" />
        <span className="text-[14px]">
          <span className="block font-medium">Allow AI processing for this plan</span>
          InGather's own matching model scores this plan against other opted-in plans on our server. Nothing is sent to an outside AI model for matching, and nobody sees your exact times, email or documents.
        </span>
      </label>
      <Button variant="agent" size="sm" className="mt-3" disabled={!checked} loading={busy} onClick={allow}>Allow and continue</Button>
      <InlineError error={error} />
    </div>
  );
}

export function AgentWorkspace() {
  const { planId = "" } = useParams();
  const { me } = useAuth();
  const plan = usePlan(planId, 4000);
  const { run, follow } = useFollowRun(planId, plan.data?.latest_run_id);
  const proposalId = run.data?.proposal_id ?? plan.data?.latest_proposal_id;
  const proposal = useProposal(proposalId);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const created = (useLocation().state as { created?: boolean } | null)?.created;

  if (plan.isPending) return <AppShell aside={<AgentGuardrails />}><LoadingBlock label="Loading plan" /></AppShell>;
  if (plan.isError) return <AppShell><ErrorState error={plan.error} onRetry={() => plan.refetch()} what="this plan" /></AppShell>;
  const p = plan.data;
  const running = run.data?.status === "running";

  const start = async () => {
    setStarting(true); setError(null);
    try { follow(await api.startRun(p.id)); } catch (e) { setError(e); } finally { setStarting(false); }
  };

  const prop = proposal.data;
  const reviewing = prop && (prop.status === "pending_owner" || prop.status === "invites_pending") && prop.members.some((m) => m.status === "suggested");
  // A plain retry button only when there is nothing to act on: no live group, not running, and no failure message (that has its own "Try again").
  const canSearch = !running && run.data?.status !== "failed" && (!prop || prop.status === "cancelled")
    && p.discovery_mode !== "paused" && me?.can_discover !== false;

  return (
    <AppShell aside={<AgentGuardrails />}>
      <PlanHeader plan={p} />
      <div className="mb-6"><PublicLocation key={p.id} plan={p} /></div>
      {created && !run.data && <p className="rise mb-4 rounded-2xl bg-emerald-soft px-4 py-3 text-[14.5px] text-emerald-ink" role="status">Plan saved privately. Nobody else can see it.</p>}

      {!p.ai_consent ? <div className="mb-6"><ConsentCard plan={p} onRun={follow} /></div> : (
        <div className="mb-6 flex flex-col gap-3">
          {run.data && <RunStatus run={run.data} onRetry={start} />}
          {canSearch && (
            <div>
              <Button variant="secondary" size="sm" onClick={start} loading={starting} icon={<RotateCcw className="size-4" aria-hidden />}>
                {run.data ? "Search again" : "Find people"}
              </Button>
            </div>
          )}
          {run.isError && !(run.error instanceof ApiError && run.error.status === 404) && <ErrorState error={run.error} onRetry={() => run.refetch()} what="the search" />}
          {p.discovery_mode === "paused" && <p className="text-[13.5px] text-muted">Discovery is paused for this plan. Resume it to search.</p>}
          {me?.can_discover === false && <p className="text-[13.5px] text-muted">Your account isn't eligible for discovery yet (verification needed, or discovery paused in Profile).</p>}
          {(me?.verification === "unverified" || (error instanceof ApiError && error.detail === "not_eligible")) && (
            <Link to="/verify" className="inline-flex min-h-11 items-center gap-1.5 text-[14.5px] font-medium underline-offset-4 hover:underline">Verify your account <ArrowRight className="size-4" aria-hidden /></Link>
          )}
          <InlineError error={error} />
        </div>
      )}

      <section className="mt-6" aria-labelledby="people-title">
        {proposal.isError && !(proposal.error instanceof ApiError && proposal.error.status === 404) && <ErrorState error={proposal.error} onRetry={() => proposal.refetch()} what="suggestions" />}
        {reviewing ? (
          <>
            <h2 id="people-title" className="mb-1 section-title">Your people</h2>
            <p className="mb-4 text-[14px] text-muted">{prop.explanation || "I found a possible group with compatible plans. You choose who to invite."}</p>
            {invitedLine(prop) && <p className="mb-4 text-[14px]">{invitedLine(prop)}</p>}
            <CandidateList proposal={prop} onRun={follow} agentWorking={running} />
            <Link to={`/proposals/${prop.id}`} className="mt-4 inline-flex min-h-11 items-center gap-1.5 text-[14.5px] font-medium underline-offset-4 hover:underline">
              See the full proposal: time, place and invitations <ArrowRight className="size-4" aria-hidden />
            </Link>
          </>
        ) : prop && prop.status !== "cancelled" ? (
          <Link to={`/proposals/${prop.id}`} className="press flex min-h-16 items-center justify-between gap-3 rounded-[20px] border border-line bg-surface px-5 py-4 hover:bg-raised">
            <span><span id="people-title" className="block font-semibold">{prop.activity_title}</span><span className="block text-[14px] text-muted">{PROPOSAL_STATUS[prop.status]}</span></span>
            <ArrowRight className="size-5" aria-hidden />
          </Link>
        ) : run.data?.status === "completed" && !running ? (
          <EmptyState title="No suitable opted-in plans yet.">
            Nobody eligible overlaps with this plan right now. Try different dates or interests, or check back later. Nobody was contacted.
          </EmptyState>
        ) : null}
      </section>
    </AppShell>
  );
}

/** /agent: open the most recent active plan's workspace, or ask the user to create one. */
export function AgentIndex() {
  const plans = usePlans();
  if (plans.isPending) return <AppShell><LoadingBlock label="Loading plans" /></AppShell>;
  if (plans.isError) return <AppShell><ErrorState error={plans.error} onRetry={() => plans.refetch()} what="your plans" /></AppShell>;
  const active = plans.data.filter((p) => p.status !== "cancelled");
  if (active.length === 1) return <Navigate to={`/plans/${active[0].id}`} replace />;
  return (
    <AppShell aside={<AgentGuardrails />}>
      <h1 className="mb-1 page-title">Gather <span className="ig-text">Agent</span></h1>
      <p className="mb-6 text-[15px] text-muted">Pick a plan. Your agent works on one private plan at a time.</p>
      {active.length === 0 ? (
        <EmptyState title="Your agent needs a plan to work from." action={<Link to="/create" className="press inline-flex min-h-11 items-center rounded-full ig-grad btn-grad px-5 font-medium text-white">Create a private plan</Link>} />
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-[20px] border border-line bg-surface">
          {active.map((p) => (
            <li key={p.id}>
              <Link to={`/plans/${p.id}`} className="flex min-h-16 items-center gap-4 px-4 py-3 hover:bg-raised">
                <span className="size-12 shrink-0 overflow-hidden rounded-xl"><Cover activity={p.activity_type} city={p.city} src={p.cover_image_url} className="size-full" /></span>
                <span className="min-w-0 flex-1"><span className="block truncate font-medium">{p.title}</span><span className="block text-[13.5px] text-muted">{p.city} · {formatDateRange(p.start_date, p.end_date)}</span></span>
                <ArrowRight className="size-4 text-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
