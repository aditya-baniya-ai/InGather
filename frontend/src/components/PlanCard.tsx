import { Link } from "react-router-dom";
import { ArrowRight, Eye, Lock } from "lucide-react";
import type { Plan } from "../lib/api";
import { useProposal } from "../lib/hooks";
import { formatDateRange } from "../lib/time";
import { activityLabel, DISCOVERY, PROPOSAL_STATUS } from "../lib/vocab";
import { Cover } from "./Brand";
import { Pill } from "./ui";

function ProposalStatusLine({ id }: { id: string }) {
  const q = useProposal(id, false);
  if (!q.data) return null;
  const p = q.data;
  const pending = p.members.filter((m) => m.status === "suggested").length;
  const accepted = p.members.filter((m) => m.status === "accepted").length;
  const text = p.status === "pending_owner" ? `${pending} ${pending === 1 ? "person" : "people"} waiting for your approval`
    : p.status === "invites_pending" ? `${accepted} accepted so far`
      : PROPOSAL_STATUS[p.status];
  return <Pill tone={p.status === "confirmed" ? "emerald" : "violet"}>{text}</Pill>;
}

export function PlanCard({ plan, index = 0 }: { plan: Plan; index?: number }) {
  return (
    <article className="rise overflow-hidden rounded-[24px] border border-line bg-surface" style={{ animationDelay: `${index * 60}ms` }}>
      <Link to={`/plans/${plan.id}`} className="group block focus-visible:outline-offset-[-2px]">
        <div className="relative aspect-[16/8] overflow-hidden bg-sunk">
          <Cover seed={plan.id} activity={plan.activity_type} src={plan.cover_image_url} className="size-full transition-transform duration-500 ease-[var(--ease-out)] group-hover:scale-[1.02]" />
          <span className="absolute left-3 top-3"><Pill tone="neutral" className="bg-surface/95 text-ink">{plan.discovery_mode === "mutual_discovery" ? <Eye className="size-3" aria-hidden /> : <Lock className="size-3" aria-hidden />} {DISCOVERY[plan.discovery_mode].label}</Pill></span>
        </div>
        <div className="p-4 sm:p-5">
          <p className="text-[13px] text-muted">{activityLabel(plan.activity_type)} · {plan.city} · {formatDateRange(plan.start_date, plan.end_date)}</p>
          <h3 className="mt-1 text-[18px] font-semibold leading-snug">{plan.title}</h3>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            {plan.latest_proposal_id ? <ProposalStatusLine id={plan.latest_proposal_id} />
              : <span className="text-[13.5px] text-muted">{plan.status === "active" ? "Your agent hasn't searched yet" : plan.status}</span>}
            <span className="inline-flex items-center gap-1 text-[14px] font-medium">Open Gather Agent <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden /></span>
          </div>
        </div>
      </Link>
    </article>
  );
}
