import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Search, Users, X } from "lucide-react";
import { api, type ChatPerson, type Conversation } from "../lib/api";
import { useAuth } from "../lib/auth";
import { MessengerContext } from "../lib/messenger";
import { useProposal } from "../lib/hooks";
import { Avatar, cx, ErrorState, LoadingBlock } from "./ui";
import { GatherChat } from "./GatherChat";
import { DirectChat } from "./DirectChat";

/** A speech bubble and a spark of connection, drawn for InGather. */
export function MessengerIcon({ className }: { className?: string }) {
  return <svg viewBox="0 0 28 28" fill="currentColor" className={className} aria-hidden="true"><path d="M14 2.5C7.1 2.5 2 7.2 2 13.5c0 3.5 1.6 6.4 4.3 8.4v3.6l4-2.1c1.2.4 2.4.6 3.7.6 6.9 0 12-4.6 12-10.5S20.9 2.5 14 2.5Z"/><path d="m7 17 6-6 3.5 2.6L21 10l-5.6 7-3.6-2.7L7 17Z" fill="var(--messenger-cutout, white)"/></svg>;
}

function GroupConversation({ id }: { id: string }) {
  const q = useProposal(id, 3000);
  if (q.isPending) return <LoadingBlock label="Loading group" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} what="this group" />;
  return <div className="min-h-0 flex-1 [&>section]:h-full [&>section]:min-h-0 [&>section]:rounded-none [&>section]:border-0 [&>section]:shadow-none"><GatherChat key={id} proposal={q.data} /></div>;
}

export function MessengerProvider({ children }: { children: ReactNode }) {
  const { signedIn, me } = useAuth();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [filter, setFilter] = useState<"all" | "group" | "direct">("all");
  const [search, setSearch] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const q = useQuery({ queryKey: ["chats"], queryFn: api.chats, enabled: signedIn && open, refetchInterval: open ? 5000 : false, retry: false });
  useEffect(() => { setOpen(false); setSelected(null); setSearch(""); }, [me?.id]);
  useEffect(() => {
    if (!open) return;
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    const outside = (e: PointerEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", escape); document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("keydown", escape); document.removeEventListener("pointerdown", outside); };
  }, [open]);
  const openPerson = (person: ChatPerson) => {
    setSelected({ id: person.user_id, kind: "direct", title: person.display_name, people: [person], last_message: null, last_sender_name: null, updated_at: new Date().toISOString() });
    setOpen(true);
  };
  const rows = q.data?.filter(c => (filter === "all" || c.kind === filter) && `${c.title} ${c.people.map(p => p.display_name).join(" ")}`.toLowerCase().includes(search.trim().toLowerCase()));
  return <MessengerContext.Provider value={openPerson}>{children}{signedIn && <div ref={root} className="fixed right-[108px] top-1.5 z-40 md:right-5 md:top-3">
    <button ref={trigger} type="button" aria-label="Messages" aria-expanded={open} aria-controls="messenger-panel" onClick={() => { setOpen(v => !v); if (!open) setSelected(null); }} className={cx("press grid size-11 place-items-center rounded-full border border-line shadow-sm transition-colors", open ? "bg-violet-soft text-violet-ink [--messenger-cutout:var(--color-violet-soft)]" : "bg-raised text-ink [--messenger-cutout:var(--color-raised)] hover:bg-violet-soft")}><MessengerIcon className="size-6" /></button>
    {open && <section id="messenger-panel" role="dialog" aria-label="Messages" className="fixed inset-x-3 top-16 bottom-20 flex flex-col overflow-hidden rounded-[24px] border border-line bg-surface shadow-[0_20px_70px_-18px_rgb(40_25_70/0.3)] md:inset-x-auto md:bottom-auto md:right-5 md:h-[min(720px,calc(100dvh-100px))] md:w-[400px]">
      <header className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-3">{selected && <button type="button" aria-label="Back to chats" onClick={() => setSelected(null)} className="press grid size-9 place-items-center rounded-full hover:bg-raised"><ArrowLeft className="size-5" /></button>}<h2 className="section-title flex-1">{selected ? selected.kind === "group" ? "Group chat" : "Message" : "Chats"}</h2><button type="button" aria-label="Close messages" onClick={() => { setOpen(false); trigger.current?.focus(); }} className="press grid size-9 place-items-center rounded-full hover:bg-raised"><X className="size-5" /></button></header>
      {selected ? selected.kind === "group" ? <GroupConversation id={selected.id} /> : <DirectChat key={selected.id} person={selected.people[0]} /> : <>
        <div className="shrink-0 p-4 pb-2"><div className="relative"><Search className="pointer-events-none absolute left-3.5 top-3 size-5 text-muted" aria-hidden /><label htmlFor="chat-search" className="sr-only">Search chats</label><input id="chat-search" autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder="Search chats" className="min-h-11 w-full rounded-full border border-line bg-raised pl-11 pr-4 outline-none focus:border-violet" /></div><div className="mt-3 flex gap-2" aria-label="Filter conversations">{([["all", "All"], ["group", "Groups"], ["direct", "People"]] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={cx("press min-h-10 rounded-full px-4 text-[14px] font-semibold", filter === value ? "bg-violet-soft text-violet-ink" : "text-muted hover:bg-raised")}>{label}</button>)}</div></div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-3">{q.isPending ? <LoadingBlock rows={4} label="Loading chats" /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} what="your chats" /> : !rows?.length ? <div className="px-5 py-10 text-center"><Users className="mx-auto mb-3 size-8 text-violet-ink" /><p className="font-semibold">{search ? "No matching chats" : "Your connections start here"}</p><p className="mt-2 text-[13px] text-muted">{search ? "Try another name or group." : "Once everyone confirms a meetup, find the group and message its members here."}</p></div> : <ul>{rows.map(c => <li key={`${c.kind}-${c.id}`}><button type="button" onClick={() => setSelected(c)} className="press flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left hover:bg-raised"><div className="relative shrink-0 pr-1 pb-1"><Avatar name={c.people[0]?.display_name ?? c.title} src={c.people[0]?.avatar_url} size={48} />{c.kind === "group" && <span className="absolute -bottom-0.5 -right-1 grid size-6 place-items-center rounded-full border-2 border-surface bg-violet-soft text-violet-ink"><Users className="size-3.5" /></span>}</div><div className="min-w-0 flex-1"><p className="truncate font-semibold">{c.title}</p><p className="mt-0.5 truncate text-[13px] text-muted">{c.last_message ? `${c.last_sender_name ?? c.title}: ${c.last_message}` : c.kind === "group" ? `${c.people.length} people · Say hello` : "Start a conversation"}</p></div></button></li>)}</ul>}</div>
        <p className="shrink-0 border-t border-line px-4 py-3 text-[12px] text-muted">Groups and people you’ve connected with through confirmed meetups.</p>
      </>}
    </section>}
  </div>}</MessengerContext.Provider>;
}
