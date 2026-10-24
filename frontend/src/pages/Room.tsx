import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Send, Sparkles } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { participantsOf } from "../components/SafeMeet";
import { SafetyActions } from "../components/SafetyActions";
import { Avatar, Button, cx, ErrorState, InlineError, LoadingBlock } from "../components/ui";
import { NotAvailable } from "./ProposalPage";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { keys, useMessages, useProposal } from "../lib/hooks";
import { formatTime } from "../lib/time";

/** Screen J: plain-text group chat for confirmed members only. React escapes all text. */
export function Room() {
  const { proposalId = "" } = useParams();
  const { me } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const proposal = useProposal(proposalId, 10000);
  const confirmed = proposal.data?.status === "confirmed";
  const msgs = useMessages(proposalId, confirmed);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const count = msgs.data?.length ?? 0;

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [count]);

  if (proposal.isPending) return <AppShell><LoadingBlock label="Loading Gather Room" /></AppShell>;
  if (proposal.isError) return <AppShell>{proposal.error instanceof ApiError && proposal.error.status === 404 ? <NotAvailable /> : <ErrorState error={proposal.error} what="this room" />}</AppShell>;
  const p = proposal.data;

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = body.trim();
    if (!text) return;
    setSending(true); setError(null);
    try {
      await api.sendMessage(p.id, text);
      setBody("");
      qc.invalidateQueries({ queryKey: keys.messages(p.id) });
    } catch (err) { setError(err); } finally { setSending(false); }
  };

  const people = participantsOf(p);
  return (
    <AppShell>
      <Link to={`/proposals/${p.id}`} className="mb-4 inline-flex min-h-11 items-center gap-1.5 text-[14px] text-muted hover:text-ink"><ArrowLeft className="size-4" aria-hidden /> Meetup details</Link>
      <header className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-semibold leading-tight">Gather Room</h1>
          <p className="text-[14px] text-muted">{p.activity_title} · {people.length} people</p>
        </div>
        <div className="flex -space-x-2">{people.map((m) => <span key={m.user_id} className="rounded-full ring-2 ring-ground"><Avatar name={m.display_name} src={m.avatar_url} size={32} /></span>)}</div>
      </header>

      {!confirmed ? (
        <p className="rounded-2xl bg-raised p-4 text-[14.5px]">The room opens once everyone has confirmed the final details.</p>
      ) : (
        <section aria-label="Messages" className="flex flex-col rounded-[24px] border border-line bg-surface">
          <div className="flex max-h-[60dvh] min-h-[40dvh] flex-col gap-3 overflow-y-auto p-4" aria-live="polite">
            {msgs.isPending ? <LoadingBlock rows={3} label="Loading messages" />
              : msgs.isError ? <ErrorState error={msgs.error} onRetry={() => msgs.refetch()} what="messages" />
                : msgs.data.length === 0 ? <p className="m-auto text-[14px] text-muted">Say hi. Keep plans to the public place you all agreed on.</p>
                  : msgs.data.map((m) => {
                    const mine = m.sender_id === me?.id;
                    const agent = m.sender_id === null;
                    return (
                      <div key={m.id} className={cx("rise flex max-w-[85%] flex-col", mine ? "self-end items-end" : "self-start")}>
                        <span className={cx("mb-1 flex items-center gap-1 text-[12.5px]", agent ? "font-medium text-violet-ink" : "text-muted")}>
                          {agent && <Sparkles className="size-3" aria-hidden />}{mine ? "You" : m.sender_name} · {formatTime(m.created_at, p.timezone)}
                        </span>
                        <p className={cx("whitespace-pre-wrap break-words rounded-[20px] px-4 py-2.5 text-[15px] leading-snug",
                          agent ? "bg-violet-soft" : mine ? "ig-grad text-white" : "bg-raised")}>{m.body}</p>
                      </div>
                    );
                  })}
            <div ref={endRef} />
          </div>
          <form onSubmit={send} className="flex items-end gap-2 border-t border-line p-3">
            <label htmlFor="msg" className="sr-only">Message</label>
            <textarea id="msg" rows={1} value={body} maxLength={1000} onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }}
              placeholder="Message the group" className="max-h-32 min-h-11 flex-1 resize-none rounded-[22px] border border-line bg-raised px-4 py-2.5 outline-none focus:border-violet focus:bg-surface" />
            <Button type="submit" loading={sending} disabled={!body.trim()} aria-label="Send message" className="size-11 px-0" icon={<Send className="size-4" aria-hidden />} />
          </form>
          <InlineError error={error} />
        </section>
      )}
      <div className="mt-5">
        <SafetyActions proposalId={p.id} leaveLabel={p.viewer_role === "owner" ? "Cancel this meetup" : undefined} onLeave={() => navigate("/home", { replace: true })} />
      </div>
    </AppShell>
  );
}
