import { RemoveButton } from "../components/RemoveButton";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { Avatar, EmptyState, ErrorState, LoadingBlock, Pill, SectionTitle } from "../components/ui";
import { api, type Plan } from "../lib/api";
import { useInvitations, usePlans, useProposal } from "../lib/hooks";
import { formatDay } from "../lib/time";
import { MEMBER_STATUS, PROPOSAL_STATUS } from "../lib/vocab";

/** Owner side: minimal per-person status for each of my open proposals. */
function SentRow({ plan }: { plan: Plan }) {
  const q = useProposal(plan.latest_proposal_id, 5000);
  if (!q.data) return null;
  const p = q.data;
  const people = p.members.filter((m) => !m.is_initiator && ["invited", "accepted", "declined", "suggested"].includes(m.status));
  if (!people.length) return null;
  return (
    <li>
      <Link to={`/proposals/${p.id}`} className="block rounded-[20px] border border-line bg-surface p-4 hover:bg-raised">
        <div className="flex items-center justify-between gap-3">
          <p className="font-semibold">{p.activity_title}</p>
          <span className="text-[13px] text-muted">{PROPOSAL_STATUS[p.status]}</span>
        </div>
        <ul className="mt-3 flex flex-wrap gap-2">
          {people.map((m) => (
            <li key={m.user_id} className="flex items-center gap-2 rounded-full bg-raised py-1 pl-1 pr-3 text-[13.5px]">
              <Avatar name={m.display_name} src={m.avatar_url} size={24} />
              {m.display_name}
              <Pill tone={MEMBER_STATUS[m.status].tone} className="ml-1">{m.status === "suggested" ? "Needs your approval" : MEMBER_STATUS[m.status].label}</Pill>
            </li>
          ))}
        </ul>
      </Link>
    </li>
  );
}

export function Invitations() {
  const inv = useInvitations();
  const plans = usePlans();
  const note = (useLocation().state as { note?: string } | null)?.note;
  const open = inv.data?.filter((i) => i.status === "invited") ?? [];
  const past = inv.data?.filter((i) => i.status !== "invited") ?? [];
  const mine = plans.data?.filter((p) => p.latest_proposal_id && p.status !== "cancelled") ?? [];

  return (
    <AppShell>
      <h1 className="mb-1 page-title">Invitations</h1>
      <p className="mb-6 text-[15px] text-muted">Only people an organizer explicitly approved can invite you. You can always say no.</p>
      {note && <p role="status" className="rise mb-4 rounded-2xl bg-raised px-4 py-3 text-[14.5px]">{note}</p>}

      <section aria-labelledby="inbox-title">
        <SectionTitle id="inbox-title">For you</SectionTitle>
        {inv.isPending ? <LoadingBlock rows={2} label="Loading invitations" />
          : inv.isError ? <ErrorState error={inv.error} onRetry={() => inv.refetch()} what="invitations" />
            : open.length === 0 && past.length === 0 ? <EmptyState title="No invitations yet.">When someone's agent suggests you and they approve, it shows up here.</EmptyState>
              : (
                <ul className="flex flex-col gap-3">
                  {[...open, ...past].map((i) => (
                    <li key={i.proposal_id} className="flex items-center gap-2">
                      <Link to={`/proposals/${i.proposal_id}`} className="press flex min-w-0 flex-1 items-center gap-4 rounded-[20px] border border-line bg-surface p-4 hover:bg-raised">
                        <Avatar name={i.from_display_name} src={i.from_avatar_url} size={48} ring={i.status === "invited"} />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">{i.activity_title}</p>
                          <p className="text-[13.5px] text-muted">From {i.from_display_name} · {i.city}{i.date ? ` · ${formatDay(i.date)}` : ""} · group of <span className="num">{i.group_size}</span></p>
                          <div className="mt-1.5"><Pill tone={MEMBER_STATUS[i.status].tone}>{i.status === "invited" ? "Waiting for your answer" : MEMBER_STATUS[i.status].label}</Pill></div>
                        </div>
                        <ArrowRight className="size-5 shrink-0 text-muted" aria-hidden />
                      </Link>
                      <RemoveButton label={`Remove ${i.activity_title}`} title={i.status === "invited" ? "Decline and remove?" : "Leave and remove this group?"}
                        confirm={i.status === "invited" ? "Decline" : "Leave group"}
                        body={i.status === "invited" ? "This privately declines the invitation and removes it from your list." : "You leave the group and lose access to its details and chat. Others keep their copy."}
                        onRemove={() => (i.status === "invited" ? api.respond(i.proposal_id, false) : api.leave(i.proposal_id))}
                        invalidate={[["invitations"], ["chats"]]} />
                    </li>
                  ))}
                </ul>
              )}
      </section>

      {mine.length > 0 && (
        <section className="mt-10" aria-labelledby="sent-title">
          <SectionTitle id="sent-title">Sent by you</SectionTitle>
          <ul className="flex flex-col gap-3">{mine.map((p) => <SentRow key={p.id} plan={p} />)}</ul>
        </section>
      )}
    </AppShell>
  );
}
