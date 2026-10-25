import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, MapPin, MessageCircle, Send, Sparkles } from "lucide-react";
import type { Proposal } from "../lib/api";
import { api } from "../lib/api";
import { useMessenger } from "../lib/messenger";
import { useAuth } from "../lib/auth";
import { keys, useMessages } from "../lib/hooks";
import { formatTime } from "../lib/time";
import { Avatar, Button, cx, ErrorState, InlineError, LoadingBlock } from "./ui";
import { participantsOf } from "./SafeMeet";
import { VenueMap } from "./VenueMap";

export function GatherChat({ proposal: p }: { proposal: Proposal }) {
  const { me } = useAuth();
  const messagePerson = useMessenger();
  const id = useId();
  const qc = useQueryClient();
  const confirmed = p.status === "confirmed";
  const messages = useMessages(p.id, confirmed);
  const people = participantsOf(p);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const sendingRef = useRef(false);
  const [showMap, setShowMap] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const count = messages.data?.length ?? 0;
  useEffect(() => {
    const el = list.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [count]);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = body.trim();
    if (!confirmed || !text || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true); setError(null);
    try {
      await api.sendMessage(p.id, text);
      setBody(""); nearBottom.current = true;
      await qc.invalidateQueries({ queryKey: keys.messages(p.id) });
    } catch (err) { setError(err); }
    finally { sendingRef.current = false; setSending(false); }
  };
  return (
    <section aria-label="Group chat" className="card flex h-[min(720px,calc(100dvh-120px))] min-h-[440px] flex-col overflow-hidden border border-line">
      <header className="shrink-0 border-b border-line bg-gradient-to-r from-rose-soft/70 to-violet-soft/70 p-4">
        <div className="flex items-center gap-3">
          <span className="ig-grad grid size-10 shrink-0 place-items-center rounded-2xl text-white"><MessageCircle className="size-5" aria-hidden /></span>
          <div className="min-w-0 flex-1"><h2 className="section-title">Gather Room</h2><p className="truncate text-[12.5px] text-muted">{p.activity_title}</p></div>
          <div className="flex -space-x-2">{people.slice(0, 4).map(m => confirmed && m.user_id !== me?.id ? <button key={m.user_id} type="button" aria-label={`Message ${m.display_name} privately`} title={`Message ${m.display_name}`} onClick={() => messagePerson(m)} className="press relative rounded-full hover:z-10 focus-visible:z-10"><Avatar name={m.display_name} src={m.avatar_url} size={28} /></button> : <Avatar key={m.user_id} name={m.display_name} src={m.avatar_url} size={28} />)}</div>
        </div>
        <p className="mt-2 text-[12px] text-muted break-words">{people.map(m => m.display_name).join(", ")} · {confirmed ? "Everyone confirmed" : "Waiting for confirmations"}</p>
      </header>
      {confirmed && p.venue_label && <div className="shrink-0 border-b border-line">
        <button type="button" onClick={() => setShowMap(v => !v)} aria-expanded={showMap} aria-controls={`chat-map-${id}`} className="press flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left text-[13px]">
          <MapPin className="size-4 shrink-0 text-rose-ink" aria-hidden /><span className="min-w-0 flex-1 truncate">{p.venue_label}</span><span className="text-rose-ink">Map</span><ChevronDown className={cx("size-4 transition-transform", showMap && "rotate-180")} aria-hidden />
        </button>
        {showMap && <div id={`chat-map-${id}`} className="px-3 pb-3"><VenueMap p={p} compact /></div>}
      </div>}
      <div ref={list} role="log" aria-label="Group messages" aria-live="polite" onScroll={() => { const el = list.current; if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {!confirmed ? <p className="text-[14px] text-muted">Chat opens automatically after everyone confirms the final time, place and group.</p>
          : messages.isPending ? <LoadingBlock rows={3} label="Loading messages" />
          : messages.isError ? <ErrorState error={messages.error} onRetry={() => messages.refetch()} what="messages" />
          : !messages.data.length ? <div className="grid h-full content-center gap-2 text-center"><MessageCircle className="mx-auto size-8 text-rose-ink" aria-hidden /><p className="font-semibold">Your plans brought you together.</p><p className="text-[13px] text-muted">Say hi to the group. Keep arrangements to your agreed public place.</p></div>
          : <div className="flex flex-col gap-4">{messages.data.map(m => {
            const mine = m.sender_id === me?.id;
            const sender = people.find(person => person.user_id === m.sender_id);
            const agent = m.sender_id === null;
            return <article key={m.id} aria-label={`Message from ${m.sender_name}`} className={cx("flex items-end gap-2", mine && "flex-row-reverse")}>
              {agent ? <span className="grid size-7 shrink-0 place-items-center rounded-full bg-violet-soft text-violet-ink"><Sparkles className="size-4" aria-hidden /></span> : <Avatar name={m.sender_name} src={sender?.avatar_url} size={28} />}
              <div className={cx("flex min-w-0 max-w-[82%] flex-col", mine && "items-end")}>
                <p className="mb-1 text-[12px] font-semibold text-muted">{m.sender_name}{mine && " · You"}</p>
                <p className={cx("whitespace-pre-wrap break-words rounded-[18px] px-3.5 py-2.5 text-[14px] leading-relaxed [overflow-wrap:anywhere]", mine ? "ig-grad rounded-br-md text-white" : agent ? "bg-violet-soft text-violet-ink" : "rounded-bl-md bg-raised")}>{m.body}</p>
                <time dateTime={m.created_at} className="mt-1 text-[10.5px] text-muted">{formatTime(m.created_at, p.timezone)}</time>
              </div>
            </article>;
          })}</div>}
      </div>
      {confirmed && <form onSubmit={send} className="shrink-0 border-t border-line bg-surface p-3">
        <div className="flex items-end gap-2">
          <label htmlFor={`message-${id}`} className="sr-only">Message the group</label>
          <textarea id={`message-${id}`} rows={1} value={body} disabled={sending} maxLength={1000} onChange={e => setBody(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} placeholder="Message the group…" className="max-h-28 min-h-11 min-w-0 flex-1 resize-y rounded-[22px] border border-line bg-raised px-4 py-2.5 outline-none focus:border-violet" />
          <Button type="submit" aria-label="Send message" loading={sending} disabled={!body.trim()} className="size-11 shrink-0 !p-0" icon={<Send className="size-5 shrink-0" aria-hidden />} />
        </div>
        <InlineError error={error} />
      </form>}
    </section>
  );
}
