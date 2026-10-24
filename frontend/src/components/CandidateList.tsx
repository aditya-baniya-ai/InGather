import { useEffect, useRef, useState } from "react";
import { Check, RefreshCw, Send, X } from "lucide-react";
import { api, ApiError, type Feedback, type Member, type Proposal, type Run } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useSetProposal } from "../lib/hooks";
import { FEEDBACK } from "../lib/vocab";
import { Avatar, Button, Chip, cx, Dialog, InlineError, Pill } from "./ui";

function CandidateCard({ m, selected, onToggle, onPass, busy }: { m: Member; selected: boolean; onToggle: () => void; onPass: (f: Feedback | null) => void; busy: boolean }) {
  const [passing, setPassing] = useState(false);
  const demo = useAuth().me?.is_demo; // demo accounts only ever see fictional seeded people
  return (
    <li className={cx("rise rounded-[20px] border bg-surface p-4 transition-colors duration-200", selected ? "border-ink" : "border-line")}>
      <div className="flex items-start gap-3">
        <Avatar name={m.display_name} src={m.avatar_url} size={48} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[16px] font-semibold">{m.display_name}</h3>
            {demo && <Pill tone="neutral">Fictional demo profile</Pill>}
          </div>
          {m.interests.length > 0 && <p className="mt-0.5 text-[13.5px] text-muted">{m.interests.slice(0, 4).join(" · ")}</p>}
        </div>
        <label className="press grid size-11 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-raised">
          <input type="checkbox" checked={selected} onChange={onToggle} className="peer sr-only" />
          <span className={cx("grid size-6 place-items-center rounded-md border-2 transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-violet",
            selected ? "border-ink bg-ink text-white" : "border-control")}>{selected && <Check className="size-4" strokeWidth={3} aria-hidden />}</span>
          <span className="sr-only">Select {m.display_name} to invite</span>
        </label>
      </div>
      {m.reason && (
        <p className="mt-3 rounded-2xl bg-violet-soft/70 px-3.5 py-2.5 text-[14.5px] leading-snug">
          <span className="font-medium text-violet-ink">Why this suggestion: </span>{m.reason}
        </p>
      )}
      {passing ? (
        <div className="rise mt-3">
          <p className="text-[13.5px] text-muted">Optional: tell your agent why. {m.display_name} will never be told.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {FEEDBACK.map((f) => <Chip key={f.label} onClick={() => onPass(f.value)}>{f.label}</Chip>)}
            <Button variant="ghost" size="sm" onClick={() => setPassing(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex gap-2">
          <Button variant={selected ? "primary" : "secondary"} size="sm" onClick={onToggle} icon={selected ? <Check className="size-4" aria-hidden /> : undefined}>
            {selected ? "Selected to invite" : "Interested"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setPassing(true)} disabled={busy} icon={<X className="size-4" aria-hidden />}>Pass</Button>
        </div>
      )}
    </li>
  );
}

/**
 * Owner-only: review suggested people, pass privately (triggers a replan), select who to invite,
 * then approve the exact roster. Nothing is sent until the approval dialog is confirmed.
 */
export function CandidateList({ proposal, onRun, agentWorking }: { proposal: Proposal; onRun: (r: Run) => void; agentWorking?: boolean }) {
  const setProposal = useSetProposal();
  const suggested = proposal.members.filter((m) => m.status === "suggested");
  const passed = proposal.members.filter((m) => m.status === "passed");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // When the replan we kicked off finishes, swap "looking…" for the outcome.
  const wasWorking = useRef(agentWorking);
  useEffect(() => {
    if (wasWorking.current && !agentWorking) setNote((n) => (n?.includes("looking") || n?.includes("Looking") ? "Here's an updated group. Nobody has been contacted." : n));
    wasWorking.current = agentWorking;
  }, [agentWorking]);

  const chosen = suggested.filter((m) => selected.has(m.user_id));
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const pass = (m: Member, f: Feedback | null) => act(async () => {
    onRun(await api.pass(proposal.id, m.user_id, f));
    setSelected((s) => { const n = new Set(s); n.delete(m.user_id); return n; });
    setNote(`No problem. I won't contact ${m.display_name}. I'm looking for different people now.`);
  });
  const replan = () => act(async () => {
    onRun(await api.replan(proposal.id, null));
    setSelected(new Set());
    setNote("Looking for different people. Nobody has been contacted.");
  });
  const approve = () => act(async () => {
    try {
      setProposal(await api.approveInvitations(proposal.id, proposal.version, chosen.map((m) => m.user_id)));
      setConfirming(false);
      setSelected(new Set());
      setNote(`${chosen.length === 1 ? "Invitation" : "Invitations"} sent to ${chosen.map((m) => m.display_name).join(" and ")}. ${chosen.length === 1 ? "They" : "Each person"} can accept or decline freely.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setConfirming(false);
        setProposal(await api.proposal(proposal.id));
        throw new ApiError(409, "The proposal changed while you were reviewing. Check the latest suggestions and approve again.");
      }
      throw e;
    }
  });

  return (
    <div>
      {note && <p className="rise mb-3 rounded-2xl bg-raised px-4 py-3 text-[14.5px]" role="status">{note}</p>}
      {suggested.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {suggested.map((m) => (
            <CandidateCard key={m.user_id} m={m} selected={selected.has(m.user_id)} onToggle={() => toggle(m.user_id)} onPass={(f) => pass(m, f)} busy={busy || !!agentWorking} />
          ))}
        </ul>
      ) : (
        <p className="text-[14.5px] text-muted">No new suggestions right now.</p>
      )}
      {passed.length > 0 && (
        <p className="mt-3 text-[13.5px] text-muted">Passed privately (never notified): {passed.map((m) => m.display_name).join(", ")}</p>
      )}
      <InlineError error={error} />
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={() => setConfirming(true)} disabled={chosen.length === 0 || busy || agentWorking} icon={<Send className="size-4" aria-hidden />}>
          <span>Review {chosen.length > 0 && <span className="num">{chosen.length} </span>}invitation{chosen.length === 1 ? "" : "s"}</span>
        </Button>
        <Button variant="secondary" onClick={replan} loading={busy && !confirming} disabled={agentWorking} icon={<RefreshCw className="size-4" aria-hidden />}>Find different people</Button>
      </div>
      <p className="mt-2 text-[13px] text-muted">{agentWorking ? "Your agent is updating these suggestions…" : "Selecting someone isn't an invitation. Nothing is sent until you approve."}</p>

      <Dialog open={confirming} onClose={() => setConfirming(false)} title="Approve invitations"
        footer={<>
          <Button variant="ghost" onClick={() => setConfirming(false)}>Not yet</Button>
          <Button onClick={approve} loading={busy} icon={<Send className="size-4" aria-hidden />}><span>Send {chosen.length} invitation{chosen.length === 1 ? "" : "s"}</span></Button>
        </>}>
        <p className="text-[15px]">Nothing has been sent yet. When you approve, only these people get an invitation:</p>
        <ul className="mt-4 flex flex-col gap-2">
          {chosen.map((m) => (
            <li key={m.user_id} className="flex items-center gap-3 rounded-2xl bg-raised px-3 py-2.5">
              <Avatar name={m.display_name} src={m.avatar_url} size={36} />
              <span className="font-medium">{m.display_name}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[13.5px] text-muted">
          They'll see the activity, city, date, group size and your display name. Not your goal text, schedule or anyone else's details.
          Each person decides independently. If the roster, time or venue changes, you'll be asked again.
        </p>
        <InlineError error={error} />
      </Dialog>
    </div>
  );
}
