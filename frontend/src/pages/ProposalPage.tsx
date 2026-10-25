import { Link, useParams } from "react-router-dom";
import { EyeOff } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { AgentTimeline } from "../components/AgentTimeline";
import { GatherChat } from "../components/GatherChat";
import { ProposalView } from "../components/ProposalView";
import { ErrorState, LoadingBlock } from "../components/ui";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Proposal, type Run } from "../lib/api";
import { keys, useFollowRun, useInvitations, usePlan, useProposal } from "../lib/hooks";

/** Owner's right panel: the agent's latest run for this plan, e.g. the decline-triggered replan. */
function OwnerAgentPanel({ proposal, inline }: { proposal: Proposal; inline?: boolean }) {
  const plan = usePlan(proposal.plan_id, 4000);
  const { run, follow } = useFollowRun(proposal.plan_id, plan.data?.latest_run_id);
  const retry = () => api.replan(proposal.id, null).then(follow, () => run.refetch());
  const activity = run.data && (
    <div className="rounded-[20px] border border-line bg-surface p-5">
      <h2 className="mb-3 text-[15px] font-semibold">Agent activity</h2>
      <AgentTimeline run={run.data} tz={proposal.timezone} onRetry={retry} />
    </div>
  );
  // Below xl the right rail is hidden: surface the agent inline while it is actually working.
  if (inline) return run.data?.status === "running" && proposal.status !== "confirmed" ? <div className="mb-4 xl:hidden">{activity}</div> : null;
  return proposal.status === "confirmed" ? null : activity || null;
}

export function NotAvailable() {
  return (
    <div className="rounded-[24px] border border-line bg-surface p-8 text-center">
      <EyeOff className="mx-auto size-6 text-muted" aria-hidden />
      <h1 className="mt-3 text-[20px] font-semibold">This meetup isn't available</h1>
      <p className="mx-auto mt-1 max-w-sm text-[14.5px] text-muted">It may not exist, or you're not part of it. InGather never shows a group's details to people outside it.</p>
      <Link to="/home" className="press mt-5 inline-flex min-h-11 items-center rounded-full ig-grad btn-grad px-5 font-medium text-white">Back home</Link>
    </div>
  );
}

export function ProposalPage() {
  const { proposalId = "" } = useParams();
  const q = useProposal(proposalId, 3000);
  const invitations = useInvitations();
  const isOwner = q.data?.viewer_role === "owner";
  const qc = useQueryClient();
  // A pass/replan here starts a run; refreshing the plan makes the agent panel follow it.
  const onRun = (r: Run) => {
    qc.setQueryData(keys.run(r.id), r);
    qc.invalidateQueries({ queryKey: keys.plan(r.plan_id) });
  };

  if (q.isPending) return <AppShell><LoadingBlock label="Loading proposal" /></AppShell>;
  if (q.isError) {
    return <AppShell>{q.error instanceof ApiError && q.error.status === 404 ? <NotAvailable /> : <ErrorState error={q.error} onRetry={() => q.refetch()} what="this proposal" />}</AppShell>;
  }
  const invitation = invitations.data?.find((i) => i.proposal_id === proposalId);
  return (
    <AppShell chatAside={q.data.status === "confirmed"} aside={q.data.status === "confirmed" ? <GatherChat key={q.data.id} proposal={q.data} /> : isOwner ? <OwnerAgentPanel proposal={q.data} /> : undefined}>
      {isOwner && <OwnerAgentPanel proposal={q.data} inline />}
      {q.data.status === "confirmed" && <div className="mb-6 xl:hidden"><GatherChat key={q.data.id} proposal={q.data} /></div>}
      <ProposalView proposal={q.data} onRun={onRun} invitation={invitation} />
    </AppShell>
  );
}
