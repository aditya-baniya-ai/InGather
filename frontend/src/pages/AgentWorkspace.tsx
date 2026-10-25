import { useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ImagePlus, Lock, Pause, Play, Sparkles } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { AgentTimeline } from "../components/AgentTimeline";
import { Cover } from "../components/Brand";
import { CandidateList } from "../components/CandidateList";
import { PublicLocation } from "../components/PublicLocation";
import { VoiceButton } from "../components/VoiceButton";
import { Button, EmptyState, ErrorState, InlineError, LoadingBlock, Panel, Pill } from "../components/ui";
import { api, ApiError, type Plan, type Proposal } from "../lib/api";
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
      <h2 className="text-[15px] font-semibold">What your agent can do</h2>
      <ul className="mt-2 flex flex-col gap-1.5">
        <li>Search only opted-in, eligible plans</li>
        <li>Check if a group's times overlap, without seeing anyone's schedule</li>
        <li>Suggest people and explain why</li>
      </ul>
      <h2 className="mt-4 text-[15px] font-semibold">What it can't do</h2>
      <ul className="mt-2 flex flex-col gap-1.5">
        <li>Invite anyone without your approval</li>
        <li>Confirm a meetup for you</li>
        <li>Show your itinerary to anyone</li>
      </ul>
      <p className="mt-4 text-[13px] text-muted">These limits are enforced by the server, not by the prompt.</p>
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

function ConsentCard({ plan }: { plan: Plan }) {
  const qc = useQueryClient();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const allow = async () => {
    setBusy(true); setError(null);
    try { qc.setQueryData(keys.plan(plan.id), await api.setDiscovery(plan.id, plan.discovery_mode, true)); }
    catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-2xl bg-violet-soft/70 p-4">
      <label className="flex cursor-pointer gap-3">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-1 size-4 shrink-0 accent-[var(--color-violet)]" />
        <span className="text-[14px]">
          <span className="block font-medium">Allow AI processing for this plan</span>
          Minimized plan details are sent to Meta's Muse Spark model to find and explain matches. Your exact times, email and documents are never sent.
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
  const [goal, setGoal] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const created = (useLocation().state as { created?: boolean } | null)?.created;

  if (plan.isPending) return <AppShell aside={<AgentGuardrails />}><LoadingBlock label="Loading plan" /></AppShell>;
  if (plan.isError) return <AppShell><ErrorState error={plan.error} onRetry={() => plan.refetch()} what="this plan" /></AppShell>;
  const p = plan.data;
  const running = run.data?.status === "running";

  const start = async () => {
    setStarting(true); setError(null);
    try { follow(await api.startRun(p.id, goal.trim() || undefined)); } catch (e) { setError(e); } finally { setStarting(false); }
  };

  const prop = proposal.data;
  const reviewing = prop && (prop.status === "pending_owner" || prop.status === "invites_pending") && prop.members.some((m) => m.status === "suggested");

  return (
    <AppShell aside={<AgentGuardrails />}>
      <PlanHeader plan={p} />
      <div className="mb-6"><PublicLocation key={p.id} plan={p} /></div>
      {created && !run.data && <p className="rise mb-4 rounded-2xl bg-emerald-soft px-4 py-3 text-[14.5px] text-emerald-ink" role="status">Plan saved privately. Nobody else can see it.</p>}

      <Panel className="p-5 sm:p-6" aria-labelledby="agent-title">
        <h2 id="agent-title" className="flex items-center gap-2 section-title"><Sparkles className="size-4 text-violet" aria-hidden /> Gather Agent</h2>
        {!p.ai_consent ? <div className="mt-4"><ConsentCard plan={p} /></div> : (
          <div className="mt-4">
            <label htmlFor="goal" className="sr-only">What should your agent look for?</label>
            <textarea id="goal" rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={500}
              placeholder="Find me a group after the conference."
              className="w-full resize-none rounded-2xl border border-line bg-raised px-4 py-3 leading-relaxed outline-none transition-[border-color] focus:border-violet focus:bg-surface" />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button variant="agent" size="lg" onClick={start} loading={starting || running} disabled={p.discovery_mode === "paused" || me?.can_discover === false}
                icon={<Sparkles className="size-4" aria-hidden />}>{running ? "Working…" : "Find my people"}</Button>
              <VoiceButton onText={(t) => setGoal((g) => (g ? `${g} ${t}` : t))} />
            </div>
            {p.discovery_mode === "paused" && <p className="mt-2 text-[13.5px] text-muted">Discovery is paused for this plan. Resume it to search.</p>}
            {me?.can_discover === false && <p className="mt-2 text-[13.5px] text-muted">Your account isn't eligible for discovery yet (verification needed, or discovery paused in Profile).</p>}
            <InlineError error={error} />
            {(me?.verification === "unverified" || (error instanceof ApiError && error.detail === "not_eligible")) && (
              <Link to="/verify" className="mt-1 inline-flex min-h-11 items-center gap-1.5 text-[14.5px] font-medium underline-offset-4 hover:underline">Verify your account <ArrowRight className="size-4" aria-hidden /></Link>
            )}
          </div>
        )}

        {run.isError && !(run.error instanceof ApiError && run.error.status === 404) && <div className="mt-5"><ErrorState error={run.error} onRetry={() => run.refetch()} what="agent activity" /></div>}
        {run.data && (
          <div className="mt-6 border-t border-line pt-5">
            <AgentTimeline run={run.data} tz={p.timezone} onRetry={start} />
            {run.data.summary && run.data.status === "completed" && !run.data.events.some((e) => e.summary === run.data!.summary) && (
              <p className="rise mt-5 rounded-2xl bg-violet-soft/70 px-4 py-3 text-[15px] leading-relaxed">{run.data.summary}</p>
            )}
          </div>
        )}
        {run.isPending && run.fetchStatus === "fetching" && <div className="mt-6"><LoadingBlock label="Loading agent activity" rows={2} /></div>}
      </Panel>

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
