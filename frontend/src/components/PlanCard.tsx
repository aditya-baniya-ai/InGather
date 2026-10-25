import { Link } from "react-router-dom";
import { ArrowRight, Eye, Lock } from "lucide-react";
import { useProposal } from "../lib/hooks";
import { formatDateRange } from "../lib/time";
import { activityLabel, DISCOVERY, PROPOSAL_STATUS } from "../lib/vocab";
import { Cover } from "./Brand";
import { Pill } from "./ui";
import { RemoveButton } from "./RemoveButton";
import { api, type Plan } from "../lib/api";

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
  const proposal = useProposal(plan.latest_proposal_id ?? undefined, false).data;
  const confirmed = proposal?.status === "confirmed";
  return (
    <article className={`rise card lift relative overflow-hidden cat-${plan.activity_type}`} style={{ animationDelay: `${index * 60}ms` }}>
      <Link to={confirmed ? `/proposals/${proposal.id}` : `/plans/${plan.id}`} className="group block focus-visible:outline-offset-[-2px]">
        <div className="relative aspect-[16/8] overflow-hidden bg-sunk">
          <Cover activity={plan.activity_type} city={plan.city} src={plan.cover_image_url} className="size-full transition-transform duration-500 ease-[var(--ease-out)] group-hover:scale-[1.02]" />
          <span className="absolute left-3 top-3"><Pill tone="neutral" className="bg-surface/95 text-ink">{plan.discovery_mode === "mutual_discovery" ? <Eye className="size-3" aria-hidden /> : <Lock className="size-3" aria-hidden />} {DISCOVERY[plan.discovery_mode].label}</Pill></span>
        </div>
        <div className="p-4 sm:p-5">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted"><Pill tone="cat">{activityLabel(plan.activity_type)}</Pill> {plan.city} · {formatDateRange(plan.start_date, plan.end_date)}</p>
          <h3 className="mt-1 text-[18px] font-semibold leading-snug">{plan.title}</h3>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            {plan.latest_proposal_id ? <ProposalStatusLine id={plan.latest_proposal_id} />
              : <span className="text-[13.5px] text-muted">{plan.status === "active" ? "Your agent hasn't searched yet" : plan.status}</span>}
            <span className="inline-flex items-center gap-1 text-[14px] font-semibold text-[var(--cat-ink)]">{confirmed ? "Open your group" : "Find my people"} <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden /></span>
          </div>
        </div>
      </Link>
      <span className="absolute right-3 top-3">
        <RemoveButton label={`Delete plan ${plan.title}`} title="Delete this plan?" confirm="Delete plan"
          body="The plan, its suggestions and any group made from it are removed for everyone. This can't be undone."
          onRemove={() => api.deletePlan(plan.id)} invalidate={[["plans"], ["invitations"], ["chats"]]} />
      </span>
    </article>
  );
}
