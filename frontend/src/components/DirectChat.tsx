import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { api, type ChatPerson } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Avatar, Button, cx, DetailChips, ErrorState, InlineError, LoadingBlock } from "./ui";

export function DirectChat({ person }: { person: ChatPerson }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const id = useId();
  const queryKey = ["direct-messages", person.user_id];
  const q = useQuery({ queryKey, queryFn: () => api.directMessages(person.user_id), refetchInterval: 3000, retry: false });
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const busy = useRef(false);
  const list = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  useEffect(() => { if (list.current && atBottom.current) list.current.scrollTop = list.current.scrollHeight; }, [q.data?.length]);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || busy.current) return;
    busy.current = true; setSending(true); setError(null);
    try {
      await api.sendDirectMessage(person.user_id, body.trim());
      setBody(""); atBottom.current = true;
      await Promise.all([qc.invalidateQueries({ queryKey }), qc.invalidateQueries({ queryKey: ["chats"] })]);
    } catch (err) { setError(err); }
    finally { busy.current = false; setSending(false); }
  };
  return <section aria-label={`Conversation with ${person.display_name}`} className="flex min-h-0 flex-1 flex-col overflow-hidden">
    <header className="flex items-center gap-3 border-b border-line bg-gradient-to-r from-rose-soft/60 to-violet-soft/60 p-4">
      <Avatar name={person.display_name} src={person.avatar_url} size={40} /><div><h3 className="font-semibold">{person.display_name}</h3><p className="text-[12px] text-muted">Connected through a confirmed meetup</p><DetailChips details={person.details} /></div>
    </header>
    <div ref={list} role="log" aria-label="Direct messages" aria-live="polite" onScroll={() => { const el = list.current; if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
      {q.isPending ? <LoadingBlock label="Loading conversation" rows={3} /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} what="this conversation" /> : !q.data.length ? <div className="grid h-full content-center gap-2 text-center"><p className="font-semibold">Say hello to {person.display_name}.</p><p className="text-[13px] text-muted">Keep the connection going, one conversation at a time.</p></div> : <div className="flex flex-col gap-4">{q.data.map(m => {
        const mine = m.sender_id === me?.id;
        return <article key={m.id} aria-label={`Message from ${m.sender_name}`} className={cx("flex items-end gap-2", mine && "flex-row-reverse")}>
          <Avatar name={m.sender_name} src={mine ? me?.avatar_url : person.avatar_url} size={28} />
          <div className={cx("min-w-0 max-w-[80%]", mine && "text-right")}><p className="mb-1 text-[12px] font-semibold text-muted">{m.sender_name}{mine && " · You"}</p><p className={cx("whitespace-pre-wrap break-words rounded-[18px] px-3.5 py-2.5 text-left text-[14px] leading-relaxed [overflow-wrap:anywhere]", mine ? "ig-grad rounded-br-md text-white" : "rounded-bl-md bg-raised")}>{m.body}</p><time dateTime={m.created_at} className="mt-1 block text-[10.5px] text-muted">{new Date(m.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time></div>
        </article>;
      })}</div>}
    </div>
    <form onSubmit={send} className="shrink-0 border-t border-line bg-surface p-3"><div className="flex items-end gap-2">
      <label htmlFor={id} className="sr-only">Message {person.display_name}</label>
      <textarea id={id} rows={1} maxLength={1000} value={body} disabled={sending || q.isError} onChange={e => setBody(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} placeholder={`Message ${person.display_name}…`} className="min-h-11 max-h-28 min-w-0 flex-1 resize-y rounded-[22px] border border-line bg-raised px-4 py-2.5 outline-none focus:border-violet" />
      <Button type="submit" aria-label="Send message" loading={sending} disabled={!body.trim() || q.isError} className="size-11 shrink-0 !p-0" icon={<Send className="size-5 shrink-0" aria-hidden />} />
    </div><InlineError error={error} /></form>
  </section>;
}
