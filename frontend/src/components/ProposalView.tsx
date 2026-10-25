import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Lock, Users, X } from "lucide-react";
import { api, type Invitation, type Proposal, type Run } from "../lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { keys, useSetProposal } from "../lib/hooks";
import { formatDay } from "../lib/time";
import { MEMBER_STATUS, PROPOSAL_STATUS } from "../lib/vocab";
import { CandidateList } from "./CandidateList";
import { SafetyActions } from "./SafetyActions";
import { FinalizeForm, SafeMeet, VenueTime } from "./SafeMeet";
import { VenueVote, canVoteVenue } from "./VenueVote";
import { Avatar, Button, InlineError, Panel, Pill } from "./ui";

function Roster({ p, title = "Group" }: { p: Proposal; title?: string }) {
  const people = p.members.filter((m) => m.status !== "suggested" && m.status !== "passed");
  return (
    <Panel className="p-5" aria-labelledby="roster-title">
      <h2 id="roster-title" className="mb-3 section-title">{title}</h2>
      <ul className="flex flex-col gap-3">
        {people.map((m) => (
          <li key={m.user_id} className="flex items-center gap-3">
            <Avatar name={m.display_name} src={m.avatar_url} size={40} />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{m.display_name}{m.is_initiator && <span className="font-normal text-muted"> · organizer</span>}</p>
              {m.interests.length > 0 && <p className="truncate text-[13px] text-muted">{m.interests.slice(0, 3).join(" · ")}</p>}
            </div>
            {!m.is_initiator && <Pill tone={MEMBER_STATUS[m.status].tone}>{MEMBER_STATUS[m.status].label}</Pill>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Header({ p, organizer }: { p: Proposal; organizer?: string }) {
  const date = p.start_at ? formatDay(p.start_at, p.timezone) : null;
  return (
    <header className="mb-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Pill tone={p.status === "confirmed" ? "emerald" : p.status === "cancelled" ? "neutral" : "violet"}>{PROPOSAL_STATUS[p.status]}</Pill>
        <span className="inline-flex items-center gap-1.5 text-[13.5px] text-muted"><Users className="size-4" aria-hidden /><span>Group of <span className="num">{p.group_size}</span></span></span>
      </div>
      <h1 className="page-title">{p.activity_title}</h1>
      <p className="mt-2 text-[15px] text-muted">{[p.city, date, organizer && `from ${organizer}`].filter(Boolean).join(" · ")}</p>
    </header>
  );
}

/** Invitee stage: only activity, city, date, size and organizer. No roster, no venue, no reasons. */
function InviteeView({ p, organizer }: { p: Proposal; organizer?: string }) {
  const setProposal = useSetProposal();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const respond = async (accept: boolean) => {
    setBusy(accept ? "accept" : "decline"); setError(null);
    try {
      const next = await api.respond(p.id, accept);
      qc.invalidateQueries({ queryKey: keys.invitations });
      if (accept && next) setProposal(next);
      else navigate("/invitations", { replace: true, state: { note: "Declined. The organizer isn't told why." } });
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return (
    <>
      <Header p={p} organizer={organizer} />
      <Panel className="p-5 sm:p-6">
        <h2 className="section-title">You've been invited to a small meetup</h2>
        <p className="mt-2 text-[15px]">
          {organizer ?? "Someone"}'s Gather Agent thought you might enjoy this. Accepting shares your display name and interests with the group, nothing else.
          You'll see who else is coming and agree on a public place before anything is final.
        </p>
        <p className="mt-3 flex items-center gap-2 text-[13.5px] text-muted"><Lock className="size-4" aria-hidden /> Venue and other members stay hidden until you accept.</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button onClick={() => respond(true)} loading={busy === "accept"} disabled={!!busy} icon={<Check className="size-4" aria-hidden />}>Accept</Button>
          <Button variant="secondary" onClick={() => respond(false)} loading={busy === "decline"} disabled={!!busy} icon={<X className="size-4" aria-hidden />}>Decline</Button>
        </div>
        <p className="mt-2 text-[13px] text-muted">Declining is private. No reason needed.</p>
        <InlineError error={error} />
        <div className="mt-5 border-t border-line pt-4">
          <SafetyActions proposalId={p.id} person={{ id: p.initiator_user_id, name: organizer ?? p.initiator_name }}
            onBlocked={() => navigate("/invitations", { replace: true })} />
        </div>
      </Panel>
    </>
  );
}

function MemberView({ p }: { p: Proposal }) {
  const navigate = useNavigate();
  const organizer = p.members.find((m) => m.is_initiator);
  const final = p.status === "awaiting_final" || p.status === "confirmed";
  return (
    <>
      <Header p={p} organizer={p.initiator_name || organizer?.display_name} />
      <div className="flex flex-col gap-4">
        {canVoteVenue(p) && <VenueVote p={p} />}
        {final ? <SafeMeet p={p} /> : (
          <Panel className="p-5"><p className="text-[15px]">You're in. Vote on a public place with the group, or the organizer will propose one; you'll confirm the final details before anything is set.</p></Panel>
        )}
        <Roster p={p} />
        <SafetyActions proposalId={p.id} person={organizer && { id: organizer.user_id, name: organizer.display_name }}
          onLeave={() => navigate("/invitations", { replace: true })} onBlocked={() => navigate("/invitations", { replace: true })} />
      </div>
    </>
  );
}

function OwnerView({ p, onRun }: { p: Proposal; onRun: (r: Run) => void }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const has = (s: string) => p.members.some((m) => m.status === s);
  const suggested = has("suggested");
  const someoneIn = p.members.some((m) => !m.is_initiator && (m.status === "invited" || m.status === "accepted"));
  const outstanding = p.status === "invites_pending" || p.status === "pending_owner";
  const canFinalize = has("accepted") && !has("invited") && (p.status === "invites_pending" || p.status === "awaiting_final");
  const final = p.status === "awaiting_final" || p.status === "confirmed";
  return (
    <>
      <Header p={p} />
      <div className="flex flex-col gap-4">
        {canVoteVenue(p) && <VenueVote p={p} />}
        {final && <SafeMeet p={p} />}
        {p.status === "pending_owner" && (
          <Panel className="p-5 sm:p-6" aria-labelledby="proposal-title">
            <h2 id="proposal-title" className="section-title">Your agent has a proposal</h2>
            {p.explanation && <p className="mt-2 text-[15px] leading-relaxed">{p.explanation}</p>}
            <div className="mt-4"><VenueTime p={p} /></div>
            <p className="mt-3 flex items-center gap-2 text-[13.5px] text-muted"><Lock className="size-4" aria-hidden /> {someoneIn ? "No new invitations have been sent." : "No invitation has been sent yet."}</p>
          </Panel>
        )}
        {has("declined") && outstanding && (
          <p className="rise rounded-2xl bg-violet-soft/70 px-4 py-3 text-[14.5px]" role="status">
            {suggested && p.status === "pending_owner"
              ? "Someone couldn't join. I found alternatives below. Nobody new is contacted until you approve."
              : "Someone couldn't join. I'll check alternatives and ask you before contacting anyone new."}
          </p>
        )}
        {suggested && outstanding && (
          <Panel className="p-5 sm:p-6" aria-labelledby="suggested-title">
            <h2 id="suggested-title" className="mb-1 section-title">{someoneIn ? "New suggestions need your approval" : "People you could invite"}</h2>
            <p className="mb-4 text-[14px] text-muted">I found a possible group with compatible plans. You choose who to invite.</p>
            <CandidateList proposal={p} onRun={onRun} />
          </Panel>
        )}
        {p.members.some((m) => !m.is_initiator && ["invited", "accepted", "declined"].includes(m.status)) && <Roster p={p} title="Invitations" />}
        {canFinalize && (!final || editing) && (
          <Panel className="p-5 sm:p-6" aria-labelledby="finalize-title">
            <h2 id="finalize-title" className="mb-4 section-title">{final ? "Change final details" : "Set the final public place and time"}</h2>
            <FinalizeForm p={p} onDone={() => setEditing(false)} />
          </Panel>
        )}
        {final && canFinalize && !editing && <div><Button variant="ghost" size="sm" onClick={() => setEditing(true)}>Change time or place</Button></div>}
        {p.status !== "cancelled" && (
          <SafetyActions proposalId={p.id} leaveLabel="Cancel this meetup" onLeave={() => navigate("/home", { replace: true })} />
        )}
      </div>
    </>
  );
}

/** Renders a proposal for exactly the stage the backend says the viewer is at. */
export function ProposalView({ proposal, onRun, invitation }: { proposal: Proposal; onRun: (r: Run) => void; invitation?: Invitation }) {
  if (proposal.viewer_role === "owner") return <OwnerView p={proposal} onRun={onRun} />;
  if (proposal.viewer_role === "invitee") {
    const organizer = proposal.initiator_name || invitation?.from_display_name;
    return <InviteeView p={proposal} organizer={organizer} />;
  }
  return <MemberView p={proposal} />;
}

