import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Check, X } from "lucide-react";
import { api, type Proposal } from "../lib/api";
import { keys, useJoinRequests } from "../lib/hooks";
import { Avatar, Button, InlineError, Panel, Switch } from "./ui";

const JOINABLE = ["invites_pending", "awaiting_final"];

/** Owner: open the group to requests from people's Home feeds, and accept or decline each one (a decline is private). */
export function JoinRequests({ p }: { p: Proposal }) {
  const qc = useQueryClient();
  const open = !!p.open_to_requests;
  const requests = useJoinRequests(p.id, JOINABLE.includes(p.status));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (!JOINABLE.includes(p.status)) return null;

  const toggle = async (v: boolean) => {
    setBusy("open"); setError(null);
    try { await api.setOpen(p.id, v); await qc.invalidateQueries({ queryKey: keys.proposal(p.id) }); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const decide = async (id: string, accept: boolean) => {
    setBusy(id); setError(null);
    try {
      qc.setQueryData(keys.joinRequests(p.id), await api.decideJoin(p.id, id, accept));
      qc.invalidateQueries({ queryKey: keys.proposal(p.id) });
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const pending = requests.data ?? [];
  return (
    <Panel className="p-5" aria-labelledby="join-title">
      <h2 id="join-title" className="section-title">Requests to join</h2>
      <div className="mt-3">
        <Switch checked={open} onChange={toggle} disabled={busy === "open"} label="Let people ask to join"
          description="While there's room, your group can appear in the Home feed of people whose interests fit. Only the activity, day, kind of place and first names are shown. You approve everyone." />
      </div>
      {pending.length > 0 && (
        <ul className="mt-4 flex flex-col gap-3">
          {pending.map((r) => (
            <li key={r.id} className="rounded-2xl bg-raised p-4">
              <div className="flex items-center gap-3">
                <Avatar name={r.display_name} src={r.avatar_url} size={40} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{r.display_name}</p>
                  {r.match !== null && <p className="flex items-center gap-1 text-[12.5px] text-muted"><BrainCircuit className="size-3" aria-hidden /> {r.match}% fit with your group</p>}
                </div>
              </div>
              {r.bio && <p className="mt-2 text-[14px]">{r.bio}</p>}
              {r.message && <p className="mt-2 rounded-xl bg-surface px-3 py-2 text-[14px] italic">“{r.message}”</p>}
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => decide(r.id, true)} loading={busy === r.id} icon={<Check className="size-4" aria-hidden />}>Accept</Button>
                <Button variant="ghost" size="sm" onClick={() => decide(r.id, false)} disabled={busy === r.id} icon={<X className="size-4" aria-hidden />}>Decline</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {open && pending.length === 0 && <p className="mt-3 text-[13.5px] text-muted">No requests yet.</p>}
      <InlineError error={error} />
    </Panel>
  );
}
